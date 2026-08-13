"""Regression tests for the shared RFID relay layer's stale-downgrade guard.

A UID-only fallback report (no vendor/type identity, see mifare_classic.uid_only_struct)
must not be allowed to overwrite an already-identified spool on the same channel -- the
same protection Snapmaker's own firmware applies in print_task_config.py's
_rfid_filament_info_update_cb. These tests exercise Bespok3dRfid._on_filament_update
directly, without going through Klipper's config/printer objects (the guard under test
does not touch either).
"""
from conftest import load_printer_extra

bespok3d_rfid = load_printer_extra("bespok3d_rfid")


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
