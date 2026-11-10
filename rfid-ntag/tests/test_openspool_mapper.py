"""Regression tests for how the OpenSpool mapper names a spool.

The glued "<vendor> <type> <sub-type>" is the name Snapmaker Orca matches against its filament
presets, exactly and case-sensitively. A tag's own subtype passes through as written; a tag that
carries none reads as Basic, the way Snapmaker names its own base line.
"""
import pytest
from conftest import FILAMENT_PROTO_OK, load_printer_extra

openspool_mapper = load_printer_extra("openspool_mapper")

CARD_UID = [0x04, 0x11, 0x22]
WHITE = 0xFFFFFF
GREEN = 0x00FF00
BLUE = 0x0000FF
OPAQUE_BLUE_ARGB = 0xFF0000FF
OPAQUE = 0xFF
MALFORMED_HEX_COLORS = [
    "", None, "zz", "F00", "+12345", "-12345", " 112233", "0x1122", "11_233", "##112233",
    "1122334", "112233ZZ", 112233,
]


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


@pytest.mark.parametrize("malformed_hex", MALFORMED_HEX_COLORS)
def test_malformed_main_color_gives_way_to_the_first_extra(malformed_hex: object) -> None:
    tag_payload = _tag_payload(color_hex=malformed_hex, additional_color_hexes=["#00FF00"])
    info = _printer_report(tag_payload)
    assert (info["RGB_1"], info["RGB_2"], info["COLOR_NUMS"]) == (GREEN, 0, 1)


def test_missing_main_color_takes_the_first_valid_extra() -> None:
    colored_payload = _tag_payload(additional_color_hexes=["zz", "#0000FF", "#00FF00"])
    tag_payload = {field: value for field, value in colored_payload.items() if field != "color_hex"}
    info = _printer_report(tag_payload)
    assert (info["RGB_1"], info["RGB_2"], info["COLOR_NUMS"]) == (BLUE, GREEN, 2)
    assert info["ARGB_COLOR"] == OPAQUE_BLUE_ARGB


def test_malformed_extra_colors_are_skipped() -> None:
    extra_hexes = ["F00", "00FF00"]
    tag_payload = _tag_payload(color_hex="#0000FF", additional_color_hexes=extra_hexes)
    info = _printer_report(tag_payload)
    assert (info["RGB_1"], info["RGB_2"], info["RGB_3"], info["COLOR_NUMS"]) == (BLUE, GREEN, 0, 2)


def test_tag_without_a_valid_color_reads_white() -> None:
    info = _printer_report(_tag_payload(color_hex="zz", additional_color_hexes=["zz"]))
    assert (info["RGB_1"], info["RGB_2"], info["COLOR_NUMS"]) == (WHITE, 0, 1)


def test_colors_stop_at_five_after_bad_ones_are_skipped() -> None:
    six_valid_extras = ["#000001", "#000002", "#000003", "#000004", "#000005", "#000006"]
    info = _printer_report(_tag_payload(color_hex="zz", additional_color_hexes=six_valid_extras))
    shown_colors = [info[f"RGB_{slot}"] for slot in range(1, 6)]
    assert (shown_colors, info["COLOR_NUMS"]) == ([1, 2, 3, 4, 5], 5)
    assert "RGB_6" not in info


def test_rgba_main_color_reads_its_rgb() -> None:
    info = _printer_report(_tag_payload(color_hex="#0000FF80"))
    assert (info["RGB_1"], info["COLOR_NUMS"]) == (BLUE, 1)


@pytest.mark.parametrize(("written_alpha", "alpha"), [("80", 0x80), ("C0", 0xC0), ("ff", 0xFF)])
def test_alpha_is_read_as_a_hex_pair(written_alpha: str, alpha: int) -> None:
    info = _printer_report(_tag_payload(color_hex="#0000FF", alpha=written_alpha))
    assert (info["ALPHA"], info["ARGB_COLOR"]) == (alpha, alpha << 24 | BLUE)


@pytest.mark.parametrize(
    "malformed_alpha", ["", "8", "0x80", "-1", "1FF", "zz", None, 1.5, True, False],
)
def test_malformed_alpha_reads_opaque(malformed_alpha: object) -> None:
    info = _printer_report(_tag_payload(color_hex="#0000FF", alpha=malformed_alpha))
    assert info["ALPHA"] == OPAQUE


def test_alpha_written_as_a_number_is_kept_in_range() -> None:
    whole_number_alphas = [128, -5, 300]
    reports = [_printer_report(_tag_payload(alpha=alpha)) for alpha in whole_number_alphas]
    assert [info["ALPHA"] for info in reports] == [128, 0x00, OPAQUE]
