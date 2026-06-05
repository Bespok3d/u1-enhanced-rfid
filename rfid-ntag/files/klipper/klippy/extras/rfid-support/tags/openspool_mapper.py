import copy
import logging

from . import filament_protocol, payload_mapper

_log = logging.getLogger('bespok3d.openspool')

FIELD_MAP = {
    'VENDOR':          ('brand',    str,                           'Generic'),
    'MANUFACTURER':    ('brand',    str,                           'Generic'),
    'MAIN_TYPE':       ('type',     lambda v: str(v).upper(),      'PLA'),
    'SUB_TYPE':        ('subtype',  str,                           'Basic'),
    'SPOOL_ID':        ('spool_id', str,                           '0'),
    'HOTEND_MIN_TEMP': ('min_temp', int,                           0),
    'HOTEND_MAX_TEMP': ('max_temp', int,                           0),
    'DIAMETER':        ('diameter', lambda v: int(float(v) * 100), 175),
    'WEIGHT':          ('weight',   int,                           0),
}


def _parse_color_hex(value):
    try:
        return int(str(value).lstrip('#'), 16)
    except (ValueError, TypeError):
        return 0xFFFFFF


def _map_colors(data, info):
    info['RGB_1'] = _parse_color_hex(data.get('color_hex', 'FFFFFF'))
    info['COLOR_NUMS'] = 1
    for idx, hex_color in enumerate(list(data.get('additional_color_hexes') or [])[:4], start=2):
        info[f'RGB_{idx}'] = _parse_color_hex(hex_color)
        info['COLOR_NUMS'] = idx
    for i in range(info['COLOR_NUMS'] + 1, 6):
        info[f'RGB_{i}'] = 0
    try:
        info['ALPHA'] = max(0x00, min(0xFF, int(data.get('alpha', 0xFF))))
    except (ValueError, TypeError):
        info['ALPHA'] = 0xFF
    info['ARGB_COLOR'] = info['ALPHA'] << 24 | info['RGB_1']


def _map_bed_temp(data, info):
    try:
        bed_min = int(data.get('bed_min_temp', 0))
        bed_max = int(data.get('bed_max_temp', 0))
        info['BED_TEMP'] = bed_min if bed_min > 0 else bed_max
    except (ValueError, TypeError):
        info['BED_TEMP'] = 0


class OpenSpoolMapper:
    protocol_id = 'openspool'

    def to_filament_info(self, data, card_uid):
        _log.info("to_filament_info: protocol=%s keys=%s", data.get('protocol'), list(data.keys()))
        info = copy.copy(filament_protocol.FILAMENT_INFO_STRUCT)
        info['VERSION'] = 1
        info['TRAY'] = 0
        info['LENGTH'] = 0
        info['DRYING_TEMP'] = 0
        info['DRYING_TIME'] = 0
        info['BED_TYPE'] = 0
        info['SKU'] = 0
        info['MF_DATE'] = '19700101'
        info['RSA_KEY_VERSION'] = 0
        info['OFFICIAL'] = True
        payload_mapper.apply_field_map(data, info, FIELD_MAP)
        _map_colors(data, info)
        _map_bed_temp(data, info)
        info['FIRST_LAYER_TEMP'] = info['HOTEND_MIN_TEMP']
        info['OTHER_LAYER_TEMP'] = info['HOTEND_MIN_TEMP']
        info['CARD_UID'] = card_uid
        _log.info(
            "to_filament_info: vendor=%s type=%s spool_id=%s bed=%d hotend=%d-%d",
            info.get('VENDOR'), info.get('MAIN_TYPE'), info.get('SPOOL_ID'),
            info.get('BED_TEMP', 0), info.get('HOTEND_MIN_TEMP', 0), info.get('HOTEND_MAX_TEMP', 0),
        )
        return filament_protocol.FILAMENT_PROTO_OK, info
