import sys
from pathlib import Path

RFID_SUPPORT = (
    Path(__file__).resolve().parent.parent
    / "files" / "klipper" / "klippy" / "extras" / "rfid-support"
)
sys.path.insert(0, str(RFID_SUPPORT / "chips"))
sys.path.insert(0, str(RFID_SUPPORT))
