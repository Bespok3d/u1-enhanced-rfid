"""Regression tests for the saved lane file across versions. Builds up to 0.1.17 saved a tag
picked up from the neighbouring spool as the lane's own, and the printer took it too: the lane
whose reader really sees the tag must end up with the spool, and a claim no read can prove is
dropped."""
import json

from relay_on_printer import (
    CHANNEL_COUNT,
    EMPTY_LANE,
    NEIGHBOUR_CHANNEL,
    NO_FIRMWARE_RECORD,
    TAGGED_CHANNEL,
    FilamentDetectDoor,
    bambu_report,
    booted_relay,
    fingerprint_file,
    firmware_record_showing,
    relay_booted_on,
    relay_loaded_from_config,
    save_lanes_as_an_older_version,
    save_lanes_as_this_version,
    saved_lanes_store,
    unproven_lanes_file,
)

OTHER_TAG_UID = [0x04, 0xD4, 0xE5, 0xF6]
BOTH_LANES_WITH_ONE_TAG = {str(NEIGHBOUR_CHANNEL): bambu_report(),
                           str(TAGGED_CHANNEL): bambu_report()}
BOTH_LANES_CLEARED = [(NEIGHBOUR_CHANNEL, EMPTY_LANE, True), (TAGGED_CHANNEL, EMPTY_LANE, True)]


def _record_showing_one_tag_on_both_lanes():
    return firmware_record_showing({NEIGHBOUR_CHANNEL: bambu_report(),
                                    TAGGED_CHANNEL: bambu_report()})


def _vendors_in(rfid_data_file):
    return [lane['VENDOR'] for lane in json.loads(rfid_data_file.read_text()).values()]


def test_lanes_saved_by_an_older_version_with_a_neighbours_tag_are_all_forgotten(
        tmp_path, monkeypatch):
    rfid_data_file = save_lanes_as_an_older_version(tmp_path, BOTH_LANES_WITH_ONE_TAG)

    relay, _ = relay_booted_on(
        rfid_data_file, monkeypatch, _record_showing_one_tag_on_both_lanes())

    assert relay._filament_state == [None] * CHANNEL_COUNT
    assert _vendors_in(rfid_data_file) == ['NONE'] * CHANNEL_COUNT


def test_a_neighbours_tag_saved_by_an_older_version_goes_to_the_lane_that_reads_it(
        tmp_path, monkeypatch):
    rfid_data_file = save_lanes_as_an_older_version(
        tmp_path, {str(NEIGHBOUR_CHANNEL): bambu_report()})
    filament_detect = FilamentDetectDoor()
    relay, _ = relay_booted_on(
        rfid_data_file, monkeypatch, firmware_record_showing({NEIGHBOUR_CHANNEL: bambu_report()}),
        filament_detect=filament_detect)

    relay._on_filament_update(TAGGED_CHANNEL, bambu_report(), is_clear=False)

    assert relay._filament_state[TAGGED_CHANNEL] == bambu_report()
    assert relay._filament_state[NEIGHBOUR_CHANNEL] is None
    assert filament_detect.set_calls == []


def test_lanes_this_version_saved_are_remembered_at_the_next_restart(tmp_path, monkeypatch):
    rfid_data_file = tmp_path / "rfid_data.json"
    firmware_record = firmware_record_showing({TAGGED_CHANNEL: bambu_report()})
    first_boot, _ = relay_booted_on(rfid_data_file, monkeypatch, firmware_record)
    first_boot._on_filament_update(TAGGED_CHANNEL, bambu_report(), is_clear=False)

    next_boot, _ = relay_booted_on(rfid_data_file, monkeypatch, firmware_record)

    assert next_boot._filament_state[TAGGED_CHANNEL] == bambu_report()


def test_lanes_rewritten_by_an_older_version_after_this_one_saved_them_are_forgotten(
        tmp_path, monkeypatch):
    spool_the_older_version_saw = bambu_report(OTHER_TAG_UID)
    rfid_data_file = save_lanes_as_this_version(tmp_path, {str(TAGGED_CHANNEL): bambu_report()})
    rfid_data_file.write_text(json.dumps({str(TAGGED_CHANNEL): spool_the_older_version_saw}))

    relay, _ = relay_booted_on(
        rfid_data_file, monkeypatch,
        firmware_record_showing({TAGGED_CHANNEL: spool_the_older_version_saw}))

    assert relay._filament_state[TAGGED_CHANNEL] is None


