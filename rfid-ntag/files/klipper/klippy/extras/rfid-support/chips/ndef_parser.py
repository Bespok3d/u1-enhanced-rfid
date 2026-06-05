import io
import logging
from collections.abc import Iterator

_log = logging.getLogger('bespok3d.ndef')

NDEF_OK = 0
NDEF_ERR = -1
NDEF_PARAMETER_ERR = -2
NDEF_NOT_FOUND_ERR = -3

CC_MAGIC = 0xE1
CC_VERSIONS = (0x10, 0x11, 0x40)
CC_LENGTH = 4
CC_SEARCH_MIN_BYTES = 12
CC_SEARCH_WINDOW = 16

TLV_HEADER_LENGTH = 2
TLV_NDEF_MESSAGE = 0x03
TLV_TERMINATOR = 0xFE
TLV_EXTENDED_LENGTH = 0xFF
EXTENDED_LENGTH_BYTES = 2

TNF_MASK = 0x07
TNF_MIME = 0x02
SHORT_RECORD_FLAG = 0x10
ID_LENGTH_FLAG = 0x08
LONG_PAYLOAD_LENGTH_BYTES = 4
RECORD_MIN_REMAINDER = 2

CARD_UID_MIN_BYTES = 8

ASCII_PRINTABLE_START = 32
ASCII_PRINTABLE_END = 127
XXD_BYTES_PER_LINE = 16
XXD_DEFAULT_MAX_LINES = 16
XXD_HEX_COLUMN_WIDTH = 48

Record = dict[str, object]


def _printable(byte: int) -> str:
    if ASCII_PRINTABLE_START <= byte < ASCII_PRINTABLE_END:
        return chr(byte)
    return '.'


def _xxd_row(data: bytes, start: int) -> str:
    chunk = data[start:start + XXD_BYTES_PER_LINE]
    hex_part = ' '.join(f'{byte:02x}' for byte in chunk)
    ascii_part = ''.join(_printable(byte) for byte in chunk)
    return f'{start:08x}: {hex_part:<{XXD_HEX_COLUMN_WIDTH}}  {ascii_part}'


def _xxd_dump(data: object, max_lines: int = XXD_DEFAULT_MAX_LINES) -> str:
    if not isinstance(data, (list, bytes, bytearray)):
        return ''
    raw = bytes(data)
    limit = min(len(raw), max_lines * XXD_BYTES_PER_LINE)
    rows = [_xxd_row(raw, start) for start in range(0, limit, XXD_BYTES_PER_LINE)]
    if len(raw) > max_lines * XXD_BYTES_PER_LINE:
        rows.append(f'... ({len(raw)} bytes total)')
    return '\n'.join(rows)


def _extract_card_uid(data: bytes) -> list[int]:
    if len(data) < CARD_UID_MIN_BYTES:
        return []
    return [data[0], data[1], data[2], data[4], data[5], data[6], data[7]]


def _find_capability_container_offset(data: bytes) -> int:
    if len(data) <= CC_SEARCH_MIN_BYTES or data[0] == CC_MAGIC:
        return 0
    window = min(CC_SEARCH_WINDOW, len(data) - CC_LENGTH)
    matches = (
        offset for offset in range(window)
        if data[offset] == CC_MAGIC and data[offset + 1] in CC_VERSIONS
    )
    return next(matches, 0)


def _read_message_length(stream: io.BytesIO, first_length: int) -> int | None:
    if first_length != TLV_EXTENDED_LENGTH:
        return first_length
    extended = stream.read(EXTENDED_LENGTH_BYTES)
    if len(extended) < EXTENDED_LENGTH_BYTES:
        return None
    return (extended[0] << 8) | extended[1]


def _iter_ndef_messages(stream: io.BytesIO) -> Iterator[bytes]:
    while True:
        header = stream.read(TLV_HEADER_LENGTH)
        if len(header) < TLV_HEADER_LENGTH or header[0] == TLV_TERMINATOR:
            return
        length = _read_message_length(stream, header[1])
        if length is None:
            return
        block = stream.read(length)
        if header[0] == TLV_NDEF_MESSAGE:
            yield block


def _read_payload_length(message: bytes, header: int, cursor: int) -> tuple[int | None, int]:
    if header & SHORT_RECORD_FLAG:
        return message[cursor], cursor + 1
    if cursor + LONG_PAYLOAD_LENGTH_BYTES > len(message):
        return None, cursor
    payload_length = (
        (message[cursor] << 24) | (message[cursor + 1] << 16)
        | (message[cursor + 2] << 8) | message[cursor + 3]
    )
    return payload_length, cursor + LONG_PAYLOAD_LENGTH_BYTES


def _read_id_length(message: bytes, header: int, cursor: int) -> tuple[int, int]:
    if header & ID_LENGTH_FLAG:
        return message[cursor], cursor + 1
    return 0, cursor


def _mime_record(header: int, mime_type: str, payload: bytes) -> Record | None:
    if header & TNF_MASK != TNF_MIME:
        return None
    _log.info("NDEF record: mime_type='%s' payload_len=%d", mime_type, len(payload))
    return {'mime_type': mime_type, 'payload': payload}


def _parse_record(message: bytes, offset: int) -> tuple[Record | None, int] | None:
    header = message[offset]
    type_length = message[offset + 1]
    payload_length, cursor = _read_payload_length(message, header, offset + 2)
    if payload_length is None:
        return None
    id_length, cursor = _read_id_length(message, header, cursor)
    end = cursor + type_length + id_length + payload_length
    if end > len(message):
        return None
    mime_type = message[cursor:cursor + type_length].decode('ascii', errors='ignore')
    payload_start = cursor + type_length + id_length
    payload = bytes(message[payload_start:payload_start + payload_length])
    return _mime_record(header, mime_type, payload), end


def _parse_records(message: bytes) -> list[Record]:
    records: list[Record] = []
    offset = 0
    while offset < len(message) - RECORD_MIN_REMAINDER:
        parsed = _parse_record(message, offset)
        if parsed is None:
            break
        record, offset = parsed
        if record is not None:
            records.append(record)
    return records


def _parse_validated(data: bytes) -> tuple[int, list[Record], list[int]]:
    card_uid = _extract_card_uid(data)
    _log.info("ndef_parse: %d bytes uid=%s", len(data), [hex(byte) for byte in card_uid])
    _log.debug("NDEF RFID data:\n%s", _xxd_dump(data))
    stream = io.BytesIO(data)
    stream.seek(_find_capability_container_offset(data))
    container = stream.read(CC_LENGTH)
    if len(container) < CC_LENGTH or container[0] != CC_MAGIC:
        _log.error("ndef_parse: bad CC (expected 0xE1): NDEF_PARAMETER_ERR")
        return NDEF_PARAMETER_ERR, [], card_uid
    records = [
        record
        for message in _iter_ndef_messages(stream)
        for record in _parse_records(message)
    ]
    if not records:
        return NDEF_NOT_FOUND_ERR, [], card_uid
    return NDEF_OK, records, card_uid


def ndef_parse(data_buf: object) -> tuple[int, list[Record], list[int]]:
    if data_buf is None or not isinstance(data_buf, (list, bytes, bytearray)):
        return NDEF_PARAMETER_ERR, [], []
    try:
        return _parse_validated(bytes(data_buf))
    except Exception as parse_err:
        _log.exception("NDEF parsing failed: %s", parse_err)
        return NDEF_ERR, [], []
