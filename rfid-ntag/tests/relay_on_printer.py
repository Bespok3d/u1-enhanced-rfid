"""Stand-ins for the printer objects the relay talks to, and a relay booted on them from a saved
lane file, shared by the relay's test modules."""
import json

from conftest import load_printer_extra

bespok3d_rfid = load_printer_extra("bespok3d_rfid")
saved_lanes_store = load_printer_extra("bespok3d_rfid_saved_lanes")

CHANNEL_COUNT = bespok3d_rfid.CHANNEL_COUNT
EMPTY_LANE = bespok3d_rfid.filament_protocol.FILAMENT_INFO_STRUCT
ALL_LANES_LOADED = [True] * CHANNEL_COUNT
ALL_LANES_EMPTY = [False] * CHANNEL_COUNT
NO_FIRMWARE_RECORD: dict = {}

# A lane whose own spool has no tag can pick up the tag of the spool next to it: the same hardware
# UID then reaches two channels. The tag belongs to the channel that already holds it.
TAGGED_CHANNEL = 3
NEIGHBOUR_CHANNEL = 2
NEIGHBOURING_TAG_UID = [0x04, 0xA1, 0xB2, 0xC3]


class FakeReactor:
    def __init__(self):
        self.deferred_callbacks = []

    def register_callback(self, callback):
        self.deferred_callbacks.append(callback)

    def monotonic(self):
        return 0.0

    def run_deferred(self):
        for callback in self.deferred_callbacks:
            callback(0.0)


class FakeTaskConfig:
    """Stands in for print_task_config: lane presence and the firmware's own record of each lane."""

    def __init__(self, filament_exist, firmware_record=NO_FIRMWARE_RECORD):
        self.filament_exist = filament_exist
        self.firmware_record = firmware_record

    def get_status(self, eventtime=None):
        return {'filament_exist': list(self.filament_exist), **self.firmware_record}


class FakePrinter:
    def __init__(self, task_config, filament_detect=None):
        self.reactor = FakeReactor()
        self.objects = {'print_task_config': task_config, 'filament_detect': filament_detect}

    def get_reactor(self):
        return self.reactor

    def lookup_object(self, name, default=None):
        return self.objects.get(name, default)

    def register_event_handler(self, event, handler):
        pass


class FakeConfig:
    def __init__(self, printer):
        self.printer = printer

    def get_printer(self):
        return self.printer


class FilamentDetectDoor:
    """Stands in for u1-base's filament_detect, recording what the relay sets on each channel."""

    def __init__(self):
        self.set_calls = []

    def set_filament_info(self, channel, info, is_clear=False):
        self.set_calls.append((channel, info, is_clear))
        return True


def bambu_report(card_uid=None):
    return {'VENDOR': 'Bambu Lab', 'MAIN_TYPE': 'PLA', 'SUB_TYPE': 'Basic',
            'ARGB_COLOR': 0xFF00AE42, 'SKU': 10100, 'OFFICIAL': True, 'SPOOL_ID': 0,
            'CARD_UID': card_uid or NEIGHBOURING_TAG_UID}


def firmware_record_of_vendors(firmware_vendors):
    return {'filament_vendor': list(firmware_vendors)}


def firmware_record_showing(lane_spools):
    """The firmware's record with each lane's spool copied in, field by field, as its own filament
    update callback copies every read it takes; a lane with no spool shows the empty one."""
    lane_infos = [lane_spools.get(channel, EMPTY_LANE) for channel in range(CHANNEL_COUNT)]
    return {status_key: [lane_info.get(field) for lane_info in lane_infos]
            for field, status_key in bespok3d_rfid.FIRMWARE_RECORD_FIELDS.items()}


def save_lanes_as_an_older_version(tmp_path, saved_lanes):
    rfid_data_file = tmp_path / "rfid_data.json"
    rfid_data_file.write_text(json.dumps(saved_lanes))
    return rfid_data_file


def fingerprint_file(rfid_data_file):
    return rfid_data_file.with_name(
        rfid_data_file.name + saved_lanes_store.RFID_DATA_FINGERPRINT_SUFFIX)


def unproven_lanes_file(rfid_data_file):
    return rfid_data_file.with_name(rfid_data_file.name + saved_lanes_store.UNPROVEN_LANES_SUFFIX)


def save_lanes_as_this_version(tmp_path, saved_lanes):
    rfid_data_file = save_lanes_as_an_older_version(tmp_path, saved_lanes)
    saved_text = rfid_data_file.read_text()
    fingerprint_file(rfid_data_file).write_text(saved_lanes_store.text_fingerprint(saved_text))
    return rfid_data_file


def relay_loaded_from_config(rfid_data_file, monkeypatch, firmware_record,
                             filament_exist=ALL_LANES_LOADED, filament_detect=None):
    monkeypatch.setattr(saved_lanes_store, "RFID_DATA_FILE", str(rfid_data_file))
    printer = FakePrinter(FakeTaskConfig(filament_exist, firmware_record), filament_detect)
    return bespok3d_rfid.Bespok3dRfid(FakeConfig(printer))


def relay_booted_on(rfid_data_file, monkeypatch, firmware_record,
                    filament_exist=ALL_LANES_LOADED, filament_detect=None):
    relay = relay_loaded_from_config(
        rfid_data_file, monkeypatch, firmware_record, filament_exist, filament_detect)
    relay._restore_remembered_lanes()
    relay.printer.reactor.run_deferred()
    return relay, rfid_data_file


def booted_relay(tmp_path, monkeypatch, saved_lanes, firmware_record,
                 filament_exist=ALL_LANES_LOADED):
    rfid_data_file = save_lanes_as_this_version(tmp_path, saved_lanes)
    return relay_booted_on(rfid_data_file, monkeypatch, firmware_record, filament_exist)