# The printer took the neighbour's tag too under those builds, so it can still show one spool on
# two lanes. Neither can be proven, so both are cleared there until a tag is read again.
def test_lanes_an_older_version_saved_with_one_tag_are_cleared_on_the_printer(
        tmp_path, monkeypatch):
    lane_with_its_own_tag = bambu_report(OTHER_TAG_UID)
    rfid_data_file = save_lanes_as_an_older_version(
        tmp_path, {"0": lane_with_its_own_tag, **BOTH_LANES_WITH_ONE_TAG})
    firmware_record = firmware_record_showing(
        {0: lane_with_its_own_tag, NEIGHBOUR_CHANNEL: bambu_report(),
         TAGGED_CHANNEL: bambu_report()})
    filament_detect = FilamentDetectDoor()

    relay_booted_on(rfid_data_file, monkeypatch, firmware_record, filament_detect=filament_detect)

    assert filament_detect.set_calls == BOTH_LANES_CLEARED
    assert not unproven_lanes_file(rfid_data_file).exists()


class _DoorEchoingToTheRelay(FilamentDetectDoor):
    """Like u1-base's filament_detect, sends every change it is told back to its listeners."""

    def __init__(self):
        super().__init__()
        self.relay = None

    def set_filament_info(self, channel, info, is_clear=False):
        super().set_filament_info(channel, info, is_clear)
        self.relay._on_filament_update(channel, info, is_clear)
        return True


# Spoolman learns of each cleared lane through the clear coming back from the printer.
def test_lanes_cleared_on_the_printer_are_cleared_for_every_listener_too(tmp_path, monkeypatch):
    rfid_data_file = save_lanes_as_an_older_version(tmp_path, BOTH_LANES_WITH_ONE_TAG)
    filament_detect = _DoorEchoingToTheRelay()
    relay = relay_loaded_from_config(rfid_data_file, monkeypatch,
                                     _record_showing_one_tag_on_both_lanes(),
                                     filament_detect=filament_detect)
    filament_detect.relay = relay
    spool_notifications = []
    relay.register_spool_notify(
        lambda channel, info, is_clear: spool_notifications.append((channel, info, is_clear)))

    relay._restore_remembered_lanes()
    relay.printer.reactor.run_deferred()

    assert spool_notifications == [(NEIGHBOUR_CHANNEL, None, True), (TAGGED_CHANNEL, None, True)]
    assert _vendors_in(rfid_data_file) == [EMPTY_LANE['VENDOR']] * CHANNEL_COUNT


def test_lanes_this_version_saved_are_never_cleared_on_the_printer_at_restart(
        tmp_path, monkeypatch):
    rfid_data_file = save_lanes_as_this_version(tmp_path, BOTH_LANES_WITH_ONE_TAG)
    filament_detect = FilamentDetectDoor()

    relay_booted_on(rfid_data_file, monkeypatch, _record_showing_one_tag_on_both_lanes(),
                    filament_detect=filament_detect)

    assert filament_detect.set_calls == []


# The spool on the other lane may be the one taken away since, so the lane left is no proof.
def test_a_shared_tag_still_shown_on_one_of_its_lanes_is_cleared_there(tmp_path, monkeypatch):
    rfid_data_file = save_lanes_as_an_older_version(tmp_path, BOTH_LANES_WITH_ONE_TAG)
    filament_detect = FilamentDetectDoor()

    relay_booted_on(rfid_data_file, monkeypatch,
                    firmware_record_showing({NEIGHBOUR_CHANNEL: bambu_report()}),
                    filament_detect=filament_detect)

    assert filament_detect.set_calls == [(NEIGHBOUR_CHANNEL, EMPTY_LANE, True)]


