"""Regression tests for the shared RFID relay layer's stale-downgrade guard.

A UID-only fallback report (no vendor/type identity, see mifare_classic.uid_only_struct)
must not be allowed to overwrite an already-identified spool on the same channel -- the
same protection Snapmaker's own firmware applies in print_task_config.py's
_rfid_filament_info_update_cb. These tests exercise Bespok3dRfid._on_filament_update
directly, without going through Klipper's config/printer objects (the guard under test
does not touch either).
"""
import json

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
    assert notified == [(CHANNEL, _tagged_report(), False), (CHANNEL, _tagged_report(), False)]


def test_explicit_clear_after_tagged_load_still_clears():
    relay = _make_relay()
    lanes_with_channel_empty = [channel != CHANNEL for channel in range(len(ALL_LANES_LOADED))]
    relay.printer = _FakePrinter(_FakeTaskConfig(lanes_with_channel_empty))
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


class _FakeReactor:
    def __init__(self):
        self.deferred_callbacks = []

    def register_callback(self, callback):
        self.deferred_callbacks.append(callback)

    def monotonic(self):
        return 0.0

    def run_deferred(self):
        for callback in self.deferred_callbacks:
            callback(0.0)


class _FakeTaskConfig:
    def __init__(self, filament_exist, filament_vendor=None):
        self.filament_exist = filament_exist
        self.filament_vendor = filament_vendor

    def get_status(self, eventtime=None):
        if self.filament_vendor is None:
            return {'filament_exist': list(self.filament_exist)}
        return {'filament_exist': list(self.filament_exist),
                'filament_vendor': list(self.filament_vendor)}


class _FakePrinter:
    def __init__(self, task_config, filament_detect=None):
        self.reactor = _FakeReactor()
        self.objects = {'print_task_config': task_config, 'filament_detect': filament_detect}

    def get_reactor(self):
        return self.reactor

    def lookup_object(self, name, default=None):
        return self.objects.get(name, default)


ALL_LANES_LOADED = [True] * bespok3d_rfid.CHANNEL_COUNT
ALL_LANES_EMPTY = [False] * bespok3d_rfid.CHANNEL_COUNT


def _firmware_vendors(channel_vendor):
    return [channel_vendor if channel == CHANNEL else 'NONE'
            for channel in range(bespok3d_rfid.CHANNEL_COUNT)]


def _booted_relay(tmp_path, monkeypatch, saved_lanes, firmware_vendors,
                  filament_exist=ALL_LANES_LOADED):
    rfid_data_file = tmp_path / "rfid_data.json"
    rfid_data_file.write_text(json.dumps(saved_lanes))
    monkeypatch.setattr(bespok3d_rfid, "RFID_DATA_FILE", str(rfid_data_file))
    relay = object.__new__(bespok3d_rfid.Bespok3dRfid)
    relay.printer = _FakePrinter(_FakeTaskConfig(filament_exist, firmware_vendors))
    relay._filament_state = [None] * bespok3d_rfid.CHANNEL_COUNT
    relay._spool_notify_cbs = []
    relay._restore_remembered_lanes()
    relay.printer.reactor.run_deferred()
    return relay, rfid_data_file


def test_failed_factory_read_after_reboot_keeps_the_remembered_spool(tmp_path, monkeypatch):
    relay, rfid_data_file = _booted_relay(
        tmp_path, monkeypatch, {str(CHANNEL): _tagged_report("Anycubic")},
        _firmware_vendors("Anycubic"))
    notified = []
    relay.register_spool_notify(
        lambda channel, info, is_clear: notified.append((channel, info, is_clear))
    )

    relay._on_filament_update(CHANNEL, _uid_only_report(), is_clear=False)

    assert notified == [(CHANNEL, _tagged_report("Anycubic"), False)]
    saved_lanes = json.loads(rfid_data_file.read_text())
    assert saved_lanes[str(CHANNEL)] == _tagged_report("Anycubic")


def test_lane_the_firmware_forgot_at_boot_forgets_the_remembered_spool(tmp_path, monkeypatch):
    relay, rfid_data_file = _booted_relay(
        tmp_path, monkeypatch, {str(CHANNEL): _tagged_report("Anycubic")},
        _firmware_vendors("NONE"))

    assert relay._filament_state[CHANNEL] is None
    saved_lanes = json.loads(rfid_data_file.read_text())
    assert saved_lanes[str(CHANNEL)]['VENDOR'] == 'NONE'


def test_unsettled_sensor_at_boot_keeps_the_spool_the_firmware_kept(tmp_path, monkeypatch):
    relay, rfid_data_file = _booted_relay(
        tmp_path, monkeypatch, {str(CHANNEL): _tagged_report("Anycubic")},
        _firmware_vendors("Anycubic"), filament_exist=ALL_LANES_EMPTY)

    assert relay._filament_state[CHANNEL] == _tagged_report("Anycubic")
    saved_lanes = json.loads(rfid_data_file.read_text())
    assert saved_lanes[str(CHANNEL)] == _tagged_report("Anycubic")


def test_new_tag_after_reboot_replaces_the_remembered_spool(tmp_path, monkeypatch):
    relay, rfid_data_file = _booted_relay(
        tmp_path, monkeypatch, {str(CHANNEL): _tagged_report("Anycubic")},
        _firmware_vendors("Anycubic"))

    relay._on_filament_update(CHANNEL, _tagged_report("Qidi"), is_clear=False)

    saved_lanes = json.loads(rfid_data_file.read_text())
    assert saved_lanes[str(CHANNEL)] == _tagged_report("Qidi")


def test_unknown_firmware_record_at_boot_keeps_every_remembered_spool(tmp_path, monkeypatch):
    relay, rfid_data_file = _booted_relay(
        tmp_path, monkeypatch, {str(CHANNEL): _tagged_report("Anycubic")}, None)

    assert relay._filament_state[CHANNEL] == _tagged_report("Anycubic")


