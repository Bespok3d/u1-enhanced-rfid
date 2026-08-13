import copy
import json
import logging
import logging.handlers
import os

from . import filament_protocol, mifare_classic

RFID_DATA_FILE = "/oem/printer_data/config/bespok3d/data/rfid_data.json"
_LOG_FILE = "/userdata/bespok3d/var/logs/bespok3d.log"
CHANNEL_COUNT = 4
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 2
SNAPMAKER_VENDOR = 'Snapmaker'
GENERIC_VENDOR = 'Generic'
SWITCH_OFF_WORDS = ('false', 'off', 'no', '0')
SWITCH_ON_WORDS = ('true', 'on', 'yes', '1')


def _setup_logger():
    log = logging.getLogger('bespok3d')
    if log.handlers:
        return log
    log.setLevel(logging.DEBUG)
    log.propagate = False
    try:
        os.makedirs(os.path.dirname(_LOG_FILE), exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            _LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT)
        file_handler.setFormatter(logging.Formatter('%(asctime)s %(name)s: %(message)s'))
        log.addHandler(file_handler)
    except Exception as setup_err:
        logging.warning(
            "bespok3d: log file unavailable (%s), falling back to klippy.log", setup_err)
    return log

_log = _setup_logger()


def _is_untagged_report(info_data):
    return info_data.get('OFFICIAL') is not True


def _reads_as_on(setting):
    """Read the switch without ever taking the printer down over it.

    The setting arrives from the app through the installer, and Klipper halts the whole printer on
    a config value its own getboolean cannot parse, so a value that never reached us, or reached us
    unreadable, falls back to the on the plugin ships with.
    """
    if setting in SWITCH_OFF_WORDS:
        return False
    if setting not in SWITCH_ON_WORDS:
        _log.warning("force_generic_vendor is %r, which reads as neither on nor off: using on",
                     setting)
    return True


