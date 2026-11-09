"""Regression tests for the shared RFID relay: what each lane keeps when a read, a clear or a
restart reaches it. The relay's report handler is driven directly, with the printer objects it
talks to stood in by relay_on_printer.
"""
import json

from relay_on_printer import (
    ALL_LANES_EMPTY,
    ALL_LANES_LOADED,
    CHANNEL_COUNT,
    NEIGHBOUR_CHANNEL,
    NEIGHBOURING_TAG_UID,
    NO_FIRMWARE_RECORD,
    TAGGED_CHANNEL,
    FakePrinter,
    FakeTaskConfig,
    FilamentDetectDoor,
    bambu_report,
    bespok3d_rfid,
    booted_relay,
    firmware_record_of_vendors,
    relay_booted_on,
)


def _make_relay():
    relay = object.__new__(bespok3d_rfid.Bespok3dRfid)
    relay._filament_state = [None] * CHANNEL_COUNT
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
    relay.printer = FakePrinter(FakeTaskConfig(lanes_with_channel_empty))
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


def _firmware_record_with_vendor(channel_vendor):
    return firmware_record_of_vendors([channel_vendor if channel == CHANNEL else 'NONE'
                                       for channel in range(CHANNEL_COUNT)])


def test_failed_factory_read_after_reboot_keeps_the_remembered_spool(tmp_path, monkeypatch):
    relay, rfid_data_file = booted_relay(
        tmp_path, monkeypatch, {str(CHANNEL): _tagged_report("Anycubic")},
        _firmware_record_with_vendor("Anycubic"))
    notified = []
    relay.register_spool_notify(
        lambda channel, info, is_clear: notified.append((channel, info, is_clear))
    )

    relay._on_filament_update(CHANNEL, _uid_only_report(), is_clear=False)

    assert notified == [(CHANNEL, _tagged_report("Anycubic"), False)]
    saved_lanes = json.loads(rfid_data_file.read_text())
    assert saved_lanes[str(CHANNEL)] == _tagged_report("Anycubic")


def test_lane_the_firmware_forgot_at_boot_forgets_the_remembered_spool(tmp_path, monkeypatch):
    relay, rfid_data_file = booted_relay(
        tmp_path, monkeypatch, {str(CHANNEL): _tagged_report("Anycubic")},
        _firmware_record_with_vendor("NONE"))

    assert relay._filament_state[CHANNEL] is None
    saved_lanes = json.loads(rfid_data_file.read_text())
    assert saved_lanes[str(CHANNEL)]['VENDOR'] == 'NONE'


def test_unsettled_sensor_at_boot_keeps_the_spool_the_firmware_kept(tmp_path, monkeypatch):
    relay, rfid_data_file = booted_relay(
        tmp_path, monkeypatch, {str(CHANNEL): _tagged_report("Anycubic")},
        _firmware_record_with_vendor("Anycubic"), filament_exist=ALL_LANES_EMPTY)

    assert relay._filament_state[CHANNEL] == _tagged_report("Anycubic")
    saved_lanes = json.loads(rfid_data_file.read_text())
    assert saved_lanes[str(CHANNEL)] == _tagged_report("Anycubic")


def test_new_tag_after_reboot_replaces_the_remembered_spool(tmp_path, monkeypatch):
    relay, rfid_data_file = booted_relay(
        tmp_path, monkeypatch, {str(CHANNEL): _tagged_report("Anycubic")},
        _firmware_record_with_vendor("Anycubic"))

    relay._on_filament_update(CHANNEL, _tagged_report("Qidi"), is_clear=False)

    saved_lanes = json.loads(rfid_data_file.read_text())
    assert saved_lanes[str(CHANNEL)] == _tagged_report("Qidi")


def test_unknown_firmware_record_at_boot_keeps_every_remembered_spool(tmp_path, monkeypatch):
    relay, rfid_data_file = booted_relay(
        tmp_path, monkeypatch, {str(CHANNEL): _tagged_report("Anycubic")}, NO_FIRMWARE_RECORD)

    assert relay._filament_state[CHANNEL] == _tagged_report("Anycubic")


def test_missing_rfid_data_file_boots_with_no_remembered_spool(tmp_path, monkeypatch):
    relay, _ = relay_booted_on(tmp_path / "absent.json", monkeypatch, NO_FIRMWARE_RECORD)

    assert relay._filament_state == [None] * CHANNEL_COUNT


def test_clear_while_the_spool_is_still_loaded_keeps_the_spool():
    relay = _make_relay()
    relay.printer = FakePrinter(FakeTaskConfig(ALL_LANES_LOADED))
    notified = []
    relay.register_spool_notify(
        lambda channel, info, is_clear: notified.append((channel, info, is_clear))
    )

    relay._on_filament_update(CHANNEL, _tagged_report("Anycubic"), is_clear=False)
    relay._on_filament_update(CHANNEL, None, is_clear=True)

    assert relay._filament_state[CHANNEL]['VENDOR'] == "Anycubic"
    assert notified[-1] == (CHANNEL, _tagged_report("Anycubic"), False)


def test_clear_while_loaded_after_boot_restore_keeps_the_file(tmp_path, monkeypatch):
    relay, rfid_data_file = booted_relay(
        tmp_path, monkeypatch, {str(CHANNEL): _tagged_report("Anycubic")},
        _firmware_record_with_vendor("Anycubic"))

    relay._on_filament_update(CHANNEL, None, is_clear=True)

    saved_lanes = json.loads(rfid_data_file.read_text())
    assert saved_lanes[str(CHANNEL)]['VENDOR'] == "Anycubic"


def _make_relay_on_printer(filament_exist=ALL_LANES_LOADED):
    relay = _make_relay()
    filament_detect = FilamentDetectDoor()
    relay.printer = FakePrinter(FakeTaskConfig(filament_exist), filament_detect)
    return relay, filament_detect


