# aPornTool

**One command from raw sub-exposures to a finished, share-ready astrophoto.**

[![PyPI](https://img.shields.io/pypi/v/aporn-tool)](https://pypi.org/project/aporn-tool/) [![Python](https://img.shields.io/pypi/pyversions/aporn-tool)](https://pypi.org/project/aporn-tool/)

📦 **Install:** `pip install aporn-tool` - [releases](https://github.com/christiantroyandrada/aporn-tool/releases) · [changelog](CHANGELOG.md).

aPornTool takes a folder of raw astrophotography subs and drives them through the full
linear-to-nonlinear editing pipeline: stacking, photometric colour calibration, gradient and noise
removal, colour-preserving stretch, and star management. Only the deliverables land in your output
folder; scratch files get tucked into a hidden working directory.

It's built for the **ZWO Seestar** workflow (internal calibration → no darks/flats/bias) but works
with any OSC `.fit` subs, and runs natively on **Windows, macOS (incl. Apple Silicon), and Linux**.

> **Design goal: processing parity.** On the *same* data, aim to match what a skilled processor
> would get, so the only remaining variable is capture (aperture, integration hours, sky darkness).
> The tool can't invent detail that isn't in the data. The final crop, curves, and watermark are
> yours to do from the 16-bit TIFF (Canva/Photoshop).

---

## Contents

- [How it works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [First-time setup](#first-time-setup)
- [Usage](#usage--from-simplest-to-advanced)
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
  immutable re-processing anchor. Re-finishing never re-stacks.
- The pipeline is **parameterised per mode**: registration, gradient tool, SPCC placement, and
  star handling all differ depending on what you're shooting (see the table below).

| Mode | Best for | Registration | Gradient | Stars |
|------|----------|--------------|----------|-------|
| `dso-galaxy` | galaxies - M31, M33, M51, M101, M81 (**mosaic auto-detected** from the subs' pointing spread; override `--mosaic`/`--single`) | WCS `framing=max`+`feather` (mosaic) or `register -2pass`+`mirrorx` (single) | GraXpert BGE | composite dual-layer (StarNet2), blend some back |
| `dso-emission-nebula` | Hα HII / SNRs - M8, M20, M42, M16, Veil | star-based 2-pass | SIRIL `subsky` | keep all (rich field) |
| `dso-reflection-nebula` | blue scattered light - VdB106, M78 | star-based 2-pass | GraXpert BGE | dual-layer screen blend |
| `dso-star-cluster` | globulars & open clusters - M13, M22, M45, M44 | 2-pass (+FWHM cull) | SIRIL `subsky` | **keep all, stars are the subject** |
| `dso-milky-way` | **wide-field Milky Way from a phone/camera** (JPEG/HEIC/PNG/TIFF stills, not FITS) | single-pass global (no cull) | GraXpert BGE (high smoothing) | **keep all, stars are the subject** |

`dso-milky-way` is the odd one out: it ingests already-processed camera **stills** instead of raw
FITS subs, so it skips calibration, plate-solving, and SPCC. Put your phone on anything steady, take
a dozen-plus frames of the same patch of sky, and it stacks them to pull the galactic core out of the
noise. See [the Milky Way section](#2b-wide-field-milky-way-from-a-phone) below.

Planetary (video → AutoStakkert → finish) is planned; it requires a manual GUI stacking step.

---

## Prerequisites

| Tool | Role | Get it |
|------|------|--------|
| **Python 3.10+** | orchestrator | python.org / your package manager |
| **Siril 1.4+** (`siril-cli`) | stack, register, plate-solve, SPCC, StarNet | https://siril.org/download/ |
| **GraXpert 3.x** | background extraction + AI denoise (galaxy & reflection) | https://github.com/Steffenhir/GraXpert/releases |
| **StarNet2** | star removal | https://www.starnetastro.com/ |
| **ffmpeg / ffprobe** | planetary + final polish | ffmpeg.org / package manager |

Every DSO tool runs natively cross-platform (incl. Apple Silicon). The tool locates each one on
`PATH`, then in the standard install locations per OS, then from `aporntool.config.json`. You
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
(module names can't contain hyphens, so the Python package keeps the one-word `aporntool` name),
and an `aporntool` alias command is installed too. Either spelling works.

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

> Installing the Python package does **not** install Siril/GraXpert/StarNet. Those are separate
> apps (see [Prerequisites](#prerequisites)). Run `aporn-tool config --check` to confirm they're found.

---

## First-time setup

Run the discovery check. It prints where each tool was found and writes a starter config:

```bash
aporn-tool config --check
```

Then complete the three one-time setup steps (the tool's preflight checks the ones it can):

1. **GraXpert AI models** *(mosaic & reflection)* - open GraXpert once and run **Background
   Extraction** and **Denoise** on any image so it downloads the model files. Preflight verifies
   they exist *before* stacking, so a missing model fails in seconds, not after a 30-minute stack.
2. **StarNet2** *(galaxy, emission, reflection)* - the composite dual-layer finish calls the StarNet2
   CLI directly, so it just needs to be **discoverable** (set `tool_paths.starnet2` in the config, or
   have it on `PATH`). No SIRIL-internal StarNet configuration is required. (Star-cluster keeps all
   its stars and needs no StarNet.)
3. **Local Gaia catalogs in SIRIL** *(SPCC colour calibration)* - online VizieR is retired. Install
   the sky region matching your target: **Milky Way** for galactic nebulae/low-latitude clusters,
   **Galaxy Season** for high-latitude galaxies. Wrong region → SPCC reports "no stars".

Validate everything without processing:

```bash
aporn-tool dso-galaxy --in "/path/to/subs" --out /path/to/out --target M31 --preflight-only
```

---

## Usage — from simplest to advanced

### 1. The simplest run

Point it at a folder of subs and pick the mode, that's all. The object name and coordinates are
read from the subs' FITS header, and the results land in a folder named after the target, right
beside your subs:

```bash
aporn-tool dso-galaxy --in "/path/to/M31 subs"
```

Produces `M31_final.tif` (16-bit, the real deliverable), `.png`, `.jpg` (quick-look), and `.fits`
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

### 2b. Wide-field Milky Way from a phone

`dso-milky-way` takes a folder of camera/phone **stills** (`.jpg .jpeg .png .tif .tiff .heic`) instead
of FITS subs — no `--target` needed (the run is just named `MilkyWay`):

```bash
aporn-tool dso-milky-way --in "/path/to/phone shots"
```

How to shoot for it: point at the Milky Way and take a dozen or more frames of roughly the **same**
framing (Night Mode or a long-exposure app gives the most signal). The tool aligns on the stars, so
even a hand-held burst stacks fine — star registration is invariant to the shift and rotation between
frames. More frames = less noise. Needs SIRIL + GraXpert (no StarNet, no Gaia catalog).

**Hand-held? Add `--no-tripod`.** Because the tool aligns on the *stars*, a *fixed* foreground
(rooftops, trees, wires) smears into a ghost as the framing drifts between hand-held frames — that is
the one thing star-aligned stacking can't fix. `--no-tripod` recovers a sharp foreground: it keeps the
deep **stacked** sky but paints the foreground back in from a **single** frame.

```bash
aporn-tool dso-milky-way --in "/path/to/phone shots" --out ~/Pictures/mw_out --no-tripod
```

It finds the foreground automatically from how much each pixel *moves* between the registered frames
(the sky is aligned = still; the foreground drifts = moving) — no horizon line to draw, and it works
whether your foreground is along the bottom, the side, or scattered rooftops. Hand-held drift also
leaves a wider ragged, colour-fringed border around the stack. For a clean, fringe-free framing, pass
an explicit `--crop "X Y W H"` box that crops *past* that border (the default auto-crop keeps the
border as a mild sky fringe rather than risk clipping into it). On a real tripod, leave `--no-tripod`
off (there's no ghost to fix). Tuning knobs live under `pipeline.no_tripod` in the config.

Two practical notes:
- **Output path with spaces:** phone shots often live under a spaced path (e.g. `~/Pictures/Milky Way`),
  and the default `--out` lands beside them, which SIRIL can't handle. Pass an explicit space-free
  `--out`, e.g. `--out ~/Pictures/mw_out`.
- **HEIC (iPhone default):** supported only if your SIRIL was built with HEIF support (most current
  builds are). The tool prints a heads-up when it sees `.heic`; if registration finds no frames,
  export the frames to JPEG or TIFF and re-run.

### 2c. DSLR / mirrorless DSO (FITS-less)

The four DSO modes also take DSLR/mirrorless lights — **raw** (`.cr2 .cr3 .nef .arw .dng .raf …`),
TIFF, or JPEG — no FITS required. Point `--in` at your lights and pass calibration frames as folders:

```bash
aporn-tool dso-galaxy \
  --in    "/data/M31/lights" \
  --darks "/data/M31/darks" \
  --flats "/data/M31/flats" \
  --bias  "/data/M31/bias" \
  --target M31 --focal 530 --pixel 3.76 --out /data/M31_out
```

Notes:
- A folder is read as **one** format (priority FITS > raw > TIFF > JPEG), so raw + in-camera JPEG
  pairs just work — the JPEGs are ignored.
- Master **darks/flats/bias** are optional and applied when given (a `masters` stage builds them).
- `--target` is required (raw has no `OBJECT` header); pass `--coords RA,DEC` for a target not in the
  built-in catalog. Raw/FITS get debayered; TIFF/JPEG are treated as already-RGB.
- `--focal`/`--pixel` set the plate-solve geometry for the SPCC in **galaxy/reflection** (SPCC runs in
  preprocess there). Emission/star-cluster solve blind in the finish phase, so those two don't use
  `--focal`/`--pixel` yet; SPCC may not calibrate DSLR emission/cluster colour without a catalog target.
- Master **darks/flats/bias** also work for cooled **astro-camera FITS** lights, not just DSLR raw.
- For accurate SPCC colour, set your camera under `pipeline.spcc.sensor` in the config (e.g.
  `"Canon EOS 2000D"` for a T7). SPCC uses the local Gaia catalog if installed, otherwise it reverts
  to the online Gaia catalogue automatically.
- **Emission targets need the right camera.** Nebulae like the Rosette or Orion are mostly
  hydrogen-alpha (656 nm), which a **stock (unmodified) DSLR's IR-cut filter largely blocks** — you
  can't process in red that wasn't captured. For strong Halpha, use an astro-modified camera or a
  dual-band/Ha filter. Broadband targets (star clusters, reflection nebulae like the Pleiades,
  galaxies, the Milky Way) are unaffected.

Already stacked elsewhere? Add `--stacked` to feed a finished linear integration (from DSS, Siril,
etc.) straight into the finish — no re-stacking:

```bash
aporn-tool dso-reflection-nebula --in "/data/PLEIADES_STACKED.tif" --target M45 --stacked --out /data/m45_out
```

`--stacked` works on any mode and imports the single image as the golden anchor, then runs that mode's
BGE / StarNet / stretch. (Galaxy and reflection do their SPCC in preprocess, which `--stacked` skips,
so they use the image's existing colour; emission and star-cluster still colour-calibrate in finish.)

### 3. Combine multiple nights (more integration = the #1 quality lever)

`--in` is repeatable; all `.fit` from every source are staged and stacked together:

```bash
aporn-tool dso-galaxy \
  --in "/data/M31/2026-07-04" \
  --in "/data/M31/2026-07-05" \
  --out /data/out --target M31
```

### 4. A target not in the built-in catalog

Nothing special needed. The coordinates come from your subs' FITS header, so unlisted targets
(VdB 106, Sh2-155, …) just work. Pass `--target` only when you want a custom output name:

```bash
aporn-tool dso-reflection-nebula --in "/data/vdb106"
aporn-tool dso-emission-nebula   --in "/data/sh2-155" --target Sh2-155
```

### 5. Control the crop

Auto-crop (default) trims empty registration/mosaic borders. Override it:

```bash
# keep the full frame (no crop)
aporn-tool dso-galaxy --in "/data/M31" --out /data/out --target M31 --no-crop

# explicit SIRIL crop box: X Y W H (x from left, y from top)
aporn-tool dso-galaxy --in "/data/M31" --out /data/out --target M31 --crop "162 108 2310 4378"
```

### 6. Check status and resume

Re-running the **same command auto-resumes** at the first unfinished stage, nothing done is
repeated. Inspect the ledger any time:

```bash
aporn-tool status --out /data/out --target M31
```
```
dso-galaxy / M31  (fingerprint 8cd20ff7d100564d)
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
aporn-tool dso-galaxy --in "/data/M31" --out /data/out --target M31 --redo spcc

# restart at a named stage
aporn-tool dso-galaxy --in "/data/M31" --out /data/out --target M31 --from finish

# ignore all checkpoints and re-run everything
aporn-tool dso-galaxy --in "/data/M31" --out /data/out --target M31 --force
```

### 8. The advanced, fully-specified run

```bash
aporn-tool dso-galaxy \
  --in "/data/M31/2026-07-04" --in "/data/M31/2026-07-05" \
  --out /data/out \
  --target M31 \
  --crop "162 108 2310 4378" \
  --star-reduce 0.35 \
  --config /data/my-aporntool.config.json \
  --redo spcc
```

- `--star-reduce 0.35` - after StarNet removes stars (mosaic), blend 35% of them back (lower =
  fewer/dimmer stars; default 0.5).
- `--config` - use a specific config file (tool paths, catalogs, Seestar defaults).
- `--redo spcc` - recompute from the `spcc` stage onward, reusing the stack.

---

## Command reference

```
aporn-tool <command> [options]
```

| Command | Purpose |
|---------|---------|
| `dso-galaxy`, `dso-emission-nebula`, `dso-reflection-nebula`, `dso-star-cluster` | process a deep-sky target (FITS subs) |
| `dso-milky-way` | stack a wide-field Milky Way from phone/camera stills (JPEG/HEIC/PNG/TIFF) |
| `config --check [--config PATH]` | show tool discovery; write a starter config |
| `status --out PATH --target NAME` | print the resume ledger |
| `--version` | print the version |

**Options for the processing modes:**

| Option | Description |
|--------|-------------|
| `--in PATH` | subs folder (**required**, repeatable for multi-night) |
| `--out PATH` | output root (optional; defaults to a `<TARGET>` folder beside the subs; must be space-free) |
| `--target NAME` | object name (optional; auto-detected from the subs' FITS `OBJECT` header) |
| `--crop "X Y W H"` | explicit SIRIL crop box (default: auto-crop) |
| `--no-crop` | disable auto-crop; keep the full frame |
| `--star-reduce F` | mosaic star blend-back fraction (default 0.5) |
| `--darks PATH` | folder of dark frames (DSLR calibration; DSO modes) |
| `--flats PATH` | folder of flat frames (DSLR calibration; DSO modes) |
| `--bias PATH` | folder of bias/offset frames (DSLR calibration; DSO modes) |
| `--focal MM` | focal length (mm) for the SPCC plate solve (DSLR; default: Seestar) |
| `--pixel UM` | pixel size (microns) for the SPCC plate solve (DSLR; default: Seestar) |
| `--no-tripod` | hand-held Milky Way: recover a sharp foreground from one frame, de-ghosting the house/trees/wires (`dso-milky-way` only) |
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

Stage names are **per-mode**. Run `aporn-tool status` to see yours. Current orders:

| Mode | Stages (what `--from` / `--redo` accept) |
|------|------------------------------------------|
| `dso-galaxy` | `calibrate → register → stack → spcc → bge → denoise → finish` |
| `dso-reflection-nebula` | `calibrate → register → stack → spcc → bge → denoise → finish` |
| `dso-emission-nebula` | `calibrate → register → stack → mirrorx → finish` |
| `dso-star-cluster` | `calibrate → register → stack → mirrorx → finish` |
| `dso-milky-way` | `register → stack → anchor → bge → denoise → finish` (convert is merged into register; no calibrate/mirrorx/SPCC); **`--no-tripod` appends `→ deghost`** |

A stage is only marked `done` after its output is verified (exists, non-empty, right type). A
crash or a raising stage is marked `failed` and reported with the log tail. Re-run to resume.
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

Multiple targets can share one `--out`; each gets its own `_work/<target>/` and deliverables at
the root.

---

## Configuration file

Every tunable parameter lives in one file, `aporntool.config.json` — tool paths, Seestar optics,
local Gaia catalogs, and a **`pipeline`** block with every processing knob grouped by stage/mode.
**The file is optional and appears out of the box:** the first run writes it (all defaults) next to
you, editing a value overrides just that knob, and deleting the file restores every default. You can
also write it on demand:

```bash
aporn-tool config --init      # write the file pre-filled with ALL defaults, ready to edit
aporn-tool config --check     # same, and verify Siril/GraXpert/StarNet are discoverable
```

```json
{
  "tool_paths": { "siril": "…", "graxpert": "…", "starnet2": "…", "ffmpeg": "…" },
  "seestar_focal_mm": 150.0,
  "seestar_pixel_um": 2.9,
  "catalog_astro": null,
  "catalog_photo": null,
  "pipeline": {
    "stack":    { "sigma_low": 3.0, "sigma_high": 3.0, "feather_mosaic": 100, "filter_round": "2.5k", "filter_wfwhm": "2.5k" },
    "graxpert": { "bge_smoothing": 0.0, "bge_correction": "Subtraction", "denoise_strength": 0.8 },
    "crop":     { "bg_frac": 0.25, "margin_frac": 0.02, "target_blocks": 700 },
    "spcc":     { "sensor": "Sony IMX662", "osc_filter": "UV/IR Block", "whiteref": "Average Spiral Galaxy", "catalog": "localgaia" },
    "mosaic_finish":     { "autostretch_clip": -2.8, "autostretch_bg": 0.15, "ght_d": 0.8, "ght_b": 3.0, "ght_sp": 0.15, "ght_hp": 0.85, "rmgreen": 1.0, "satu": 0.7, "star_reduce": 0.5 },
    "emission_finish":   { "subsky_degree": 1, "satu": 0.7, "satu_bg": 0.1 },
    "cluster_finish":    { "subsky_degree": 1, "denoise_mod": 0.5, "autostretch_clip": -2.8, "autostretch_bg": 0.12, "ght_d": 0.7, "ght_b": 3.0, "ght_hp": 0.9, "satu": 0.6, "satu_bg": 0.1 },
    "reflection_finish": { "target_bg": 0.35, "shadows_clip": -2.8, "sat_r": 0.30, "sat_g": 1.3, "sat_b": 4.5, "midboost": 0.55, "lc": 1.3, "bgpull": 0.08, "gamma": 0.85, "bg_desat": 0.14, "bg_desat_soft": 0.14, "st_bright": 1.5, "st_sat": 1.2 },
    "milkyway_finish":   { "bge_smoothing": 1.0, "bge_correction": "Subtraction", "denoise_strength": 0.8, "autostretch_clip": -2.9, "autostretch_bg": 0.10, "rmgreen": 1.0, "satu": 0.85, "satu_bg": 0.1 },
    "no_tripod":         { "barrier_pct": 85.0, "barrier_dilate": 4, "feather": 12.0, "min_island_frac": 0.002, "fg_target_bg": 0.10, "fg_shadows_clip": -1.8, "fg_gain": 0.6 },
    "jpeg_quality": 95
  }
}
```

**Guards (a hand-edited file can't break a run):** no file / deleted / empty / corrupt → all
built-in defaults (a corrupt file just warns and falls back). A partial file overrides only the keys
it sets; missing keys, unknown keys, and wrong-typed or non-finite values are ignored and keep their
default. Change a value and re-run: only the affected stage recomputes (a stretch tweak → just
`finish`; a `stack`/`crop` change → from that stage), reusing the golden linear stack.

**Precedence:** an explicit CLI flag beats the config — e.g. `--star-reduce 0.3` overrides
`pipeline.mosaic_finish.star_reduce`. Tool-path resolution: explicit config path → `PATH` →
known install locations.

**Scope:** `pipeline` holds the tunable *look* dials. Rig optics (`seestar_focal_mm` / `pixel_um`)
stay top-level (they describe the scope, not the processing), and a few deep reflection-algorithm
internals (white-point percentile, bloom kernels) remain structural constants — ask if you want
any of those exposed too.

---

## FAQ

**Do I need darks/flats/bias?** No. The Seestar calibrates internally. For other rigs, calibrate
your subs beforehand (the tool ingests already-calibrated `.fit`).

**How many subs do I need?** More integration is the biggest quality lever. Combine nights with
repeated `--in`. There's no hard minimum, but a handful of subs won't stack meaningfully.

**Will it delete my raw data?** No. Subs are hardlinked into `_work/00_lights/`; the golden linear
stack and your originals are never overwritten.

**Can I re-process without re-stacking?** Yes, that's the point of the golden anchor. Tweak a
finishing parameter and re-run; only `finish` (or the changed stage onward) recomputes.

**It didn't crop the mosaic tightly.** Auto-crop trims the black/near-empty borders, but it
thresholds on brightness rather than per-pixel coverage, so a **noisy low-coverage band can survive
on mosaics** (those edge pixels are normalized to near the sky level). Pass an explicit
`--crop "X Y W H"`, or do the final crop by hand in Canva/Photoshop. Tighter mosaic cropping is on
the roadmap.

**Which mode for the Pleiades (M45)?** It's an open cluster in blue reflection nebulosity, so use
`dso-reflection-nebula`, not the plain cluster finish.

**Does it need a GPU?** No. GraXpert uses the GPU when available and falls back to CPU.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `StarNet2 not found` (galaxy/emission/reflection) | The composite finish calls the StarNet2 CLI directly - set `tool_paths.starnet2` in the config or put it on `PATH`. |
| Preflight: GraXpert models missing (but installed) | Open GraXpert, run BGE + Denoise once so it downloads the model files. |
| SPCC "no stars" / imprecise | Install the Gaia region matching the target (Milky Way vs Galaxy Season). |
| `--out path must not contain spaces` | Choose a space-free output folder (SIRIL limitation). |
| `golden anchor not found` on `--from`/`--redo` | Run the full pipeline first (drop `--from`/`--redo`) so preprocess produces the anchor. |
| Plate-solving fails on a mosaic | Ensure SIRIL's astrometry catalog is installed; the tool verifies solves by frame count, not exit code. |
| Noisy/ragged band left after auto-crop | Known mosaic limitation (brightness-based crop misses low-coverage edges). Pass `--crop "X Y W H"`, or crop in post. |

Every stage saves its SIRIL script and stdout under `_work/<target>/logs/`. Check `<stage>.log`
for the exact tool error.

---

## Limitations

- **Deconvolution / wavelets are skipped** for undersampled Seestar data (they amplify noise
  without adding real detail).
- **The last 5%** (final crop, curves, watermark) is done by hand from the 16-bit TIFF.
- **Planetary** needs a manual AutoStakkert stacking step (no usable CLI) and is not yet shipped.
- **Auto-crop** trims black borders but can leave a noisy low-coverage band on mosaics (it crops by
  brightness, not coverage). Tighten with `--crop` or in post; a coverage-aware crop is planned.

---

## Development

```bash
.venv/bin/python -m pip install -e . pytest pytest-timeout
.venv/bin/python -m pytest -q          # unit suite; external tools are mocked
```

Tests mock Siril/GraXpert/StarNet, so they run anywhere. Integration runs need the real tools and
real subs. See [REQUIREMENTS.md](REQUIREMENTS.md) for the full design, the per-mode pipeline
contract, and the load-bearing SIRIL/GraXpert/StarNet gotchas.
