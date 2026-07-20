# Changelog

## v0.6.0 — 2026-07-20

### Added
- **New `dso-milky-way` mode: wide-field Milky Way from a phone or camera.** It ingests already-
  debayered **stills** (`.jpg .jpeg .png .tif .tiff .heic`) instead of raw FITS subs — point a phone
  on anything steady at the Milky Way, take a dozen-plus frames, and it stacks them to pull the
  galactic core out of the noise. Mirrors how the Seestar (and smart cameras like the S30 Pro /
  Dwarf 3) separate a wide Milky Way mode from telescope captures.
  - **Pipeline:** `register → stack → anchor → bge → denoise → finish`. Because phone stills are
    already RGB and carry no WCS, the mode **skips calibration, plate-solving, SPCC, and the mirrorx
    flip**. `convert` is merged into the register stage (SIRIL `convert -out=` doesn't persist a
    `.seq`, same gotcha as `link -out=`). Registration is **single-pass global** with no roundness
    cull — phone frames vary too much frame-to-frame, and the DSO 2-pass `-filter-round` cull could
    drop the reference frame and abort. GraXpert BGE runs at **high smoothing** so the large-scale
    Milky Way band isn't subtracted as background. No StarNet (the stars are the subject).
  - **Dependencies:** SIRIL + GraXpert only (no StarNet, no Gaia catalog).
  - **Config:** new `pipeline.milkyway_finish` block (BGE smoothing, denoise, stretch, saturation).
  - `--target` is optional (the run is named `MilkyWay`); `--out` still defaults beside the input.
- **DSLR / mirrorless DSO support — the existing modes no longer require FITS.** `dso-galaxy`,
  `dso-emission-nebula`, `dso-reflection-nebula`, and `dso-star-cluster` now accept DSLR lights in
  **raw** (`.cr2 .cr3 .nef .arw .dng .raf .orf .rw2 .pef .srw`), TIFF, or JPEG, with **full master
  calibration**.
  - **Ingest picks one format per folder** by priority (FITS > raw > TIFF > JPEG), so a Seestar sub
    is never mixed with its `.jpg` preview, nor a DSLR raw with its in-camera JPEG. FITS is `link`ed
    (unchanged); everything else is `convert`ed to FITS. Raw/FITS are debayered; TIFF/JPEG are treated
    as already-RGB.
  - **Master calibration:** `--darks`, `--flats`, `--bias` (each a folder). A new `masters` stage
    builds master bias/dark (sigma-clip, `-nonorm`) and master flat (bias-subtract + `-norm=mul`),
    then `calibrate` applies them (`-bias= -dark= -cc=dark -flat=`).
  - **Optics:** `--focal` / `--pixel` set the plate-solve geometry for SPCC (defaults stay Seestar).
    `--target` is required (raw frames carry no `OBJECT` header). DSLR frames are not vertically
    flipped, so the mirrorx step is skipped for them.
  - **Seestar path is byte-identical:** with FITS input and no calibration frames, every command is
    exactly as before.
- **`--stacked` finish-only input.** Feed an already-stacked **linear** image (a FITS/TIFF/PNG/JPEG
  integration from DSS, Siril, etc.) straight into a mode's finish — BGE, StarNet, stretch — on any
  mode. It skips calibrate/register/stack (a single frame can't form a SIRIL sequence anyway) and
  imports the image as the golden anchor via `convert` + `load` + `save`. Note: galaxy/reflection run
  SPCC in preprocess, which `--stacked` bypasses, so those two skip colour calibration; emission and
  star-cluster still SPCC in their finish phase.

### Fixed
- **Emission / star-cluster finish now seeds its plate solve** with the target coords + `--focal`/
  `--pixel`, instead of a blind solve that failed (`invalid input image`) on wide DSLR fields and
  already-stacked frames — so SPCC actually runs on DSLR/`--stacked` data. SIRIL resolves the Gaia
  catalog itself (local if present, else it reverts to the online catalogue), giving a
  local → remote → skip chain.
- **...and no longer aborts when the solve still can't lock.** If SPCC fails anyway (truly offline,
  or an unsolvable frame), the finish falls back to finishing WITHOUT SPCC and still produces
  deliverables, matching the fault tolerance the preprocess SPCC stage already had. (Set your camera
  under `pipeline.spcc.sensor` in the config for accurate DSLR colour.)

## v0.5.0 — 2026-07-15

