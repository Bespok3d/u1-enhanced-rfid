import copy
import json
import logging

from . import filament_protocol, ndef_parser
from .ntag_reader import NtagReader
from .openspool_mapper import OpenSpoolMapper

_log = logging.getLogger('bespok3d.ntag')

STRING_FIELDS = ('VENDOR', 'MAIN_TYPE', 'SUB_TYPE')
INT_FIELDS = ('HOTEND_MIN_TEMP', 'HOTEND_MAX_TEMP', 'BED_TEMP')
EXTRA_COLOR_FIELDS = ('RGB_2', 'RGB_3', 'RGB_4', 'RGB_5')
ALPHA_MASK = 0xFF
RGB_MASK = 0xFFFFFF
ALPHA_SHIFT = 24


def _apply_named_fields(filament_info, params):
    for str_key in STRING_FIELDS:
        if str_key in params:
            filament_info[str_key] = str(params.pop(str_key))
    for int_key in INT_FIELDS:
        if int_key in params:
            filament_info[int_key] = int(params.pop(int_key))


def _apply_colors(filament_info, params):
    if 'ALPHA' in params:
        filament_info['ALPHA'] = int(params.pop('ALPHA')) & ALPHA_MASK
    if 'RGB_1' in params:
        filament_info['RGB_1'] = int(params.pop('RGB_1')) & RGB_MASK
    filament_info['COLOR_NUMS'] = 1
    for key in EXTRA_COLOR_FIELDS:
        if key in params:
            filament_info[key] = int(params.pop(key)) & RGB_MASK
            filament_info['COLOR_NUMS'] += 1
    filament_info['ARGB_COLOR'] = filament_info['ALPHA'] << ALPHA_SHIFT | filament_info['RGB_1']


def _apply_misc_fields(filament_info, params):
    if 'MULTI_MODE' in params:
        filament_info['MULTI_MODE'] = int(params.pop('MULTI_MODE')) & ALPHA_MASK
    if 'CARD_UID' in params:
        filament_info['CARD_UID'] = [int(byte) for byte in params.pop('CARD_UID')]
    if 'SKU' in params:
        filament_info['SKU'] = int(params.pop('SKU'))


def _build_filament_info(params):
    filament_info = copy.deepcopy(filament_protocol.FILAMENT_INFO_STRUCT)
    _apply_named_fields(filament_info, params)
    _apply_colors(filament_info, params)
    _apply_misc_fields(filament_info, params)
    return filament_info


class RfidNtag:
    def __init__(self, config):
        self.printer = config.get_printer()
        self._rfid_hub = None
        self._protocol_mappers = {}
        self.printer.register_event_handler("klippy:ready", self._handle_ready)

    def register_protocol_mapper(self, mapper):
        self._protocol_mappers[mapper.protocol_id] = mapper

    def _handle_ready(self):
        hub = self.printer.lookup_object('bespok3d_rfid', None)
        if hub is None:
            _log.warning("bespok3d_rfid not loaded: NTAG support inactive")
            return
        self._rfid_hub = hub
        hub.register_hw_reader(NtagReader())
        hub.register_payload_parser(self)
        self.register_protocol_mapper(OpenSpoolMapper())
        _log.info("ready: NTAG reader + OpenSpool mapper registered")

        webhooks = self.printer.lookup_object('webhooks')
        webhooks.register_endpoint("filament_detect/set", self._handle_filament_detect_set)

    def to_filament_protocol(self, raw_bytes):
        _log.info("to_filament_protocol called, %d bytes", len(raw_bytes) if raw_bytes else 0)
        error, records, card_uid = ndef_parser.ndef_parse(raw_bytes)
        if error != ndef_parser.NDEF_OK or not records:
            _log.error("NDEF parse failed (code=%d, records=%d)",
                       error, len(records) if records else 0)
            return filament_protocol.FILAMENT_PROTO_ERR, None
        for record in records:
            mime_type = record['mime_type']
            if mime_type != 'application/json':
                _log.warning("no handler for mime_type='%s'", mime_type)
                continue
            err, info = self._dispatch_json(record['payload'], card_uid)
            if err == filament_protocol.FILAMENT_PROTO_OK:
                return err, info
        return filament_protocol.FILAMENT_PROTO_ERR, None

    def _dispatch_json(self, payload_bytes, card_uid):
        try:
            data = json.loads(payload_bytes.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            _log.error("JSON decode failed: %s", err)
            return filament_protocol.FILAMENT_PROTO_ERR, None
        if not isinstance(data, dict):
            return filament_protocol.FILAMENT_PROTO_ERR, None
        protocol_id = data.get('protocol')
        mapper = self._protocol_mappers.get(protocol_id)
        if mapper is None:
            _log.warning("no mapper for protocol='%s'", protocol_id)
            return filament_protocol.FILAMENT_PROTO_ERR, None
        _log.info("dispatching to mapper protocol='%s'", protocol_id)
        err, info = mapper.to_filament_info(data, card_uid)
        if err == filament_protocol.FILAMENT_PROTO_OK:
            safe = info or {}
            _log.info("mapped ok vendor=%s type=%s spool_id=%s",
                      safe.get('VENDOR'), safe.get('MAIN_TYPE'), safe.get('SPOOL_ID'))
        else:
            _log.error("mapper returned error %d", err)
        return err, info

    def _resolve_channel(self, web_request):
        channel = web_request.get_int('channel', None)
        if channel is None:
            raise web_request.error("channel must be specified!")
        detector = self.printer.lookup_object('filament_detect', None)
        if detector is None:
            raise web_request.error("filament_detect not available")
        if channel < 0 or channel >= detector.channel_count:
            raise web_request.error(
                f"channel[{channel}] is out of range[0, {detector.channel_count - 1}]")
        return channel, detector

    def _should_apply(self, channel, has_params):
        if has_params:
            return True
        ptc = self.printer.lookup_object('print_task_config', None)
        return ptc is not None and ptc.print_task_config['filament_official'][channel]

    def _handle_filament_detect_set(self, web_request):
        try:
            channel, detector = self._resolve_channel(web_request)
            params = web_request.get_dict('info', {})
            has_params = len(params) > 0
            filament_info = _build_filament_info(params)
            if params:
                raise web_request.error(f"unsupported fields: {', '.join(sorted(params.keys()))}")
            filament_info['OFFICIAL'] = has_params
            if self._should_apply(channel, has_params):
                detector.set_filament_info(
                    channel, self._rfid_hub.apply_generic_vendor(filament_info))
            web_request.send({'state': 'success'})
        except Exception as err:
            _log.error("filament_detect/set: %s", str(err))
            web_request.send({'state': 'error', 'message': str(err)})


def load_config(config):
    return RfidNtag(config)