def test_a_shared_tag_on_lanes_the_printer_no_longer_shows_clears_nothing(tmp_path, monkeypatch):
    rfid_data_file = save_lanes_as_an_older_version(tmp_path, BOTH_LANES_WITH_ONE_TAG)
    filament_detect = FilamentDetectDoor()

    relay_booted_on(rfid_data_file, monkeypatch, firmware_record_showing({}),
                    filament_detect=filament_detect)

    assert filament_detect.set_calls == []


# The firmware only takes a new read over an identified spool when its article number changes, so
# a lane showing the same vendor with another article number holds a spool read since then.
def test_a_shared_tag_on_lanes_the_printer_shows_with_another_spool_clears_nothing(
        tmp_path, monkeypatch):
    rfid_data_file = save_lanes_as_an_older_version(tmp_path, BOTH_LANES_WITH_ONE_TAG)
    spool_read_since = {**bambu_report(), 'SKU': 10200}
    filament_detect = FilamentDetectDoor()

    relay_booted_on(rfid_data_file, monkeypatch,
                    firmware_record_showing({NEIGHBOUR_CHANNEL: spool_read_since,
                                             TAGGED_CHANNEL: spool_read_since}),
                    filament_detect=filament_detect)

    assert filament_detect.set_calls == []


def test_a_shared_tag_with_no_firmware_record_clears_nothing(tmp_path, monkeypatch):
    rfid_data_file = save_lanes_as_an_older_version(tmp_path, BOTH_LANES_WITH_ONE_TAG)
    filament_detect = FilamentDetectDoor()

    relay_booted_on(rfid_data_file, monkeypatch, NO_FIRMWARE_RECORD,
                    filament_detect=filament_detect)

    assert filament_detect.set_calls == []


def test_a_shared_tag_is_cleared_at_the_next_restart_after_one_with_no_firmware_record(
        tmp_path, monkeypatch):
    rfid_data_file = save_lanes_as_an_older_version(tmp_path, BOTH_LANES_WITH_ONE_TAG)
    relay_booted_on(rfid_data_file, monkeypatch, NO_FIRMWARE_RECORD)
    filament_detect = FilamentDetectDoor()

    relay_booted_on(rfid_data_file, monkeypatch, _record_showing_one_tag_on_both_lanes(),
                    filament_detect=filament_detect)

    assert filament_detect.set_calls == BOTH_LANES_CLEARED


def test_a_shared_tag_is_cleared_once_after_a_restart_that_never_got_ready(
        tmp_path, monkeypatch):
    rfid_data_file = save_lanes_as_an_older_version(tmp_path, BOTH_LANES_WITH_ONE_TAG)
    relay_loaded_from_config(rfid_data_file, monkeypatch, NO_FIRMWARE_RECORD)
    first_ready_clears = FilamentDetectDoor()
    relay_booted_on(rfid_data_file, monkeypatch, _record_showing_one_tag_on_both_lanes(),
                    filament_detect=first_ready_clears)
    next_ready_clears = FilamentDetectDoor()

    relay_booted_on(rfid_data_file, monkeypatch, _record_showing_one_tag_on_both_lanes(),
                    filament_detect=next_ready_clears)

    assert first_ready_clears.set_calls == BOTH_LANES_CLEARED
    assert next_ready_clears.set_calls == []


def test_a_save_that_fails_keeps_the_lanes_saved_before_it(tmp_path, monkeypatch):
    firmware_record = firmware_record_showing({TAGGED_CHANNEL: bambu_report()})
    relay, rfid_data_file = booted_relay(
        tmp_path, monkeypatch, {str(TAGGED_CHANNEL): bambu_report()}, firmware_record)
    relay._filament_state[TAGGED_CHANNEL] = bambu_report(card_uid=b"\x04\xa1")
    relay._write_rfid_data()

    rebooted_relay, _ = relay_booted_on(rfid_data_file, monkeypatch, firmware_record)

    assert rebooted_relay._filament_state[TAGGED_CHANNEL] == bambu_report()


def _open_with_a_full_disk(file_path, mode='r', **open_options):
    if 'w' in mode:
        raise OSError("no space left on device")
    return open(file_path, mode, **open_options)


