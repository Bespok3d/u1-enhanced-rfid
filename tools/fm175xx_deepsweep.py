#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (C) 2026 unlucio and the Bespok3d contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Deep RECEIVER-side register sweep for the U1 fm175xx, validated by a full ISO 14443-A
activation (WUPA -> anticollision -> select). Only a stable, BCC-valid UID counts as a hit, so
receiver noise cannot fake a read. Touches only volatile receiver registers; resets between probes.
Klipper must be stopped first. Safe: no EEPROM, no TX-driver over-drive."""
import time
import spidev, gpiod

OK = 0; ERR = -1; TIMER = -20; COMM = -22; COLL = -23; LENGTH = -21
RESET = 0; SET = 1
COMMAND = 0x01; COM_I_EN = 0x02; DIV_I_EN = 0x03; COM_IRQ = 0x04; DIV_IRQ = 0x05; ERROR = 0x06
STATUS2 = 0x08; FIFO_LEVEL = 0x0A; WATER = 0x0B; CONTROL = 0x0C; BITFRAMING = 0x0D
TXMODE = 0x12; RXMODE = 0x13; TXCTRL = 0x14; TXAUTO = 0x15; RXSEL = 0x17; RXTHRESH = 0x18; DEMOD = 0x19
MODEWIDTH = 0x24; RFCFG = 0x26; GSNON = 0x27; CWGSP = 0x28
TMODE = 0x2A; TPRESC = 0x2B; TRELMSB = 0x2C; TRELLSB = 0x2D
CMD_IDLE = 0x00; CMD_TRANSCEIVE = 0x0C
WUPA = 0x52; ANTICOL = [0x93, 0x95, 0x97]; SELECT = [0x93, 0x95, 0x97]
CH = {0: (2, 1, 28, True), 1: (2, 1, 28, False), 2: (2, 0, 25, True), 3: (2, 0, 25, False)}


class FM:
    def __init__(s, bus, dev, rstl):
        s.spi = spidev.SpiDev(); s.spi.open(bus, dev); s.spi.mode = 0; s.spi.max_speed_hz = 500000
        c = gpiod.Chip('gpiochip1')
        s.rst = c.get_line(rstl); s.rst.request(consumer='d_r', type=gpiod.LINE_REQ_DIR_OUT, default_val=1)
        s.up = c.get_line(27); s.up.request(consumer='d_u', type=gpiod.LINE_REQ_DIR_OUT, default_val=0)
        s.lo = c.get_line(24); s.lo.request(consumer='d_l', type=gpiod.LINE_REQ_DIR_OUT, default_val=0)
    def rr(s, a): return s.spi.xfer2([((a << 1) | 0x80) & 0xFF, 0])[1]
    def rw(s, a, v): s.spi.xfer2([(a << 1) & 0x7E, v & 0xFF])
    def rm(s, a, m, st): v = s.rr(a); s.rw(a, (v | m) if st else (v & (~m & 0xFF)))
    def fw(s, b): s.spi.xfer2([0x12] + list(b))
    def fr(s, n): return s.spi.xfer2([0x92] * n + [0])[1:n + 1]
    def coil(s, up): s.up.set_value(1 if up else 0); s.lo.set_value(0 if up else 1)
    def reset(s): s.rst.set_value(0); time.sleep(0.02); s.rst.set_value(1); time.sleep(0.04)
    def to(s, us):
        p = 0; r = 0
        while p < 0xFFF:
            r = int(((us * 13560) - 1) / (p * 2 + 1))
            if r < 0xFFFF:
                break
            p += 1
        r &= 0xFFFF; s.rw(TMODE, 0x80 | ((p >> 8) & 0xF)); s.rw(TPRESC, p & 0xFF); s.rw(TRELMSB, r >> 8); s.rw(TRELLSB, r & 0xFF)
    def carrier(s, m):
        if m == 'cw1':
            s.rm(TXCTRL, 0x01, SET); s.rm(TXCTRL, 0x02, RESET)
        elif m == 'cw2':
            s.rm(TXCTRL, 0x01, RESET); s.rm(TXCTRL, 0x02, SET)
        elif m == 'off':
            s.rm(TXCTRL, 0x03, RESET)
        else:
            s.rm(TXCTRL, 0x03, SET)
    def init(s, demod, rxsel, rxth, gain):
        # TX path left at Snapmaker defaults (GsN 0xF0 / CWGsP 0x3F); only receiver regs vary
        s.rw(TXMODE, 0x00); s.rw(RXMODE, 0x08); s.rm(TXAUTO, 0x40, SET); s.rw(MODEWIDTH, 0x26)
        s.rw(CONTROL, 0x10); s.rw(GSNON, 0xF0); s.rw(CWGSP, 0x3F)
        s.rw(RFCFG, gain); s.rw(RXTHRESH, rxth); s.rw(DEMOD, demod); s.rw(RXSEL, rxsel)
        s.rm(STATUS2, 0x08, RESET)
    def tx(s, send, expect, scrc, rcrc, bits=0):
        buff = list(send); slen = len(buff); recv = []
        s.rw(COMMAND, CMD_IDLE); s.rw(FIFO_LEVEL, 0x80); s.rw(COM_IRQ, 0x7F); s.rw(DIV_IRQ, 0x7F)
        s.rw(COM_I_EN, 0x80); s.rw(DIV_I_EN, 0x00); s.rw(WATER, 32)
        s.rm(TXMODE, 0x80, SET if scrc else RESET); s.rm(RXMODE, 0x80, SET if rcrc else RESET); s.to(10)
        s.rw(COMMAND, CMD_TRANSCEIVE); s.rw(BITFRAMING, bits & 0xFF)
        t = time.time() * 1000; res = ERR
        while True:
            if time.time() * 1000 - t > 50:
                res = TIMER; break
            irq = s.rr(COM_IRQ)
            if irq & 0x01:
                res = TIMER; break
            if irq & 0x02:
                e = s.rr(ERROR); res = COLL if (e & 0x08) else COMM; break
            if irq & 0x04:
                if slen > 0:
                    ch = min(slen, 32); s.fw(buff[0:ch]); del buff[0:ch]; slen -= ch; s.rm(BITFRAMING, 0x80, SET)
                s.rw(COM_IRQ, 0x04)
            if irq & 0x20:
                n = s.rr(FIFO_LEVEL) & 0x7F; recv = s.fr(n) if n else []
                res = OK if (not expect or len(recv) == expect) else LENGTH; break
            time.sleep(0.001)
        s.rm(BITFRAMING, 0x80, RESET); s.rw(COMMAND, CMD_IDLE)
        return res, recv
    def activate(s):
        e, atqa = s.tx([WUPA], 2, False, False, 7)
        if e != OK or len(atqa) != 2:
            return ERR, None
        levels = {0x00: 1, 0x40: 2, 0x80: 3}.get(atqa[0] & 0xC0, 1); uid = []
        for lvl in range(levels):
            e, d = s.tx([ANTICOL[lvl], 0x20], 5, False, False)
            if e != OK or len(d) != 5 or (d[0] ^ d[1] ^ d[2] ^ d[3]) != d[4]:
                return COLL, None
            e, sak = s.tx([SELECT[lvl], 0x70] + d[0:4] + [d[4]], 1, True, True)
            if e != OK:
                return ERR, None
            uid += (d[1:4] if d[0] == 0x88 else d[0:4])
        return OK, uid
    def close(s):
        s.carrier('off')
        for l in (s.rst, s.up, s.lo):
            try:
                l.release()
            except Exception:
                pass
        s.spi.close()


def hexb(b): return ' '.join('%02X' % x for x in b)


def sweep(name, ch):
    bus, dev, rstl, upper = CH[ch]
    fm = FM(bus, dev, rstl)
    print("==== %s ====" % name)
    hits = []
    for cw in ('both', 'cw1', 'cw2'):
        for gain in (0x48, 0x58, 0x68, 0x70):
            for demod in (0x4D, 0x4F, 0x6D, 0x0D, 0xAD, 0x40):
                for rxsel in (0x84, 0x8C):
                    for rxth in (0x84, 0x55, 0x44):
                        uids = {}
                        for _ in range(3):
                            fm.reset(); fm.coil(upper); fm.init(demod, rxsel, rxth, gain)
                            fm.carrier(cw); time.sleep(0.02)
                            e, uid = fm.activate()
                            if e == OK and uid:
                                uids[hexb(uid)] = uids.get(hexb(uid), 0) + 1
                        stable = [(u, n) for u, n in uids.items() if n >= 2]
                        if len(stable) == 1:
                            line = "REAL %s cw=%s gain=0x%02X demod=0x%02X rxsel=0x%02X rxth=0x%02X -> UID [%s] x%d/3" % (
                                name, cw, gain, demod, rxsel, rxth, stable[0][0], stable[0][1])
                            print(line); hits.append(line)
    print("%s: %d combos gave a STABLE real UID" % (name, len(hits)))
    fm.close()
    return hits


a = sweep("ch0 Elegoo", 0)
b = sweep("ch3 Elegoo", 3)
print("TOTAL STABLE REAL UID combos:", len(a) + len(b))
print("DONE")
