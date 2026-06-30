"""Pure helpers for the Mifare-Classic substrate (no relative imports, unit-tested).

The fm175xx reader patch routes a SAK 0x08 card that the stock Snapmaker key could not
open to registered claim handlers (Bambu, Creality, ...). When no handler authenticates,
the reader surfaces the card's UID under card type ``M1_UID_CARD_TYPE`` so a foreign tag
is still trackable by its UID (Spoolman ``nfc_id``) instead of disappearing.

This module is the host-testable half of that path: the random-UID guard and the
UID-only struct builder. The card-type value is mirrored, on purpose, into the reader
patch (``FM175XX_MIFARE_CARD_TYPE_M1_UID``), which cannot import a sibling at patch time;
``test_mifare_classic`` locks the two to the same value.
"""

from collections.abc import Sequence
from typing import Any

M1_UID_CARD_TYPE = 0x88  # mirror of fm175xx_reader.FM175XX_MIFARE_CARD_TYPE_M1_UID
RANDOM_UID_PREFIX = 0x08  # NXP AN10927: a random (non-stable) UID starts with 0x08


def is_random_uid(uid: Sequence[int] | None) -> bool:
    """A re-randomized DESFire/Ultralight UID (first byte 0x08) is not a stable key."""
    return uid is not None and len(uid) > 0 and uid[0] == RANDOM_UID_PREFIX


def uid_only_struct(template: dict[str, Any], card_data: Sequence[int] | None) -> dict[str, Any]:
    """Build a filament struct carrying only the UID (no decoded filament).

    ``template`` is ``filament_protocol.FILAMENT_INFO_STRUCT`` (injected so this stays
    pure); ``card_data`` is the reader's selected-card UID byte list.
    """
    info = dict(template)
    info['CARD_UID'] = [int(byte) for byte in (card_data or [])]
    return info
