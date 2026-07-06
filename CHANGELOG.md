# Changelog

## Unreleased

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
