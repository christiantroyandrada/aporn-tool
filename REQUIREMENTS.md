# aPornTool — Requirements Breakdown

**aPornTool** (Astropornography tool) — a single command-line tool that takes raw astrophotography
captures and drives them through a finished image, across five processing modes.

> Status: **requirements / design** (nothing built yet). Grounded in the four existing skills
> (`/dso-mosaic`, `/dso-emission-nebula`, `/dso-reflection-nebula`, `/planetary`), the proven M31 /
> M8 / Veil / VdB106 / Saturn runs, and current tool CLI capabilities (July 2026). The 5th mode,
> `dso-star-cluster`, is authored from that same knowledge base — **not** from a prior run.

---

## 1. Vision & one-line goal

Point the tool at a folder of raw subs (or a planet video), tell it where to put results, pick a mode
— and get a finished, share-ready image with all the intermediate junk tucked out of sight.

**Design north star #1 — clean output:** the *outer* output folder shows only deliverables
(FITS / TIF / PNG / JPG). Every scratch file, sequence, log, and generated script lives in one hidden
working subfolder.

**Design north star #2 — processing parity (the sole variable is data, not skill):** the tool encodes
the *professional* linear→nonlinear editing pipeline (gradient removal → photometric color calibration →
noise → color-preserving stretch → star management → local contrast) so that, on the **same** target,
the user's result matches what a skilled processor would get. The remaining difference is then purely
**data acquisition** — Seestar S30 vs a full astro rig (aperture, integration hours, sky darkness,
mount/guiding, sensor temp). Processing becomes a solved, repeatable step; effort moves to capture.
*Honest limit:* the tool can't manufacture SNR or resolution that isn't in the data — parity is on
**processing**, not on out-resolving a bigger telescope. See the parity checklist in §3a.

**Design north star #3 — close the skill gap + teach coding:** aPornTool exists so the user no longer
has to invoke a Claude skill for every edit — the hard-won recipes become a runnable, self-contained
tool. And because the user is learning to code, the **source itself teaches**: every block carries a
brief, plain-language explanation of what it does and why (see NFR-9).

---

## 2. Modes (scope)

| Mode | Input | Target class | Engine | Headless? |
|------|-------|--------------|--------|-----------|
| `dso-mosaic` | folder of raw `.fit` subs (multi-panel or single) | Galaxies & large mosaics — **M31, M33, M51, M101**, NGC7000 | SIRIL → GraXpert → StarNet2 → (finish) | ✅ Full (crop is the only pause) |
| `dso-emission-nebula` | folder of raw `.fit` subs *(or salvage JPEG)* | Hα HII + Hα/OIII SNRs — M8, M20, M42, M16, Veil | SIRIL (+SPCC / HOO) | ✅ Full (crop pause) |
| `dso-reflection-nebula` | a clean linear FITS **or** raw subs | Blue scattered-light — VdB106, IC4604, M78 | SIRIL preprocess → **Python dual-layer finish** | ✅ Full |
| `dso-star-cluster` 🆕 | folder of raw `.fit` subs | Globulars (M13, M22, M4, M92…) & open clusters (M45, M44, Double Cluster…) | SIRIL preprocess + SPCC → cluster finish (**stars preserved**) | ✅ Full (crop pause) |
| `planetary` | one or more **video files** (`.MOV/.MP4`) | Jupiter, Saturn, Mars, Moon | ffmpeg → **AutoStakkert (GUI)** → Python finish | ⚠️ **Partial** — GUI stack step |

> 🆕 `dso-star-cluster` is **authored from principle + the existing SIRIL/SPCC knowledge base — not yet
> rig-validated on a real cluster run** (unlike mosaic/emission/reflection, which have proven runs).
> Treat its finishing params as starting points until an M13/M45 capture confirms them.

**Cross-mode note (parameterized core, NOT one-size-fits-all):** the four DSO modes share a
*parameterized* SIRIL core, not an identical one — registration, feather, `mirrorx`, background tool,
and SPCC placement all differ per mode (see **§4.4a** for the exact contract). `dso-mosaic` is the
WCS-assembled galaxy/mosaic path; emission / reflection / star-cluster are single-panel.
`dso-star-cluster` **inverts** the usual star handling — stars are the subject, so no star removal.
`planetary` is a separate toolchain entirely (never SIRIL). Emission Route B (dual-band HOO) and
Route C (JPEG salvage) are **experimental / Phase 3**, not MVP.

---

## 3. Actors, assumptions & environment

- **Primary dev/target machine is Windows 11** (PowerShell primary; Python 3.10 available — numpy,
  scipy, astropy, tifffile, Pillow; **no** skimage/cv2/ImageMagick). **But the tool must run on
  Windows, macOS (incl. Apple Silicon), and Debian-based Linux** — see the compatibility matrix in §6a
  and NFR-10. Nothing may assume Windows-only paths or shells.
- **Primary capture rig:** ZWO Seestar S30 (150 mm f/5, Sony IMX662, GRBG Bayer, 3.99″/px, ~10–20 s
  subs, broadband/IRCUT). Seestar calibrates internally → **no darks/flats/bias**. Frames need a
  vertical flip (`mirrorx`).
- **Planetary rig:** phone/afocal or Celestron 130SLT (alt-az), 10-bit HEVC `.MOV` or 8-bit H.264 `.MP4`.
- **Deliverable habit:** final curves/crop/watermark done manually in Canva/Photoshop from the 16-bit
  TIFF. The tool produces that TIFF + a good auto-finish, not the last 5% of taste.

---

## 3a. Processing-parity checklist (closing the pro-editing gap)

The canonical professional DSO sequence is linear-domain (gradient → color-calibrate → deconvolve-if-
sampled → denoise) then stretch, then nonlinear (masked NR → star management → local contrast →
refine). This maps the pipeline against it, so "parity" is concrete and the intentional gaps are honest:

