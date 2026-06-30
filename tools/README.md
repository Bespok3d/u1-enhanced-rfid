# fm175xx reader debug tools (Snapmaker U1)

Standalone, on-printer diagnostics for the U1's fm175xx RFID reader. Use them when a tag will
not read through the normal plugin path and you need to see the raw RF behavior.

They talk to the reader directly over SPI + GPIO, so **Klipper must be stopped first** (it owns
the bus):

```sh
/etc/init.d/S60klipper stop      # free the reader
python3 fm175xx_probe.py read 0  # ... probe ...
/etc/init.d/S60klipper start     # always restart when done
```

Safe by construction: they only write the fm175xx's volatile RAM registers (never EEPROM), keep
the transmit drivers within Snapmaker's own range, reset the chip between probes, and Klipper
re-initializes the reader to its known-good config on restart.

## fm175xx_probe.py (the keeper)

Full ISO 14443-A activation (WUPA -> anticollision -> select), so a "hit" is a tag that really
answered: the anticollision BCC check rejects receiver noise, so an over-sensitive setting cannot
fake a UID.

```sh
python3 fm175xx_probe.py read  <ch> [--th 0x.. --mw 0x.. --gain 0x.. --cw both|cw1|cw2]
python3 fm175xx_probe.py check <ch> [--tries 20]   # repeat; reports UID stability (real vs noise)
python3 fm175xx_probe.py sweep <ch>                # register sweep; reports only STABLE real UIDs
```

Channel map (U1, from factory printer.cfg): ch0,1 = extra chip (spi 2.1, reset gpio1 line 28);
ch2,3 = soc chip (spi 2.0, reset gpio1 line 25). Coils: upper = line 27 (ch0, ch2),
lower = line 24 (ch1, ch3).

`fm175xx_deepsweep.py` / `fm175xx_txsweep.py` are wider one-off sweeps (receiver demod/threshold/
gain; transmit drive/modulation depth) built on the same validated activation.

## Findings (2026-06-29, junior)

The sanity path works: Snapmaker M1 and NTAG (incl. NTAG on the upper coil) activate every time
and return stable UIDs. The factory **Elegoo Centauri (Feiju) tags do not** activate on the U1
across the entire configurable register space (receiver AND transmitter), even with the tag pressed
to the antenna, while a phone and the Elegoo Canvas read them. The limit is the U1 reader's physical
antenna/matching coupling with that specific tag, not a software setting, not field strength, and not
a data lock (Elegoo's data is open NTAG213 user memory).
