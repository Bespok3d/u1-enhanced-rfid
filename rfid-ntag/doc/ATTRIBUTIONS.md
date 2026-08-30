# Attributions - rfid-ntag

**Plugin author:** Bespok3d, with parts of the Extended Firmware overlay `13-patch-rfid`, OpenRFID there by @suchmememanyskill and the OpenSpool `subtype` field by @morgendagen

Reads NTAG filament tags on the printer's built-in reader.

| Upstream project | Author | Licence | Needed at runtime | Code ships in this package |
| --- | --- | --- | --- | --- |
| OpenSpool tag format | the OpenSpool project | published format | no | no |
| Extended Firmware overlay `13-patch-rfid` | @suchmememanyskill and @morgendagen, packaged by paxx12 | GPL-3.0 | no | yes |

This plugin no longer changes Snapmaker's own firmware files. Those changes moved to the base layer
plugins `u1-base-fm175xx-reader`, `u1-base-filament-detect` and `u1-base-print-task-config`, which
this plugin now requires and calls into. In `openspool_mapper.py`, 22 lines are the Extended
Firmware overlay `13-patch-rfid`'s, GPL-3.0: they fill Snapmaker's own tray structure field by
field, with the same defaults. OpenRFID in that firmware is credited to @suchmememanyskill and the
OpenSpool `subtype` field to @morgendagen.

The rest of the reader code (`bespok3d_rfid.py`, `ntag_reader.py`, `ndef_parser.py`,
`mifare_classic.py`) is written from scratch.
