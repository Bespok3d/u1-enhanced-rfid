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


# A lane whose own spool has no tag can pick up the tag of the spool next to it: the same hardware
# UID then reaches two channels. The tag belongs to the channel that already holds it.
TAGGED_CHANNEL = 3
NEIGHBOUR_CHANNEL = 2
NEIGHBOURING_TAG_UID = [0x04, 0xA1, 0xB2, 0xC3]


class FilamentDetectDoor:
    """Stands in for u1-base's filament_detect, recording what the relay sets on each channel."""

    def __init__(self):
        self.set_calls = []

    def set_filament_info(self, channel, info, is_clear=False):
        self.set_calls.append((channel, info, is_clear))
        return True


class PrinterWithFilamentDetect:
    def __init__(self, filament_detect):
        self.filament_detect = filament_detect

    def lookup_object(self, name, default=None):
        return self.filament_detect if name == 'filament_detect' else default


def _make_relay_on_printer():
    relay = _make_relay()
    filament_detect = FilamentDetectDoor()
    relay.printer = PrinterWithFilamentDetect(filament_detect)
    return relay, filament_detect


def _bambu_report(card_uid=None):
    return {'VENDOR': 'Bambu Lab', 'MAIN_TYPE': 'PLA', 'OFFICIAL': True, 'SPOOL_ID': 0,
            'CARD_UID': card_uid or NEIGHBOURING_TAG_UID}


def test_tag_already_held_by_another_channel_is_dropped_and_cleared_on_the_printer():
    relay, filament_detect = _make_relay_on_printer()
    notified = []
    relay.register_spool_notify(
        lambda channel, info, is_clear: notified.append((channel, info, is_clear))
    )

    relay._on_filament_update(TAGGED_CHANNEL, _bambu_report(), is_clear=False)
    relay._on_filament_update(NEIGHBOUR_CHANNEL, _bambu_report(), is_clear=False)

    assert relay._filament_state[TAGGED_CHANNEL] == _bambu_report()
    assert relay._filament_state[NEIGHBOUR_CHANNEL] is None
    assert notified == [(TAGGED_CHANNEL, _bambu_report(), False)]
    assert filament_detect.set_calls == [
        (NEIGHBOUR_CHANNEL, bespok3d_rfid.filament_protocol.FILAMENT_INFO_STRUCT, True)
    ]


def test_uid_only_report_of_a_tag_another_channel_holds_is_dropped():
    relay, filament_detect = _make_relay_on_printer()

    relay._on_filament_update(TAGGED_CHANNEL, _bambu_report(), is_clear=False)
    relay._on_filament_update(
        NEIGHBOUR_CHANNEL, _uid_only_report(NEIGHBOURING_TAG_UID), is_clear=False)

    assert relay._filament_state[NEIGHBOUR_CHANNEL] is None
    assert [channel for channel, _, _ in filament_detect.set_calls] == [NEIGHBOUR_CHANNEL]


def test_rereading_the_same_channel_keeps_its_own_tag():
    relay, filament_detect = _make_relay_on_printer()

    relay._on_filament_update(TAGGED_CHANNEL, _bambu_report(), is_clear=False)
    relay._on_filament_update(TAGGED_CHANNEL, _bambu_report(), is_clear=False)

    assert relay._filament_state[TAGGED_CHANNEL] == _bambu_report()
    assert filament_detect.set_calls == []


def test_spool_moved_after_its_old_channel_was_cleared_is_read_on_the_new_one():
    relay, filament_detect = _make_relay_on_printer()

    relay._on_filament_update(TAGGED_CHANNEL, _bambu_report(), is_clear=False)
    relay._on_filament_update(TAGGED_CHANNEL, None, is_clear=True)
    relay._on_filament_update(NEIGHBOUR_CHANNEL, _bambu_report(), is_clear=False)

    assert relay._filament_state[NEIGHBOUR_CHANNEL] == _bambu_report()
    assert filament_detect.set_calls == []


def test_different_tags_on_neighbouring_channels_are_both_kept():
    relay, filament_detect = _make_relay_on_printer()
    other_tag_uid = [0x04, 0xD4, 0xE5, 0xF6]

    relay._on_filament_update(TAGGED_CHANNEL, _bambu_report(), is_clear=False)
    relay._on_filament_update(NEIGHBOUR_CHANNEL, _bambu_report(other_tag_uid), is_clear=False)

    assert relay._filament_state[NEIGHBOUR_CHANNEL] == _bambu_report(other_tag_uid)
    assert filament_detect.set_calls == []