def test_a_save_the_disk_refuses_keeps_the_lanes_saved_before_it(tmp_path, monkeypatch):
    firmware_record = firmware_record_showing({TAGGED_CHANNEL: bambu_report()})
    relay, rfid_data_file = booted_relay(
        tmp_path, monkeypatch, {str(TAGGED_CHANNEL): bambu_report()}, firmware_record)
    monkeypatch.setattr(saved_lanes_store, "open", _open_with_a_full_disk, raising=False)
    relay._on_filament_update(TAGGED_CHANNEL, bambu_report(OTHER_TAG_UID), is_clear=False)
    monkeypatch.delattr(saved_lanes_store, "open")

    rebooted_relay, _ = relay_booted_on(rfid_data_file, monkeypatch, firmware_record)

    assert rebooted_relay._filament_state[TAGGED_CHANNEL] == bambu_report()


def test_a_shared_tag_the_printer_could_not_clear_is_cleared_at_the_next_restart(
        tmp_path, monkeypatch):
    rfid_data_file = save_lanes_as_an_older_version(tmp_path, BOTH_LANES_WITH_ONE_TAG)
    relay_booted_on(rfid_data_file, monkeypatch, _record_showing_one_tag_on_both_lanes())
    filament_detect = FilamentDetectDoor()

    relay_booted_on(rfid_data_file, monkeypatch, _record_showing_one_tag_on_both_lanes(),
                    filament_detect=filament_detect)

    assert filament_detect.set_calls == BOTH_LANES_CLEARED


def test_lanes_an_older_version_saved_with_one_unidentified_tag_are_not_cleared_on_the_printer(
        tmp_path, monkeypatch):
    unidentified_report = {**bambu_report(), 'VENDOR': 'NONE', 'OFFICIAL': False}
    rfid_data_file = save_lanes_as_an_older_version(
        tmp_path, {str(NEIGHBOUR_CHANNEL): unidentified_report,
                   str(TAGGED_CHANNEL): unidentified_report})
    filament_detect = FilamentDetectDoor()

    relay_booted_on(rfid_data_file, monkeypatch,
                    firmware_record_showing({NEIGHBOUR_CHANNEL: unidentified_report,
                                             TAGGED_CHANNEL: unidentified_report}),
                    filament_detect=filament_detect)

    assert filament_detect.set_calls == []
    assert not unproven_lanes_file(rfid_data_file).exists()


# The spoolman plugin restores tags from this file in its own ready handler, which can run first.
def test_lanes_an_older_version_saved_are_forgotten_in_the_file_before_any_plugin_starts(
        tmp_path, monkeypatch):
    rfid_data_file = save_lanes_as_an_older_version(tmp_path, BOTH_LANES_WITH_ONE_TAG)

    relay_loaded_from_config(rfid_data_file, monkeypatch, _record_showing_one_tag_on_both_lanes())

    assert _vendors_in(rfid_data_file) == ['NONE'] * CHANNEL_COUNT
    assert fingerprint_file(rfid_data_file).read_text() == \
        saved_lanes_store.text_fingerprint(rfid_data_file.read_text())
    assert json.loads(unproven_lanes_file(rfid_data_file).read_text()) == BOTH_LANES_WITH_ONE_TAG


def test_lanes_this_version_saved_are_left_in_the_file_while_the_config_loads(
        tmp_path, monkeypatch):
    rfid_data_file = save_lanes_as_this_version(tmp_path, {str(TAGGED_CHANNEL): bambu_report()})
    saved_text = rfid_data_file.read_text()

    relay_loaded_from_config(
        rfid_data_file, monkeypatch, firmware_record_showing({TAGGED_CHANNEL: bambu_report()}))

    assert rfid_data_file.read_text() == saved_text


def test_an_unreadable_lane_file_is_replaced_with_empty_lanes_while_the_config_loads(
        tmp_path, monkeypatch):
    rfid_data_file = tmp_path / "rfid_data.json"
    rfid_data_file.write_bytes(b"\xff\xfe not text")

    relay_loaded_from_config(rfid_data_file, monkeypatch, NO_FIRMWARE_RECORD)

    assert _vendors_in(rfid_data_file) == ['NONE'] * CHANNEL_COUNT
    assert fingerprint_file(rfid_data_file).read_text() == \
        saved_lanes_store.text_fingerprint(rfid_data_file.read_text())

