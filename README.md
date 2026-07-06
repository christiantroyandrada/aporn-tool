# aPornTool

**One command from raw sub-exposures to a finished, share-ready astrophoto.**

[![PyPI](https://img.shields.io/pypi/v/aporn-tool)](https://pypi.org/project/aporn-tool/) [![Python](https://img.shields.io/pypi/pyversions/aporn-tool)](https://pypi.org/project/aporn-tool/)

📦 **Install:** `pip install aporn-tool` — [releases](https://github.com/christiantroyandrada/aporn-tool/releases) · [changelog](CHANGELOG.md).

aPornTool takes a folder of raw astrophotography subs and drives them through the full
linear→nonlinear editing pipeline — stacking, photometric colour calibration, gradient and noise
removal, colour-preserving stretch, and star management — leaving only the deliverables in your
output folder and every scratch file tucked into a hidden working directory.

It's built for the **ZWO Seestar** workflow (internal calibration → no darks/flats/bias) but works
with any OSC `.fit` subs, and runs natively on **Windows, macOS (incl. Apple Silicon), and Linux**.

> **Design goal — processing parity:** on the *same* data, aim to match what a skilled processor
> would get, so the only remaining variable is capture (aperture, integration hours, sky darkness).
> The tool can't invent detail that isn't in the data — the final crop, curves, and watermark are
> yours to do from the 16-bit TIFF (Canva/Photoshop).

---

## Contents

- [How it works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [First-time setup](#first-time-setup)
- [Usage — from simplest to advanced](#usage--from-simplest-to-advanced)
- [Command reference](#command-reference)
- [Stages & resume](#stages--resume)
- [Output layout](#output-layout)
- [Configuration file](#configuration-file)
- [FAQ](#faq)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [Development](#development)

---

## How it works

```
raw .fit subs ──► stage ──► SIRIL: calibrate ─► register ─► stack ─► [SPCC] ─► golden linear stack
                                                                                       │
   deliverables ◄── finish ◄── [StarNet] ◄── [GraXpert BGE + denoise] ◄── [auto-crop] ◄┘
   (.tif/.png/.jpg/.fits)
```

- Each **stage** is checkpointed. The **golden linear stack** (`_work/<target>/02_linear/`) is the
  immutable re-processing anchor — re-finishing never re-stacks.
- The pipeline is **parameterised per mode**, not one-size-fits-all: registration, gradient tool,
  SPCC placement, and star handling differ (see the table below).

| Mode | Best for | Registration | Gradient | Stars |
|------|----------|--------------|----------|-------|
| `dso-mosaic` | galaxies & multi-panel — M31, M33, M51, M101, NGC7000 | WCS plate-solve (`framing=max`) | GraXpert BGE | StarNet2, blend some back |
| `dso-emission-nebula` | Hα HII / SNRs — M8, M20, M42, M16, Veil | star-based 2-pass | SIRIL `subsky` | keep all (rich field) |
| `dso-reflection-nebula` | blue scattered light — VdB106, M78 | star-based 2-pass | GraXpert BGE | dual-layer screen blend |
| `dso-star-cluster` | globulars & open clusters — M13, M22, M45, M44 | 2-pass (+FWHM cull) | SIRIL `subsky` | **keep all — stars are the subject** |

Planetary (video → AutoStakkert → finish) is planned; it requires a manual GUI stacking step.

---

## Prerequisites

| Tool | Role | Get it |
|------|------|--------|
| **Python 3.10+** | orchestrator | python.org / your package manager |
| **Siril 1.4+** (`siril-cli`) | stack, register, plate-solve, SPCC, StarNet | https://siril.org/download/ |
| **GraXpert 3.x** | background extraction + AI denoise (mosaic & reflection) | https://github.com/Steffenhir/GraXpert/releases |
| **StarNet2** | star removal | https://www.starnetastro.com/ |
| **ffmpeg / ffprobe** | planetary + final polish | ffmpeg.org / package manager |

Every DSO tool is natively cross-platform (incl. Apple Silicon). The tool locates each one on
`PATH`, then in the standard install locations per OS, then from `aporntool.config.json` — you
never hard-code paths.

<details>
<summary>Where the tools usually live per OS</summary>

| | Windows | macOS | Linux |
|--|--|--|--|
| siril-cli | `C:\Program Files\Siril\bin\siril-cli.exe` | `/Applications/Siril.app/Contents/MacOS/siril-cli` | `/usr/bin/siril-cli` |
| GraXpert | `%LOCALAPPDATA%\Programs\GraXpert\GraXpert.exe` | `/Applications/GraXpert.app/Contents/MacOS/GraXpert` | package / AppImage |
| StarNet2 | (set in SIRIL) | `/usr/local/bin/starnet2` | `/usr/local/bin/starnet2` |
| GraXpert AI models | `%LOCALAPPDATA%\GraXpert\GraXpert\{bge,denoise}-ai-models\` | `~/Library/Application Support/GraXpert/{bge,denoise}-ai-models/` | `~/.local/share/GraXpert/…` |
| SIRIL config | `%LOCALAPPDATA%\siril\` | `~/Library/Application Support/org.siril.Siril/siril/` | `~/.config/siril/` |

</details>

---

## Installation

**Already have Python 3.10+?** Install from PyPI:

```bash
pip install aporn-tool
```

That gives you the `aporn-tool` command. `python -m aporntool` also works as a module fallback
(the Python module keeps the one-word name — module names can't contain hyphens), and an `aporntool`
alias command is installed too, so either spelling runs.

<details>
<summary>Or install from source (for development / latest main)</summary>

```bash
git clone https://github.com/christiantroyandrada/aporn-tool.git
cd aporn-tool
python3 -m venv .venv
.venv/bin/python -m pip install -e .
# Windows: .venv\Scripts\python -m pip install -e .
```

</details>

> Installing the Python package does **not** install Siril/GraXpert/StarNet — those are separate
> apps (see [Prerequisites](#prerequisites)). Run `aporn-tool config --check` to confirm they're found.

---

## First-time setup

Run the discovery check — it prints where each tool was found and writes a starter config:

```bash
aporn-tool config --check
```

Then complete the three one-time setup steps (the tool's preflight checks the ones it can):

1. **GraXpert AI models** *(mosaic & reflection)* — open GraXpert once and run **Background
   Extraction** and **Denoise** on any image so it downloads the model files. Preflight verifies
   they exist *before* stacking, so a missing model fails in seconds, not after a 30-minute stack.
2. **StarNet inside SIRIL** *(mosaic)* — SIRIL's built-in `starnet` command runs the executable set
   in **SIRIL → Preferences → External Programs**. Being on `PATH` is **not** enough for mosaic
   mode. (Reflection mode calls the StarNet CLI directly, so it only needs it discoverable.)
3. **Local Gaia catalogs in SIRIL** *(SPCC colour calibration)* — online VizieR is retired. Install
   the sky region matching your target: **Milky Way** for galactic nebulae/low-latitude clusters,
   **Galaxy Season** for high-latitude galaxies. The wrong region → SPCC reports "no stars".

Validate everything without processing:

```bash
aporn-tool dso-mosaic --in "/path/to/subs" --out /path/to/out --target M31 --preflight-only
```

---

## Usage — from simplest to advanced

### 1. The simplest run

Point it at a folder of subs and pick the mode — that's all. The object name and coordinates are
read from the subs' FITS header, and the results land in a folder named after the target, right
beside your subs:

```bash
aporn-tool dso-mosaic --in "/path/to/M31 subs"
```

Produces `M31_final.tif` (16-bit — the real deliverable), `.png`, `.jpg` (quick-look), and `.fits`
next to the input; everything else lives under `_work/`.

Override either default when you want to: `--target` for a custom name, `--out` for a custom
location.

> ⚠️ **The output path must not contain spaces** (a SIRIL limitation). The default output inherits
> the subs' parent folder; if that path has spaces, pass a space-free `--out`. The `--in` path and
> sub filenames may contain spaces.

### 2. Other modes

```bash
aporn-tool dso-emission-nebula   --in "/data/M8"
aporn-tool dso-reflection-nebula --in "/data/M78"
aporn-tool dso-star-cluster      --in "/data/M13"
```

### 3. Combine multiple nights (more integration = the #1 quality lever)

`--in` is repeatable; all `.fit` from every source are staged and stacked together:

```bash
aporn-tool dso-mosaic \
  --in "/data/M31/2026-07-04" \
  --in "/data/M31/2026-07-05" \
  --out /data/out --target M31
```

### 4. A target not in the built-in catalog

Nothing special needed — the coordinates come from your subs' FITS header, so unlisted targets
(VdB 106, Sh2-155, …) just work. Pass `--target` only when you want a custom output name:

```bash
aporn-tool dso-reflection-nebula --in "/data/vdb106"
aporn-tool dso-emission-nebula   --in "/data/sh2-155" --target Sh2-155
```

### 5. Control the crop

Auto-crop (default) trims empty registration/mosaic borders. Override it:

```bash
# keep the full frame (no crop)
aporn-tool dso-mosaic --in "/data/M31" --out /data/out --target M31 --no-crop

# explicit SIRIL crop box: X Y W H (x from left, y from top)
aporn-tool dso-mosaic --in "/data/M31" --out /data/out --target M31 --crop "162 108 2310 4378"
```

### 6. Check status and resume

Re-running the **same command auto-resumes** at the first unfinished stage — nothing done is
repeated. Inspect the ledger any time:

```bash
aporn-tool status --out /data/out --target M31
```
```
dso-mosaic / M31  (fingerprint 8cd20ff7d100564d)
  calibrate  done
  register   done
  stack      done
  spcc       done
  bge        done
  denoise    done
  finish     failed
Resume at: finish
```

### 7. Re-run specific stages (cheap, from the golden anchor)

```bash
# redo colour calibration and everything after it (e.g. once the right Gaia region is installed)
aporn-tool dso-mosaic --in "/data/M31" --out /data/out --target M31 --redo spcc

# restart at a named stage
aporn-tool dso-mosaic --in "/data/M31" --out /data/out --target M31 --from finish

# ignore all checkpoints and re-run everything
aporn-tool dso-mosaic --in "/data/M31" --out /data/out --target M31 --force
```

### 8. The advanced, fully-specified run

```bash
aporn-tool dso-mosaic \
  --in "/data/M31/2026-07-04" --in "/data/M31/2026-07-05" \
  --out /data/out \
  --target M31 \
  --crop "162 108 2310 4378" \
  --star-reduce 0.35 \
  --config /data/my-aporntool.config.json \
  --redo spcc
```

- `--star-reduce 0.35` — after StarNet removes stars (mosaic), blend 35% of them back (lower =
  fewer/dimmer stars; default 0.5).
- `--config` — use a specific config file (tool paths, catalogs, Seestar defaults).
- `--redo spcc` — recompute from the `spcc` stage onward, reusing the stack.

---

## Command reference

```
aporn-tool <command> [options]
```

| Command | Purpose |
|---------|---------|
| `dso-mosaic`, `dso-emission-nebula`, `dso-reflection-nebula`, `dso-star-cluster` | process a target |
| `config --check [--config PATH]` | show tool discovery; write a starter config |
| `status --out PATH --target NAME` | print the resume ledger |
| `--version` | print the version |

**Options for the processing modes:**

| Option | Description |
|--------|-------------|
| `--in PATH` | subs folder — **required**, repeatable for multi-night |
| `--out PATH` | output root — optional; defaults to a `<TARGET>` folder beside the subs; must be space-free |
| `--target NAME` | object name — optional; auto-detected from the subs' FITS `OBJECT` header |
| `--crop "X Y W H"` | explicit SIRIL crop box (default: auto-crop) |
| `--no-crop` | disable auto-crop; keep the full frame |
| `--star-reduce F` | mosaic star blend-back fraction (default 0.5) |
| `--clean` | on success, delete working files except the golden anchor (reclaims disk) |
| `--from STAGE` | restart at this stage |
| `--redo STAGE` | re-run this stage + everything downstream |
| `--force` | re-run all stages, ignore checkpoints |
| `--preflight-only` | validate the environment, then stop |
| `--config PATH` | config file (default `aporntool.config.json`) |

Catalogued targets get canonical coordinates: `M3 M4 M5 M6 M7 M8 M11 M13 M15 M16 M20 M22 M31 M33 M42
M44 M45 M51 M81 M92 M101 NGC869 NGC6960 NGC7000`. Anything else uses the RA/DEC from your subs'
FITS header automatically.

---

## Stages & resume

Stage names are **per-mode** — run `aporn-tool status` to see yours. Current orders:

| Mode | Stages (what `--from` / `--redo` accept) |
|------|------------------------------------------|
| `dso-mosaic` | `calibrate → register → stack → spcc → bge → denoise → finish` |
| `dso-reflection-nebula` | `calibrate → register → stack → spcc → bge → denoise → finish` |
| `dso-emission-nebula` | `calibrate → register → stack → mirrorx → finish` |
| `dso-star-cluster` | `calibrate → register → stack → mirrorx → finish` |

A stage is only marked `done` after its output is verified (exists, non-empty, right type). A
crash or a raising stage is marked `failed` and reported with the log tail — re-run to resume.
Changing a parameter re-runs that stage and everything downstream, nothing upstream.

---

## Output layout

```
<OUT>/                       ← DELIVERABLES ONLY
├─ M31_final.tif             ← 16-bit, the real deliverable
├─ M31_final.png
├─ M31_final.jpg             ← quick-look
├─ M31_final.fits
└─ _work/                    ← everything scratch, hidden here
   └─ M31/
      ├─ 00_lights/          hardlinked .fit subs
      ├─ 01_process/         SIRIL sequences + frames
      ├─ 02_linear/          M31_Linear.fit  ← GOLDEN ANCHOR (never deleted)
      ├─ 03_graxpert/        BGE / denoise intermediates
      ├─ 05_finish/          finish scratch
      ├─ logs/               generated .ssf + per-stage stdout
      └─ aporntool.json      run manifest / resume state
```

Multiple targets can share one `--out` — each gets its own `_work/<target>/` and deliverables at
the root.

---

## Configuration file

`aporn-tool config --check` writes `aporntool.config.json`. Edit it to pin tool paths or set the
local Gaia catalogs:

```json
{
  "tool_paths": {
    "siril": "/Applications/Siril.app/Contents/MacOS/siril-cli",
    "graxpert": "/Applications/GraXpert.app/Contents/MacOS/GraXpert",
    "starnet2": "/usr/local/bin/starnet2",
    "ffmpeg": "/opt/homebrew/bin/ffmpeg"
  },
  "seestar_focal_mm": 150.0,
  "seestar_pixel_um": 2.9,
  "catalog_astro": null,
  "catalog_photo": null
}
```

Resolution order for each tool: **explicit config path → `PATH` → known install locations.**

---

## FAQ

**Do I need darks/flats/bias?** No — the Seestar calibrates internally. For other rigs, calibrate
your subs beforehand (the tool ingests already-calibrated `.fit`).

**How many subs do I need?** More integration is the biggest quality lever. Combine nights with
repeated `--in`. There's no hard minimum, but a handful of subs won't stack meaningfully.

**Will it delete my raw data?** No. Subs are hardlinked into `_work/00_lights/`; the golden linear
stack and your originals are never overwritten.

**Can I re-process without re-stacking?** Yes — that's the point of the golden anchor. Tweak a
finishing parameter and re-run; only `finish` (or the changed stage onward) recomputes.

**It didn't crop the mosaic tightly.** Auto-crop is deliberately conservative (it never cuts faint
data). Pass an explicit `--crop "X Y W H"`, or do the final crop by hand in Canva/Photoshop.

**Which mode for the Pleiades (M45)?** It's an open cluster in blue reflection nebulosity — use
`dso-reflection-nebula`, not the plain cluster finish.

**Does it need a GPU?** No. GraXpert uses the GPU when available and falls back to CPU.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `no StarNet executable set` (mosaic) | Set StarNet in **SIRIL → Preferences → External Programs**. PATH alone isn't enough for mosaic. |
| Preflight: GraXpert models missing (but installed) | Open GraXpert, run BGE + Denoise once so it downloads the model files. |
| SPCC "no stars" / imprecise | Install the Gaia region matching the target (Milky Way vs Galaxy Season). |
| `--out path must not contain spaces` | Choose a space-free output folder (SIRIL limitation). |
| `golden anchor not found` on `--from`/`--redo` | Run the full pipeline first (drop `--from`/`--redo`) so preprocess produces the anchor. |
| Plate-solving fails on a mosaic | Ensure SIRIL's astrometry catalog is installed; the tool verifies solves by frame count, not exit code. |
| Faint colour fringe left after auto-crop | Expected on noisy mosaic edges — use `--crop`, or finish the crop in post. |

Every stage saves its SIRIL script and stdout under `_work/<target>/logs/` — check `<stage>.log`
for the exact tool error.

---

## Limitations

- **Deconvolution / wavelets are skipped** for undersampled Seestar data (they amplify noise
  without adding real detail).
- **The last 5%** — final crop, curves, watermark — is done by hand from the 16-bit TIFF.
- **Planetary** needs a manual AutoStakkert stacking step (no usable CLI) and is not yet shipped.
- **Auto-crop is conservative** and may leave a thin edge fringe on irregular mosaics.

---

## Development

```bash
.venv/bin/python -m pip install -e . pytest pytest-timeout
.venv/bin/python -m pytest -q          # unit suite; external tools are mocked
```

Tests mock Siril/GraXpert/StarNet, so they run anywhere. Integration runs need the real tools and
real subs. See [REQUIREMENTS.md](REQUIREMENTS.md) for the full design, the per-mode pipeline
contract, and the load-bearing SIRIL/GraXpert/StarNet gotchas.
