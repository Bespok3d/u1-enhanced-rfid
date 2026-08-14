"""Regression tests for how the OpenSpool mapper names a spool.

The glued "<vendor> <type> <sub-type>" is the name Snapmaker Orca matches against its filament
presets, exactly and case-sensitively. A tag's own subtype passes through as written; a tag that
carries none reads as Basic, the way Snapmaker names its own base line.
"""
from conftest import FILAMENT_PROTO_OK, load_printer_extra

openspool_mapper = load_printer_extra("openspool_mapper")

CARD_UID = [0x04, 0x11, 0x22]


def _tag_payload(**tag_fields) -> dict:
    payload = {"protocol": "openspool", "version": "1.0", "type": "PLA", "color_hex": "#FF0000"}
    payload.update(tag_fields)
    return payload


def _printer_report(tag_payload: dict) -> dict:
    error, info = openspool_mapper.OpenSpoolMapper().to_filament_info(tag_payload, CARD_UID)
    assert error == FILAMENT_PROTO_OK
    return info


def test_tag_variant_is_reported_as_written() -> None:
    info = _printer_report(_tag_payload(brand="ELEGOO", type="PLA+", subtype="Rapid"))
    assert info["VENDOR"] == "ELEGOO"
    assert info["MAIN_TYPE"] == "PLA+"
    assert info["SUB_TYPE"] == "Rapid"


def test_tag_without_variant_reads_as_the_basic_line() -> None:
    info = _printer_report(_tag_payload(brand="JAYO"))
    assert info["VENDOR"] == "JAYO"
    assert info["SUB_TYPE"] == "Basic"