class Bespok3dRfid:
    def __init__(self, config):
        self.printer = config.get_printer()
        self._force_generic_vendor = _reads_as_on(
            config.get('force_generic_vendor', 'True').strip().lower())
        self._hw_readers = []
        self._payload_parsers = []
        self._spool_notify_cbs = []
        self._filament_state = [None] * CHANNEL_COUNT
        self.printer.register_event_handler("klippy:ready", self._handle_ready)

    def register_hw_reader(self, reader):
        self._hw_readers.append(reader)
        self._register_reader_handler(reader)
        self._register_reader_parser(reader)

    def _register_reader_handler(self, reader):
        fm_reader = self.printer.lookup_object('fm175xx_reader', None)
        claim = getattr(reader, 'claims', None)
        if fm_reader is None:
            _log.warning("fm175xx_reader patch absent: HW tag pipeline inactive")
        elif callable(claim) and hasattr(fm_reader, 'register_card_handler'):
            fm_reader.register_card_handler(reader.claims, reader.read_hw_tag)
            _log.info("HW claim reader registered card_type=0x%02X", reader.card_type)
        elif hasattr(fm_reader, 'register_card_type_handler'):
            fm_reader.register_card_type_handler(reader.sak, reader.read_hw_tag)
            _log.info("HW reader registered SAK=0x%02X", reader.sak)
        else:
            _log.warning("fm175xx_reader patch absent: HW tag pipeline inactive")

    def _register_reader_parser(self, reader):
        parse = getattr(reader, 'parse', None)
        parser = parse if callable(parse) else self._dispatch_parsers
        self._register_protocol_parser(reader.card_type, parser)

    def _register_protocol_parser(self, card_type, parser):
        """The one door every parser goes through, so the vendor rule is applied exactly once."""
        detector = self.printer.lookup_object('filament_detect', None)
        if detector is None or not hasattr(detector, 'register_card_protocol_parser'):
            _log.warning("filament_detect patch absent: SW payload pipeline inactive")
            return

        def parse_then_name_the_spool(card_bytes):
            error, info = parser(card_bytes)
            if error != filament_protocol.FILAMENT_PROTO_OK or info is None:
                return error, info
            return error, self.apply_generic_vendor(info)

        detector.register_card_protocol_parser(card_type, parse_then_name_the_spool)
        _log.info("protocol parser registered card_type=0x%02X force_generic_vendor=%s",
                  card_type, self._force_generic_vendor)

    def apply_generic_vendor(self, info):
        """Describe a non-Snapmaker spool in the words Snapmaker Orca ships filaments for.

        Orca lists a loaded spool only when "<vendor> <type> <sub-type>" is exactly a filament it
        already has, and it ships none for third-party brands, so a spool read perfectly off its tag
        is dropped from Machine Filament with no error at all. Reporting Generic and no sub-type
        lands on the Generic <type> filaments Orca does ship. Snapmaker spools keep their own name.
        """
        if not self._force_generic_vendor:
            return info
        if str(info.get('VENDOR', '')).lower() == SNAPMAKER_VENDOR.lower():
            return info
        generically_named = dict(info)
        generically_named['VENDOR'] = GENERIC_VENDOR
        generically_named['SUB_TYPE'] = ''
        return generically_named

    def register_payload_parser(self, parser):
        self._payload_parsers.append(parser)

    def register_spool_notify(self, cb):
        self._spool_notify_cbs.append(cb)

    def _handle_ready(self):
        detector = self.printer.lookup_object('filament_detect', None)
        if detector is None:
            _log.warning("filament_detect not found: all pipelines inactive")
            return
        detector.register_cb_2_update_filament_info(self._on_filament_update)
        self._register_protocol_parser(
            mifare_classic.M1_UID_CARD_TYPE, self._uid_fallback_parser)
        _log.info("ready: registered filament update callback")

    def _uid_fallback_parser(self, card_data):
        info = mifare_classic.uid_only_struct(filament_protocol.FILAMENT_INFO_STRUCT, card_data)
        _log.info("UID-only fallback: card_uid=%s", info.get('CARD_UID'))
        return filament_protocol.FILAMENT_PROTO_OK, info

    def _dispatch_parsers(self, raw_bytes):
        _log.info("_dispatch_parsers called bytes=%d parsers=%d",
                  len(raw_bytes) if raw_bytes else 0, len(self._payload_parsers))
        for parser in self._payload_parsers:
            error, info = parser.to_filament_protocol(raw_bytes)
            if error == filament_protocol.FILAMENT_PROTO_OK:
                return error, info
        _log.warning("_dispatch_parsers: no parser succeeded")
        return filament_protocol.FILAMENT_PROTO_ERR, None

    def _on_filament_update(self, channel, info, is_clear):
        if not (0 <= channel < CHANNEL_COUNT):
            return
        info_data = info or {}
        _log.info("filament update ch=%d is_clear=%s vendor=%s type=%s official=%s spool_id=%s",
                  channel, is_clear,
                  info_data.get('VENDOR', '?'), info_data.get('MAIN_TYPE', '?'),
                  info_data.get('OFFICIAL', '?'), info_data.get('SPOOL_ID', '?'))
        if not is_clear and self._is_stale_downgrade(channel, info_data):
            _log.warning(
                "filament update ch=%d suppressed: no-identity report would overwrite "
                "known-good state (mirrors Snapmaker's own official-vendor guard)", channel)
            return
        self._filament_state[channel] = None if is_clear else info
        self._write_rfid_data()
        notify_info = None if is_clear else info
        for notify_cb in self._spool_notify_cbs:
            try:
                notify_cb(channel, notify_info, is_clear)
            except Exception as notify_err:
                _log.error("spool_notify cb error: %s", notify_err)

    def _is_stale_downgrade(self, channel, info_data):
        current_state = self._filament_state[channel]
        if current_state is None:
            return False
        if _is_untagged_report(current_state):
            return False
        return _is_untagged_report(info_data)

    def _write_rfid_data(self):
        empty = filament_protocol.FILAMENT_INFO_STRUCT
        data = {}
        for channel in range(CHANNEL_COUNT):
            data[str(channel)] = copy.deepcopy(self._filament_state[channel] or empty)
        try:
            os.makedirs(os.path.dirname(RFID_DATA_FILE), exist_ok=True)
            with open(RFID_DATA_FILE, 'w') as file_out:
                json.dump(data, file_out)
        except Exception as write_err:
            _log.error("rfid_data.json write failed: %s", write_err)


def load_config(config):
    return Bespok3dRfid(config)