def test_missing_rfid_data_file_boots_with_no_remembered_spool(tmp_path, monkeypatch):
    monkeypatch.setattr(bespok3d_rfid, "RFID_DATA_FILE", str(tmp_path / "absent.json"))
    relay = object.__new__(bespok3d_rfid.Bespok3dRfid)
    relay.printer = _FakePrinter(_FakeTaskConfig(ALL_LANES_LOADED))
    relay._filament_state = [None] * bespok3d_rfid.CHANNEL_COUNT

    relay._restore_remembered_lanes()
    relay.printer.reactor.run_deferred()

    assert relay._filament_state == [None] * bespok3d_rfid.CHANNEL_COUNT


def test_clear_while_the_spool_is_still_loaded_keeps_the_spool():
    relay = _make_relay()
    relay.printer = _FakePrinter(_FakeTaskConfig(ALL_LANES_LOADED))
    notified = []
    relay.register_spool_notify(
        lambda channel, info, is_clear: notified.append((channel, info, is_clear))
    )

    relay._on_filament_update(CHANNEL, _tagged_report("Anycubic"), is_clear=False)
    relay._on_filament_update(CHANNEL, None, is_clear=True)

    assert relay._filament_state[CHANNEL]['VENDOR'] == "Anycubic"
    assert notified[-1] == (CHANNEL, _tagged_report("Anycubic"), False)


def test_clear_while_loaded_after_boot_restore_keeps_the_file(tmp_path, monkeypatch):
    relay, rfid_data_file = _booted_relay(
        tmp_path, monkeypatch, {str(CHANNEL): _tagged_report("Anycubic")},
        _firmware_vendors("Anycubic"))

    relay._on_filament_update(CHANNEL, None, is_clear=True)

    saved_lanes = json.loads(rfid_data_file.read_text())
    assert saved_lanes[str(CHANNEL)]['VENDOR'] == "Anycubic"


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


def _make_relay_on_printer(filament_exist=ALL_LANES_LOADED):
    relay = _make_relay()
    filament_detect = FilamentDetectDoor()
    relay.printer = _FakePrinter(_FakeTaskConfig(filament_exist), filament_detect)
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
    lanes_with_old_channel_empty = [channel != TAGGED_CHANNEL
                                    for channel in range(bespok3d_rfid.CHANNEL_COUNT)]
    relay, filament_detect = _make_relay_on_printer(lanes_with_old_channel_empty)

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


def _deliver_printer_sets(relay, filament_detect):
    """filament_detect hands every set back to its listeners on a later reactor turn. One turn
    only: a set the relay makes in answer shows up in set_calls instead of looping the test."""
    for channel, info, is_clear in list(filament_detect.set_calls):
        relay._on_filament_update(channel, info, is_clear)


def test_read_through_on_a_lane_remembered_across_a_restart_keeps_its_spool_on_the_printer(
        tmp_path, monkeypatch):
    remembered_spool = _tagged_report("Anycubic")
    firmware_lane_vendors = {NEIGHBOUR_CHANNEL: "Anycubic", TAGGED_CHANNEL: "Bambu Lab"}
    firmware_vendors = [firmware_lane_vendors.get(channel, 'NONE')
                        for channel in range(bespok3d_rfid.CHANNEL_COUNT)]
    relay, rfid_data_file = _booted_relay(
        tmp_path, monkeypatch,
        {str(NEIGHBOUR_CHANNEL): remembered_spool, str(TAGGED_CHANNEL): _bambu_report()},
        firmware_vendors)
    filament_detect = FilamentDetectDoor()
    relay.printer.objects['filament_detect'] = filament_detect
    notified = []
    relay.register_spool_notify(
        lambda channel, info, is_clear: notified.append((channel, info, is_clear))
    )

    relay._on_filament_update(NEIGHBOUR_CHANNEL, _bambu_report(), is_clear=False)
    _deliver_printer_sets(relay, filament_detect)

    assert filament_detect.set_calls == [(NEIGHBOUR_CHANNEL, remembered_spool, False)]
    assert relay._filament_state[NEIGHBOUR_CHANNEL] == remembered_spool
    saved_lanes = json.loads(rfid_data_file.read_text())
    assert saved_lanes[str(NEIGHBOUR_CHANNEL)] == remembered_spool
    assert notified[-1] == (NEIGHBOUR_CHANNEL, remembered_spool, False)


# Older builds kept a read-through tag as the lane's own spool, so a lane can come back from a
# restart holding its neighbour's UID. Its spool goes back on the printer once, not on every echo.
def test_a_lane_restored_with_its_neighbours_tag_is_put_back_on_the_printer_once(
        tmp_path, monkeypatch):
    restored_read_through = _bambu_report()
    firmware_vendors = ["Bambu Lab"] * bespok3d_rfid.CHANNEL_COUNT
    relay, _ = _booted_relay(
        tmp_path, monkeypatch,
        {str(NEIGHBOUR_CHANNEL): restored_read_through, str(TAGGED_CHANNEL): _bambu_report()},
        firmware_vendors)
    filament_detect = FilamentDetectDoor()
    relay.printer.objects['filament_detect'] = filament_detect
    rewritten_neighbouring_tag = {**_bambu_report(), 'SPOOL_ID': 5}

    relay._on_filament_update(NEIGHBOUR_CHANNEL, rewritten_neighbouring_tag, is_clear=False)
    _deliver_printer_sets(relay, filament_detect)

    assert filament_detect.set_calls == [(NEIGHBOUR_CHANNEL, restored_read_through, False)]
    assert relay._filament_state[NEIGHBOUR_CHANNEL] == restored_read_through
