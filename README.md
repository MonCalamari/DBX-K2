# DBX-K2 – Resonator Kick for the Elektron Machinedrum

A USR machine for the Machinedrum running jmamma's MDX firmware **X.20**
(Machine Dump Standard, MDS 1.1).

DBX-K2 is a resonator kick drum in the spirit of the Korg Volca Kick, ported from my DIY
groovebox (doergbox, Teensy 4.1, built on the [MicroDexed-touch](https://codeberg.org/positionhigh/MicroDexed-touch) hardware, with my own firmware written from scratch). Each trigger strikes a tuned resonator. Its pitch sweeps
down from a higher start, then it rings out like a struck drum skin – or, with HOLD, keeps
ringing at full level and then cuts off. A short click adds the attack; a saturation stage
(from gentle to brutal) and a lowpass shape the result. The initial transient is
intentionally hard and punchy: the resonator starts at full swing.

Runs on **MKI and MKII, on all 16 tracks**. Certified cycle counts per track and block:
MKII 2,508 · MKI (DRAM) 2,850 · MKI (SRAM) 2,513. Tested on a MKII +Drive UW.

🔊 Sound example (0.9): [dbx-k2-0.9-example.mp3](https://github.com/MonCalamari/DBX-K2/releases/download/kick2-v0.9/dbx-k2-0.9-example.mp3)
– a quick recording straight from a Machinedrum MKII: the default sound first, then some
knob turning. Not polished and not always in time, but it gives an idea of the sound. No
filter, no EQ, no other processing on the Machinedrum or afterwards – only the level was
raised.

## Status & known limitations

This is my first USR machine and a first attempt – and honestly nothing special: just
another kick for the Machinedrum, with its own flavour. Known weak spots:

- Comments in the source and tools are in **German**.
- Tested on hardware so far on a single MKII +Drive UW; on MKI it is certified, not yet
  played.

## How this was made

The sound design comes from the KICK2 of my doergbox groovebox. The groovebox has grown
over more than 300 iterations, developed together with AI, and the KICK2 is one of its
machines: over that time I shaped how it should sound and behave – the resonator
principle, the attack pulse, the character of the hard transient. For this Machinedrum port I set the goals, made the sound decisions and tested on
the hardware; [Claude Code](https://claude.com/claude-code) (Anthropic) wrote the DSP56303
code, the Python models and the tooling, and ran the certification.

## Knobs

| Knob | Function |
|---|---|
| **PTCH** | Base pitch of the resonator, 38–160 Hz |
| **BEND** | Depth of the pitch sweep at the start, 0–5 octaves above PTCH |
| **BTIM** | Speed of the pitch sweep, 3–300 ms |
| **DCAY** | Ring-out time of the resonator, 40 ms to 3 s (to −40 dB) |
| **PULS** | Strength of the attack pulse. It is heard directly and also pushes the resonator for extra punch |
| **HOLD** | Time after the hit during which the resonator rings on at full level before DCAY takes over, 0 to ~245 ms. Gives a fat, pressed, gated punch; 0 = classic decay |
| **DRIV** | Saturation, from gentle (0) to heavily driven. The soft saturation is always on and catches the peaks |
| **TONE** | Lowpass filter, roughly 200 Hz to 18 kHz |

Made for hard modern EBM, industrial and dark techno on big systems. The default sound is a
short, pressed, driven kick (PTCH 33 ≈ 55 Hz, BEND 75, BTIM 20, DCAY 40, PULS 100, HOLD 50,
DRIV 70, TONE 105).

Tips: A little HOLD with a short DCAY gives a fat, boxy kick that cuts off cleanly – add DRIV
for brutal. High BEND with short BTIM gives zappy electro kicks. Low PTCH with BEND 0 and long
DCAY gives a deep, booming sub.

## Repository layout

| Path | Content |
|---|---|
| `machines/kick2/kick2.asm56k` | DSP56303 source |
| `machines/kick2/kick2.json` | MDS machine definition (parameters, memory, relocations) |
| `machines/kick2/kick2.pbm` | Machine logo, 32 × 24 pixels |
| `machines/kick2/model/kick2_ref.py` | Floating-point reference of the original doergbox KICK2 |
| `machines/kick2/model/kick2_dsp.py` | Model with the same structure as the DSP code |
| `tools/mds_build.py` | Assemble, package, certify, create SysEx |
| `tools/render/` | `mds-render`: runs a `.mds` in the certifier's DSP emulator and writes a WAV |
| `tools/compare_kick2.py` | Compares the emulated DSP code with the Python model |
| `vendor/MDS`, `vendor/mds-tools` | jmamma's specification and tools (git submodules) |

Comments in the source and tools are in German.

## How it works (short)

- Resonator in "magic circle" form with 48-bit states: decay and frequency are separate,
  and even very long decays keep fading instead of getting stuck in rounding.
- Pitch sweep envelope per block, frequency interpolated linearly within the block.
- All knob curves come from one cubic 2^x routine (error < 0.25 cent); decay and tone
  coefficients are recomputed in alternation, one per block.
- HOLD sets the resonator's damping to zero for a number of blocks after the hit.
- Saturation uses the DSP's limiter plus a cubic curve (1.5u − 0.5u³); it is always on.

## Credits

- [Claude Code](https://claude.com/claude-code) (Anthropic) for the DSP code, models and
  tooling of this port (see "How this was made").
- jmamma for the MDX firmware, the Machine Dump Standard and mds-tools.
- positionhigh, developer of [MicroDexed-touch](https://codeberg.org/positionhigh/MicroDexed-touch),
  the hardware my doergbox is built on – thanks and greetings!
- The dsp56300 emulator project (used inside mds-certifier).

## License

GPL-3.0 – see [LICENSE](LICENSE). The submodules keep their own licenses.

## Changelog

- **0.9** – COLR replaced by **HOLD**; PTCH range 38–160 Hz; new default sound for EBM;
  saturation always on (DRIV 0 used to hard-clip the output); machine logo.
- **0.7** – first public release.
