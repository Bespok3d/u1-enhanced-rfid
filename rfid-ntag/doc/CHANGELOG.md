# Changelog

## 0.1.14

- This plugin no longer changes Klipper's own program files. The three firmware changes it needed
  now come from the shared base layer, which is installed alongside it. Your pressure advance still
  stays where you set it and tags still read exactly as before.
- Because of that, this plugin and the Force print preferences plugin no longer fight over the same
  firmware file when both are installed.

## 0.1.13

- Your pressure advance now stays where you set it. Before, every time the printer was told what
  filament a lane holds, it threw that lane's pressure advance away and put the value from its own
  material table in place of it: loading a spool, unloading it, swapping it, reading a tag or
  picking a filament by hand, and it happened mid print too. A lane you had tuned, or a value your
  slicer sent, came out replaced with the machine's default. Now the number you set is left alone.
- Sending `FLOW_RESET_K` yourself still works exactly as before, so you can put a lane back on the
  material table default whenever you want.
- This covers printers on firmware 1.3 and newer. On anything older, the plugin installs the rest of
  itself and leaves the pressure advance behaviour as it was.

## 0.1.12

- The **Show my spools in Snapmaker Orca** setting is removed. Every spool is now always reported
  under the name written on its tag: brand, material and variant, like `ELEGOO PLA+ Rapid`; a tag
  with no `subtype` reads as `Basic` (`eSun PLA Basic`), the way Snapmaker names its own base line.
  Nothing is renamed to `Generic` any more, on the printer's screen or anywhere else.
- To see a spool in Snapmaker Orca, name a filament preset exactly what the printer reports,
  capitals included. It matches against every preset, the ones it ships and the ones you made
  yourself; no match means the spool is listed nowhere, with no error. The name the printer filed is
  shown on the slot in Orca's **Device** tab, so you can copy it from there. (The 0.1.10 notes said
  only built-in filaments matched; that was wrong.) Plain OrcaSlicer matches differently, and how it
  should behave is being worked out with one of its developers.
- A spool already loaded keeps the name it was filed under until you take it out and put it back.

## 0.1.11

- Fix: 0.1.10 could stop the printer from starting. If the new setting did not reach the printer
  with the plugin, Klipper refused the config and halted, and the plugin was switched off to keep
  the printer usable. A setting that does not arrive, or arrives unreadable, now simply reads as on,
  which is what it ships as.
- Worth knowing when you update: a spool that is already loaded keeps the name it was filed under.
  Take it out and put it back and it appears as `Generic`. Only spools loaded before the update need
  it, and only once.

## 0.1.10

- Fix: your tagged spools show up in Snapmaker Orca. Before, a spool of any brand but Snapmaker was
  read correctly off its tag and then listed nowhere: Orca drew the **Machine Filament** header with
  nothing under it, and said nothing about why. The printer now reports such a spool as `Generic`
  plus its material, the only name Orca can match, so the spool appears. The printer's own screen
  shows `Generic` too, and Snapmaker's own spools keep their name.
- New setting, **Show my spools in Snapmaker Orca**, on by default. Turn it off and the brand written
  on the tag is reported everywhere again, with Orca back to listing nothing for third-party spools.

## 0.1.9

- Doc only, nothing about how the plugin works has changed. The advice on naming filaments for a
  hand-written tag was wrong: Snapmaker Orca only matches filaments it ships itself, so `Generic PLA`
  lands exactly and `Generic PLA Basic` does not, because there is no such built-in. Anything Orca
  does not recognise syncs its colour and falls back to `Generic <type>`.

## 0.1.8

- Licensing only, nothing about how the plugin works has changed. The files it installs that came
  from other projects now carry those projects' own licence notices, plus a line recording what
  Bespok3d changed in them and when.

## 0.1.7

