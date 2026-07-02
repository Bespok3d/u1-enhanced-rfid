# Changelog

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
