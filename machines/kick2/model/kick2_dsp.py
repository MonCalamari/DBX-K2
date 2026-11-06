#!/usr/bin/env python3
"""KICK2 – Modell in der Struktur des DSP-Codes (Gleitkomma).

Gleiches Prinzip wie die doergbox-KICK2, aber mit DSP-günstigen Bausteinen:
  - Resonator in Kreisform ("Magic Circle"): x1 = r·x1 − e·x2 + in, x2 = r·x2 + e·x1
    (x1 neu). Frequenz e ≈ 2πf/fs, Dämpfung r unabhängig davon. Ausgang x1
    (Kosinus-Phase: der Anschlag beginnt mit voller Auslenkung).
  - Bend-Hüllkurve pro Block, e innerhalb des Blocks linear interpoliert.
  - Puls (Klick..Rauschen) stößt den Resonator an und ist direkt hörbar.
  - Drive: kubische Kennlinie statt rationaler Funktion.
  - Tiefpass erster Ordnung, Ausgang hart bei Vollaussteuerung gekappt.
  - Rauschen: 24-Bit-Galois-LFSR.
Alle Exponentialfunktionen nur einmal pro Block (2^x).

  python3 kick2_dsp.py [--set NAME=WERT ...] [-o datei.wav]
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from kick2_ref import DEFAULTS_MD as DEFAULTS, write_wav  # noqa: E402

FS = 44100.0
BLOCK = 32
LN100 = math.log(100.0)

# Feste Größen (an die doergbox angelehnt)
F_LO, F_HI = 38.0, 160.0          # PTCH (ab 0.9; doergbox 30..150)
BEND_OCT = 5.0                    # BEND 127
BT_LO, BT_HI = 3.0, 300.0         # BTIM in ms
DC_LO, DC_HI = 40.0, 3000.0       # DCAY in ms (−40 dB)
TO_LO, TO_HI = 200.0, 18000.0     # TONE in Hz
F_MAX = 6000.0                    # Resonator-Obergrenze (Magic Circle bleibt stabil)
IMPULSE = 1.0                     # Grundanstoß
K_PULSE = 0.16                    # Puls in den Resonator (doergbox: 2·g·0,08/g)
K_DIRECT = 1.2                    # Puls direkt hörbar
OUT_GAIN = 0.72                   # 0,9 · 0,8 wie doergbox
HOLD_BLOCKS = 344                 # HOLD 127: 338 Blöcke ≈ 245 ms ungedämpft
P_LO, P_HI = 1.5, 11.5            # Pulsdauer in ms (COLR 0 .. 127)
TA_LO = 1.0 - math.exp(-2 * math.pi * TO_LO / FS)   # 0,0281
TA_HI = 1.0 - math.exp(-2 * math.pi * TO_HI / FS)   # 0,923


def exp_map(v, lo, hi):
    return lo * (hi / lo) ** (v / 127.0)


def cubic(x):
    """Weiche Sättigung, Grenzwert ±1 ab |x| ≥ 1,5."""
    if x >= 1.5:
        return 1.0
    if x <= -1.5:
        return -1.0
    return x - (4.0 / 27.0) * x * x * x


class Kick2Dsp:
    def __init__(self, params=None):
        self.p = dict(DEFAULTS)
        if params:
            self.p.update(params)
        self.x1 = self.x2 = self.lp = 0.0
        self.env = self.penv = 0.0
        self.hold = 0
        self.e_prev = 0.0                  # e am Ende des letzten Blocks (DSP: Y:ECO)
        self.rot = 0
        # Puls-Farbe fest (wie früher COLR 20); DCAY/TONE: Startpreset (DSP: INIT), danach im Wechsel neu
        self.md = -0.0006701571058820476
        self.pc, self.p1 = 0.15625, 0.84375
        self.pcoef = 0.9890036039501158
        self.ta = 0.5040822881762151
        self.lfsr = 0x5A5A5B
        self.trig = False
        self.active = False
        self.quiet = 0

    def trigger(self):
        self.trig = True

    def _noise(self):
        # wie im DSP-Code: multiplikativ, s = s * 1664525 mod 2^24
        self.lfsr = (self.lfsr * 1664525) & 0xFFFFFF
        v = self.lfsr
        return (v - (1 << 24) if v & 0x800000 else v) / 8388608.0

    def _rotate(self):
        p = self.p
        if self.rot == 0:
            t60 = exp_map(p["DCAY"], DC_LO, DC_HI) / 1000.0 * FS
            self.md = -LN100 / t60
        else:
            self.ta = min(TA_LO * 2.0 ** (p["TONE"] / 127.0 * math.log2(TA_HI / TA_LO)), TA_HI)
        self.rot = (self.rot + 1) % 2

    def render_block(self):
        p = self.p
        out = [0.0] * BLOCK
        start = self.trig
        self.trig = False
        if start:
            self.env = 1.0
            self.penv = 1.0
            self.active = True
            self.quiet = 0

        # ---- reihum ein Koeffizient (DSP: ROTATE, auch in stillen Blöcken) ----
        self._rotate()
        if not self.active:
            return out
        # ---- einmal pro Block ----
        f_base = exp_map(p["PTCH"], F_LO, F_HI)
        bend = p["BEND"] / 127.0 * BEND_OCT
        tau_b = exp_map(p["BTIM"], BT_LO, BT_HI) / 1000.0 * FS        # Samples
        xb = BLOCK / tau_b                                  # ≤ 0,242
        self.env = self.env * (1.0 - xb + xb * xb / 2 - xb * xb * xb / 6)
        e1 = 2 * math.pi * min(f_base * 2.0 ** (bend * self.env), F_MAX) / FS
        e0 = e1 if start else self.e_prev      # nach Trig kein Gleiten von der alten Tonhöhe
        de = (e1 - e0) / BLOCK
        r = 1.0 + self.md
        pl = p["PULS"] / 127.0
        pc, pcoef, ta = self.pc, self.pcoef, self.ta
        amount = p["DRIV"] / 127.0
        dv = 1.0 + 15.0 * amount * amount   # Sättigung läuft immer (ab 0.9), DRIV 0 = am weichsten
        dn = 1.0
        if start:
            self.x1 += IMPULSE          # Anstoß vor dem ersten Sample (wie im DSP-Code)
            # HOLD (unipolar quadratisch): so viele Blöcke schwingt der Resonator ungedämpft
            u2 = (p["HOLD"] * p["HOLD"]) / 16384.0          # wie die Firmware: (v*v) << 9, Q23
            self.hold = int(u2 * HOLD_BLOCKS)
        if self.hold > 0:
            r = 1.0
            self.hold -= 1
        e = e0
        for i in range(BLOCK):
            pulse = 0.0
            if self.penv > 0.0005:
                pulse = pl * self.penv * (pc * self._noise() + self.p1)
                self.penv *= pcoef
            x_in = pulse * K_PULSE
            self.x1 = r * self.x1 - e * self.x2 + x_in
            self.x2 = r * self.x2 + e * self.x1
            e += de
            y = self.x1 + pulse * K_DIRECT
            if dv:
                y = cubic(y * dv) * dn
            self.lp += ta * (y - self.lp)
            out[i] = max(-1.0, min(1.0, self.lp * OUT_GAIN))
        self.e_prev = e1

        # Ruhe: Resonator und Puls praktisch verklungen
        if abs(self.x1) + abs(self.x2) < 0.0005 and self.penv <= 0.0005:
            self.quiet += 1
            if self.quiet > 8:
                self.active = False
                self.x1 = self.x2 = self.lp = 0.0
        else:
            self.quiet = 0
        return out


def render(params, trig_times, length_s):
    k = Kick2Dsp(params)
    trig_blocks = {int(t * FS) // BLOCK for t in trig_times}
    out = []
    for b in range(int(length_s * FS) // BLOCK):
        if b in trig_blocks:
            k.trigger()
        out.extend(k.render_block())
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", action="append", default=[], metavar="NAME=WERT")
    ap.add_argument("-o", "--output", default=os.path.join(os.path.dirname(__file__), "..", "demos", "kick2_dsp_start.wav"))
    a = ap.parse_args()
    params = {n.upper(): int(v) for n, v in (s.split("=") for s in a.set)}
    samples = render(params, [i * 0.5 for i in range(8)], 4.5)
    peak = write_wav(a.output, samples)
    print(f"{os.path.normpath(a.output)}: Spitze {20 * math.log10(peak):.1f} dBFS" if peak else "Stille")


if __name__ == "__main__":
    main()
