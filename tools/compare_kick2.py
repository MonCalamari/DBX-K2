#!/usr/bin/env python3
"""Vergleicht die KICK2 im DSP-Emulator (build/kick2/kick2.mds) mit model/kick2_dsp.py.
Aufruf: tools/compare_kick2.py [NAME=WERT ...]"""
import math, os, subprocess, sys, tempfile, wave
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "machines", "kick2", "model"))
import kick2_dsp as D  # noqa: E402
NAMES = ["PTCH", "BEND", "BTIM", "DCAY", "PULS", "COLR", "DRIV", "TONE"]
params = {n.upper(): int(v) for n, v in (a.split("=") for a in sys.argv[1:])}
with tempfile.TemporaryDirectory() as tmp:
    wav = os.path.join(tmp, "e.wav")
    cmd = [os.path.join(ROOT, "tools", "render", "mds-render"), os.path.join(ROOT, "build", "kick2", "kick2.mds"),
           wav, "-s", "1.05", "-t", "2.0", "-f", "0.05"]
    for n, v in params.items():
        cmd += ["-p", f"{NAMES.index(n)}={v}"]
    info = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
    w = wave.open(wav); d = w.readframes(w.getnframes())
emu = [int.from_bytes(d[i:i + 3], "little", signed=True) / 8388608 for i in range(0, len(d), 3)]
k = D.Kick2Dsp(params); mod = []
pre = int(0.05 * 44100) // 32                 # Vorlauf: Koeffizienten laufen schon mit
for b in range(len(emu) // 32):
    if b == pre:
        k.trigger()
    mod += k.render_block()
emu, mod = emu[pre * 32:], mod[pre * 32:]
def db(s, ms):
    n = int(ms * 44.1); seg = s[n:n + 441]
    return 20 * math.log10(math.sqrt(sum(x * x for x in seg) / len(seg)) + 1e-12)
n = 13230
corr = sum(a * b for a, b in zip(emu[:n], mod[:n])) / math.sqrt(sum(a * a for a in emu[:n]) * sum(b * b for b in mod[:n]) + 1e-30)
print(params or "Startpreset", "|", info.split(": ", 1)[1])
print("  RMS dB Emu|Modell: " + "  ".join(f"{ms}ms {db(emu, ms):6.1f}|{db(mod, ms):6.1f}" for ms in (0, 20, 60, 150, 400, 800)))
print(f"  Korrelation 0..300 ms: {corr:.4f}")
