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

`brand`, `type` and `subtype` are what the printer reports as the filament's name, and what
Snapmaker Orca's **Sync Filament Information** then tries to match. Orca only ever matches against
filaments it ships itself, so the name has to be one of those to land exactly: `Generic PLA` does,
`Generic PLA Basic` does not (there is no such built-in), and `Elegoo PETG Basic` does not either,
because Orca ships nothing under a third-party brand. That is Orca's own behaviour, not something the
printer controls; the Spoolman Bridge doc has the full story under "Limits worth knowing about".

## Show my spools in Snapmaker Orca

A setting of this plugin, on by default. On, every spool whose tag says any brand other than
Snapmaker is reported as `Generic` plus the material, with no sub-type, because those are the only
filament names Orca can match: your loaded spools then appear under **Machine Filament** instead of
the list coming up empty. The printer's own screen shows `Generic` too. Snapmaker's own spools are
never renamed.

A spool that was already loaded when you installed or changed this setting keeps the name it was filed
under until you take it out and put it back, because the printer only files a spool again when the
slot changes.

Off, the brand written on the tag is reported everywhere, which is what you want if you read the tags
with something other than Orca. Orca will then list nothing for anything but Snapmaker spools.

Change it from the plugin's settings in the Bespok3d app; the printer picks it up on the next Klipper
restart.

## Troubleshooting

- **Tag not detected:** confirm it is NTAG213/215/216, hold it 1-3 cm from the reader, and
  place it on the side of the spool facing the printer housing. A vendor tag already on the
  spool (Bambu, for example) can interfere; cover it with foil tape.
- **Wrong material or color:** the values come straight from the tag; re-encode it with the
  correct OpenSpool data.
- **OpenPrintTag tags do nothing:** expected. They use ISO15693, which the U1 cannot read.
  Use NTAG tags with OpenSpool instead.
