"""Regression tests for the field-map applier used by tag mappers."""
from payload_mapper import apply_field_map


def test_present_key_is_converted() -> None:
    dest: dict[str, object] = {}
    apply_field_map({"brand": "polymaker"}, dest, {"VENDOR": ("brand", str.upper, "Generic")})
    assert dest["VENDOR"] == "POLYMAKER"


def test_missing_key_falls_back_to_default() -> None:
    dest: dict[str, object] = {}
    apply_field_map({}, dest, {"VENDOR": ("brand", str, "Generic")})
    assert dest["VENDOR"] == "Generic"


def test_none_source_key_uses_default() -> None:
    dest: dict[str, object] = {}
    apply_field_map({"brand": "x"}, dest, {"SPOOL_ID": (None, str, "0")})
    assert dest["SPOOL_ID"] == "0"


def test_failed_conversion_uses_default() -> None:
    dest: dict[str, object] = {}
    apply_field_map({"temp": "not-a-number"}, dest, {"MIN_TEMP": ("temp", int, 0)})
    assert dest["MIN_TEMP"] == 0
