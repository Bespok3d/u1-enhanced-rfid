"""Regression tests for the shared RFID relay layer's stale-downgrade guard.

A UID-only fallback report (no vendor/type identity, see mifare_classic.uid_only_struct)
must not be allowed to overwrite an already-identified spool on the same channel -- the
same protection Snapmaker's own firmware applies in print_task_config.py's
_rfid_filament_info_update_cb. These tests exercise Bespok3dRfid._on_filament_update
directly, without going through Klipper's config/printer objects (the guard under test
does not touch either).
"""
import importlib
import sys
import types
from pathlib import Path

EXTRAS_DIR = Path(__file__).resolve().parent.parent / "files" / "rfid-base" / "extras"


def _install_stub_package():
    """Load bespok3d_rfid.py as extras_stub.bespok3d_rfid so its `from . import` resolves.

    Mirrors the real deployment: on the printer, bespok3d_rfid.py lives inside Klipper's
    klippy.extras package alongside Snapmaker's own filament_protocol.py, so its relative
    import resolves to real sibling modules. Here the stub package supplies a minimal
    filament_protocol (matching FILAMENT_INFO_STRUCT / OFFICIAL) and an unused mifare_classic
    placeholder, so the module under test imports exactly as it does on-device.
    """
    package_name = "extras_stub"
    package = types.ModuleType(package_name)
    package.__path__ = [str(EXTRAS_DIR)]
    sys.modules[package_name] = package

    filament_protocol = types.ModuleType(f"{package_name}.filament_protocol")
    filament_protocol.FILAMENT_INFO_STRUCT = {
        'VENDOR': 'NONE',
        'MAIN_TYPE': 'NONE',
        'OFFICIAL': False,
        'CARD_UID': 0,
        'SPOOL_ID': 0,
    }
    filament_protocol.FILAMENT_PROTO_OK = 0
    filament_protocol.FILAMENT_PROTO_ERR = 1
    sys.modules[f"{package_name}.filament_protocol"] = filament_protocol

    mifare_classic = types.ModuleType(f"{package_name}.mifare_classic")
    mifare_classic.M1_UID_CARD_TYPE = 0x88

    def uid_only_struct(template, card_data):
        info = dict(template)
        info['CARD_UID'] = [int(byte) for byte in (card_data or [])]
        return info

    mifare_classic.uid_only_struct = uid_only_struct
    sys.modules[f"{package_name}.mifare_classic"] = mifare_classic

    return importlib.import_module(f"{package_name}.bespok3d_rfid")


bespok3d_rfid = _install_stub_package()


def _make_relay():
    relay = object.__new__(bespok3d_rfid.Bespok3dRfid)
    relay._filament_state = [None] * bespok3d_rfid.CHANNEL_COUNT
    relay._spool_notify_cbs = []
    relay._write_rfid_data = lambda: None
    return relay


def _tagged_report(vendor="Polymaker"):
    return {'VENDOR': vendor, 'MAIN_TYPE': 'PLA', 'OFFICIAL': True, 'SPOOL_ID': 7}


def _uid_only_report(card_uid=None):
    return {'VENDOR': 'NONE', 'MAIN_TYPE': 'NONE', 'OFFICIAL': False,
            'CARD_UID': card_uid or [0x04, 0x01, 0x02, 0x03], 'SPOOL_ID': 0}


def _brandless_openspool_report():
    return {'VENDOR': 'Generic', 'MAIN_TYPE': 'PLA', 'OFFICIAL': True, 'SPOOL_ID': 42}


CHANNEL = 0


def test_uid_only_report_after_tagged_load_is_suppressed():
    relay = _make_relay()
    notified = []
    relay.register_spool_notify(
        lambda channel, info, is_clear: notified.append((channel, info, is_clear))
    )

    relay._on_filament_update(CHANNEL, _tagged_report(), is_clear=False)
    relay._on_filament_update(CHANNEL, _uid_only_report(), is_clear=False)

    assert relay._filament_state[CHANNEL] == _tagged_report()
    assert notified == [(CHANNEL, _tagged_report(), False)]


def test_explicit_clear_after_tagged_load_still_clears():
    relay = _make_relay()
    notified = []
    relay.register_spool_notify(
        lambda channel, info, is_clear: notified.append((channel, info, is_clear))
    )

    relay._on_filament_update(CHANNEL, _tagged_report(), is_clear=False)
    relay._on_filament_update(CHANNEL, None, is_clear=True)

    assert relay._filament_state[CHANNEL] is None
    assert notified[-1] == (CHANNEL, None, True)


def test_first_ever_uid_only_report_on_empty_channel_is_not_suppressed():
    relay = _make_relay()
    notified = []
    relay.register_spool_notify(
        lambda channel, info, is_clear: notified.append((channel, info, is_clear))
    )

    report = _uid_only_report()
    relay._on_filament_update(CHANNEL, report, is_clear=False)

    assert relay._filament_state[CHANNEL] == report
    assert notified == [(CHANNEL, report, False)]


def test_brandless_openspool_swap_after_tagged_load_is_not_suppressed():
    relay = _make_relay()
    notified = []
    relay.register_spool_notify(
        lambda channel, info, is_clear: notified.append((channel, info, is_clear))
    )

    relay._on_filament_update(CHANNEL, _tagged_report(), is_clear=False)
    swap_report = _brandless_openspool_report()
    relay._on_filament_update(CHANNEL, swap_report, is_clear=False)

    assert relay._filament_state[CHANNEL] == swap_report
    assert notified[-1] == (CHANNEL, swap_report, False)
