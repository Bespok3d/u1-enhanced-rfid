import copy
import logging
import logging.handlers
import os
from typing import Any

from . import bespok3d_rfid_saved_lanes as saved_lanes_store
from . import filament_protocol, mifare_classic

_LOG_FILE = "/userdata/bespok3d/var/logs/bespok3d.log"
CHANNEL_COUNT = 4
# The base layer keeps a lane's tuned pressure advance while an owner is registered, and this
# is the name it holds this plugin's registration under.
PRESSURE_ADVANCE_OWNER = "rfid-ntag"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 2
# The firmware copies these fields of every read it takes into its own record of the lane, the
# filament lists print_task_config reports, keyed here by the read's own field name.
FIRMWARE_RECORD_FIELDS = {
    'VENDOR': 'filament_vendor',
    'MAIN_TYPE': 'filament_type',
    'SUB_TYPE': 'filament_sub_type',
    'ARGB_COLOR': 'filament_color',
    'SKU': 'filament_sku',
}
SavedLanes = saved_lanes_store.SavedLanes
FirmwareRecord = dict[str, Any]


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


def _remembered_state(saved_lanes, channel):
    saved_info = saved_lanes.get(str(channel))
    if not isinstance(saved_info, dict) or _is_untagged_report(saved_info):
        return None
    return saved_info


def _saved_tag_uid(saved_lanes: SavedLanes, channel: int) -> Any:
    return (_remembered_state(saved_lanes, channel) or {}).get('CARD_UID')


# One tag sits on one spool, so two lanes saved with the same tag prove a reader picked up its
# neighbour's spool, without telling which of the two lanes is the wrong one.
def _channels_sharing_a_tag(saved_lanes: SavedLanes) -> list[int]:
    tag_uids = [_saved_tag_uid(saved_lanes, channel) for channel in range(CHANNEL_COUNT)]
    return [channel for channel, tag_uid in enumerate(tag_uids)
            if tag_uid and tag_uids.count(tag_uid) > 1]


def _kept_by_firmware(remembered_state, firmware_vendor):
    if remembered_state is None or firmware_vendor is None:
        return remembered_state
    return remembered_state if remembered_state.get('VENDOR') == firmware_vendor else None


def _is_lane_list(status_value: Any) -> bool:
    return isinstance(status_value, list) and len(status_value) >= CHANNEL_COUNT


# With no firmware record every lane is kept, so nothing is forgotten on a guess.
def _lane_vendors_in(task_status: dict[str, Any]) -> list[str | None]:
    filament_vendor = task_status.get('filament_vendor')
    if not _is_lane_list(filament_vendor):
        _log.warning("firmware filament record unknown at boot: every remembered lane is kept")
        return [None] * CHANNEL_COUNT
    return filament_vendor[:CHANNEL_COUNT]


def _lane_records_in(task_status: dict[str, Any]) -> list[FirmwareRecord | None]:
    lane_lists = {field: task_status.get(status_key)
                  for field, status_key in FIRMWARE_RECORD_FIELDS.items()}
    if not all(_is_lane_list(lane_list) for lane_list in lane_lists.values()):
        return [None] * CHANNEL_COUNT
    return [{field: lane_list[channel] for field, lane_list in lane_lists.items()}
            for channel in range(CHANNEL_COUNT)]


# Unlike a restore, which keeps every lane when there is no firmware record, a clear needs the
# record to show that very spool: nothing is cleared on a guess.
def _shown_by_printer(
        saved_lanes: SavedLanes, channel: int, firmware_record: FirmwareRecord | None) -> bool:
    remembered_state = _remembered_state(saved_lanes, channel)
    if remembered_state is None or firmware_record is None:
        return False
    return all(remembered_state.get(field) == value for field, value in firmware_record.items())


# A lane saved with a shared tag stays unproven even when the other lane has moved on since: the
# printer may still show the neighbour's spool there.
def _shared_tag_channels_still_shown(
        saved_lanes: SavedLanes, firmware_records: list[FirmwareRecord | None]) -> list[int]:
    return [channel for channel in _channels_sharing_a_tag(saved_lanes)
            if _shown_by_printer(saved_lanes, channel, firmware_records[channel])]