- Fix: a genuine Snapmaker-official spool could lose its identity the moment a print started
  (AFC's feed motion re-triggers a fresh RFID read right at launch, and a read taken during
  motion is more likely to glitch than one taken at rest). When the firmware's own official
  M1 read attempt failed mid-print, the UID-only fallback (added in 0.1.6) still reported a
  "successful" read carrying no vendor/type identity, and the shared relay layer
  (bespok3d_rfid.py) applied that report unconditionally, overwriting the channel's
  already-correctly-resolved spool with a blank one and notifying every downstream consumer
  (Spoolman tracking included) of the loss. Snapmaker's own firmware already protects itself
  against exactly this case (it ignores a report with `OFFICIAL == False` when a real vendor
  is already recorded for that channel); the relay layer now applies the same guard, keyed
  off the same `OFFICIAL` flag, so a no-identity report can never downgrade already-known-good
  state; only an explicit clear (spool removed) or a genuine first-ever read on an empty
  channel still goes through. This only ever affected official Snapmaker spools; custom-tagged
  (NTAG/OpenSpool/etc.) filament was never routed through the UID-only fallback path and was
  unaffected.

## 0.1.6

- Claim-based card handlers + SAK 0x08 collision fix. Bambu (and other) Mifare-Classic
  spools share the SAK (0x08) of Snapmaker's own M1 tags, so they used to fall into the
  Snapmaker decode path, fail on the foreign key, and surface nothing. The reader now lets a
  plugin register a `(claim, read)` handler: when the stock Snapmaker key cannot open a 0x08
  card, each claiming plugin gets to authenticate and read it with its own key. The Snapmaker
  M1 and NTAG read paths are byte-for-byte unchanged; the new dispatch runs only after the
  stock read has already failed. A decoder plugin can ship a whole new Mifare-Classic tag
  family with zero further firmware edits.
- New reader primitives for those plugins: `read_mifare_classic` (crypto1-auth a sector with
  a supplied key, then read its blocks) and `reactivate_card` (re-select a card after the
  stock read consumed its crypto session), beside the existing `mifare_authenticate` /
  `transceive`.
- UID-only fallback for unrecognized 0x08 tags: when no plugin claims a foreign Mifare-Classic
  card, the reader surfaces its UID (written to `rfid_data.json` as `CARD_UID`) so the spool is
  still trackable by UID, instead of disappearing. Re-randomized DESFire UIDs (first byte 0x08)
  are excluded, since they are not a stable key.

## 0.1.5

- Generic reader substrate: the reader now exposes everything a tag needs as a plugin, so
  new tag families are added without patching the firmware reader again. Added a raw
  `transceive` primitive (ISO 14443-4 / APDU and any custom frame), `mifare_authenticate`
  (crypto1 tags such as Bambu), and accessors for the SELECT-phase facts
  (`selected_card_uid` / `selected_card_sak` / `selected_card_atqa`), alongside the existing
  SAK-keyed handler registry and `read_nfc_type2_pages`. Snapmaker's M1 path is untouched.
- Note on factory Elegoo (Centauri) spools: their Shanghai Feiju anti-clone chip returns no
  RF response to the U1 reader on either antenna coil (verified on hardware: WUPA and REQA
  time out with zero bytes even after a chip reset at maximum receiver gain), while NTAG and
  M1 read normally on the same coils. A phone reads them because its NFC front end is
  stronger; this is an RF/hardware limit of the reader, not a decode or plugin gap.

## 0.1.4

- Reader activation: trap the WUPA wakeup failure (err -24) and recover it ourselves.
  Some anti-clone NFC chips (e.g. the Feiju chip in Elegoo spools) ignore the reader's
  WUPA while left in a HALT / ISO-14443-4 state; the reader now power-cycles the RF
  carrier and retries the wakeup once, so it activates them like a phone does, instead
  of giving up. Snapmaker's own M1 path is unchanged.

## 0.1.3

- Publishing from bundled to online official registry.

## 0.1.0

- First release. Reads NTAG215 / OpenSpool RFID tags and writes the shared
  rfid_data.json; supports multiple firmware revisions.
