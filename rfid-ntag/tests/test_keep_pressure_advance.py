"""Regression tests for keeping a lane's tuned pressure advance across a filament change.

Stock Klipper throws the pressure advance away every time it is told what filament a lane holds:
loading, unloading, swapping, reading a tag and picking a filament by hand all end in a
`FLOW_RESET_K`, mid print included, so a tuned lane comes out untuned. Holding that back is the
base layer's job now, not this plugin's: `u1-base-print-task-config` owns the change to Snapmaker's
file and offers `suppress_pressure_advance_reset(owner)`, and this plugin registers itself as an
owner at startup. These tests hold that registration, hold that a printer without the base layer
still starts, and hold that no patch of Snapmaker's own code is left in this package.
"""
import json
from pathlib import Path

from conftest import load_printer_extra

bespok3d_rfid = load_printer_extra("bespok3d_rfid")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
REQUIRED_BASE_SERVICES = [
    "u1-base-print-task-config",
    "u1-base-fm175xx-reader",
    "u1-base-filament-detect",
]


class FakePrintTaskConfig:
    """The base layer's door, which counts registered owners rather than flipping a flag."""

    def __init__(self):
        self.pressure_advance_held_by = set()

    def suppress_pressure_advance_reset(self, owner):
        self.pressure_advance_held_by.add(owner)

    def resume_pressure_advance_reset(self, owner):
        self.pressure_advance_held_by.discard(owner)


class UnpatchedPrintTaskConfig:
    """Snapmaker's own object with no base layer applied: present, but offering no door."""


class FakeFilamentDetect:
    def __init__(self):
        self.filament_update_cbs = []
        self.protocol_parsers = {}

    def register_cb_2_update_filament_info(self, callback):
        self.filament_update_cbs.append(callback)

    def register_card_protocol_parser(self, card_type, parser):
        self.protocol_parsers[card_type] = parser


class FakePrinter:
    def __init__(self, klipper_objects):
        self._klipper_objects = klipper_objects
        self.ready_handlers = []

    def lookup_object(self, name, default=None):
        return self._klipper_objects.get(name, default)

    def register_event_handler(self, event, handler):
        self.ready_handlers.append((event, handler))


class FakeConfig:
    def __init__(self, printer):
        self._printer = printer

    def get_printer(self):
        return self._printer


def start_plugin(klipper_objects):
    """Build the plugin the way Klipper does, then fire klippy:ready."""
    printer = FakePrinter(klipper_objects)
    bespok3d_rfid.Bespok3dRfid(FakeConfig(printer))
    for event, handler in printer.ready_handlers:
        assert event == "klippy:ready"
        handler()
    return printer


def manifest():
    return json.loads((PLUGIN_DIR / "manifest.json").read_text())


def test_the_lane_keeps_its_pressure_advance_because_this_plugin_registers_for_it():
    task_config = FakePrintTaskConfig()
    start_plugin({'print_task_config': task_config, 'filament_detect': FakeFilamentDetect()})

    assert task_config.pressure_advance_held_by == {bespok3d_rfid.PRESSURE_ADVANCE_OWNER}


def test_the_owner_name_is_this_plugin_so_a_second_plugin_can_hold_the_same_door():
    assert bespok3d_rfid.PRESSURE_ADVANCE_OWNER == "rfid-ntag"


def test_a_printer_without_the_base_layer_still_starts_and_reads_tags(caplog):
    """The old behaviour, stated: with no door to register at, startup carries on unchanged and the
    rest of the RFID pipeline still comes up. This is required behaviour for the release where a
    printer may have this plugin updated before the base layer is installed."""
    detector = FakeFilamentDetect()
    with caplog.at_level("WARNING", logger="bespok3d"):
        start_plugin({'filament_detect': detector})

    assert detector.filament_update_cbs != []
    assert len([record for record in caplog.records
                if "pressure advance hold absent" in record.getMessage()]) == 1


def test_a_base_layer_too_old_to_offer_the_door_is_treated_as_no_door(caplog):
    task_config = UnpatchedPrintTaskConfig()
    with caplog.at_level("WARNING", logger="bespok3d"):
        start_plugin({'print_task_config': task_config,
                      'filament_detect': FakeFilamentDetect()})

    assert not hasattr(task_config, 'pressure_advance_held_by')
    assert len([record for record in caplog.records
                if "pressure advance hold absent" in record.getMessage()]) == 1


def test_this_plugin_changes_none_of_snapmakers_own_files():
    """R-MOVE-1. An instrument entry is what patches Snapmaker's code, and a conflict_resolution is
    what swapped one of those patches for a firmware generation. Both belong to the base layer
    now."""
    install = manifest()["install"]

    assert "instrument" not in install
    assert manifest()["conflict_resolutions"] == []
    assert "klipper-source" not in manifest()["permissions"]
    assert list(PLUGIN_DIR.glob("files/**/*.patch")) == []


def test_the_base_layer_plugins_are_required_and_carry_no_version_floor():
    """R-MOVE-4. Both plugins that used to patch print_task_config.py ride one base release, so a
    require names the service and nothing else: a floor would pin them to separate releases."""
    required = manifest()["require"]

    assert [entry["service"] for entry in required] == REQUIRED_BASE_SERVICES
    assert all(set(entry) == {"service", "cardinality"} for entry in required)