class Bespok3dRfid:
    def __init__(self, config):
        self.printer = config.get_printer()
        self._hw_readers = []
        self._payload_parsers = []
        self._spool_notify_cbs = []
        self._filament_state = [None] * CHANNEL_COUNT
        self._proven_lanes = self._take_saved_lanes()
        self._unproven_lanes = saved_lanes_store.read_unproven_lanes()
        self.printer.register_event_handler("klippy:ready", self._handle_ready)

    # Other plugins read rfid_data.json in their own klippy:ready handler, which can run before this
    # one, so a file this version cannot trust is replaced while the config loads, before any reads.
    # Only lanes saved with one tag can still be wrong on the printer, so only those are kept aside.
    def _take_saved_lanes(self) -> SavedLanes:
        saved_lanes, is_proven = saved_lanes_store.read_saved_lanes()
        if is_proven:
            return saved_lanes
        if _channels_sharing_a_tag(saved_lanes):
            saved_lanes_store.set_aside_unproven_lanes()
        self._write_rfid_data()
        return {}

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
        self._restore_remembered_lanes()
        detector = self.printer.lookup_object('filament_detect', None)
        if detector is None:
            _log.warning("filament_detect not found: all pipelines inactive")
            return
        detector.register_cb_2_update_filament_info(self._on_filament_update)
        self._register_protocol_parser(
            mifare_classic.M1_UID_CARD_TYPE, self._uid_fallback_parser)
        _log.info("ready: registered filament update callback")

    # A factory tag can fail to answer while its spool sits still on the holder, so the last
    # identified spool per lane outlives a restart. A lane the firmware itself no longer
    # remembers was emptied while powered off and forgets it; a different tag answering
    # replaces it.
    def _restore_remembered_lanes(self) -> None:
        self._filament_state = [_remembered_state(self._proven_lanes, channel)
                                for channel in range(CHANNEL_COUNT)]
        self.printer.get_reactor().register_callback(self._forget_lanes_the_firmware_forgot)

    # The filament sensors are not settled this early at boot and report a loaded lane empty,
    # so presence cannot decide. The firmware's own saved filament per lane survives the same
    # restart and is the truth for what still sits on the holder.
    def _forget_lanes_the_firmware_forgot(self, eventtime: float) -> None:
        task_status = self._task_status(eventtime)
        firmware_vendors = _lane_vendors_in(task_status)
        self._filament_state = [_kept_by_firmware(state, firmware_vendors[channel])
                                for channel, state in enumerate(self._filament_state)]
        _log.info("boot restore: firmware=%s vendors=%s", firmware_vendors,
                  [(state or {}).get('VENDOR', 'NONE') for state in self._filament_state])
        self._write_rfid_data()
        self._reset_lanes_shown_with_a_shared_tag(_lane_records_in(task_status))

    # An older version let the printer take the neighbour's tag too, so it can still show one spool
    # on two lanes. Every such lane is cleared there; the right one comes back at its next read.
    # The older lanes are only forgotten once the printer has cleared each lane they put in doubt.
    def _reset_lanes_shown_with_a_shared_tag(
            self, firmware_records: list[FirmwareRecord | None]) -> None:
        if not self._unproven_lanes:
            return
        if None in firmware_records:
            _log.warning("firmware filament record unknown at boot: lanes an older version saved "
                         "are checked at the next restart")
            return
        doubtful_channels = _shared_tag_channels_still_shown(self._unproven_lanes, firmware_records)
        reset_results = [self._reset_shared_tag_channel(channel) for channel in doubtful_channels]
        if not all(reset_results):
            _log.warning("lanes an older version saved are checked again at the next restart")
            return
        saved_lanes_store.forget_unproven_lanes()
        self._unproven_lanes = {}

    def _reset_shared_tag_channel(self, channel: int) -> bool:
        _log.warning("ch=%d still shows a tag an older version also saved on another lane: "
                     "cleared on the printer until its tag is read again", channel)
        return self._reset_printer_channel(channel)

    def _task_status(self, eventtime: float) -> dict[str, Any]:
        task_config = self.printer.lookup_object('print_task_config', None)
        return task_config.get_status(eventtime) if task_config is not None else {}

    # Same presence rule the firmware applies to its own filament_exist flags; with no
    # signal every lane counts as loaded, so nothing is forgotten on a guess.
    def _lane_presence(self, eventtime: float) -> list[bool]:
        filament_exist = self._task_status(eventtime).get('filament_exist')
        if not _is_lane_list(filament_exist):
            _log.warning("filament presence unknown: the lane counts as loaded")
            return [True] * CHANNEL_COUNT
        return [bool(lane_loaded) for lane_loaded in filament_exist[:CHANNEL_COUNT]]

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
                "known-good state (mirrors Snapmaker's own official-vendor guard), "
                "re-sending the remembered spool", channel)
            self._notify_spool(channel, self._filament_state[channel], False)
            return
        if is_clear and self._is_clear_of_loaded_spool(channel):
            _log.warning(
                "filament clear ch=%d ignored: the lane still holds filament, "
                "re-sending the remembered spool", channel)
            self._notify_spool(channel, self._filament_state[channel], False)
            return
        if not is_clear and self._is_read_through(channel, info_data):
            return
        self._filament_state[channel] = None if is_clear else info
        self._write_rfid_data()
        self._notify_spool(channel, None if is_clear else info, is_clear)

    def _notify_spool(self, channel, notify_info, is_clear):
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

    def _tag_owner_channel(self, channel, card_uid):
        """The other channel already holding this tag, if any. One tag sits on one spool, so the
        same hardware UID turning up on a second channel is that channel's reader picking up the
        tag of the spool next to it, which happens when its own spool carries no tag."""
        owners = (
            owner_channel for owner_channel, owner_state in enumerate(self._filament_state)
            if owner_channel != channel and owner_state
            and owner_state.get('CARD_UID') == card_uid
        )
        return next(owners, None)

    # The lane's own spool coming back, the echo of _reset_printer_channel included, is never a
    # read-through. A lane holding the same UID as another lane would otherwise be reset again by
    # its own echo, forever.
    def _is_read_through(self, channel, info_data):
        card_uid = info_data.get('CARD_UID')
        if not card_uid or info_data == self._filament_state[channel]:
            return False
        owner_channel = self._tag_owner_channel(channel, card_uid)
        if owner_channel is None:
            return False
        _log.warning(
            "filament update ch=%d dropped: tag uid=%s already belongs to ch=%d, so this reader "
            "picked up the neighbouring spool's tag", channel, card_uid, owner_channel)
        self._reset_printer_channel(channel)
        return True

    def _reset_printer_channel(self, channel: int) -> bool:
        """The printer took the read-through tag too (filament_detect notifies every listener at
        once), so put the lane back there as this relay holds it: its remembered spool, or
        cleared the way removing the spool clears it. A clear of a lane that remembers a spool
        would come back to this relay and be ignored by the loaded-lane clear guard, leaving the
        printer empty while this relay still holds the spool, and the next boot would forget it."""
        detector = self.printer.lookup_object('filament_detect', None)
        set_filament_info = getattr(detector, 'set_filament_info', None)
        if not callable(set_filament_info):
            _log.warning(
                "filament_detect set_filament_info door absent: ch=%d keeps the neighbouring "
                "spool's tag on the printer", channel)
            return False
        remembered_spool = self._filament_state[channel]
        if remembered_spool is None:
            return bool(set_filament_info(
                channel, copy.deepcopy(filament_protocol.FILAMENT_INFO_STRUCT), is_clear=True))
        return bool(set_filament_info(channel, copy.deepcopy(remembered_spool), is_clear=False))

    # The firmware sends a clear on every sensor blip, a reboot included, while the spool never
    # left the holder. Only a lane the sensor reports empty has really been unloaded.
    def _is_clear_of_loaded_spool(self, channel):
        current_state = self._filament_state[channel]
        if current_state is None or _is_untagged_report(current_state):
            return False
        eventtime = self.printer.get_reactor().monotonic()
        return self._lane_presence(eventtime)[channel]

    def _write_rfid_data(self) -> None:
        saved_lanes = {
            str(channel): copy.deepcopy(lane_state or filament_protocol.FILAMENT_INFO_STRUCT)
            for channel, lane_state in enumerate(self._filament_state)}
        saved_lanes_store.save_lanes(saved_lanes)


def load_config(config):
    return Bespok3dRfid(config)
