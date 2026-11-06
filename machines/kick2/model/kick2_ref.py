#!/usr/bin/env python3
"""KICK2 – Gleitkomma-Referenzmodell nach doergbox (src/dsp/reso_kick.cpp,
src/engine/kick2_engine.cpp), angepasst an die Machinedrum: 44.100 Hz, Blöcke zu
32 Samples, keine Retrigs, kein Accent.

Standard ist der Charakter der doergbox, einschließlich des Überschwingers: Bei BEND 0
und tiefem PTCH schaukelt der Puls den Resonator bis ≈ +21 dB auf; der Ausgang wird dann
hart bei Vollaussteuerung gekappt (doergbox: 16 Bit, DSP: Sättigung beim Speichern).
Gewollt so (Entscheidung des Users, 0.3). Im DSP-Code brauchen die Zustände dafür
Reserve, gekappt wird erst am Ausgang.

Nur zum Vergleich: --clean normiert den Puls-Anstoß (PULSE_NORM) und fügt eine
Pegelreserve (HEADROOM) vor DRIV ein – nichts übersteuert ohne DRIV.

Nur Standardbibliothek. Dient als Klangreferenz für das spätere Festkomma-Modell
und den DSP-Code.

  python3 kick2_ref.py                    Demo mit dem Startpreset nach ../demos/
  python3 kick2_ref.py --set DCAY=110     Regler abweichend setzen (0..127)
  python3 kick2_ref.py --clean            saubere Variante (zum Vergleich)
"""
import argparse
import math
import os
import struct
import wave

FS = 44100.0
BLOCK = 32
PULSE_NORM = 2.0      # Puls-Anstoß = 2 × Grundanstoß bei PULS 127 (Fläche, unabhängig von COLR)
HEADROOM = 0.434      # schlimmster Fall ohne DRIV ≈ −1 dBFS, Startpreset ≈ −6 dBFS

# Startpreset = Defaults aus kick2.json
DEFAULTS = {"PTCH": 45, "BEND": 70, "BTIM": 40, "DCAY": 70,
            "PULS": 71, "COLR": 20, "DRIV": 0, "TONE": 110}
# Machinedrum-Version ab 0.8: COLR fest auf 20, an seiner Stelle HOLD (0 = wie bisher)
DEFAULTS_MD = {"PTCH": 33, "BEND": 75, "BTIM": 20, "DCAY": 40,     # ab 0.9: EBM-Startpreset,
               "PULS": 100, "HOLD": 50, "DRIV": 70, "TONE": 105}  # PTCH 38..160 Hz


def map_exp(v, a, b):
    return a * (b / a) ** (v / 127.0)


def soft_clip(x):
    if x > 3.0:
        return 1.0
    if x < -3.0:
        return -1.0
    x2 = x * x
    return x * (27.0 + x2) / (27.0 + 9.0 * x2)