### Changed (breaking)
- **Modes are now target *types*, and mosaic is an auto-detected capture attribute.** `dso-mosaic`
  is **removed**; galaxies use the new **`dso-galaxy`** mode. Whether a capture is a single panel or
  a multi-panel **mosaic** is detected automatically from the subs' pointing spread (>~½ FOV → mosaic)
  and selects the assembly (WCS + `feather`, no flip) vs single-panel (`register -2pass` + `mirrorx`).
  Override with `--mosaic` / `--single`; the decision is always printed. This matches how the
  community (and the Seestar UI) treats a mosaic — a technique applied to any target type, not a
  target category. M31 → `dso-galaxy` (auto-mosaic); M51/M101/M33 → `dso-galaxy` (auto-single).
  NGC 7000 recategorised from mosaic to `emission`.
  - *Scope:* single↔mosaic assembly is wired for galaxies now; nebula-complex mosaics
    (Rho Ophiuchi, Orion) via emission/reflection are architecture-ready but deferred (a warning
    fires if a nebula capture looks like a mosaic).

### Added
- **Composite dual-layer finish across all non-cluster DSO modes** (`dso-galaxy`,
  `dso-emission-nebula`, `dso-reflection-nebula`). Following the modern standard (StarNet /
  StarXTerminator): the stars are removed, the starless *nebula* layer and the *stars* layer are
  processed independently, then recombined with a **screen blend**. This lets the background be
  darkened and denoised hard without smearing the stars — dramatically cleaner results on
  short-integration / light-polluted data. New shared core `aporntool/stages/composite_finish.py`
  (`run_composite_finish`, `composite_layers`, per-mode `PROFILES`), reusing the VdB106-validated
  reflection primitives so there is one implementation shared everywhere.
- **`--star-reduce` now applies to every composite mode** as the star-layer strength (0..1; 1.0
  keeps all stars, lower reduces them). Per-mode defaults: galaxy 0.5, emission/reflection 1.0.

### Changed
- `dso-emission-nebula` now runs a SIRIL prep (crop → gradient → local-Gaia platesolve + SPCC →
  denoise) into a linear `_clean.fit`, then the composite dual-layer finish. On reddened
  galactic-plane fields where SPCC can't derive a valid white balance, the composite's SCNR +
  red-preserving saturation still delivers crimson Hα. Emission now depends on **StarNet2**
  (checked in preflight), like reflection.
- `dso-galaxy` finish is now the composite dual-layer on the GraXpert-cleaned linear (was a SIRIL
  stretch → GHT → StarNet → PixelMath blend).
- `dso-star-cluster` is unchanged and deliberately excluded — the stars ARE the subject.

### Notes
- Emission/galaxy composite look is currently governed by the documented `PROFILES` constants;
  wiring those into the config schema is a planned follow-up (reflection stays config-driven).

## v0.4.0 — 2026-07-09

### Added
- **All pipeline parameters centralized in one config file.** Every tunable knob — stack sigma /
  feather / registration filters, GraXpert smoothing·correction·denoise-strength, auto-crop
  thresholds, SPCC sensor·filter·whiteref·catalog, per-mode stretch·GHT·saturation·star-blend, the
  reflection dual-layer dials, `subsky` degree, `rmgreen`, and deliverable JPEG quality — now lives
  under a `pipeline` block in `aporntool.config.json`, grouped by stage/mode.
- **`aporn-tool config --init`** writes a config pre-filled with every default, ready to edit.
- **Out of the box:** the first mode run auto-writes `aporntool.config.json` (all defaults) next
  to you so the knobs are there to tweak with no command to run or code to touch — it never
  overwrites an existing file, and a read-only location just falls back to defaults.
- Defaults live in code; the file only *overlays*, with guards: no file / deleted / empty / corrupt
  → built-in defaults (a corrupt file warns and carries on); a partial file overrides only the keys
  it sets; unknown keys and wrong-typed or non-finite values are ignored. A hand-edited file can't
  break a run. An explicit CLI flag (e.g. `--star-reduce`) still beats the config.

### Fixed
- `platesolve` in the emission/cluster finish now honours the configured SPCC catalog (was hardcoded
  `localgaia` — a split-brain if the catalog was changed).
- A config `crop.target_blocks: 0` no longer divides-by-zero mid-run (floored to ≥ 1).

With no config file, every emitted SIRIL/GraXpert/StarNet command is **byte-identical to v0.3.3** —
locked by tests.

## v0.3.3 — 2026-07-07

- **Docs cleanup.** Tightened the README and changelog prose. No functional changes.

## v0.3.2 — 2026-07-07

- **Cleaner reflection backgrounds.** Added selective background desaturation to the reflection
  finish: the global blue boost that makes the nebula pop no longer floods the sky with blue
  speckle. Low-signal pixels fade to neutral black while the nebula keeps its colour. (New
  `desaturate_background`; defaults `bg_desat=0.14`, `bg_desat_soft=0.14`.)
