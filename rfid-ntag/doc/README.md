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

## Your pressure advance stays put

Stock, the printer replaces a lane's pressure advance with the value from its own material table
every time it learns what filament that lane holds: a spool loaded, unloaded or swapped, a tag read,
or a filament picked by hand, mid print included. This plugin stops that, so a lane keeps the number
you set or the one your slicer sent. Only one lane was ever affected at a time, the one being told
about; the others were never touched.

Resetting on purpose still works: send `FLOW_RESET_K EXTRUDER=<lane>` and that lane goes back to the
material table default.

Firmware 1.3 and newer. On older firmware the rest of the plugin installs and this part is skipped.

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
Snapmaker Orca's **Sync Filament Information** looks up. It needs a filament preset named exactly
that, capitals included, from the ones it ships and the ones you made yourself: `Generic PLA` finds
a built-in, `ELEGOO PLA+ Rapid` finds a preset only if you made one with that name, because it ships
none under a third-party brand. A tag with no `subtype` is reported as `Basic`, the way Snapmaker
names its own base line, so an `eSun` + `PLA` tag reads as `eSun PLA Basic` and its preset needs the
`Basic` too. That is Snapmaker Orca's own behaviour, not something the printer controls. Plain
OrcaSlicer matches differently, and how it should behave is being worked out with one of its
developers.

## How a spool shows up in Snapmaker Orca

The name written on the tag is reported everywhere: brand, material and variant, like
`ELEGOO PLA+ Rapid`; a tag with no `subtype` reads as `Basic`. Snapmaker Orca lists the spool under
**Machine Filament** when one of your filament presets is named exactly that, capitals included, so
name your presets after your tags (or your tags after your presets) and your spools show under their
real names. The name the printer filed is shown on the slot in Orca's **Device** tab: read it there
and copy it into a preset name letter for letter.

A spool that was already loaded keeps the name it was filed under until you take it out and put it
back, because the printer only files a spool again when the slot changes.

## Troubleshooting

- **Tag not detected:** confirm it is NTAG213/215/216, hold it 1-3 cm from the reader, and
  place it on the side of the spool facing the printer housing. A vendor tag already on the
  spool (Bambu, for example) can interfere; cover it with foil tape.
- **Wrong material or color:** the values come straight from the tag; re-encode it with the
  correct OpenSpool data.
- **OpenPrintTag tags do nothing:** expected. They use ISO15693, which the U1 cannot read.
  Use NTAG tags with OpenSpool instead.