def test_tag_already_held_by_another_channel_is_dropped_and_cleared_on_the_printer():
    relay, filament_detect = _make_relay_on_printer()
    notified = []
    relay.register_spool_notify(
        lambda channel, info, is_clear: notified.append((channel, info, is_clear))
    )

    relay._on_filament_update(TAGGED_CHANNEL, bambu_report(), is_clear=False)
    relay._on_filament_update(NEIGHBOUR_CHANNEL, bambu_report(), is_clear=False)

    assert relay._filament_state[TAGGED_CHANNEL] == bambu_report()
    assert relay._filament_state[NEIGHBOUR_CHANNEL] is None
    assert notified == [(TAGGED_CHANNEL, bambu_report(), False)]
    assert filament_detect.set_calls == [
        (NEIGHBOUR_CHANNEL, bespok3d_rfid.filament_protocol.FILAMENT_INFO_STRUCT, True)
    ]


def test_uid_only_report_of_a_tag_another_channel_holds_is_dropped():
    relay, filament_detect = _make_relay_on_printer()

    relay._on_filament_update(TAGGED_CHANNEL, bambu_report(), is_clear=False)
    relay._on_filament_update(
        NEIGHBOUR_CHANNEL, _uid_only_report(NEIGHBOURING_TAG_UID), is_clear=False)

    assert relay._filament_state[NEIGHBOUR_CHANNEL] is None
    assert [channel for channel, _, _ in filament_detect.set_calls] == [NEIGHBOUR_CHANNEL]


def test_rereading_the_same_channel_keeps_its_own_tag():
    relay, filament_detect = _make_relay_on_printer()

    relay._on_filament_update(TAGGED_CHANNEL, bambu_report(), is_clear=False)
    relay._on_filament_update(TAGGED_CHANNEL, bambu_report(), is_clear=False)

    assert relay._filament_state[TAGGED_CHANNEL] == bambu_report()
    assert filament_detect.set_calls == []


def test_spool_moved_after_its_old_channel_was_cleared_is_read_on_the_new_one():
    lanes_with_old_channel_empty = [channel != TAGGED_CHANNEL
                                    for channel in range(CHANNEL_COUNT)]
    relay, filament_detect = _make_relay_on_printer(lanes_with_old_channel_empty)

    relay._on_filament_update(TAGGED_CHANNEL, bambu_report(), is_clear=False)
    relay._on_filament_update(TAGGED_CHANNEL, None, is_clear=True)
    relay._on_filament_update(NEIGHBOUR_CHANNEL, bambu_report(), is_clear=False)

    assert relay._filament_state[NEIGHBOUR_CHANNEL] == bambu_report()
    assert filament_detect.set_calls == []


def test_different_tags_on_neighbouring_channels_are_both_kept():
    relay, filament_detect = _make_relay_on_printer()
    other_tag_uid = [0x04, 0xD4, 0xE5, 0xF6]

    relay._on_filament_update(TAGGED_CHANNEL, bambu_report(), is_clear=False)
    relay._on_filament_update(NEIGHBOUR_CHANNEL, bambu_report(other_tag_uid), is_clear=False)

    assert relay._filament_state[NEIGHBOUR_CHANNEL] == bambu_report(other_tag_uid)
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
                        for channel in range(CHANNEL_COUNT)]
    relay, rfid_data_file = booted_relay(
        tmp_path, monkeypatch,
        {str(NEIGHBOUR_CHANNEL): remembered_spool, str(TAGGED_CHANNEL): bambu_report()},
        firmware_record_of_vendors(firmware_vendors))
    filament_detect = FilamentDetectDoor()
    relay.printer.objects['filament_detect'] = filament_detect
    notified = []
    relay.register_spool_notify(
        lambda channel, info, is_clear: notified.append((channel, info, is_clear))
    )

    relay._on_filament_update(NEIGHBOUR_CHANNEL, bambu_report(), is_clear=False)
    _deliver_printer_sets(relay, filament_detect)

    assert filament_detect.set_calls == [(NEIGHBOUR_CHANNEL, remembered_spool, False)]
    assert relay._filament_state[NEIGHBOUR_CHANNEL] == remembered_spool
    saved_lanes = json.loads(rfid_data_file.read_text())
    assert saved_lanes[str(NEIGHBOUR_CHANNEL)] == remembered_spool
    assert notified[-1] == (NEIGHBOUR_CHANNEL, remembered_spool, False)


# Should a lane come back from a restart holding its neighbour's UID, its spool goes back on the
# printer once, not on every echo.
def test_a_lane_restored_with_its_neighbours_tag_is_put_back_on_the_printer_once(
        tmp_path, monkeypatch):
    restored_read_through = bambu_report()
    firmware_vendors = ["Bambu Lab"] * CHANNEL_COUNT
    relay, _ = booted_relay(
        tmp_path, monkeypatch,
        {str(NEIGHBOUR_CHANNEL): restored_read_through, str(TAGGED_CHANNEL): bambu_report()},
        firmware_record_of_vendors(firmware_vendors))
    filament_detect = FilamentDetectDoor()
    relay.printer.objects['filament_detect'] = filament_detect
    rewritten_neighbouring_tag = {**bambu_report(), 'SPOOL_ID': 5}

    relay._on_filament_update(NEIGHBOUR_CHANNEL, rewritten_neighbouring_tag, is_clear=False)
    _deliver_printer_sets(relay, filament_detect)

    assert filament_detect.set_calls == [(NEIGHBOUR_CHANNEL, restored_read_through, False)]
    assert relay._filament_state[NEIGHBOUR_CHANNEL] == restored_read_through

