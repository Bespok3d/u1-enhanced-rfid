# ruff: noqa: PLR2004  Tests assert on literal counts/values by design.
"""Regression tests for the NDEF parser.

These pin the observable behavior of ndef_parse before and after refactoring:
the status code, the parsed MIME-type records, and the extracted card UID.
"""
import ndef_parser
from ndef_parser import (
    NDEF_NOT_FOUND_ERR,
    NDEF_OK,
    NDEF_PARAMETER_ERR,
    ndef_parse,
)

CAPABILITY_CONTAINER = bytes([0xE1, 0x10, 0x12, 0x00])
NDEF_TERMINATOR = bytes([0xFE])


def short_record(mime_type: str, payload: bytes) -> bytes:
    """One short-record NDEF message entry: MIME type (TNF 0x02), SR flag set."""
    header = 0x12
    return bytes([header, len(mime_type), len(payload)]) + mime_type.encode("ascii") + payload


def message_tlv(message: bytes) -> bytes:
    return bytes([0x03, len(message)]) + message


def test_rejects_none() -> None:
    assert ndef_parse(None) == (NDEF_PARAMETER_ERR, [], [])


def test_rejects_wrong_type() -> None:
    assert ndef_parse("not bytes") == (NDEF_PARAMETER_ERR, [], [])


def test_bad_capability_container_is_parameter_error() -> None:
    status, records, card_uid = ndef_parse(bytes([0x00, 0x00, 0x00, 0x00]))
    assert status == NDEF_PARAMETER_ERR
    assert records == []
    assert card_uid == []


def test_valid_container_without_records_is_not_found() -> None:
    data = CAPABILITY_CONTAINER + message_tlv(b"") + NDEF_TERMINATOR + bytes([0x00])
    status, records, _ = ndef_parse(data)
    assert status == NDEF_NOT_FOUND_ERR
    assert records == []


def test_parses_single_mime_record() -> None:
    payload = b'{"v":1}'
    message = short_record("application/json", payload)
    data = CAPABILITY_CONTAINER + message_tlv(message) + NDEF_TERMINATOR
    status, records, _ = ndef_parse(data)
    assert status == NDEF_OK
    assert records == [{"mime_type": "application/json", "payload": payload}]


def test_extracts_card_uid_from_leading_bytes() -> None:
    message = short_record("a/b", b"x")
    data = CAPABILITY_CONTAINER + message_tlv(message) + NDEF_TERMINATOR
    _, _, card_uid = ndef_parse(data)
    expected = [data[0], data[1], data[2], data[4], data[5], data[6], data[7]]
    assert card_uid == expected


def test_skips_non_message_tlv_blocks() -> None:
    lock_control_tlv = bytes([0x01, 0x03, 0xAA, 0xBB, 0xCC])
    payload = b"42"
    message = short_record("text/plain", payload)
    data = (
        CAPABILITY_CONTAINER
        + lock_control_tlv
        + message_tlv(message)
        + NDEF_TERMINATOR
    )
    status, records, _ = ndef_parse(data)
    assert status == NDEF_OK
    assert records == [{"mime_type": "text/plain", "payload": payload}]


def test_status_codes_are_distinct() -> None:
    assert len({ndef_parser.NDEF_OK, ndef_parser.NDEF_ERR,
                ndef_parser.NDEF_PARAMETER_ERR, ndef_parser.NDEF_NOT_FOUND_ERR}) == 4
