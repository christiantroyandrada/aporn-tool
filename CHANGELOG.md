# Changelog

## v0.3.2 — 2026-07-07

- **Cleaner reflection backgrounds.** Added selective background desaturation to the reflection
  finish: the global blue boost that makes the nebula pop no longer floods the sky with blue
  speckle — low-signal pixels fade to neutral black while the nebula keeps its colour. (New
  `desaturate_background`; defaults `bg_desat=0.14`, `bg_desat_soft=0.14`.)
- **`--version` is now correct.** It read a hardcoded string that was never bumped (so 0.3.0/0.3.1
  both reported `0.2.0`); it now derives from the installed package metadata and can't drift again.

## v0.3.1 — 2026-07-07

Maintenance release — no functional changes.

- **Refreshed the PyPI page.** The 0.3.0 upload was tagged one commit before the README badge/header
  fix, so its PyPI description still showed a stale "Latest release: v0.2.0" line. PyPI freezes a
  version's description at upload, so this rebuild (from the corrected README) is the only way to
  update the page.
- **CI:** publish-workflow actions bumped off the deprecated Node 20 — `checkout@v7`,
  `setup-python@v6`, `upload-artifact@v7`, `download-artifact@v8`.

## v0.3.0 — 2026-07-07

First release published to **PyPI** — `pip install aporn-tool`, then run `aporn-tool <mode> --in …`
(the one-word `aporntool` and `python -m aporntool` also work).

### Added
- **Target + coordinate auto-detection** — `--target` is now optional: when omitted, the object name
  and coordinates are read from the subs' FITS header (`OBJECT` + `RA`/`DEC`), so unlisted targets
  (e.g. VdB 106) work with no manual coords. `--out` is now optional too, defaulting to a `<TARGET>`
  folder beside the input subs. The everyday command is just **mode + `--in`** (e.g.
  `aporntool dso-mosaic --in "/path/to/M31 subs"`). `--target`/`--out` still override.
- **`--clean` flag** (all `dso-*` modes): on a fully successful run, deletes the working files in
  `_work/<target>/` except the golden anchor (`02_linear/<TARGET>_Linear.fit`), the manifest, and
  logs. Reclaims almost all scratch disk (a real M8 run went 18 GB → 25 MB) while keeping a cheap
  re-finish — `--from bge` (mosaic/reflection) or `--from finish` (emission/cluster) rebuilds every
  deliverable from the anchor with no re-stack. Off by default; a failed run never cleans, so resume
  always works.

### Removed
- **`--coords` flag** — no longer needed now that coordinates are read from the FITS header. The
  `resolve_target(name, coords=…)` library function still accepts explicit coords.

## v0.2.0 — 2026-07-07

First cross-platform, end-to-end-verified release. One command turns raw OSC sub-exposures into a
finished, share-ready astrophoto.

### Highlights
- Runs on **Windows, macOS (incl. Apple Silicon), and Linux** — Siril/GraXpert/StarNet2/ffmpeg are
  resolved from PATH → standard per-OS install locations → config, with no hard-coded paths.
- **`dso-mosaic` verified end-to-end** on a real 922-sub M31 Seestar mosaic: SIRIL WCS assembly →
  GraXpert background extraction + AI denoise → StarNet2 → finished `.tif/.png/.jpg/.fits`.
- **Checkpoint + auto-resume:** re-run the same command to continue from the first unfinished stage;
  the golden linear stack is preserved so re-finishing never re-stacks.
- **Preflight** validates tools, GraXpert AI models, and (for mosaic) SIRIL's StarNet config before
  any heavy compute, each with an actionable remediation message.

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
  golden anchor on `--from`/`--redo` gives an actionable message.

### Known limitations
- Emission / reflection / star-cluster are not yet rig-validated on real data.
- Planetary mode and `aporntool auto` (FITS-header mode detection) are not implemented.
- The final crop/curves/watermark are done by hand from the 16-bit TIFF; auto-crop is conservative.
