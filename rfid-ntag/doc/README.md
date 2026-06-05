# RFID Spool Reader

Reads OpenSpool-encoded NTAG RFID tags and publishes the detected filament to the rest of
your Bespok3d stack, so the printer always knows what spool is loaded. Tags are read
automatically when filament is loaded and cleared when it is removed.

## Supported tags

This plugin adds **OpenSpool** support on top of the U1's stock reader:

| | OpenSpool (recommended) | Snapmaker |
| --- | --- | --- |
| Tag type | NTAG215 (540 bytes) / NTAG216 (888 bytes) | Mifare Classic 1K |
| Encoding | Human-readable JSON (NDEF) | Encrypted proprietary |
| Programming | Any NDEF-capable NFC app | Official tags only |
| Spec | [openspool.io](https://openspool.io/rfid.html) | closed |

NTAG215 is the sweet spot for capacity and compatibility. ISO15693 tags (for example
OpenPrintTag) are not supported by the U1 hardware.

## How it works

When a spool is loaded, the reader parses the tag's OpenSpool NDEF payload (vendor,
material, color, temperatures) and writes the active spool for each extruder to a shared
file other plugins read:

```
/oem/printer_data/config/bespok3d/data/rfid_data.json
```

Pairs naturally with the **Spoolman Bridge** plugin, which syncs the detected spool to
your Spoolman server.

## Programming tags (OpenSpool)

1. Get NTAG215 or NTAG216 tags.
2. On an Android phone with Chrome, open [printtag-web.pages.dev](https://printtag-web.pages.dev).
3. Enter the filament information and tap the tag to the phone to write it.

Any NFC app that writes an NDEF record with MIME type `application/json` also works.

### Example payload

```json
{
  "protocol": "openspool",
  "version": "1.0",
  "brand": "Generic",
  "type": "PLA",
  "color_hex": "#FF0000",
  "min_temp": 190,
  "max_temp": 220,
  "bed_min_temp": 50,
  "bed_max_temp": 60
}
```

### Field reference

**Required:** `protocol` (must be `openspool`), `version`, `type` (PLA, PETG, ABS, TPU...),
`color_hex` (`#RRGGBB`).

**Optional:** `brand`, `min_temp` / `max_temp` (nozzle, Celsius), `bed_min_temp` /
`bed_max_temp`, `subtype` (Basic, Rapid, Silk...), `alpha` (00-FF), `additional_color_hexes`
(up to 4, for multicolor), `weight` (grams), `diameter` (mm).

To show up correctly in Snapmaker Orca, name filaments `<brand> <type> <subtype>`, for
example `Generic PLA Basic`.

## Troubleshooting

- **Tag not detected:** confirm it is NTAG213/215/216, hold it 1-3 cm from the reader, and
  place it on the side of the spool facing the printer housing. A vendor tag already on the
  spool (Bambu, for example) can interfere; cover it with foil tape.
- **Wrong material or color:** the values come straight from the tag; re-encode it with the
  correct OpenSpool data.
- **OpenPrintTag tags do nothing:** expected. They use ISO15693, which the U1 cannot read.
  Use NTAG tags with OpenSpool instead.
