# DBX-K2 – Resonator Kick for the Elektron Machinedrum

A USR machine for the Machinedrum running jmamma's MDX firmware **X.20**
(Machine Dump Standard, MDS 1.1).

DBX-K2 is a resonator kick drum in the spirit of the Korg Volca Kick, ported from my DIY
groovebox (doergbox, Teensy 4.1, built on the [MicroDexed-touch](https://codeberg.org/positionhigh/MicroDexed-touch) firmware). Each trigger strikes a tuned resonator. Its pitch sweeps
down from a higher start, then it rings out like a struck drum skin. A short click or noise
burst adds the attack, and an optional saturation stage and lowpass shape the result. The
initial transient is intentionally hard and punchy: the resonator starts at full swing, and
very hot settings clip briefly at the output.

Runs on **MKI and MKII, on all 16 tracks**. Certified cycle counts per track and block:
MKII 2,476 · MKI (DRAM) 2,807 · MKI (SRAM) 2,481. Tested on a MKII +Drive UW.

## Status & known limitations

This is my first USR machine and a first attempt – and honestly nothing special: just
another kick for the Machinedrum, with its own flavour. Known weak spots:

- **COLR** has too little audible effect; it will become more useful in the next version.
- Comments in the source and tools are in **German**.
- Tested on hardware so far on a single MKII +Drive UW; on MKI it is certified, not yet
  played.

## How this was made

The sound design comes from the KICK2 of my doergbox groovebox. That machine grew over
roughly 300 iterations in which I shaped how it should sound and behave – the resonator
principle, the attack pulse, the character of the hard transient – developed together
with AI. For this Machinedrum port I set the goals, made the sound decisions and tested on
the hardware; [Claude Code](https://claude.com/claude-code) (Anthropic) wrote the DSP56303
code, the Python models and the tooling, and ran the certification.

## Knobs

| Knob | Function |
|---|---|
| **PTCH** | Base pitch of the resonator, 30–150 Hz |
| **BEND** | Depth of the pitch sweep at the start, 0–5 octaves above PTCH |
| **BTIM** | Speed of the pitch sweep, 3–300 ms |
| **DCAY** | Ring-out time of the resonator, 40 ms to 3 s (to −40 dB) |
| **PULS** | Strength of the attack pulse. It is heard directly and also pushes the resonator for extra punch |
| **COLR** | Character of the attack pulse: from a short click (0) to a longer noise burst (127), 1.5–11.5 ms |
| **DRIV** | Saturation, from off (0) to heavily driven |
| **TONE** | Lowpass filter, roughly 200 Hz to 18 kHz |

Tips: Low PTCH with BEND 0 and long DCAY gives a deep, booming sub that is easy to
overdrive. High BEND with short BTIM gives zappy electro kicks. High COLR with a little BEND
makes noisy, industrial attacks. Raise DRIV for dirt on purpose.

## Installation

Download the files from the [Releases](../../releases) page:

- `kick2-<version>.slot1.syx` – ready to send, installs to **USR slot 01** (overwrites
  whatever is there).
- `kick2-<version>.mds` – the certified package, if you want to create a SysEx file for
  another slot: `python3 vendor/mds-tools/tools/mds_to_syx.py kick2-<version>.mds --slot N`.

The transfer is acknowledged message by message, so leave a short pause between SysEx
messages, e.g. on Linux:

```sh
amidi -l
amidi -p hw:1,0,0 -s kick2-0.7.slot1.syx -i 300
```

A failed transfer never replaces the machine already installed in a slot.

As jmamma points out: only install MDS machines from developers you trust – machine code
runs directly on the DSP.

## Repository layout

| Path | Content |
|---|---|
| `machines/kick2/kick2.asm56k` | DSP56303 source |
| `machines/kick2/kick2.json` | MDS machine definition (parameters, memory, relocations) |
| `machines/kick2/model/kick2_ref.py` | Floating-point reference of the original doergbox KICK2 |
| `machines/kick2/model/kick2_dsp.py` | Model with the same structure as the DSP code |
| `tools/mds_build.py` | Assemble, package, certify, create SysEx |
| `tools/render/` | `mds-render`: runs a `.mds` in the certifier's DSP emulator and writes a WAV |
| `tools/compare_kick2.py` | Compares the emulated DSP code with the Python model |
| `vendor/MDS`, `vendor/mds-tools` | jmamma's specification and tools (git submodules) |

Comments in the source and tools are in German.

## Building

Tested on Fedora Linux. You need Python 3.10+, CMake, a C++17 compiler, `patch` and Wine.

1. Clone with submodules:
   `git clone --recurse-submodules https://github.com/MonCalamari/DBX-K2.git`
2. Assembler: install NXP **Symphony Studio** (Windows installer, contains `asm56300.exe`
   and `cldlod.exe`) under Wine. It is proprietary and not part of this repository.
   `tools/mds_build.py` looks for it in the Wine prefix `~/dsp-tools/wine-symphony`;
   override with `MDS_WINEPREFIX` or `MDS_DSP_TOOLS`.
   `python3 tools/mds_build.py --verify` checks the toolchain against jmamma's example
   machines (all must be byte-identical).
3. Certifier (on Linux, the emulator build needs two extra include paths):
   ```sh
   cmake -S vendor/mds-tools -B vendor/mds-tools/build -DCMAKE_BUILD_TYPE=Release \
         -DCMAKE_CXX_FLAGS="-I$PWD/vendor/mds-tools/external/dsp56300/source"
   cmake --build vendor/mds-tools/build -j"$(nproc)"   # stops at vtuneSdk the first time
   ln -sfn "$PWD/vendor/mds-tools/external/dsp56300/source/vtuneSdk" \
           vendor/mds-tools/build/certifier/dsp56300/source/vtuneSdk
   cmake --build vendor/mds-tools/build -j"$(nproc)"
   ```
4. Build, certify (takes a while) and create the SysEx file for slot 1:
   `python3 tools/mds_build.py machines/kick2 --certify --slot 1` → `build/kick2/`
5. Optional, to listen without hardware: `tools/render/build.sh`, then
   `tools/render/mds-render build/kick2/kick2.mds out.wav -p 6=90` (parameter index = value).

## How it works (short)

- Resonator in "magic circle" form with 48-bit states: decay and frequency are separate,
  and even very long decays keep fading instead of getting stuck in rounding.
- Pitch sweep envelope per block, frequency interpolated linearly within the block.
- All knob curves come from one cubic 2^x routine (error < 0.25 cent); decay, pulse and
  tone coefficients are recomputed in rotation, one per block.
- Saturation uses the DSP's limiter plus a cubic curve (1.5u − 0.5u³).

## Credits

- [Claude Code](https://claude.com/claude-code) (Anthropic) for the DSP code, models and
  tooling of this port (see "How this was made").
- jmamma for the MDX firmware, the Machine Dump Standard and mds-tools.
- positionhigh, developer of [MicroDexed-touch](https://codeberg.org/positionhigh/MicroDexed-touch),
  the firmware my doergbox is built on – thanks and greetings!
- The dsp56300 emulator project (used inside mds-certifier).

## License

GPL-3.0 – see [LICENSE](LICENSE). The submodules keep their own licenses.
