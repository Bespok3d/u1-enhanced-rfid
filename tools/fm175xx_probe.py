#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (C) 2026 unlucio and the Bespok3d contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Standalone fm175xx RFID reader probe + register sweep for the Snapmaker U1.

Drives the reader directly over SPI + GPIO, so it is a hardware debug tool for tags that
will not read through Klipper. Klipper must be stopped first (it owns the SPI/GPIO):
    /etc/init.d/S60klipper stop      (and ... start when done)

It does a FULL ISO 14443-A activation (WUPA -> anticollision -> select) and returns the real
UID/SAK, so a "hit" is a tag that genuinely answered (the anticollision BCC check rejects noise),
not a stray byte from an over-sensitive receiver.

Usage:
    python3 fm175xx_probe.py read  <ch> [--th 0xNN --mw 0xNN --gain 0xNN --cw both|cw1|cw2]
    python3 fm175xx_probe.py check <ch> [--tries 20] [reg opts]   # repeat, report UID stability
    python3 fm175xx_probe.py sweep <ch> [--tries 6]               # sweep regs, report stable UIDs

U1 wiring (from factory printer.cfg): ch0,1 -> extra chip (spi 2.1, reset gpio1 line28);
ch2,3 -> soc chip (spi 2.0, reset gpio1 line25). Coils: upper = line27, lower = line24;
upper serves ch0,ch2 and lower serves ch1,ch3.
"""
import sys, time, argparse
import spidev, gpiod

OK = 0; ERR = -1; TIMER = -20; COMM = -22; COLL = -23; LENGTH = -21
RESET = 0; SET = 1
# registers
COMMAND = 0x01; COM_I_EN = 0x02; DIV_I_EN = 0x03; COM_IRQ = 0x04; DIV_IRQ = 0x05; ERROR = 0x06
STATUS2 = 0x08; FIFO_LEVEL = 0x0A; WATER = 0x0B; CONTROL = 0x0C; BITFRAMING = 0x0D; COLLREG = 0x0E
TXMODE = 0x12; RXMODE = 0x13; TXCTRL = 0x14; TXAUTO = 0x15; RXTHRESH = 0x18
MODEWIDTH = 0x24; RFCFG = 0x26; GSNON = 0x27; CWGSP = 0x28
TMODE = 0x2A; TPRESC = 0x2B; TRELMSB = 0x2C; TRELLSB = 0x2D
CMD_IDLE = 0x00; CMD_TRANSCEIVE = 0x0C
WUPA = 0x52; REQA = 0x26
ANTICOL = [0x93, 0x95, 0x97]; SELECT = [0x93, 0x95, 0x97]

CHANNELS = {
    0: dict(bus=2, dev=1, reset=28, upper=True),
    1: dict(bus=2, dev=1, reset=28, upper=False),
    2: dict(bus=2, dev=0, reset=25, upper=True),
    3: dict(bus=2, dev=0, reset=25, upper=False),
}


class Fm175xx:
    def __init__(self, bus, dev, reset_line):
        self.spi = spidev.SpiDev(); self.spi.open(bus, dev); self.spi.mode = 0; self.spi.max_speed_hz = 500000
        chip = gpiod.Chip('gpiochip1')
        self.rst = chip.get_line(reset_line); self.rst.request(consumer='probe_rst', type=gpiod.LINE_REQ_DIR_OUT, default_val=1)
        self.upper = chip.get_line(27); self.upper.request(consumer='probe_up', type=gpiod.LINE_REQ_DIR_OUT, default_val=0)
        self.lower = chip.get_line(24); self.lower.request(consumer='probe_lo', type=gpiod.LINE_REQ_DIR_OUT, default_val=0)

    def reg_read(self, addr): return self.spi.xfer2([((addr << 1) | 0x80) & 0xFF, 0])[1]
    def reg_write(self, addr, val): self.spi.xfer2([(addr << 1) & 0x7E, val & 0xFF])
    def reg_modify(self, addr, mask, set_bit):
        val = self.reg_read(addr); self.reg_write(addr, (val | mask) if set_bit else (val & (~mask & 0xFF)))
    def fifo_write(self, buff): self.spi.xfer2([0x12] + list(buff))
    def fifo_read(self, count): return self.spi.xfer2([0x92] * count + [0])[1:count + 1]

    def select_coil(self, upper):
        self.upper.set_value(1 if upper else 0); self.lower.set_value(0 if upper else 1)

    def hard_reset(self):
        self.rst.set_value(0); time.sleep(0.05); self.rst.set_value(1); time.sleep(0.1)

    def set_timeout(self, microseconds):
        prescaler = 0; reload = 0
        microseconds = max(1, microseconds)
        while prescaler < 0xFFF:
            reload = int(((microseconds * 13560) - 1) / (prescaler * 2 + 1))
            if reload < 0xFFFF:
                break
            prescaler += 1
        reload &= 0xFFFF
        self.reg_write(TMODE, 0x80 | ((prescaler >> 8) & 0x0F)); self.reg_write(TPRESC, prescaler & 0xFF)
        self.reg_write(TRELMSB, reload >> 8); self.reg_write(TRELLSB, reload & 0xFF)

    def set_carrier(self, mode):
        if mode == 'cw1':
            self.reg_modify(TXCTRL, 0x01, SET); self.reg_modify(TXCTRL, 0x02, RESET)
        elif mode == 'cw2':
            self.reg_modify(TXCTRL, 0x01, RESET); self.reg_modify(TXCTRL, 0x02, SET)
        elif mode == 'off':
            self.reg_modify(TXCTRL, 0x03, RESET)
        else:
            self.reg_modify(TXCTRL, 0x03, SET)

    def reader_init(self, modewidth=0x26, rxthresh=0x84, gain=0x60):
        self.reg_write(TXMODE, 0x00); self.reg_write(RXMODE, 0x08); self.reg_modify(TXAUTO, 0x40, SET)
        self.reg_write(MODEWIDTH, modewidth); self.reg_write(CONTROL, 0x10); self.reg_write(GSNON, 0xF0)
        self.reg_write(CWGSP, 0x3F); self.reg_write(RFCFG, gain); self.reg_write(RXTHRESH, rxthresh)
        self.reg_modify(STATUS2, 0x08, RESET)

    def transceive(self, send, recv_expect, send_crc, recv_crc, bits_to_send=0):
        send_buff = list(send); send_length = len(send_buff); send_done = 0
        bytes_recved = 0; recv = []
        self.reg_write(COMMAND, CMD_IDLE); self.reg_write(FIFO_LEVEL, 0x80)
        self.reg_write(COM_IRQ, 0x7F); self.reg_write(DIV_IRQ, 0x7F)
        self.reg_write(COM_I_EN, 0x80); self.reg_write(DIV_I_EN, 0x00); self.reg_write(WATER, 32)
        self.reg_modify(TXMODE, 0x80, SET if send_crc else RESET)
        self.reg_modify(RXMODE, 0x80, SET if recv_crc else RESET)
        self.set_timeout(10)
        self.reg_write(COMMAND, CMD_TRANSCEIVE); self.reg_write(BITFRAMING, ((0 << 4) | bits_to_send) & 0xFF)
        start = time.time() * 1000; result = ERR
        while True:
            if time.time() * 1000 - start > 60:
                result = TIMER; break
            irq = self.reg_read(COM_IRQ)
            if irq & 0x01:
                result = TIMER; break
            if irq & 0x02:
                err = self.reg_read(ERROR)
                result = COLL if (err & 0x08) else COMM
                break
            if irq & 0x04:
                if send_length > 0:
                    chunk = min(send_length, 32)
                    self.fifo_write(send_buff[0:chunk]); del send_buff[0:chunk]; send_length -= chunk
                    self.reg_modify(BITFRAMING, 0x80, SET)
                self.reg_write(COM_IRQ, 0x04)
            if irq & 0x20:
                level = self.reg_read(FIFO_LEVEL) & 0x7F
                recv = self.fifo_read(level) if level else []
                bytes_recved = len(recv)
                if recv_expect and bytes_recved != recv_expect:
                    result = LENGTH; break
                result = OK; break
            if irq & 0x40:
                send_done = 1
            time.sleep(0.001)
        self.reg_modify(BITFRAMING, 0x80, RESET); self.reg_write(COMMAND, CMD_IDLE)
        return result, recv

    def wakeup(self, cmd=WUPA):
        err, atqa = self.transceive([cmd], 2, send_crc=False, recv_crc=False, bits_to_send=7)
        return (OK, atqa) if (err == OK and len(atqa) == 2) else (err if err != OK else COMM, atqa)

    def anticoll(self, level):
        err, data = self.transceive([ANTICOL[level], 0x20], 5, send_crc=False, recv_crc=False)
        if err != OK or len(data) != 5:
            return ERR, [], 0
        if (data[0] ^ data[1] ^ data[2] ^ data[3]) != data[4]:
            return COMM, [], 0          # BCC mismatch = noise / collision, not a real UID
        return OK, data[0:4], data[4]

    def select(self, level, uid4, bcc):
        err, sak = self.transceive([SELECT[level], 0x70] + list(uid4) + [bcc], 1, send_crc=True, recv_crc=True)
        if err != OK or len(sak) != 1:
            return ERR, None
        return OK, sak[0]

    def activate(self):
        err, atqa = self.wakeup(WUPA)
        if err != OK:
            return err, None, None, atqa
        levels = {0x00: 1, 0x40: 2, 0x80: 3}.get(atqa[0] & 0xC0, 1)
        uid = []
        sak = None
        for level in range(levels):
            err, uid_part, bcc = self.anticoll(level)
            if err != OK:
                return COLL, uid, sak, atqa
            err, sak = self.select(level, uid_part, bcc)
            if err != OK:
                return ERR, uid, sak, atqa
            uid += (uid_part[1:4] if uid_part[0] == 0x88 else uid_part[0:4])  # 0x88 = cascade tag
        return OK, uid, sak, atqa

    def close(self):
        self.set_carrier('off')
        for line in (self.rst, self.upper, self.lower):
            try:
                line.release()
            except Exception:
                pass
        self.spi.close()


def open_channel(ch):
    cfg = CHANNELS[ch]
    fm = Fm175xx(cfg['bus'], cfg['dev'], cfg['reset'])
    fm.upper_coil = cfg['upper']
    return fm


def prep(fm, mw, th, gain, cw):
    fm.hard_reset(); fm.select_coil(fm.upper_coil)
    fm.reader_init(modewidth=mw, rxthresh=th, gain=gain); fm.set_carrier(cw); time.sleep(0.02)


def hexb(seq):
    return ' '.join('%02X' % x for x in seq) if seq else '-'


def cmd_read(ch, mw, th, gain, cw):
    fm = open_channel(ch)
    try:
        prep(fm, mw, th, gain, cw)
        err, uid, sak, atqa = fm.activate()
        print("ch%d mw=0x%02X th=0x%02X gain=0x%02X cw=%s -> ret=%d ATQA=[%s] UID=[%s] SAK=%s"
              % (ch, mw, th, gain, cw, err, hexb(atqa), hexb(uid), ('0x%02X' % sak) if sak is not None else '-'))
    finally:
        fm.close()


def cmd_check(ch, mw, th, gain, cw, tries):
    fm = open_channel(ch)
    uids = {}; oks = 0
    try:
        for _ in range(tries):
            prep(fm, mw, th, gain, cw)
            err, uid, sak, atqa = fm.activate()
            if err == OK and uid:
                oks += 1; key = hexb(uid); uids[key] = uids.get(key, 0) + 1
    finally:
        fm.close()
    print("ch%d th=0x%02X mw=0x%02X gain=0x%02X cw=%s: %d/%d full activations" % (ch, th, mw, gain, cw, oks, tries))
    for uid, n in sorted(uids.items(), key=lambda kv: -kv[1]):
        print("   UID [%s] x%d" % (uid, n))
    stable = [u for u, n in uids.items() if n >= max(2, tries // 2)]
    print("   VERDICT:", "REAL stable UID" if len(stable) == 1 else ("noise/none" if not uids else "inconsistent (noise)"))


def cmd_sweep(ch, tries):
    fm = open_channel(ch)
    real = []
    try:
        for cw in ('both', 'cw1', 'cw2'):
            for gain in (0x50, 0x60, 0x70):
                for th in (0x84, 0x44, 0x33, 0x22, 0x11):
                    for mw in (0x26, 0x16, 0x14, 0x0E, 0x0A):
                        uids = {}
                        for _ in range(tries):
                            prep(fm, mw, th, gain, cw)
                            err, uid, sak, atqa = fm.activate()
                            if err == OK and uid:
                                uids[hexb(uid)] = uids.get(hexb(uid), 0) + 1
                        stable = [(u, n) for u, n in uids.items() if n >= max(2, tries // 2)]
                        if len(stable) == 1:
                            line = "REAL ch%d cw=%s gain=0x%02X th=0x%02X mw=0x%02X -> UID [%s] x%d/%d" % (
                                ch, cw, gain, th, mw, stable[0][0], stable[0][1], tries)
                            print(line); real.append(line)
    finally:
        fm.close()
    print("ch%d: %d register combos gave a STABLE real UID" % (ch, len(real)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['read', 'check', 'sweep'])
    ap.add_argument('ch', type=int)
    ap.add_argument('--th', default='0x84'); ap.add_argument('--mw', default='0x26')
    ap.add_argument('--gain', default='0x60'); ap.add_argument('--cw', default='both')
    ap.add_argument('--tries', type=int, default=20)
    a = ap.parse_args()
    th = int(a.th, 0); mw = int(a.mw, 0); gain = int(a.gain, 0)
    if a.mode == 'read':
        cmd_read(a.ch, mw, th, gain, a.cw)
    elif a.mode == 'check':
        cmd_check(a.ch, mw, th, gain, a.cw, a.tries)
    else:
        cmd_sweep(a.ch, a.tries)


if __name__ == '__main__':
    main()
