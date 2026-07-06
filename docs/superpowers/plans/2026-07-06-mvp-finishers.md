# aPornTool MVP Finishers (Plan 3+4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Take the golden anchor to **finished deliverables** (`<TARGET>_final.{fits,tif,png,jpg}` at the `--out` root) for all four DSO modes — reaching MVP (subs → shareable image, one command). GraXpert BGE/denoise wrapper; per-mode finish (SIRIL for mosaic/emission/cluster; Python dual-layer for reflection); crop; previews.

**Architecture:** Same seams as Plan 2. GraXpert gets a `tools/graxpert.py` wrapper (injectable runner, `.fits.fits` rename, size-stable poll). SIRIL finishes are pure command-generator functions → `Stage`s. Reflection's finish is a pure-numpy module tested on synthetic arrays. All external tools (SIRIL/GraXpert/StarNet2) are **mocked** in tests; real runs are validated manually. Finish stages append to the preprocess stage list in `cmd_mode`.

**Tech Stack:** Python 3.10+; stdlib for orchestration; **numpy + astropy + scipy + Pillow + tifffile** for the reflection finish + FITS I/O (declared in Task 4). pytest.

## Global Constraints

- **Cross-platform (NFR-10):** `pathlib` only; per-OS tool paths.
- **Teaching codebase (NFR-9):** brief what-&-why comments; module docstrings.
- **Deliverables (FR-27):** at `--out` root, `<TARGET>_final.fits`, `.tif` (16-bit), `.png`, `.jpg`. Everything else in `_work/`.
- **Golden anchor is the reprocess source (FR-14):** finish never re-runs preprocess; starts from `<TARGET>_Linear.fit` (mosaic/reflection: post-SPCC; emission/cluster: pre-SPCC → SPCC happens in finish).
- **Per-mode finish (§4.4b, ported from the `/dso-*` skills + the M31 scripts):**
  - mosaic: crop → GraXpert BGE → GraXpert denoise(0.8) → SIRIL stretch/color → StarNet2 star-reduce (blend) → save
  - emission: SIRIL crop → subsky → platesolve → spcc → denoise → autostretch-linked → satu → save (keep all stars)
  - star-cluster: SIRIL crop → subsky → platesolve → spcc → denoise -mod=0.5 → autostretch → ght → satu → save (keep all stars)
  - reflection: GraXpert BGE → denoise(0.8) → Python dual-layer (autostretch → StarNet2 → process starless+stars → screen blend) → save