class Kick2:
    def __init__(self, params=None, clean=False):
        self.clean = clean
        self.p = dict(DEFAULTS)
        if params:
            self.p.update(params)
        self.ic1 = self.ic2 = self.env = self.p_env = self.lp = 0.0
        self.a1 = self.a2 = self.a3 = 0.0
        self.g = 0.01
        self.c_f = self.c_k = -1.0
        self.noise = 22222
        self.quiet = 0
        self.active = False
        self.start = False

    # ---- Reglerwerte -> interne Größen (kick2_engine.cpp apply/trigger) ----
    def _derived(self):
        p = self.p
        base_hz = map_exp(p["PTCH"], 30.0, 150.0)
        bend_oct = p["BEND"] / 127.0 * 5.0
        btim_ms = min(max(map_exp(p["BTIM"], 3.0, 300.0), 1.0), 2000.0)
        bend_coef = math.exp(-1.0 / (btim_ms * FS / 1000.0))
        ring_s = map_exp(p["DCAY"], 40.0, 3000.0) / 1000.0
        p_level = min(max(p["PULS"] / 127.0, 0.0), 1.0)     # beim Trig linear (ohne Accent)
        p_colour = p["COLR"] / 127.0
        amount = p["DRIV"] / 127.0
        if amount <= 0.0:
            drv, drv_norm = 0.0, 1.0
        else:
            drv = 1.0 + 15.0 * amount * amount
            drv_norm = 1.0 / soft_clip(drv)
        tone_hz = min(max(map_exp(p["TONE"], 200.0, 18000.0), 50.0), 20000.0)
        tone_a = 1.0 - math.exp(-2.0 * math.pi * tone_hz / FS)
        return base_hz, bend_oct, bend_coef, ring_s, p_level, p_colour, drv, drv_norm, tone_a

    def trigger(self):
        self.start = True

    def render_block(self):
        """Ein Block mit 32 Samples (wie RENDER auf dem DSP)."""
        out = [0.0] * BLOCK
        start = self.start
        self.start = False
        if start:
            self.env = 1.0
            self.p_env = 1.0
            self.active = True
            self.quiet = 0
        if not self.active:
            return out

        base, bo, bc, ring_s, pl, pc, dv, dn, ta = self._derived()
        k_time = math.log(100.0) / (math.pi * min(max(ring_s, 0.01), 5.0))   # -40 dB nach ring_s
        p_tau = (1.5 + 10.0 * pc) * FS / 1000.0                              # Klick 1,5 ms .. Rauschen 11,5 ms
        p_coef = math.exp(-1.0 / p_tau)
        if self.clean:
            kp, head, quiet_lvl = PULSE_NORM * 0.5 / p_tau, HEADROOM, 0.0003 * HEADROOM
        else:
            kp, head, quiet_lvl = 0.08, 1.0, 0.0003
        peak = 0.0
        for i in range(BLOCK):
            if (i & 3) == 0:                      # Koeffizienten alle 4 Samples
                e = bo * self.env
                f = base * 2.0 ** e if abs(e) > 1e-6 else base
                f = min(f, 16000.0)
                if f != self.c_f or k_time != self.c_k:
                    self.c_f, self.c_k = f, k_time
                    self.g = math.tan(math.pi * f / FS)
                    k = k_time / f
                    self.a1 = 1.0 / (1.0 + self.g * (self.g + k))
                    self.a2 = self.g * self.a1
                    self.a3 = self.g * self.a2
            self.env *= bc
            if self.env < 1e-7:
                self.env = 0.0
            pulse = 0.0
            if self.p_env > 0.0005:
                self.noise = (self.noise * 1664525 + 1013904223) & 0xFFFFFFFF
                nz = (self.noise - (1 << 32) if self.noise & 0x80000000 else self.noise) / 2147483648.0
                pulse = pl * self.p_env * (pc * nz + (1.0 - pc))
                self.p_env *= p_coef
            x = pulse * kp / self.g
            if start and i == 0:
                x += 0.5 / self.g
            v3 = x - self.ic2
            v1 = self.a1 * self.ic1 + self.a2 * v3
            v2 = self.ic2 + self.a2 * self.ic1 + self.a3 * v3
            self.ic1 = 2.0 * v1 - self.ic1
            self.ic2 = 2.0 * v2 - self.ic2
            y = (v1 + pulse * 1.2) * head
            if dv > 0.0:
                y = soft_clip(y * dv) * dn
            self.lp += ta * (y - self.lp)
            o = max(-1.0, min(1.0, self.lp * 0.9 * 0.8))   # 0.8 = outGain doergbox; Kappen wie dort
            peak = max(peak, abs(o))
            out[i] = o
        # nach ~0,3 s fast Stille: Ruhe bis zum nächsten Trig (doergbox: 100 Blöcke à 128 = 400 à 32)
        if peak < quiet_lvl:
            self.quiet += 1
            if self.quiet > 400:
                self.active = False
                self.ic1 = self.ic2 = self.lp = 0.0
        else:
            self.quiet = 0
        return out


def render(params, trig_times, length_s, clean=False):
    k = Kick2(params, clean)
    trig_blocks = {int(t * FS) // BLOCK for t in trig_times}
    out = []
    for b in range(int(length_s * FS) // BLOCK):
        if b in trig_blocks:
            k.trigger()
        out.extend(k.render_block())
    return out


def write_wav(path, samples):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    peak = max((abs(s) for s in samples), default=0.0)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(3)
        w.setframerate(int(FS))
        w.writeframes(b"".join(struct.pack("<i", int(round(max(-1.0, min(1.0, s)) * 8388607)))[:3]
                               for s in samples))
    return peak


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", action="append", default=[], metavar="NAME=WERT")
    ap.add_argument("--clean", action="store_true", help="Puls normiert + Pegelreserve (nur Vergleich)")
    ap.add_argument("-o", "--output", default=os.path.join(os.path.dirname(__file__), "..", "demos", "kick2_start.wav"))
    a = ap.parse_args()
    params = {}
    for s in a.set:
        n, v = s.split("=")
        params[n.upper()] = int(v)
    # 4/4 bei 120 BPM, zwei Takte
    trigs = [i * 0.5 for i in range(8)]
    samples = render(params, trigs, 4.5, a.clean)
    peak = write_wav(a.output, samples)
    print(f"{os.path.normpath(a.output)}: Spitze {20 * math.log10(peak):.1f} dBFS" if peak else "Stille")


if __name__ == "__main__":
    main()