- **`--version` is now correct.** It read a hardcoded string that was never bumped (so 0.3.0/0.3.1
  both reported `0.2.0`); it now derives from the installed package metadata and can't drift again.

## v0.3.1 — 2026-07-07

Maintenance release, no functional changes.

- **Refreshed the PyPI page.** The 0.3.0 upload was tagged one commit before the README badge/header
  fix, so its PyPI description still showed a stale "Latest release: v0.2.0" line. PyPI freezes a
  version's description at upload, so this rebuild (from the corrected README) is the only way to
  update the page.
- **CI:** publish-workflow actions bumped off the deprecated Node 20: `checkout@v7`,
  `setup-python@v6`, `upload-artifact@v7`, `download-artifact@v8`.

## v0.3.0 — 2026-07-07

First release published to **PyPI**. `pip install aporn-tool`, then run `aporn-tool <mode> --in …`
(the one-word `aporntool` and `python -m aporntool` also work).

### Added
- **Target + coordinate auto-detection.** `--target` is now optional: when omitted, the object name
  and coordinates are read from the subs' FITS header (`OBJECT` + `RA`/`DEC`), so unlisted targets
  (e.g. VdB 106) work with no manual coords. `--out` is now optional too, defaulting to a `<TARGET>`
  folder beside the input subs. The everyday command is just **mode + `--in`** (e.g.
  `aporntool dso-mosaic --in "/path/to/M31 subs"`). `--target`/`--out` still override.
- **`--clean` flag** (all `dso-*` modes): on a fully successful run, deletes the working files in
  `_work/<target>/` except the golden anchor (`02_linear/<TARGET>_Linear.fit`), the manifest, and
  logs. Reclaims almost all scratch disk (a real M8 run went 18 GB → 25 MB) while keeping a cheap
  re-finish. `--from bge` (mosaic/reflection) or `--from finish` (emission/cluster) rebuilds every
  deliverable from the anchor with no re-stack. Off by default; a failed run never cleans, so resume
  always works.

### Removed
- **`--coords` flag** removed. No longer needed now that coordinates are read from the FITS header.
  The `resolve_target(name, coords=…)` library function still accepts explicit coords.

## v0.2.0 — 2026-07-07

First cross-platform, end-to-end-verified release. One command turns raw OSC sub-exposures into a
finished, share-ready astrophoto.

### Highlights
- Runs on **Windows, macOS (incl. Apple Silicon), and Linux**. Siril/GraXpert/StarNet2/ffmpeg are
  resolved from PATH → standard per-OS install locations → config, with no hard-coded paths.
- **`dso-mosaic` verified end-to-end** on a real 922-sub M31 Seestar mosaic: SIRIL WCS assembly →
  GraXpert background extraction + AI denoise → StarNet2 → finished `.tif/.png/.jpg/.fits`.
- **Checkpoint + auto-resume:** re-run the same command to continue from the first unfinished stage;
  the golden linear stack is preserved so re-finishing never re-stacks.
- **Preflight** validates tools, GraXpert AI models, and (for mosaic) SIRIL's StarNet config before
  any heavy compute, each with a clear remediation message.

### Modes
`dso-mosaic` (galaxies/mosaics) · `dso-emission-nebula` · `dso-reflection-nebula` ·
`dso-star-cluster`. Mosaic is rig-verified end-to-end; the reflection dual-layer finish (StarNet2
CLI + grid-fix + dual-layer blend) is smoke-tested on real linear data; emission and star-cluster
are code-complete and unit-tested.

### Fixed
- **Auto-crop** removes irregular `framing=max` mosaic borders (largest-signal rectangle;
  block-covered-only-if-fully-covered so no black leaks in; NaN/inf-safe) and uses the correct SIRIL
  top-down crop coordinates (the y-axis was previously flipped).
- **macOS path detection**: GraXpert models under `~/Library/Application Support/GraXpert/` and SIRIL
  1.4.x config under `org.siril.Siril/`; preflight now catches "StarNet not configured inside SIRIL"
  for mosaic mode instead of failing at the finish stage.
- **imagecodecs** is now a dependency so the reflection finish can decode StarNet's LZW-compressed
  TIFF output (it previously crashed reading the starless layer).
- **Resume never crashes**: a stage that raises fails loud-but-clean with the log tail; a missing
  golden anchor on `--from`/`--redo` gives a clear message.

### Known limitations
- Emission / reflection / star-cluster are not yet rig-validated on real data.
- Planetary mode and `aporntool auto` (FITS-header mode detection) are not implemented.
- The final crop/curves/watermark are done by hand from the 16-bit TIFF; auto-crop is conservative.
