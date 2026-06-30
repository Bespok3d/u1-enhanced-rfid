# ruff: noqa: PLR2004  Tests assert on literal counts/values by design.
"""Regression tests for the Mifare-Classic substrate helpers.

These pin the two host-testable halves of the claim/UID-fallback path: the random-UID
guard and the UID-only struct builder, plus the card-type value that the reader patch
mirrors (the patch cannot import this module, so the constant is locked here).
"""
import mifare_classic
from mifare_classic import M1_UID_CARD_TYPE, is_random_uid, uid_only_struct

TEMPLATE = {'VENDOR': 'NONE', 'MAIN_TYPE': 'NONE', 'CARD_UID': 0, 'OFFICIAL': False}


def test_card_type_matches_reader_patch_constant():
    # Mirrors fm175xx_reader.FM175XX_MIFARE_CARD_TYPE_M1_UID = 0x88 (see the reader patch).
    assert M1_UID_CARD_TYPE == 0x88
    assert mifare_classic.RANDOM_UID_PREFIX == 0x08


def test_genuine_uid_is_not_random():
    # Genuine NXP Mifare-Classic UIDs start with the 0x04 manufacturer byte.
    assert is_random_uid([0x04, 0xA1, 0xB2, 0xC3]) is False


def test_desfire_random_uid_is_flagged():
    assert is_random_uid([0x08, 0x11, 0x22, 0x33]) is True


def test_empty_uid_is_not_random():
    assert is_random_uid([]) is False
    assert is_random_uid(None) is False


def test_uid_only_struct_carries_uid_and_keeps_template_defaults():
    info = uid_only_struct(TEMPLATE, [0x04, 0xA1, 0xB2, 0xC3])
    assert info['CARD_UID'] == [0x04, 0xA1, 0xB2, 0xC3]
    assert info['VENDOR'] == 'NONE'
    assert info['MAIN_TYPE'] == 'NONE'
    assert info['OFFICIAL'] is False


def test_uid_only_struct_does_not_mutate_template():
    uid_only_struct(TEMPLATE, [0x04, 0x01, 0x02, 0x03])
    assert TEMPLATE['CARD_UID'] == 0


def test_uid_only_struct_coerces_bytes_to_ints():
    info = uid_only_struct(TEMPLATE, bytes([0x04, 0x05, 0x06, 0x07]))
    assert info['CARD_UID'] == [4, 5, 6, 7]
    assert all(isinstance(byte, int) for byte in info['CARD_UID'])
