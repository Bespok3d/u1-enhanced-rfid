import contextlib
import hashlib
import json
import logging
import os
from typing import Any

RFID_DATA_FILE = "/oem/printer_data/config/bespok3d/data/rfid_data.json"
RFID_DATA_FINGERPRINT_SUFFIX = ".sha256"
UNPROVEN_LANES_SUFFIX = ".unproven"
STAGED_SAVE_SUFFIX = ".saving"
SavedLanes = dict[str, Any]

_log = logging.getLogger('bespok3d')


def _fingerprint_path() -> str:
    return RFID_DATA_FILE + RFID_DATA_FINGERPRINT_SUFFIX


def _unproven_lanes_path() -> str:
    return RFID_DATA_FILE + UNPROVEN_LANES_SUFFIX


def text_fingerprint(saved_text: str) -> str:
    return hashlib.sha256(saved_text.encode('utf-8')).hexdigest()


# A file that is there but cannot be read reads as empty text, never as missing: a missing file is
# trusted as a first start, while an unreadable one must be replaced like one nobody can prove.
def _read_saved_text(saved_path: str) -> str | None:
    try:
        with open(saved_path, encoding='utf-8') as file_in:
            return file_in.read()
    except FileNotFoundError:
        return None
    except Exception as read_err:
        _log.error("%s read failed: %s", os.path.basename(saved_path), read_err)
        return ""


# The text is swapped in whole, so a reader never meets half a save, even after a power cut.
def _write_saved_text(saved_path: str, saved_text: str) -> None:
    staged_path = saved_path + STAGED_SAVE_SUFFIX
    with open(staged_path, 'w', encoding='utf-8') as file_out:
        file_out.write(saved_text)
        file_out.flush()
        os.fsync(file_out.fileno())
    os.replace(staged_path, saved_path)


def _remove_if_there(saved_path: str) -> None:
    with contextlib.suppress(FileNotFoundError):
        os.remove(saved_path)


def _is_proven(saved_text: str) -> bool:
    saved_fingerprint = _read_saved_text(_fingerprint_path())
    if saved_fingerprint is None:
        return False
    return saved_fingerprint.strip() == text_fingerprint(saved_text)


def _lane_map_or_none(saved_text: str) -> SavedLanes | None:
    try:
        saved_lanes = json.loads(saved_text)
    except ValueError:
        return None
    return saved_lanes if isinstance(saved_lanes, dict) else None


# Builds up to 0.1.17 saved a tag picked up from the neighbouring spool as the lane's own, and
# their file cannot prove which lane really holds a tag: a wrong lane kept from it would block the
# real one. Only a file this version saved, proven by its fingerprint, is trusted.
def read_saved_lanes() -> tuple[SavedLanes, bool]:
    saved_text = _read_saved_text(RFID_DATA_FILE)
    if saved_text is None:
        return {}, True
    saved_lanes = _lane_map_or_none(saved_text)
    is_proven = _is_proven(saved_text)
    if not is_proven:
        _log.info("rfid_data.json has no matching fingerprint (an older version saved it, or a "
                  "save was cut short): starting with no remembered spool")
    elif saved_lanes is None:
        _log.error("rfid_data.json holds no lane map: starting with no remembered spool")
    return saved_lanes or {}, is_proven


# The fingerprint is swapped in after the lanes, so a save cut between the two leaves lanes the
# next restart will not trust, and one cut before them leaves the last save whole.
def save_lanes(saved_lanes: SavedLanes) -> None:
    try:
        saved_text = json.dumps(saved_lanes)
        os.makedirs(os.path.dirname(RFID_DATA_FILE), exist_ok=True)
        _write_saved_text(RFID_DATA_FILE, saved_text)
        _write_saved_text(_fingerprint_path(), text_fingerprint(saved_text))
    except Exception as write_err:
        _log.error("rfid_data.json write failed: %s", write_err)


# The lanes an older version saved are checked against the printer once it is ready, and a restart
# that never gets there must not lose them, so they wait in a file of their own until then.
def set_aside_unproven_lanes() -> None:
    try:
        os.replace(RFID_DATA_FILE, _unproven_lanes_path())
    except OSError as move_err:
        _log.error("rfid_data.json could not be set aside for checking: %s", move_err)


def read_unproven_lanes() -> SavedLanes:
    saved_text = _read_saved_text(_unproven_lanes_path())
    if saved_text is None:
        return {}
    return _lane_map_or_none(saved_text) or {}


def forget_unproven_lanes() -> None:
    try:
        _remove_if_there(_unproven_lanes_path())
    except OSError as remove_err:
        _log.error("rfid_data.json.unproven could not be removed: %s", remove_err)
