import importlib
import sys
import types
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
RFID_SUPPORT = PLUGIN_ROOT / "files" / "klipper" / "klippy" / "extras" / "rfid-support"
BASE_EXTRAS = PLUGIN_ROOT / "files" / "rfid-base" / "extras"
EXTRAS_STUB = "extras_stub"

sys.path.insert(0, str(RFID_SUPPORT / "chips"))
sys.path.insert(0, str(RFID_SUPPORT))

FILAMENT_INFO_STRUCT = {
    'VENDOR': 'NONE',
    'MANUFACTURER': 'NONE',
    'MAIN_TYPE': 'NONE',
    'SUB_TYPE': 'NONE',
    'ALPHA': 0xFF,
    'COLOR_NUMS': 1,
    'ARGB_COLOR': 0xFFFFFFFF,
    'RGB_1': 0xFFFFFF,
    'HOTEND_MIN_TEMP': 0,
    'HOTEND_MAX_TEMP': 0,
    'BED_TEMP': 0,
    'OFFICIAL': False,
    'CARD_UID': 0,
    'SPOOL_ID': 0,
}
FILAMENT_PROTO_OK = 0
FILAMENT_PROTO_ERR = 1
M1_UID_CARD_TYPE = 0x88

# NOTE: values below this line were added for ntag_reader test coverage. Both are confirmed
# against the real base file (Snapmaker/u1-klipper, klippy/extras/fm175xx_reader.py):
# FM175XX_OK = 0 and FM175XX_CARD_READ_ERR = -29, straight from that file's own "Error code"
# block, not assumed.
FM175XX_OK = 0
FM175XX_CARD_READ_ERR = -29


def _uid_only_struct(template, card_data):
    info = dict(template)
    info['CARD_UID'] = [int(byte) for byte in (card_data or [])]
    return info


def _firmware_stub_modules():
    """The Snapmaker firmware modules this plugin's extras import but this repo does not ship."""
    filament_protocol = types.ModuleType(f"{EXTRAS_STUB}.filament_protocol")
    filament_protocol.FILAMENT_INFO_STRUCT = FILAMENT_INFO_STRUCT
    filament_protocol.FILAMENT_PROTO_OK = FILAMENT_PROTO_OK
    filament_protocol.FILAMENT_PROTO_ERR = FILAMENT_PROTO_ERR

    mifare_classic = types.ModuleType(f"{EXTRAS_STUB}.mifare_classic")
    mifare_classic.M1_UID_CARD_TYPE = M1_UID_CARD_TYPE
    mifare_classic.uid_only_struct = _uid_only_struct

    fm175xx_reader = types.ModuleType(f"{EXTRAS_STUB}.fm175xx_reader")
    fm175xx_reader.FM175XX_OK = FM175XX_OK
    fm175xx_reader.FM175XX_CARD_READ_ERR = FM175XX_CARD_READ_ERR

    return [filament_protocol, mifare_classic, fm175xx_reader]


def _install_stub_package():
    """Mirror the printer: one package holding every extra this plugin places, plus the firmware's.

    On the printer each file lands in Klipper's klippy.extras package next to Snapmaker's own
    filament_protocol.py, so a `from . import` in the plugin's code resolves to a real sibling. Here
    one stub package spans this repo's source directories and supplies the firmware modules the repo
    does not ship, so a module under test imports exactly as it does on-device.
    """
    if EXTRAS_STUB in sys.modules:
        return
    package = types.ModuleType(EXTRAS_STUB)
    package.__path__ = [str(BASE_EXTRAS), str(RFID_SUPPORT), str(RFID_SUPPORT / "chips"),
                        str(RFID_SUPPORT / "tags")]
    sys.modules[EXTRAS_STUB] = package
    for stub in _firmware_stub_modules():
        sys.modules[stub.__name__] = stub


def load_printer_extra(module_name):
    """Import one of the extras this plugin places on the printer, as the printer imports it."""
    _install_stub_package()
    return importlib.import_module(f"{EXTRAS_STUB}.{module_name}")
