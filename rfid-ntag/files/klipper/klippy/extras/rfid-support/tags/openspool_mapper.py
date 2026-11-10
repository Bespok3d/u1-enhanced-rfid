import copy
import logging
import string

from . import filament_protocol, payload_mapper

_log = logging.getLogger('bespok3d.openspool')

MAIN_COLOR_FIELD = 'color_hex'
EXTRA_COLORS_FIELD = 'additional_color_hexes'
WHITE_RGB = 0xFFFFFF
EMPTY_COLOR_SLOT = 0
MAX_COLORS = 5   # the printer shows at most five colors per spool
HEX_RADIX = 16
RGB_HEX_DIGITS = 6
# RRGGBBAA: the trailing alpha pair is read past; OpenSpool carries alpha in its own field.
RGBA_HEX_DIGITS = 8
COLOR_HEX_DIGIT_COUNTS = (RGB_HEX_DIGITS, RGBA_HEX_DIGITS)
HEX_COLOR_PREFIX = '#'
ALPHA_FIELD = 'alpha'
ALPHA_HEX_DIGIT_COUNTS = (2,)
TRANSPARENT_ALPHA = 0x00
OPAQUE_ALPHA = 0xFF
ALPHA_SHIFT = 24

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


def _is_hex(digits: str, digit_counts: tuple[int, ...]) -> bool:
    has_expected_length = len(digits) in digit_counts
    return has_expected_length and all(digit in string.hexdigits for digit in digits)


def _hex_rgb(color_hex: object) -> int | None:
    if not isinstance(color_hex, str):
        return None
    digits = color_hex.removeprefix(HEX_COLOR_PREFIX)
    if not _is_hex(digits, COLOR_HEX_DIGIT_COUNTS):
        return None
    return int(digits[:RGB_HEX_DIGITS], HEX_RADIX)


def _listed_color_hexes(data: dict) -> list[object]:
    extra_hexes = data.get(EXTRA_COLORS_FIELD)
    listed_extras = extra_hexes if isinstance(extra_hexes, list) else []
    return [data.get(MAIN_COLOR_FIELD), *listed_extras]


def _spool_colors(data: dict) -> list[int]:
    parsed_colors = (_hex_rgb(color_hex) for color_hex in _listed_color_hexes(data))
    valid_colors = [rgb for rgb in parsed_colors if rgb is not None]
    return valid_colors[:MAX_COLORS] or [WHITE_RGB]


def _spool_alpha(alpha: object) -> int:
    # The U1 OpenSpool extension writes alpha as a hex pair ("80" is half see-through); a JSON
    # whole number is taken as the value itself, as before. A JSON true/false is not a number.
    if isinstance(alpha, int) and not isinstance(alpha, bool):
        return max(TRANSPARENT_ALPHA, min(OPAQUE_ALPHA, alpha))
    if isinstance(alpha, str) and _is_hex(alpha, ALPHA_HEX_DIGIT_COUNTS):
        return int(alpha, HEX_RADIX)
    return OPAQUE_ALPHA


def _map_colors(data: dict, info: dict) -> None:
    colors = _spool_colors(data)
    color_slots = colors + [EMPTY_COLOR_SLOT] * (MAX_COLORS - len(colors))
    info.update({f'RGB_{slot}': rgb for slot, rgb in enumerate(color_slots, start=1)})
    info['COLOR_NUMS'] = len(colors)
    info['ALPHA'] = _spool_alpha(data.get(ALPHA_FIELD))
    info['ARGB_COLOR'] = info['ALPHA'] << ALPHA_SHIFT | info['RGB_1']


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