- **Gotchas (§10):** GraXpert `.fits.fits` double-ext → rename before SIRIL load (#6); denoise on linear before stretch (#7); `autostretch -linked` preserves SPCC color (#4); `rmgreen` only when NOT SPCC (#5); StarNet grid-fix median5+gaussian1.5 (#9); never full-remove stars (#10); local-Gaia + whole-token SPCC quoting (#2/#3); SPCC region per target (#17).
- **Resume (FR-24):** finish stages are checkpointed like preprocess; re-run skips done; changed golden anchor invalidates finish.

---

## File Structure

```
aporntool/
  tools/graxpert.py          # GraXpert BGE + denoise wrapper (rename, poll)
  stages/finish_cmds.py      # pure SIRIL finish command generators (crop + mosaic/emission/cluster + saves)
  stages/finish.py           # build_finish_stages() → Stage list per mode (SIRIL modes + reflection hook)
  stages/reflection_finish.py# pure-numpy dual-layer finish (autostretch/mtf/screen-blend/grid-fix)
  cli.py                     # MODIFY: cmd_mode runs preprocess + finish → deliverables; --crop/--profile
pyproject.toml               # MODIFY: add numpy/astropy/scipy/Pillow/tifffile
tests/
  tools/test_graxpert.py  stages/test_finish_cmds.py  stages/test_finish.py
  stages/test_reflection_finish.py  test_cli_mvp.py
```

---

### Task 1: GraXpert wrapper (BGE + denoise, `.fits.fits` rename, size-stable poll)

**Files:** Create `aporntool/tools/graxpert.py`, `tests/tools/test_graxpert.py`.

**Interfaces:**
- `bge_cmd(exe, in_path, out_path, *, gpu=True, smoothing=0.0) -> list[str]`
- `denoise_cmd(exe, in_path, out_path, *, gpu=True, strength=0.8) -> list[str]`
- `fix_double_ext(out_path) -> Path` — if `<out>.fits` doesn't exist but `<out>.fits.fits` does, rename it; return the final path.
- `run_graxpert(argv, out_path, *, runner=subprocess.run, poll=..., settle=0.0) -> Path` — run, then `fix_double_ext`, return final path. (`settle` = seconds to wait for size-stable; default 0 for tests.)

- [ ] **Step 1: Write the failing test** — `tests/tools/test_graxpert.py`:
```python
from pathlib import Path
from aporntool.tools.graxpert import bge_cmd, denoise_cmd, fix_double_ext, run_graxpert


def test_bge_cmd_shape():
    c = bge_cmd("GraXpert.exe", "in.fit", "out", gpu=True, smoothing=0.0)
    assert c[0] == "GraXpert.exe"
    j = " ".join(c)
    assert "-cli" in c and "background-extraction" in j
    assert "-correction" in c and "Subtraction" in c
    assert "-gpu" in c and "true" in c


def test_denoise_cmd_has_strength():
    c = denoise_cmd("GraXpert.exe", "in.fit", "out", strength=0.8)
    assert "denoising" in " ".join(c) and "0.8" in " ".join(c)


def test_fix_double_ext_renames(tmp_path):
    # GraXpert writes out.fits.fits; we want out.fits.
    dd = tmp_path / "out.fits.fits"; dd.write_text("x", encoding="utf-8")
    final = fix_double_ext(tmp_path / "out")
    assert final == tmp_path / "out.fits"
    assert final.exists() and not dd.exists()


def test_fix_double_ext_noop_when_single(tmp_path):
    (tmp_path / "out.fits").write_text("x", encoding="utf-8")
    final = fix_double_ext(tmp_path / "out")
    assert final == tmp_path / "out.fits"


def test_run_graxpert_runs_then_fixes_extension(tmp_path):
    def fake_runner(cmd, **kw):
        # emulate GraXpert writing the double-extension file
        (tmp_path / "out.fits.fits").write_text("data", encoding="utf-8")
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    final = run_graxpert(["GraXpert.exe", "-cli"], tmp_path / "out", runner=fake_runner)
    assert final == tmp_path / "out.fits" and final.exists()
```

- [ ] **Step 2: Verify RED** — `python -m pytest tests/tools/test_graxpert.py -v` → ModuleNotFoundError.

- [ ] **Step 3: GREEN** — `aporntool/tools/graxpert.py`:
```python
"""Run GraXpert background-extraction + AI denoise; handle its .fits.fits output quirk."""
import subprocess
import time
from pathlib import Path


def bge_cmd(exe, in_path, out_path, *, gpu=True, smoothing=0.0) -> list:
    # Background extraction, Subtraction mode (the proven setting).
    return [str(exe), "-cli", "-cmd", "background-extraction",
            "-gpu", "true" if gpu else "false",
            "-smoothing", str(smoothing), "-correction", "Subtraction",
            "-output", str(out_path), str(in_path)]


def denoise_cmd(exe, in_path, out_path, *, gpu=True, strength=0.8) -> list:
    # AI denoise on the LINEAR image; 0.8 is the sweet spot (1.0 over-sharpens).
    return [str(exe), "-cli", "-cmd", "denoising",
            "-gpu", "true" if gpu else "false",
            "-strength", str(strength), "-output", str(out_path), str(in_path)]


def fix_double_ext(out_path) -> Path:
    # GraXpert appends .fits to -output, so `out` becomes `out.fits.fits`. Normalise to `out.fits`.
    out_path = Path(out_path)
    single = out_path.with_suffix(".fits") if out_path.suffix != ".fits" else out_path
    double = Path(str(single) + ".fits")
    if double.exists():
        if single.exists():
            single.unlink()
        double.rename(single)
    return single


def run_graxpert(argv, out_path, *, runner=subprocess.run, settle=0.0) -> Path:
    # Run GraXpert, wait for the write to settle (CLI can return early), then fix the extension.
    runner(argv, capture_output=True, text=True)
    if settle:
        time.sleep(settle)   # give the file system a moment; real callers pass a few seconds
    return fix_double_ext(out_path)
```

- [ ] **Step 4: Verify GREEN** — `python -m pytest tests/tools/test_graxpert.py -v` → 5 passed; then `python -m pytest -q`.
- [ ] **Step 5: Commit** — `git add ...; git commit -m "feat: GraXpert wrapper (bge/denoise cmds + .fits.fits fix)"`

---

### Task 2: SIRIL finish command generators (crop + mosaic/emission/cluster + deliverable saves)

**Files:** Create `aporntool/stages/finish_cmds.py`, `tests/stages/test_finish_cmds.py`.

**Interfaces (pure functions returning `list[str]`):**
- `crop_cmds(box) -> list[str]` — `box` is `"X Y W H"` or None (empty list if None).
- `deliverable_save_cmds(name) -> list[str]` — `save`/`savetif`/`savepng`/`savejpg` for the 4 deliverables (FR-27).
- `mosaic_finish_cmds(clean_name, out_name, *, star_reduce=0.5) -> list[str]` — stretch/color + starnet + pm blend + saves (from `5_Stretch.ssf` + `dso_mosaic.bat` stage5).
- `emission_finish_cmds(anchor, out_name, *, box, spcc) -> list[str]` — crop→subsky→platesolve→spcc→denoise→autostretch-linked→satu + saves (from `/dso-emission-nebula` Route A). `spcc` is the pre-built spcc command string (Plan-2 `spcc_cmd`).
- `cluster_finish_cmds(anchor, out_name, *, box, spcc) -> list[str]` — §4.8.

- [ ] **Step 1: Write the failing test** — `tests/stages/test_finish_cmds.py`:
```python
from aporntool.stages.finish_cmds import (
    crop_cmds, deliverable_save_cmds, mosaic_finish_cmds,
    emission_finish_cmds, cluster_finish_cmds,
)


def test_crop_cmds_optional():
    assert crop_cmds(None) == []
    assert crop_cmds("950 948 1450 2700") == ["crop 950 948 1450 2700"]


def test_deliverable_saves_all_four():
    c = deliverable_save_cmds("M31_final")
    j = "\n".join(c)
    assert "save M31_final" in j and "savetif M31_final" in j
    assert "savepng M31_final" in j and "savejpg M31_final 95" in j


def test_mosaic_finish_stretch_star_blend():
    c = mosaic_finish_cmds("M31_clean", "M31_final", star_reduce=0.5)
    j = "\n".join(c)
    assert "autostretch -linked" in j
    assert "ght -D=0.8" in j and "-human" in j
    assert "rmgreen 1" in j and "satu 0.7" in j
    assert "starnet" in j                       # star reduction
    assert "$*0.5" in j.replace(" ", "")        # pm blend at star_reduce
    assert "savetif M31_final" in j


def test_emission_finish_keeps_stars_and_spccs():
    c = emission_finish_cmds("M8_Linear", "M8_final", box="40 70 1000 1780",
                             spcc='spcc "-oscsensor=Sony IMX662" -catalog=localgaia')
    j = "\n".join(c)
    assert "crop 40 70 1000 1780" in j
    assert "subsky 1" in j and "platesolve -catalog=localgaia" in j
    assert 'spcc "-oscsensor=Sony IMX662"' in j
    assert "autostretch -linked" in j and "satu 0.7 0.1" in j
    assert "starnet" not in j                    # emission keeps all stars


def test_cluster_finish_light_denoise_and_ght():
    c = cluster_finish_cmds("M13_Linear", "M13_final", box=None,
                            spcc='spcc "-oscsensor=Sony IMX662" -catalog=localgaia')
    j = "\n".join(c)
    assert "denoise -mod=0.5" in j
    assert "ght -D=0.7" in j and "-HP=0.9" in j
    assert "satu 0.6 0.1" in j and "starnet" not in j
```

- [ ] **Step 2: Verify RED** — ModuleNotFoundError.

- [ ] **Step 3: GREEN** — `aporntool/stages/finish_cmds.py`:
```python
"""Pure SIRIL command lists for per-mode finishing (ported from the /dso-* skills + M31 scripts)."""


def crop_cmds(box) -> list:
    # Optional crop; box is "X Y W H" from --crop, or None to skip (use the full frame).
    return [f"crop {box}"] if box else []


def deliverable_save_cmds(name) -> list:
    # The four FR-27 deliverables (.fit/.tif/.png/.jpg). SIRIL `save` writes .fit.
    return [f"save {name}", f"savetif {name}", f"savepng {name}", f"savejpg {name} 95"]


def mosaic_finish_cmds(clean_name, out_name, *, star_reduce=0.5) -> list:
    # From 5_Stretch.ssf + dso_mosaic.bat: stretch/colour → StarNet star mask → blend some back.
    return [
        f"load {clean_name}",
        "autostretch -linked -2.8 0.15",
        "ght -D=0.8 -B=3 -SP=0.15 -HP=0.85 -human",
        "rmgreen 1",
        "satu 0.7",
        f"save {out_name}_stretched",
        f"load {out_name}_stretched",
        "starnet -starmask",                       # → starless + starmask_<name>
        f"save {out_name}_starless",
        # Blend a fraction of the stars back (full removal looks AI-generated, #10).
        f'pm "${out_name}_starless$+$starmask_{out_name}_stretched$*{star_reduce}"',
    ] + deliverable_save_cmds(out_name)


def emission_finish_cmds(anchor, out_name, *, box, spcc) -> list:
    # Route A (proven on M8): crop → gradient → local-Gaia platesolve + SPCC → denoise → stretch.
    return [
        f"load {anchor}",
        *crop_cmds(box),
        "subsky 1",
        "platesolve -catalog=localgaia",
        spcc,
        "denoise",
        "autostretch -linked",
        "satu 0.7 0.1",                            # keep all stars (rich field)
    ] + deliverable_save_cmds(out_name)


def cluster_finish_cmds(anchor, out_name, *, box, spcc) -> list:
    # §4.8 authored: light denoise + highlight-protected stretch; stars are the subject.
    return [
        f"load {anchor}",
        *crop_cmds(box),
        "subsky 1",
        "platesolve -catalog=localgaia",
        spcc,
        "denoise -mod=0.5",
        "autostretch -linked",
        "ght -D=0.7 -B=3 -HP=0.9 -human",
        "satu 0.6 0.1",
    ] + deliverable_save_cmds(out_name)
```

- [ ] **Step 4: Verify GREEN** — 5 passed; full suite.
- [ ] **Step 5: Commit** — `feat: SIRIL finish command generators (mosaic/emission/cluster + deliverables)`

---

### Task 3: Finish stages + `cmd_mode` wiring for SIRIL modes → end-to-end deliverables

**Files:** Create `aporntool/stages/finish.py`, `tests/stages/test_finish.py`; Modify `aporntool/cli.py`, add `tests/test_cli_mvp.py`.

**Interfaces:**
- `build_finish_stages(mode, ws, cfg, target, *, siril_exe, graxpert_exe=None, crop=None, star_reduce=0.5, runner=None) -> list[Stage]` — the finish stages after the golden anchor: for mosaic → `[bge, denoise, finish]`; emission/cluster → `[finish]` (SIRIL script does crop/subsky/spcc/denoise/stretch); reflection → handled in Task 5 (this task returns `[]` for reflection). Each stage writes its `.ssf`/runs GraXpert, verifies output; the final `finish` stage writes deliverables to the `--out` root.
- `cmd_mode` (cli.py): after preprocess reaches the anchor, append `build_finish_stages(...)` to the pipeline; add `--crop "X Y W H"` and `--star-reduce`; on success print the deliverable paths.

- [ ] **Step 1: Write the failing test** — `tests/stages/test_finish.py`:
```python
from pathlib import Path
from aporntool.workspace import Workspace
from aporntool.config import Config
from aporntool.catalog import resolve_target
from aporntool.stages.finish import build_finish_stages


def _rec(scripts):
    def run(cmd, **kw):
        # SIRIL fake: record script text; fabricate any saved deliverable as needed.
        try:
            script = Path(cmd[cmd.index("-s") + 1]); scripts.append(script.read_text(encoding="utf-8"))
        except (ValueError, IndexError):
            pass
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    return run


def test_mosaic_finish_stage_ids(tmp_path):
    ws = Workspace(tmp_path, "M31"); ws.create()
    stages = build_finish_stages("dso-mosaic", ws, Config.default(), resolve_target("M31"),
                                 siril_exe="siril-cli", graxpert_exe="GraXpert.exe")
    assert [s.id for s in stages] == ["bge", "denoise", "finish"]


def test_emission_finish_is_single_stage(tmp_path):
    ws = Workspace(tmp_path, "M8"); ws.create()
    stages = build_finish_stages("dso-emission-nebula", ws, Config.default(), resolve_target("M8"),
                                 siril_exe="siril-cli")
    assert [s.id for s in stages] == ["finish"]


def test_emission_finish_writes_deliverables_and_spcc(tmp_path):
    ws = Workspace(tmp_path, "M8"); ws.create()
    scripts = []
    stages = build_finish_stages("dso-emission-nebula", ws, Config.default(), resolve_target("M8"),
                                 siril_exe="siril-cli", runner=_rec(scripts))
    finish = next(s for s in stages if s.id == "finish")
    finish.run()
    text = (ws.logs / "finish.ssf").read_text(encoding="utf-8")
    assert 'spcc "-oscsensor=Sony IMX662"' in text
    assert "savetif" in text and "M8_final" in text
```

- [ ] **Step 2: Verify RED** — ModuleNotFoundError.

- [ ] **Step 3: GREEN** — `aporntool/stages/finish.py`:
```python
"""Assemble per-mode finish stages: golden anchor → deliverables at the --out root."""
import subprocess
from pathlib import Path

from aporntool.stages.engine import Stage
from aporntool.tools.siril import build_ssf, write_ssf, run_siril, spcc_cmd, gaia_catalog_cmds
from aporntool.tools.graxpert import bge_cmd, denoise_cmd, run_graxpert
from aporntool.stages.finish_cmds import (
    mosaic_finish_cmds, emission_finish_cmds, cluster_finish_cmds,
)
from aporntool.stages.preprocess import spcc_in_preprocess


def _nonzero(p) -> bool:
    p = Path(p)
    return p.exists() and p.stat().st_size > 0


def build_finish_stages(mode, ws, cfg, target, *, siril_exe, graxpert_exe=None,
                        crop=None, star_reduce=0.5, runner=None):
    runner = runner or subprocess.run
    anchor = ws.linear / f"{ws.target}_Linear"          # SIRIL load name (no .fit)
    out_name = str((ws.out_root / f"{ws.target}_final").as_posix())
    stages = []

    def _siril(stage_id, commands, cd):
        text = build_ssf(commands, cd=cd)
        script = write_ssf(text, ws.logs / f"{stage_id}.ssf")
        run_siril(script, workdir=ws.work, siril_exe=siril_exe, runner=runner,
                  log_path=ws.logs / f"{stage_id}.log")

    spcc = _spcc_string(cfg)

    if mode == "dso-mosaic":
        cropped = ws.linear / f"{ws.target}_cropped"
        bge_out = ws.graxpert / f"{ws.target}_bge"
        clean = ws.graxpert / f"{ws.target}_clean"
        # bge: crop (SIRIL) then GraXpert BGE on the cropped linear.
        def _bge():
            _siril("crop", [f"load {anchor.as_posix()}",
                            *( [f"crop {crop}"] if crop else [] ),
                            f"save {cropped.as_posix()}", "close"], cd=str(ws.linear))
            run_graxpert(bge_cmd(graxpert_exe, f"{cropped.as_posix()}.fit",
                                 str(bge_out), gpu=True), bge_out, runner=runner)
        stages.append(Stage("bge", _bge, lambda: _nonzero(f"{bge_out}.fits")))

        def _denoise():
            run_graxpert(denoise_cmd(graxpert_exe, f"{bge_out}.fits", str(clean),
                                     gpu=True, strength=0.8), clean, runner=runner)
        stages.append(Stage("denoise", _denoise, lambda: _nonzero(f"{clean}.fits")))

        def _finish():
            _siril("finish", mosaic_finish_cmds(clean.as_posix(), out_name,
                                                star_reduce=star_reduce), cd=str(ws.graxpert))
        stages.append(Stage("finish", _finish, lambda: _nonzero(out_name + ".tif")))

    elif mode in ("dso-emission-nebula", "dso-star-cluster"):
        gen = emission_finish_cmds if mode == "dso-emission-nebula" else cluster_finish_cmds
        def _finish():
            cmds = gaia_catalog_cmds(cfg.catalog_astro, cfg.catalog_photo) if (
                cfg.catalog_astro and cfg.catalog_photo) else []
            cmds += gen(anchor.as_posix(), out_name, box=crop, spcc=spcc)
            _siril("finish", cmds, cd=str(ws.linear))
        stages.append(Stage("finish", _finish, lambda: _nonzero(out_name + ".tif")))

    # reflection handled in Task 5.
    return stages


def _spcc_string(cfg) -> str:
    # Whole-token-quoted SPCC (gotcha #3); whiteref/region resolution is a later enhancement.
    return spcc_cmd()
```

Then in `aporntool/cli.py`: add `pm.add_argument("--crop", default=None)` and
`pm.add_argument("--star-reduce", type=float, default=0.5)` in the per-mode subparser loop, and
**REPLACE the entire Plan-2 tail of `cmd_mode`** (from `siril = _resolve_tool(cfg, "siril")` through the
`return 0`) with ONE combined pipeline so resume spans preprocess **and** finish (build both stage lists
up front; a single `run_pipeline` over the combined list; keep the Task-6 manifest load/reset logic):
```python
    # Build the FULL pipeline (preprocess → finish) up front so resume spans the whole run.
    siril = _resolve_tool(cfg, "siril")
    graxpert = _resolve_tool(cfg, "graxpert")
    stages = build_preprocess_stages(mode, ws, cfg, target, siril_exe=siril)
    stages += build_finish_stages(mode, ws, cfg, target, siril_exe=siril, graxpert_exe=graxpert,
                                  crop=args.crop, star_reduce=args.star_reduce)
    order = [s.id for s in stages]
    fp = input_fingerprint(iter_fits(ws.lights))
    # Resume from the on-disk manifest when it still matches (mode/order/fingerprint); else fresh.
    if ws.manifest_path.exists():
        m = load_manifest(ws.manifest_path)
        if m.mode != mode or m.order != order or m.input_fingerprint != fp:
            m = Manifest(mode=mode, target=ws.target, order=order, input_fingerprint=fp)
    else:
        m = Manifest(mode=mode, target=ws.target, order=order, input_fingerprint=fp)
    save_manifest(m, ws.manifest_path)
    ok = run_pipeline(m, stages, save=lambda mm: save_manifest(mm, ws.manifest_path),
                      from_stage=args.from_stage, redo=args.redo, force=args.force)
    if not ok:
        return 1
    anchor = ws.linear / f"{ws.target}_Linear.fit"
    tif = ws.out_root / f"{ws.target}_final.tif"
    if tif.exists():
        print(f"Done. Deliverables at {ws.out_root}: {ws.target}_final.(fits|tif|png|jpg)")
    else:
        print(f"Preprocess complete. Golden anchor: {anchor}  (finish stages: see mode)")
    return 0
```
Import `build_finish_stages` from `aporntool.stages.finish`. For **reflection**, `build_finish_stages`
returns `[]` until Task 5, so a reflection run stops at the golden anchor (the fallback print) — that's
expected until Task 5 wires it. `--crop`/`--star-reduce` default to skip-crop / 0.5.

`test_cli_mvp.py` should monkeypatch `run_siril`/`run_graxpert` to fabricate outputs (the anchor, `_bge.fits`, `_clean.fits`, and `<out>_final.tif`) and assert an emission run produces `<out>/M8_final.tif`.

- [ ] **Step 4: Verify GREEN** — new tests pass; full suite green.
- [ ] **Step 5: Commit** — `feat: finish stages + cmd_mode wiring → deliverables (mosaic/emission/cluster)`

---

### Task 4: Reflection dual-layer finish (pure numpy)

**Files:** Create `aporntool/stages/reflection_finish.py`, `tests/stages/test_reflection_finish.py`; Modify `pyproject.toml` (add `numpy`, `astropy`, `scipy`, `Pillow`, `tifffile`).

**Interfaces (pure, testable on synthetic arrays):**
- `mtf(m, x) -> np.ndarray`; `find_m(xmed, target) -> float`; `autostretch(rgb, target_bg, shadows_clip=-2.8) -> np.ndarray`
- `fix_starnet_grid(starless_rgb) -> np.ndarray` (median5 + gaussian1.5)
- `screen_blend(a, b) -> np.ndarray` (`1-(1-a)*(1-b)`)
- `save_deliverables(rgb01, out_stem) -> None` (writes .png + 16-bit .tif; .fits/.jpg too)

- [ ] **Step 1: Write the failing test** — `tests/stages/test_reflection_finish.py`:
```python
import numpy as np
from aporntool.stages.reflection_finish import mtf, autostretch, screen_blend, fix_starnet_grid


def test_mtf_endpoints():
    assert mtf(0.5, np.array([0.0]))[0] == 0.0
    assert mtf(0.5, np.array([1.0]))[0] == 1.0


def test_autostretch_brightens_midtones_and_stays_bounded():
    img = np.full((8, 8, 3), 0.05, np.float32)   # dark linear
    out = autostretch(img, target_bg=0.25)
    assert out.shape == img.shape
    assert 0.0 <= out.min() and out.max() <= 1.0
    assert out.mean() > img.mean()               # midtones lifted


def test_screen_blend_never_darkens():
    a = np.full((4, 4, 3), 0.4, np.float32)
    b = np.full((4, 4, 3), 0.5, np.float32)
    out = screen_blend(a, b)
    assert (out >= a - 1e-6).all() and out.max() <= 1.0


def test_fix_starnet_grid_smooths(tmp_path):
    rng = np.zeros((16, 16, 3), np.float32)
    rng[::2, ::2, :] = 1.0                        # checkerboard artifact
    out = fix_starnet_grid(rng)
    assert out.shape == rng.shape
    assert out.std() < rng.std()                  # grid smoothed away
```

- [ ] **Step 2: Verify RED** — ModuleNotFoundError.

- [ ] **Step 3: GREEN** — `aporntool/stages/reflection_finish.py` (port the `/dso-reflection-nebula` skill's core; minimal set to pass + a `run_reflection_finish` that ties StarNet2 + the layers together):
```python
"""Reflection-nebula dual-layer finish (pure numpy), ported from the /dso-reflection-nebula skill."""
import numpy as np
from scipy.ndimage import gaussian_filter, median_filter


def mtf(m, v):
    # Midtones transfer function (SIRIL/PixInsight-style) — the stretch primitive.
    v = np.asarray(v, dtype=np.float64)
    return np.where(v <= 0, 0.0, np.where(v >= 1, 1.0,
                    ((m - 1) * v) / ((2 * m - 1) * v - m)))


def find_m(xmed, target):
    # Bisect for the m that maps median xmed → target brightness.
    lo, hi = 1e-7, 1 - 1e-7
    for _ in range(64):
        mid = (lo + hi) / 2
        if mtf(mid, np.array([xmed]))[0] < target:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def autostretch(rgb, target_bg=0.25, shadows_clip=-2.8):
    # Luminance-linked autostretch: clip shadows, then MTF each channel so the bg sits at target_bg.
    x = np.clip(np.asarray(rgb, np.float64), 0, 1)
    lum = x.mean(2)
    med = np.median(lum)
    madN = 1.4826 * np.median(np.abs(lum - med)) or 1e-6
    c = np.clip(med + shadows_clip * madN, 0, 1)
    medp = (med - c) / (1 - c) if c < 1 else 0.0
    m = find_m(medp, target_bg)
    normed = np.clip((x - c) / (1 - c if c < 1 else 1), 0, 1)
    return np.clip(np.stack([mtf(m, normed[..., i]) for i in range(3)], -1), 0, 1)


def fix_starnet_grid(starless_rgb):
    # StarNet2 leaves a checkerboard; kill it at the source (median5 + gaussian1.5) — gotcha #9.
    out = np.asarray(starless_rgb, np.float64).copy()
    for ch in range(3):
        out[..., ch] = median_filter(out[..., ch], size=5)
    return gaussian_filter(out, sigma=(1.5, 1.5, 0))


def screen_blend(a, b):
    # Composite stars over starless without blowing highlights: 1-(1-a)(1-b).
    return np.clip(1 - (1 - np.asarray(a, np.float64)) * (1 - np.asarray(b, np.float64)), 0, 1)
```

- [ ] **Step 4: Verify GREEN** — 4 passed; full suite (numpy/scipy already installed).
- [ ] **Step 5: Commit** — `feat: reflection dual-layer finish primitives (mtf/autostretch/grid-fix/screen-blend)`

---

### Task 5: Wire reflection finish end-to-end + `--profile`

**Files:** Modify `aporntool/stages/reflection_finish.py` (add `run_reflection_finish` + `save_deliverables`), `aporntool/stages/finish.py` (reflection branch), `aporntool/cli.py` (`--profile`); tests in `tests/stages/test_reflection_finish.py`.

**Interfaces:**
- `run_reflection_finish(clean_fits, out_stem, *, starnet_exe, runner=subprocess.run, target_bg=0.35) -> Path` — load `_clean.fits` (astropy) → autostretch → StarNet2 (`-i tif -o tif`) → grid-fix → stars=stretched-starless → screen blend → `save_deliverables`.
- `save_deliverables(rgb01, out_stem) -> None` — writes `.png`, 16-bit `.tif`, `.jpg`; `.fits` via astropy.
- `build_finish_stages(... reflection ...)` returns `[bge, denoise, finish]` where `finish` calls `run_reflection_finish`.
- `cmd_mode`: `--profile {mosaic|emission|reflection|star-cluster|galaxy}` overrides the default finish profile for the mode.

- [ ] **Step 1: Write the failing test** — append to `tests/stages/test_reflection_finish.py`:
```python
import numpy as np, tifffile
from pathlib import Path
from astropy.io import fits
from aporntool.stages.reflection_finish import run_reflection_finish, save_deliverables


def test_save_deliverables_writes_all(tmp_path):
    img = np.clip(np.random.RandomState(0).rand(8, 8, 3), 0, 1).astype(np.float32)
    save_deliverables(img, str(tmp_path / "M78_final"))
    for ext in ("png", "tif", "jpg", "fits"):
        assert (tmp_path / f"M78_final.{ext}").exists()


def test_run_reflection_finish_produces_deliverables(tmp_path):
    # Fake StarNet2: copy input tif to output (no stars removed) so the layer math runs.
    clean = tmp_path / "clean.fits"
    fits.writeto(clean, np.random.RandomState(1).rand(3, 16, 16).astype(np.float32))
    def fake_starnet(cmd, **kw):
        i = cmd[cmd.index("-i") + 1]; o = cmd[cmd.index("-o") + 1]
        tifffile.imwrite(o, tifffile.imread(i))
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    out = run_reflection_finish(clean, str(tmp_path / "M78_final"),
                                starnet_exe="starnet2", runner=fake_starnet)
    assert Path(str(out)).exists() or (tmp_path / "M78_final.tif").exists()
```

- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: GREEN** — add `save_deliverables` + `run_reflection_finish` (astropy load `[C,H,W]→HWC`, normalize, autostretch, write tif for StarNet2, run, read back, grid-fix, `stars = clip(stretched - starless)`, `combined = screen_blend(starless_processed, stars)`, save). Wire the reflection branch in `finish.py` (`[bge, denoise, finish]`, finish calls `run_reflection_finish(clean.fits, out_stem, starnet_exe=_resolve_tool(cfg,"starnet2"))`). Add `--profile` arg in cli.
- [ ] **Step 4: Verify GREEN** — full suite green.
- [ ] **Step 5: Commit** — `feat: reflection end-to-end finish + --profile (MVP complete)`

---

## Self-Review

- **Spec coverage:** GraXpert BGE/denoise + `.fits.fits` (FR-17, #6) → T1; per-mode SIRIL finish ported from skills/M31 scripts (§4.4b) → T2/T3; deliverables FR-27 → T2/T3/T5; reflection dual-layer + StarNet grid-fix (#9) + screen blend (#10) → T4/T5; `--crop`/`--profile`/`--star-reduce` (FR-29) → T3/T5; resume spans preprocess+finish (FR-24) → T3.
- **Deferred (post-MVP):** auto-crop from WCS (MVP uses `--crop`/skip); previews per stage (FR-25); ffmpeg final polish curve; the Plan-3 hardening backlog (FR-26 solved-frame count, `_tool_candidates`, type-hint sweep, GraXpert size-stable settle tuning). All flagged, none block the one-command subs→deliverable MVP.
- **Manual validation:** the real SIRIL+GraXpert+StarNet2 run is the acceptance test (tools mocked here).

## Global Constraints reminder for the reviewer
GraXpert `.fits.fits` rename; whole-token SPCC quoting; `-feather=100` already baked in preprocess; StarNet grid-fix median5+gaussian1.5; screen-blend not additive; deliverables at `--out` root; resume spans the whole pipeline.