| Pro step | aPornTool coverage | Seestar-appropriate note |
|----------|--------------------|--------------------------|
| Calibration (dark/flat/bias) | Seestar calibrates internally → skipped by design | not a gap |
| Registration + bad-frame rejection | ✅ `register`/`seqapplyreg` + `-filter-round` / FWHM cull | — |
| Integration (sigma-clip stack) | ✅ `stack rej 3 3 -rgb_equal` | **more hours = the real lever → FR-9a multi-night** |
| Drizzle (recover undersampled detail) | 🔶 candidate preprocess knob | Seestar is 3.99″/px undersampled — drizzle *may* help; evaluate |
| Gradient / light-pollution removal | ✅ GraXpert BGE (mosaic/reflection) or SIRIL `subsky` (emission/cluster) | — |
| **Photometric color calibration** | ✅ **SPCC via local Gaia** | the pro-grade color step; watch the region gotcha |
| Deconvolution (linear, PSF + mask) | ❌ **intentionally skipped** | undersampled → rings/noise, no real detail (gotcha #13) |
| Linear noise reduction | ✅ GraXpert AI 0.8 / SIRIL `denoise` | on linear data, before stretch |
| Stretch (GHS/GHT, color-preserving) | ✅ `autostretch -linked` + GHT/GHS | linked preserves SPCC color |
| Star management (reduce, *not* remove) | ✅ StarNet2 two-pass + blend-back; **cluster = keep all** | full removal looks AI-generated |
| Nonlinear NR with masks | ✅ dual-layer luma/chroma masking (reflection engine) | — |
| Local contrast / detail | ✅ local contrast (dual-layer) + ffmpeg curves | **no wavelet on mosaics** (amplifies seams) |
| Color refinement / saturation | ✅ `satu`, `rmgreen` (non-SPCC only), selective desat | — |
| HDR bright-core recovery | 🔶 Phase 3 (M42) | manual highlight-protect for MVP |
| Synthetic-luminance detail pass | 🔶 candidate refinement | optional |

**Bottom line:** with the ✅ rows encoded, processing stops being the limiting variable. The 🔶/❌ rows
are either honest physical limits of the data (deconvolution) or deferred niceties (HDR, drizzle,
synthetic-L) — flagged, not hidden.

---

## 4. Functional requirements

### 4.1 Invocation & I/O contract  *(the core ask)*

- **FR-1** Mode selected as a subcommand: `aporntool dso-mosaic ...` (bridge the existing `/mode`
  slash-command muscle memory in docs).
- **FR-2** `--in <path>` = folder where the user extracted their individual subs (DSO), or the video
  file(s) (planetary). Required.
- **FR-2a** **Drag-and-drop input (Windows).** Two ways to supply the subs folder by dragging from
  Explorer — no typing paths:
  1. **Drop onto the prompt** *(the flow you asked for)* — when the tool interactively asks for the
     subs folder (FR-6), the user drags the folder onto the console window; Windows pastes its full
     path, they press Enter.
  2. **Drop onto the launcher icon** — dragging a folder (or even a single sub) onto `aporntool.bat` /
     a desktop shortcut passes the path as an argument (`argv`), which the launcher maps to `--in` and
     then prompts for mode/target. *More robust than #1* — prompt-drop works in the classic console
     host but is inconsistent in Windows Terminal, whereas icon-drop always works.
  - **Path sanitization is load-bearing** — a dropped path arrives as raw text and must be cleaned
    before use: strip surrounding **double *and* single quotes** (Windows quotes any path with spaces),
    trim leading/trailing whitespace (drops frequently append a trailing space), expand env vars
    (`%USERPROFILE%`), normalize separators, and strip a trailing `\`.
  - If the user drops a **file** (e.g. one `.fit`) instead of the folder, use its **parent folder**.
    Re-prompt on anything that isn't an existing directory, and **echo the resolved path back** for
    confirmation. Multiple dropped paths (space-separated, quoted) feed multi-session integration
    (FR-9a).
  - **Cross-platform drag-drop** (the mechanism differs per OS; the tool handles each — see §6a):
    **Windows** — drop on the console / on the `.bat` icon (argv). **macOS** — Terminal.app pastes the
    path natively (reliable), or drop on a `.command` / Automator droplet. **Linux** — terminal
    emulators paste the path, often as a **`file://` URI that must be URL-decoded**, or drop on a
    `.desktop` launcher (`%U`/`%f`). Sanitization above **plus `file://` decoding** covers all three.
- **FR-3** `--out <path>` = user-chosen output root. Required. **Only deliverables live at this level.**
- **FR-4** Tool creates and owns a single working subfolder (`_work/`) under `--out` for *all*
  intermediates. Nothing scratch ever lands beside the deliverables. (See §7 layout.)
- **FR-5** Missing/empty `--in`, unwritable `--out`, or zero matching input files → fail fast with a
  clear message (mirror the existing `.bat`'s guard checks).
- **FR-6** Interactive fallback: if `--target`/coords/paths are omitted, prompt for them (the skills
  already "gather info" this way). **Precedence when they conflict: an explicit flag > `auto` detection
  (FR-10a) > interactive prompt.**

### 4.2 Input staging & hygiene

- **FR-7** DSO: copy/**hardlink only `.fit`** into `_work/00_lights/` — Seestar folders also contain
  `.jpg`/`_thn.jpg` that SIRIL's `convert`/`link` would wrongly ingest (hard-won gotcha).
- **FR-8** Report sub count before starting; **abort if < 10 subs** (below that, stacking isn't worth
  it) — overridable with `--min-subs N`.
- **FR-9** Planetary: probe every clip first (`ffprobe`: codec, res, fps, frame count, **rotation
  metadata**) and echo it.
- **FR-9a** **Multi-session integration:** `--in` may be passed more than once (or given a parent folder
  of per-night subfolders); the tool stages `.fit` from every source into `00_lights/` and stacks them
  together. Rationale: "more integration" is the #1 lever for closing the data-quality gap (§3a) — the
  extra hours a pro gets in one night, a Seestar user gets by combining nights.

### 4.3 Target intelligence

- **FR-10** Built-in target catalog (§9): name → RA/DEC, companions, per-target notes. Unknown target →
  require `--coords RA,DEC`.
- **FR-10a** **Auto-detect mode from FITS headers** (`aporntool auto --in … --out …`, or `--target auto`
  on any mode). Inspect the headers of a sample of subs to *propose* the pipeline, target, coords,
  mosaic-flag, and filter — so the user need not know which mode to run. Detection ladder:
  1. `OBJECT` keyword → normalize → catalog lookup → **mode + RA/DEC** (highest confidence).
  2. else `OBJCTRA`/`OBJCTDEC` (or `RA`/`DEC`) → nearest known catalog target within a tolerance.
  3. **Mosaic detection (orthogonal to type, computed from the data):** angular spread of pointing
     across *all* subs; if it exceeds ~1 Seestar FOV (≈1.3°×0.7° at 150 mm / IMX662), route to
     `dso-mosaic` (WCS assembly) regardless of object type — this is the "galaxy + mosaic" case; else
     single-panel.
  4. `FILTER` keyword → broadband (IRCUT / UV-IR) vs LP / duo-band → picks emission broadband-vs-HOO.
  5. `INSTRUME`/`TELESCOP` → confirm Seestar → focal/pixel defaults (FR-11).
  - **Always print the detection + its reasons and let the user confirm/override** — never silently
    commit to a guess. If unresolved, fall back to the interactive prompt **pre-filled** with the best
    guess (e.g. *"Detected OBJECT=M8 → emission nebula, broadband, single-panel. Use
    dso-emission-nebula? [Y/n]"*).
  - **Honest limit:** the galaxy / emission / reflection / cluster *type* for a target **not** in the
    catalog is **not** present in a Seestar header — it comes from the catalog match, or an *optional
    offline SIMBAD/NED object-type lookup* (deferred, see O4). Mosaic-vs-single and broadband-vs-duoband
    ARE derivable from the data; object *type* is not. **No image-content guessing.**
  - New module `aporntool/detect.py` → `detect_mode(sub_paths) -> Detection(mode, target, coords,
    is_mosaic, filter, confidence, reasons)`. **First feature to need `astropy`** (FITS header read).
- **FR-11** Seestar defaults baked in: focal 150 mm, pixel 2.9 µm — overridable.

### 4.4 Pipeline execution (per mode)

- **FR-12** Generate SIRIL `.ssf` (or pyscript) per stage, **save it into `_work/logs/`** for
  reproducibility, then run via `siril-cli -s`.
- **FR-13** Always pass absolute paths to `.ssf` and set `-d <workdir>` (siril-cli's default CWD is
  elsewhere; relative paths fail).
- **FR-14** **Golden source:** after register+stack+SPCC, persist the linear stack
  (`<TARGET>_Linear.fit`) as the immutable reprocess anchor. All reprocessing restarts here — never
  stack GraXpert-on-GraXpert, never re-stretch a finished output.
- **FR-15** Mosaic-specific: `stack ... -feather=100` is **mandatory** (without it panel seams are
  permanent); `-framing=max`.
- **FR-16** SPCC path: set both local-Gaia catalog paths, pass `-catalog=localgaia` to **both**
  `platesolve` and `spcc`, and pass the Seestar OSC sensor args with the whole-token quoting
  (`"-oscsensor=Sony IMX662"`). (See §10.)
- **FR-17** GraXpert stage (**mosaic & reflection only** — emission and star-cluster use SIRIL
  `subsky`/`denoise` instead): BGE (Subtraction) then AI denoise on **linear** data (strength 0.8);
  **auto-rename the `.fits.fits` double extension**; and confirm completion by **polling until the
  output file size is stable for ≥3 s** (the GraXpert CLI can return before the write finishes).
- **FR-18** Star handling policy per mode: mosaics/galaxies → StarNet2 two-pass, blend ~30–40 % stars
  back; rich-field emission nebulae → default keep all stars; reflection → dual-layer screen blend
  with the mandatory StarNet grid-artifact fix (median5 + gaussian1.5 on raw output).
- **FR-19** Planetary: transcode to raw AVI (`-fps_mode passthrough`), **hand off to AutoStakkert GUI**
  (see FR-21), then headless Python finish (RL deconv → centroid RGB align → asinh stretch with white
  point above disc peak → warm balance → saturation → PNG). Never auto-combine multiple clips.

### 4.4a Preprocess core — *parameterized, not identical*

The DSO modes call **one** core function with per-mode knobs — they pass a config, they do not fork the
pipeline. This table is the contract (it replaces the earlier "shared core" oversimplification):

| Knob | dso-mosaic | dso-emission | dso-reflection | dso-star-cluster |
|------|-----------|--------------|----------------|------------------|
| Registration | `seqplatesolve` + `seqapplyreg -framing=max` (WCS) | `register -2pass` (star) | `register -2pass` (star) | `register -2pass` (star) |
| Frame filter | `-filter-round=2.5k` | `-filter-round=2.5k` | `-filter-round=2.5k` | `-filter-round=2.5k -filter-wfwhm=2.5k` (**authored** — tighter cull; tight round stars are the payoff) |
| `-feather` | 100 | — | — | — |
| `mirrorx` | ❌ (WCS sets orientation) | ✅ `mirrorx_single` | ✅ | ✅ |
| Background extraction | GraXpert BGE | SIRIL `subsky 1` | GraXpert BGE | SIRIL `subsky 1` |
| SPCC placement | right after stack (pre-crop) | in finish, after crop | after stack | in finish, after crop |
| **Golden anchor** | post-SPCC linear (pre-crop) | post-stack linear (pre-SPCC) | GraXpert `_clean` linear | post-stack linear (pre-SPCC) |
| Denoise | GraXpert AI 0.8 (linear) | SIRIL `denoise` | GraXpert AI 0.8 | **light only** (preserve stars) |
| Star handling | StarNet2 two-pass, blend 30–40% | keep all (rich field) | dual-layer screen blend | **keep all — stars ARE the subject** |

- **FR-12a** The core is a single function parameterized by the columns above. The **"golden anchor"**
  (immutable reprocess source, FR-14) is therefore **mode-specific** — the manifest records exactly
  which file it is for the run, so resume/reprocess always restarts from the right place.
- **FR-12b** **Star-handling stage placement (resolves review finding #9).** `dso-mosaic` runs SIRIL
  `starnet -starmask` as a **discrete `starnet` stage** in its order. `dso-emission-nebula` (rich
  fields) and `dso-star-cluster` **keep all stars → no `starnet` stage.** `dso-reflection-nebula`
  performs star handling **inside its Python dual-layer `finish`** (which calls the StarNet2 CLI
  directly), so it has **no separate `starnet` stage** — yet StarNet2 is still a real dependency, so
  preflight correctly lists it for reflection. Rule: **`MODE_ORDER` (named stages) and `MODE_TOOLS`
  (required binaries) need not be 1:1** — a required tool can be invoked *inside* a stage (e.g.
  reflection's `finish`) rather than as its own stage. This is consistent by design, not drift.

### 4.4b Stage vocabulary, per-stage I/O & the golden anchor — *the resume contract*

The concrete contract Plan 2/4 build against, and what resume-verification (FR-24b), invalidation
(FR-24e), and the manifest (FR-23) structurally require. **Canonical stage IDs** (superset; each mode's
manifest lists its own active subset + order — supersedes the shorter list in FR-24d):

`stage → convert → calibrate → register → stack → mirrorx → spcc → crop → bge → denoise → starnet → finish`

Per-stage I/O (files under `_work/<target>/`; SIRIL sequence basename = `light`):

| Stage | Consumes | Produces | Type | Command / modes |
|-------|----------|----------|------|-----------------|
| `stage` | user `--in` `.fit` | `00_lights/*.fit` (hardlinked, collision-safe) | raw CFA 16-bit | all DSO (FR-7/9a) |
| `convert` | `00_lights/` | `01_process/light_*.fit` + `light_.seq` | CFA seq | `link light -out=../01_process` |
| `calibrate` | `light_.seq` | `01_process/pp_light_*.fit` + `pp_light_.seq` | debayered RGB seq | `calibrate light -debayer` (no darks/flats) |
| `register` | `pp_light_.seq` | `01_process/r_pp_light_*.fit` + `r_pp_light_.seq` | registered RGB seq | mosaic: `seqplatesolve`+`seqapplyreg -framing=max`; single: `register -2pass`+`seqapplyreg` |
| `stack` | `r_pp_light_.seq` | `01_process/result.fit` | linear RGB | `stack r_pp_light rej 3 3 -norm=addscale -output_norm -rgb_equal` (+`-feather=100` mosaic) |
| `mirrorx` | `result.fit` | `result.fit` (flipped) | linear RGB | **single-panel only** (`mirrorx_single`) |
| `spcc` | linear RGB | color-calibrated linear | linear RGB | mosaic/reflection: here; emission/cluster: in finish, post-crop |
| **→ GOLDEN ANCHOR** | | `02_linear/<TARGET>_Linear.fit` | linear RGB | see below (FR-14) |
| `crop` | `<TARGET>_Linear.fit` | `02_linear/<TARGET>_cropped.fit` | linear RGB | auto (FR-20) + `--pause-crop` |
| `bge` | cropped | `03_graxpert/<TARGET>_bge.fit` | linear RGB | mosaic/reflection (GraXpert BGE) — Plan 3 |
| `denoise` | bge / cropped | `03_graxpert/<TARGET>_clean.fit` (GraXpert) / in-place (SIRIL) | linear RGB | GraXpert (mosaic/refl) or SIRIL `denoise` (emission/cluster) — Plan 3 |
| `starnet` | stretched | `04_starnet/<TARGET>_starless.fit` + `starmask_<TARGET>.fit` | nonlinear RGB | mosaic discrete; reflection inside `finish` (FR-12b) — Plan 4 |
| `finish` | clean / starless | `<OUT>/<TARGET>_final.{fits,tif,png,jpg}` | nonlinear RGB | ported from the mode's `/dso-*` skill — Plan 4 |

- **FR-12c Golden anchor (FR-14) — one canonical file, mode-specific *state*, recorded in the
  manifest:** `02_linear/<TARGET>_Linear.fit`. **mosaic & reflection → post-SPCC** (stack → [mirrorx
  for reflection] → platesolve → spcc → save). **emission & star-cluster → post-stack + post-mirrorx,
  pre-SPCC** (their SPCC runs later, post-crop, in the finish phase). Every mode's downstream loads
  exactly this file. Reflection's effective anchor advances to `03_graxpert/<TARGET>_clean.fit` once
  BGE+denoise run (its Python finish starts there); the manifest always names the current anchor.
- **FR-12d Preprocess-core scope (what Plan 2 delivers) — per-mode sequence up to the anchor:**
  - **dso-mosaic:** `stage→convert→calibrate→register(WCS,framing=max)→stack(feather=100)→spcc` → anchor (post-SPCC)
  - **dso-reflection-nebula:** `stage→convert→calibrate→register(-2pass)→stack→mirrorx→spcc` → anchor (post-SPCC)
  - **dso-emission-nebula:** `stage→convert→calibrate→register(-2pass)→stack→mirrorx` → anchor (post-stack, pre-SPCC)
  - **dso-star-cluster:** `stage→convert→calibrate→register(-2pass, +FWHM cull)→stack→mirrorx` → anchor (post-stack, pre-SPCC)
  - Each stage is `done` only when its produced file(s) exist, are non-zero, and are the expected type
    (FR-24b). `seqplatesolve` false-negatives are verified by solved-frame count, not exit code (FR-26).
- **FR-12e Stage folders reflect stage IDs:** on-disk folders are named `NN_<area>/` where the manifest
  is the source of truth; a mode only creates the folders its sequence uses (emission/cluster never
  create `03_graxpert/`).
- **FR-12f Where each `finish` spec lives:** the `finish` command sequences for **mosaic**, **emission
  (Route A)**, and **reflection** are the corresponding `/dso-*` skill, **ported verbatim** (§8) — §4.4a
  and §4.4b govern *preprocess* only. **star-cluster** is the sole `finish` authored inline here (§4.8),
  since it has no prior skill. Plan 4 (finishers) reads those skills; Plan 2 (preprocess core) does not.

### 4.5 Human-in-the-loop steps

- **FR-20** **Crop (DSO):** auto-crop by default, `--pause-crop` to enter a manual `X Y W H`; a JPG
  preview is always written. The auto algorithm depends on WCS availability: **mosaic** (plate-solved in
  preprocess) crops to target framing from catalog RA/DEC + pixel scale with a margin; **single-panel**
  modes have no WCS yet (they platesolve in finish), so auto-crop **trims the ragged registration
  borders to the largest rectangle covered by (nearly) all frames, minus a small inward margin.**
- **FR-21** **AutoStakkert (planetary):** the tool launches AS!4, prints the exact click-path, and
  **waits** for the user to produce the stacks; then it resumes automatically by finding the newest
  `AS_Pxx/*.tif`.
- **FR-22** **Parameter tuning:** finishing params exposed as flags/env vars (never code edits), so the
  user can re-run just the finish stage from the golden source.

### 4.6 Preflight, checkpoints & resume — *never waste completed work*

> **Motivating scenario (real):** GraXpert has no AI model downloaded yet. Under the old `.bat` the
> pipeline stacks 900 subs (~30 min), *then* dies at the GraXpert stage. The user downloads the model
> and has to re-do everything. aPornTool must (a) catch the missing model **before** stacking, and
> (b) if any stage fails for a fixable reason, let the user fix it and **continue from that stage**,
> re-using every completed stage.

**Preflight (run before any expensive compute):**
- **FR-PF1** Validate *all* preconditions for the **entire chosen mode** up front — not just stage 1 —
  so a stage-4 blocker is reported at second zero:
  - external binaries discoverable (SIRIL / GraXpert / StarNet2 / ffmpeg as the mode needs);
  - **GraXpert AI models present** for every op the run will use — check the model cache dirs
    `%LOCALAPPDATA%\GraXpert\GraXpert\bge-ai-models\<ver>\model.onnx` and `…\denoise-ai-models\<ver>\`
    are present and non-empty (**path is per-OS — see §6a**; GraXpert's CLI does **not** reliably
    auto-download when offline/missing);
  - StarNet2 weights configured (SIRIL config keys or CLI weights file);
  - SPCC: both local-Gaia catalog paths exist **and the correct sky region** is installed for the
    target (Milky Way vs Galaxy Season — wrong region = "no stars");
  - **enough free disk** — heuristic `≥ 2.5 × (sub count × sub size)` (calibrated `pp_` + registered
    `r_pp_` copies + stack; `00_lights` is hardlinked so ≈ free), plus GraXpert intermediates for
    mosaic/reflection. **GPU availability is informational only — never blocking** (CPU fallback, NFR-6).
- **FR-PF2** Each failed check prints a **specific, actionable remediation** and a one-line "then just
  re-run the same command to continue" (e.g. *"GraXpert denoise model missing → open GraXpert once and
  run Denoise on any image to download it, or use Model Manager; then re-run."*).
- **FR-PF3** `--skip-preflight` escape hatch for power users; `--preflight-only` to just validate the
  environment without processing.

**Checkpoints & resume:**
- **FR-23** Write a run manifest (`_work/aporntool.json`): mode, inputs, resolved params, tool versions,
  and a **per-stage record** — status (`pending`/`running`/`done`/`failed`), timestamps, output
  path(s) + hash, and on failure the **error class + remediation hint**.
- **FR-24** **Auto-continue is the default.** Re-running the same command detects the last good
  checkpoint and resumes at the first `failed`/`pending` stage, skipping everything `done`. No flag
  needed — this is the headline behavior. `--continue` names it explicitly.
- **FR-24a** Overrides: `--from <stage>` forces a restart at a named stage; `--redo <stage>` / `--force`
  re-runs even `done` stages (ignore checkpoints). All restarts remain cheap because the **golden
  linear stack and each stage's saved output are preserved** — recompute only what changed.
- **FR-24b** A stage is only marked `done` after its output is **verified** (exists, non-zero,
  expected type/dims). A crash/kill mid-stage leaves it `running`→treated as `failed` on next run, so
  a half-written file never counts as complete (idempotent, atomic-ish stage boundaries).
- **FR-24c** `aporntool status --out <root>` prints the stage ledger (what's done, what failed + why,
  where to resume) without running anything.
- **FR-24d** **Canonical stage IDs** (what `--from`/`--redo` accept) = the complete vocabulary in
  **§4.4b**: `stage → convert → calibrate → register → stack → mirrorx → spcc → crop → bge → denoise →
  starnet → finish`. Both presence and order are per-mode (§4.4b/§4.4a — e.g. emission/star-cluster run
  `spcc` *after* `crop`, and only single-panel modes run `mirrorx`). The manifest lists the run's active
  sequence **and the current golden-anchor file** (FR-12c).
- **FR-24e** **Invalidation rule** (what makes "just re-run" *safe* instead of *stale*). Each stage
  records the resolved params it depends on; changing a param re-runs **that stage and everything
  downstream, nothing upstream**. A stretch/saturation change re-runs only `finish`; changing
  `feather` or registration re-runs from `stack`; changing the crop box re-runs from `crop`.
- **FR-24f** **Input fingerprint.** The manifest records an input signature (sub count + size/mtime
  digest; video file hash for planetary). If `--in` is repointed or the sub set grows, the golden
  anchor is flagged **stale** and preprocessing re-runs — the tool never serves a finish built on
  different data than the manifest claims.
- **FR-25** Save a **JPG preview after every major stage** into `_work/previews/` for eyeball QA.
  Linear-stage previews are **display-autostretched** (a temporary STF for visibility only — never fed
  downstream).
- **FR-26** Verify each stage's output before proceeding; treat SIRIL's known `seqplatesolve`
  "finalization failed" as a **false negative** — verify by counting solved frames, not by exit code.

### 4.7 Output deliverables

- **FR-27** At `--out` root, produce for DSO: `<TARGET>_final.fits`, `<TARGET>_final.tif` (16-bit,
  the real deliverable), `<TARGET>_final.png`, `<TARGET>_final.jpg` (preview). Planetary: `_final.png`
  (+ variants). Everything else stays in `_work/`.
- **FR-28** Emit a one-line "what next" pointer (open the TIFF in Canva for landscape crop / watermark).
- **FR-29** **Finishing profiles:** `--profile {mosaic|emission|reflection|star-cluster|galaxy}` selects
  the color + stretch preset; every finishing param stays overridable by flag/env (FR-22). Cluster
  default = keep all stars, star-color saturation from a background floor, highlight-protected stretch.
  (`galaxy` is a color/stretch preset used *within* `dso-mosaic`, **not** a separate mode.)

### 4.8 Star-cluster pipeline (authored recipe for the new mode)

> No prior rig-validated cluster run exists — this is derived from the SIRIL/SPCC knowledge base and
> the Seestar capture gotchas. **Philosophy: the stars ARE the subject.** This inverts every other DSO
> mode: no star removal, showcase star *colour*, and — for globulars — resolve into the core.

**Preprocess** (single-panel core, §4.4b): stage `.fit`-only → `link` → `calibrate -debayer` →
`register -2pass` → `seqapplyreg -filter-round=2.5k -filter-wfwhm=2.5k` (**authored** tighter cull;
round, tight stars matter more here than for fuzzy nebulae) → `stack r_pp_light rej 3 3 -norm=addscale
-output_norm -rgb_equal` → `mirrorx_single`. Golden anchor = `02_linear/<TARGET>_Linear.fit` (post-stack
+ mirrorx, pre-SPCC; FR-12c).

**Finish (SIRIL, broadband + SPCC):** *(authored; validate on a real M13/M45 run — D7)*
```
load <TARGET>_Linear             # the golden anchor (FR-12c)
crop <auto|X Y W H>              # FR-20; frame the cluster + a little sky
subsky 1                         # gradient (or -rbf on a clean high-latitude field)
platesolve -catalog=localgaia
spcc "-oscsensor=Sony IMX662" "-oscfilter=UV/IR Block" "-whiteref=<RESOLVED>" -catalog=localgaia
denoise -mod=0.5                 # LIGHT ONLY — heavy/chroma denoise greys star colour + merges faint stars
autostretch -linked              # gentle; linked preserves SPCC colour
ght -D=0.7 -B=3 -HP=0.9 -human   # AUTHORED default — highlight-protected so cores resolve, not blow white
satu 0.6 0.1                     # AUTHORED default — star-colour pop from a background floor
# rmgreen ONLY if SPCC was skipped
save <TARGET>_final              # writes .fit; then also emit the other deliverables (FR-27):
savetif <TARGET>_final
savepng <TARGET>_final
savejpg <TARGET>_final 95
```
- **`-whiteref` and the SPCC catalog region are resolved per target** from the catalog (§9 tags region:
  Milky-Way vs Galaxy-Season; FR-16/gotcha #17). `Average Spiral Galaxy` is an **authored** cluster
  whiteref default to validate (a stellar field may want a different reference). `-oscfilter=UV/IR Block`
  = the Seestar IRCUT broadband case.

**Sub-types & knobs:**
- **Globular** (M13, M22, M4, M92, M5, M15, M3): dense bright core → strongest highlight protection +
  optional mild local contrast to separate core stars; red giants give the golden accents.
- **Open** (M44, Double Cluster, M11, M6, M7): sparser → emphasise field-star colour, gentler stretch,
  darker background.
- **M45 Pleiades (hybrid):** open cluster embedded in blue reflection nebulosity → route to the
  **reflection dual-layer finish** (screen-blend stars over a stretched starless nebula), *not* this
  plain cluster finish.

**Never:** StarNet star removal (default OFF — stars are the point; only a gentle two-pass blending
~90–100% back if the brightest stars bloat), deconvolution (Seestar undersampling), or nebula-style
heavy chroma denoise.

---

## 5. Non-functional requirements

- **NFR-1 Portability of paths:** all tool paths resolved from PATH first, then known install
  locations, then config — no hard-coded absolute paths in logic (the current `.bat` hard-codes them).
- **NFR-2 Reproducibility:** given the same inputs + params + manifest, a run is deterministic and
  re-creatable from saved scripts.
- **NFR-3 Fail loud, fail early:** every external-tool call is checked; partial failure never silently
  produces a "finished" image (the AutoStakkert-quality-estimator and false-negative traps taught this).
- **NFR-4 Non-destructive:** never delete or overwrite the golden linear stack or the user's raw subs.
- **NFR-5 Performance realism:** stacking 900+ subs is ~10–30 min; communicate long steps (progress /
  "grab a coffee") rather than appearing hung.
- **NFR-6 GPU-aware:** GraXpert `-gpu true` when available, graceful CPU fallback.
- **NFR-7 Config over code:** tool paths, Seestar defaults, catalog paths, target table all in one
  config file.
- **NFR-8 Testability:** unit-test the deterministic logic with external tools **mocked** — path
  discovery, the `.fits.fits` rename, the manifest/resume state machine, stage invalidation (FR-24e),
  crop-from-WCS math, and the input fingerprint. Integration tests need real subs + tools + GPU and are
  run manually against known targets. Image-quality criteria (§13) are **human-gated**; the automated
  gate is file existence/type/dims + the resume ledger.
- **NFR-9 Self-documenting, teaching codebase (the user is learning to code):** every function and every
  non-obvious block carries a **brief, plain-language comment** — *what it does and why*, in layman's
  terms, not a restatement of the syntax (e.g. `# feather=100 blends panel edges so mosaic seams don't
  show` — not `# call stack with feather`). Prefer small, clearly-named functions over clever
  one-liners; each pipeline stage reads top-to-bottom like the recipe it implements. Each stage file
  opens with a short header: what astro step it performs, its inputs, and its output. This is a **hard
  standard checked in review**, and it makes the code the user's tutorial as well as the tool.
- **NFR-10 Cross-platform (Windows / macOS incl. Apple Silicon / Debian-based Linux):** all logic uses
  `pathlib` / `os.path` — never hard-coded separators or drive letters. Tool discovery, the GraXpert
  model-cache check (FR-PF1), SIRIL config/catalog paths, and the launcher all resolve **per-OS**
  (see §6a). No feature may assume Windows. The one documented exception is planetary's AutoStakkert
  step (Wine or PSS on Mac/Linux). CI should at minimum run the unit suite (NFR-8) on all three OSes.

---

## 6. External tool dependencies (current capabilities, July 2026)

| Tool | Role | CLI reality | Key flags / gotchas |
|------|------|-------------|---------------------|
| **SIRIL 1.4.x** (`siril-cli.exe`) | debayer, register, stack, platesolve, SPCC, StarNet, pixelmath | ✅ Full headless. `.ssf` scripts **or new Python (pyscript)** with `-async` (1.4.3+) | Abs paths + `-d`; false-neg on `seqplatesolve`; local-Gaia mandatory |
| **GraXpert 3.x** | background extraction + AI denoise | ✅ `-cli -cmd background-extraction\|denoising`, `-gpu`, `-smoothing`, `-correction`, `-strength`, `-batch_size`, `-ai_version` | Appends `.fits` → double extension; may return before done (poll output); **AI models NOT auto-downloaded by CLI** — must pre-exist in `%LOCALAPPDATA%\GraXpert\GraXpert\{bge,denoise}-ai-models\<ver>\` (preflight-checked) |
| **StarNet2 2.5.3** | star removal / star mask | ✅ `-i in -o out`; TIFF/PNG 16-bit; `--unscreen` star layer; `--eight` for 8-bit | Grid/checkerboard artifact → **must** median5+gaussian1.5 the raw output |
| **AutoStakkert! 4** | planetary lucky-imaging stack | ⚠️ **No usable CLI.** GUI only; limited batch, no scriptable automation | Hard human-in-the-loop step; alt-az field rotation → don't auto-combine clips |
| **ffmpeg / ffprobe** | video transcode + final DSO polish curve | ✅ Full | `-c:v rawvideo -pix_fmt bgr24 -fps_mode passthrough -f avi` |
| **Python 3.10** | reflection dual-layer + planetary finish | ✅ | scipy-only (no skimage/cv2) |

**Consequence:** a "one command, walk away" experience is achievable for all three DSO modes.
Planetary is inherently "start → stack by hand → resume." Design must embrace, not fight, that.

---

## 6a. Platform compatibility (Windows / macOS / Debian-Linux)

**Direct answer to "are the tools cross-platform?": yes — every DSO-pipeline tool is natively
cross-platform (incl. Apple Silicon). The only gap is AutoStakkert (planetary), which is Windows-native.**

| Tool | Windows | macOS Intel | macOS Apple Silicon | Debian/Linux x64 |
|------|:---:|:---:|:---:|:---:|
| SIRIL (`siril-cli`) | ✅ | ✅ | ✅ native ARM | ✅ repo / AppImage / Flatpak |
| GraXpert | ✅ AMD64 | ✅ AMD64 | ✅ ARM64 | ✅ AMD64 |
| StarNet2 CLI | ✅ x64 | ✅ x64 | ✅ ARM64 (CoreML, 2.5.2+) | ✅ x64 (glibc) |
| ffmpeg / ffprobe | ✅ | ✅ | ✅ | ✅ |
| Python 3.10+ | ✅ | ✅ | ✅ | ✅ |
| **AutoStakkert! 4** (planetary) | ✅ native | ⚠️ Wine ≥6 | ⚠️ Wine ≥6 | ⚠️ Wine ≥6 |

- **All three DSO modes run natively on all three OSes** — no blockers.
- **Planetary is the exception:** AutoStakkert is Windows-only (no planned native Mac/Linux build). On
  Mac/Linux, either run it under **Wine ≥ 6.x** (works well) or use the cross-platform native
  alternative **PlanetarySystemStacker (PSS)** for the stack step. Planetary already has a manual GUI
  stack step (§2) and is Phase 2, so this is contained.
- **GPU is per-OS but automatic:** GraXpert ships CUDA (NVIDIA), DirectML (Windows generic), CoreML
  (macOS) and NVIDIA/AMD/Intel Linux runtimes — the tool just passes `-gpu true` and lets GraXpert
  pick (CPU fallback, NFR-6).

**Per-OS locations the tool must resolve (never hard-code):**

| What | Windows | macOS | Linux |
|------|---------|-------|-------|
| GraXpert model cache | `%LOCALAPPDATA%\GraXpert\GraXpert\{bge,denoise}-ai-models\` | `~/Library/Application Support/GraXpert/…` | `~/.local/share/GraXpert/…` (XDG) |
| SIRIL config | `%LOCALAPPDATA%\siril\config.1.4.ini` | `~/Library/Application Support/siril/` | `~/.config/siril/` |
| Local Gaia catalogs | `%LOCALAPPDATA%\siril\…` | `~/Library/Application Support/siril/…` | `~/.config/siril/` or XDG data dir |

*(Exact Mac/Linux paths confirmed at build time; the requirement is that discovery is per-OS.)*

---

## 7. Directory layout (satisfies the core ask)

```
<OUT>/                          ← user-chosen; DELIVERABLES ONLY
├─ M31_final.fits
├─ M31_final.tif               ← 16-bit, the real deliverable
├─ M31_final.png
├─ M31_final.jpg               ← quick-look
└─ _work/                       ← ALL intermediates hidden here
   ├─ 00_lights/               hardlinked .fit only
   ├─ 01_process/              SIRIL link/calibrate/register seq + frames
   ├─ 02_linear/               M31_Linear.fit   ← GOLDEN SOURCE (never delete)
   ├─ 03_graxpert/             _bge / _clean
   ├─ 04_starnet/              _starless / starmask
   ├─ 05_finish/               stretch/composite intermediates
   ├─ previews/                per-stage .jpg for QA
   ├─ logs/                    generated .ssf/.py + stdout per stage
   └─ aporntool.json           run manifest / resume state
```

Stage folders are **per-mode** — emission and star-cluster have no `03_graxpert/`; the numbers above are
illustrative and the **manifest is the source of truth**. Handling multiple targets under one `--out`
(namespaced `_work/<target>/` vs one-target-per-`--out`) is an **OPEN decision** — see §11.

(Optionally set the `_work` folder Hidden on Windows so the outer folder is visually clean.)

---

## 8. Architecture & tech-stack recommendation

- **Language: Python 3.10** as the orchestrator (already installed; already the finishing engine for
  reflection + planetary; real arg-parsing, JSON manifest, subprocess control, cross-tool glue). Keep
  a thin **per-OS** launcher for double-click convenience (`.bat` on Windows, `.command` / shell script
  on macOS, shell script / `.desktop` on Linux) — the launcher also accepts a folder **dropped onto its
  icon** (passed as `argv` → `--in`; see FR-2a). *Retire the monolithic `.bat`* — its hard-coded paths
  and lack of resume are the main pain today.
- **Shape:** `aporntool <mode>` dispatch → shared `preprocess` core (SIRIL) → mode-specific `finish`.
  Each stage is an idempotent function that reads/writes the manifest.
- **Config:** one `aporntool.config.json` (tool paths, Seestar defaults, catalog paths, target table).
- **SIRIL scripting:** stay on `.ssf` for the proven stages; consider pyscript later where computed
  params help (e.g. crop math from WCS).
- **Relationship to existing assets:** this tool *productizes* the four skills. The skills stay as the
  human-readable recipe/authority; aPornTool is the runnable implementation. Consider vendoring both
  into the existing `christiantroyandrada/claude-astro-skills` repo.

---

## 9. Consolidated target catalog

| Target | RA,DEC | Mode | Companions / notes |
|--------|--------|------|--------------------|
| M31 Andromeda | 11.25,41.4 | mosaic | M32, M110 — frame all three |
| M33 Triangulum | 23.46,30.66 | mosaic | face-on; boost Hα regions |
| M51 Whirlpool | 202.47,47.20 | mosaic | NGC 5195 — frame the pair |
| M101 Pinwheel | 210.80,54.35 | mosaic | very low surface brightness |
| M81 | 148.89,69.07 | mosaic | — |
| NGC 7000 N. America | 314.68,44.53 | mosaic/emission | Pelican IC5070; dual-band benefits |
| M8 Lagoon | 271.43,-24.41 | emission | bright hourglass core |
| M20 Trifid | 270.6,-23.03 | emission | Hα + blue reflection lobe |
| M42 Orion | 83.82,-5.39 | emission | very bright core → HDR/highlight protect |
| M16 Eagle | 274.7,-13.8 | emission | Hα HII |
| Veil NGC 6960 | 311.6,30.9 | emission | SNR Hα+OIII, dense field |
| VdB106 | (per-target) | reflection | blue scattered light |
| M13 Hercules | 250.42,36.46 | star-cluster | globular; bright core → protect highlights; high latitude (region gotcha) |
| M22 | 279.10,-23.90 | star-cluster | globular; low + rich Milky Way field (MW region) |
| M4 | 245.90,-26.53 | star-cluster | globular; near Antares |
| M5 | 229.64,2.08 | star-cluster | globular; high latitude (region gotcha) |
| M92 | 259.28,43.14 | star-cluster | globular |
| M15 | 322.49,12.17 | star-cluster | globular; very compact core |
| M3 | 205.55,28.38 | star-cluster | globular; high latitude |
| M45 Pleiades | 56.87,24.12 | star-cluster* | open + blue reflection → *use reflection dual-layer* |
| M44 Beehive | 130.05,19.98 | star-cluster | open; sparse, wide |
| Double Cluster NGC 869/884 | 34.74,57.13 | star-cluster | open pair; wide field |
| M11 Wild Duck | 282.77,-6.27 | star-cluster | open; dense, rich field |
| M6 Butterfly | 265.08,-32.22 | star-cluster | open; low (MW region) |
| M7 Ptolemy | 268.46,-34.79 | star-cluster | open; low (MW region) |
| Jupiter / Saturn / Mars / Moon | — | planetary | see per-target AP/drizzle table |

---

## 10. Load-bearing constraints & gotchas (must be encoded)

1. **`-feather=100`** on mosaic stacks — non-negotiable or seams are permanent.
2. **Local Gaia mandatory for SPCC** — online VizieR TAP is dead. Set both catalog paths + pass
   `-catalog=localgaia` to platesolve **and** spcc. Region matters: **Milky Way** region for galactic
   nebulae, **Galaxy Season** region for high-latitude galaxies (wrong region → "no stars").
3. **SPCC OSC quoting:** `"-oscsensor=Sony IMX662"` (quote the whole token incl. flag), *not*
   `-oscsensor="Sony IMX662"`.
4. **`autostretch -linked`**, never unlinked (linked preserves SPCC color ratios).
5. **`rmgreen` only when NOT using SPCC** (SPCC already neutralizes green).
6. **GraXpert double `.fits.fits`** — auto-rename before SIRIL load.
7. **Denoise on linear data, before stretch.** The **0.8 sweet spot is the GraXpert AI strength**
   (mosaic/reflection; 1.0 over-sharpens) — **not** the same scale as SIRIL `denoise -mod=` (emission
   uses bare `denoise`, or `-mod=0.8 -da3d` for faint SNRs; star-cluster uses `-mod=0.5`, light).
8. **Seestar `.fit`-only staging**; **`mirrorx` on single-panel modes only** (emission / reflection /
   star-cluster) — mosaic orientation comes from WCS, so mosaic does **not** `mirrorx`.
9. **StarNet grid fix** (median5 + gaussian1.5 on raw output) before any further processing.
10. **Never full-remove stars** — blend some back or galaxies/nebulae look AI-generated.
11. **Planetary: don't auto-combine clips** — alt-az field rotation smears rings; AS! only translates.
    Stack each clip separately, keep the best. Keep the disc **gold, not white** (white point above
    disc peak). RGB align by **centroid**, not phase-correlation.
12. **SIRIL `seqplatesolve` false negative** — verify by counting solved frames, not exit code.
13. **No deconvolution/wavelet on Seestar DSO** (undersampled 3.99″/px → only amplifies noise).
14. **GraXpert AI models must pre-exist** — the CLI won't download them on a fresh/offline machine.
    **Preflight-check the model cache before stacking** so a missing model fails at second zero, not
    after a 30-min stack; on fix, auto-continue from the GraXpert stage (see §4.6).
15. **Star clusters — stars are the subject: never StarNet-remove them**, and never apply nebula-style
    heavy chroma denoise (it greys out star colour and merges faint stars). Light denoise only.
16. **Globular cores blow out easily** — protect highlights / gentle stretch so the core resolves into
    stars, not a white blob (same rule as M42).
17. **SPCC region scatter for clusters** — clusters span the whole sky; high-latitude globulars
    (M13 / M3 / M5 / M15 / M92) may sit in *neither* the Milky-Way nor the Galaxy-Season catalog region
    you have installed → SPCC errors "no stars" until the matching AOI is installed. Preflight (FR-PF1)
    must check the target's region, not just that *some* region exists.
18. **M45 Pleiades is a hybrid** (open cluster + blue reflection nebula) → route it through the
    reflection dual-layer finish, not the plain cluster finish.

---

## 11. Decisions (locked) & remaining risks

| # | Decision | Choice |
|---|----------|--------|
| D1 | Implementation language | **✅ LOCKED — Python orchestrator + thin launcher.** Retire the monolithic `.bat`. |
| D2 | Interactive crop | **✅ LOCKED — auto-crop from WCS/target framing; `--pause-crop` for a manual `X Y W H` box.** Preview always written. |
| D3 | Planetary GUI gap | Accept manual AS! step; resume by watching for newest `AS_Pxx/*.tif`. |
| D4 | Interface surface | Standalone CLI now; keep the four skills as recipe authority. |
| D5 | Dual-band support | Defer — flag HOO as experimental (unvalidated on rig). |
| D6 | Config of tool paths | Both — auto-discover → config file → clear error. |
| MVP | Build scope | **✅ LOCKED — the three proven DSO modes** on the parameterized core (§4.4a); star-cluster rides the same single-panel core (D7); planetary follows. |
| D7 | Star-cluster mode | **Added** — authored from principle, **not yet rig-validated**; reuses the single-panel core, so marginal cost ≈ one finish profile. Validate on a real M13 / M45 run. |
| O1 | Disk / cleanup policy | **✅ LOCKED** — always keep the golden anchor + deliverables; `aporntool --clean` purges the big `01_process` seq after a successful finish (never automatic). |
| O2 | Multi-target under one `--out` | **✅ LOCKED** — namespace `_work/<target>/`; deliverables sit side by side at the `--out` root, each target with its own manifest. |
| O3 | MVP nebula boundary | **✅ LOCKED** — Route A (broadband+SPCC) + reflection dual-layer + star-cluster; defer M42-HDR, dual-band HOO, JPEG-salvage to Phase 3. |
| D8 | Auto-detect mode (FR-10a) | **Added** — `auto` mode reads FITS headers → proposes pipeline/target/mosaic/filter, user confirms. New `detect.py`; needs `astropy`. |
| O4 | Unknown-target type classification | **🔶 OPEN** — for targets NOT in the catalog: (a) catalog + coordinate match + mosaic/filter only *(recommended for now)*; (b) add an offline SIMBAD/NED object-type lookup later. No image-content guessing either way. |

---

## 12. Phased roadmap (locked)

- **Phase 1 — MVP** on the **parameterized SIRIL preprocess core (§4.4a)**, plus Python orchestrator +
  thin launcher, the `_work/` I/O contract, manifest + resume (incl. stage IDs / invalidation /
  fingerprint), target catalog, config-driven tool paths, auto-crop with `--pause-crop`. Finishing
  paths on top of the core:
  - `dso-mosaic` — feathered stack → GraXpert → StarNet2 two-pass (M31-proven).
  - `dso-emission-nebula` — Route A broadband + SPCC, crimson-Hα (M8-proven).
  - `dso-reflection-nebula` — port the Python dual-layer finish (VdB106-proven).
  - `dso-star-cluster` — §4.8 authored recipe (**unvalidated**; cheap because it reuses the core).
- **Phase 2 — `planetary`:** ffmpeg → AutoStakkert GUI hand-off → headless Python finish.
- **Phase 3 — extras:** dual-band HOO (experimental), Route C JPEG salvage, **M42 short+long HDR blend**,
  optional `_work` auto-hide, batch over multiple targets.

---

## 13. Acceptance criteria (per mode)

- **Resilience (all modes) — the "GraXpert had no model" test:** with the GraXpert AI model *removed*,
  the run **aborts during preflight in seconds** (before stacking) with a clear "download the model,
  then re-run" message. After the user downloads the model, re-running the same command **skips
  stacking/crop/BGE-if-done and resumes at the failed stage**, producing the final image without
  redoing the expensive earlier phases. `aporntool status` shows the ledger throughout.
- **Input UX (Windows):** dragging the subs folder onto the prompt *or* onto the launcher icon
  populates `--in` correctly — including a path **with spaces** and a stray trailing space; dropping a
  single `.fit` resolves to its **parent folder**; a non-existent path **re-prompts** rather than crashing.
- **dso-mosaic:** from a folder of Seestar subs + a known target name, one command yields
  `<TARGET>_final.tif/png/jpg` at `--out` root with a **seamless** (no visible panel seams), color-
  calibrated, star-reduced result; golden linear stack preserved in `_work/02_linear/`; every stage
  has a preview + saved script; re-running is idempotent.
- **dso-emission-nebula:** Hα reads **crimson** (not pink-brown), background dark-not-clipped, bright
  core not blown; SPCC applied via local Gaia. *(M42's core may still clip — dedicated short+long HDR
  is Phase 3; for MVP, protect highlights and finish HDR manually.)*
- **dso-reflection-nebula:** blue scattered light preserved, no StarNet grid artifacts, stars screen-
  blended on a darkened starless layer; 16-bit TIFF deliverable.
- **dso-star-cluster:** stars **preserved** (no removal), tight/round and **colour-accurate** via SPCC
  (blue-white hot stars vs golden red-giants clearly visible); globular cores **resolved into stars**,
  not blown to white; background dark-not-black. *(Authored target — validate on a real M13 / M45 run.)*
- **planetary:** transcode + finish fully automated around a single manual AS! stack step; disc stays
  colored (not clipped white); no field-rotation smear.

---

## Appendix — sources (tool capability research)

- Siril headless / scripting / pyscript: https://siril.readthedocs.io/en/stable/Headless.html ,
  https://siril.readthedocs.io/en/stable/Scripts.html , https://siril.org/tutorials/pysiril/
- GraXpert CLI: https://github.com/Steffenhir/GraXpert/blob/main/README.md
- StarNet2 CLI: https://starnetastro.com/cli-tools/starnet/
- AutoStakkert (no CLI / batch limits): https://www.autostakkert.com/wp/guides/
