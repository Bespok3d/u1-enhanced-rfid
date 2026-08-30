import copy
import json
import logging
import logging.handlers
import os

from . import filament_protocol, mifare_classic

RFID_DATA_FILE = "/oem/printer_data/config/bespok3d/data/rfid_data.json"
_LOG_FILE = "/userdata/bespok3d/var/logs/bespok3d.log"
CHANNEL_COUNT = 4
# The base layer keeps a lane's tuned pressure advance while an owner is registered, and this
# is the name it holds this plugin's registration under.
PRESSURE_ADVANCE_OWNER = "rfid-ntag"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 2


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


class Bespok3dRfid:
    def __init__(self, config):
        self.printer = config.get_printer()
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
            _log.warning("fm175xx_reader card hook absent: HW tag pipeline inactive")
        elif callable(claim) and hasattr(fm_reader, 'register_card_handler'):
            fm_reader.register_card_handler(reader.claims, reader.read_hw_tag)
            _log.info("HW claim reader registered card_type=0x%02X", reader.card_type)
        elif hasattr(fm_reader, 'register_card_type_handler'):
            fm_reader.register_card_type_handler(reader.sak, reader.read_hw_tag)
            _log.info("HW reader registered SAK=0x%02X", reader.sak)
        else:
            _log.warning("fm175xx_reader card hook absent: HW tag pipeline inactive")

    def _register_reader_parser(self, reader):
        parse = getattr(reader, 'parse', None)
        parser = parse if callable(parse) else self._dispatch_parsers
        self._register_protocol_parser(reader.card_type, parser)

    def _register_protocol_parser(self, card_type, parser):
        detector = self.printer.lookup_object('filament_detect', None)
        if detector is None or not hasattr(detector, 'register_card_protocol_parser'):
            _log.warning("filament_detect parser hook absent: SW payload pipeline inactive")
            return
        detector.register_card_protocol_parser(card_type, parser)
        _log.info("protocol parser registered card_type=0x%02X", card_type)

    def register_payload_parser(self, parser):
        self._payload_parsers.append(parser)

    def register_spool_notify(self, cb):
        self._spool_notify_cbs.append(cb)

    def _hold_pressure_advance(self):
        task_config = self.printer.lookup_object('print_task_config', None)
        if task_config is None or not hasattr(task_config, 'suppress_pressure_advance_reset'):
            _log.warning(
                "print_task_config pressure advance hold absent: a lane loses its tuned "
                "pressure advance on every filament change, as it does on stock firmware")
            return
        task_config.suppress_pressure_advance_reset(PRESSURE_ADVANCE_OWNER)
        _log.info("pressure advance hold registered owner=%s", PRESSURE_ADVANCE_OWNER)

    def _handle_ready(self):
        self._hold_pressure_advance()
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
