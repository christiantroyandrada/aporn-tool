# aPornTool Preprocess Core (Plan 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the parameterized SIRIL **preprocess core** — take the staged `.fit` subs through `convert → calibrate → register → stack → [mirrorx] → [spcc]` to the per-mode **golden anchor** (`02_linear/<TARGET>_Linear.fit`), with every stage checkpointed, verified, and resumable via the manifest, and wired into `cmd_mode`.

**Architecture:** Pure, unit-testable pieces glued by a small stage engine. Per-stage SIRIL `.ssf` command lists are produced by pure functions (trivially testable by asserting the exact commands per mode). A `run_siril` wrapper invokes `siril-cli` through an **injectable runner** so all tests run with SIRIL *mocked* (SIRIL is not installed on the dev box; real stacking is validated manually — NFR-8). The stage engine runs each stage only if the manifest says it isn't `done`, verifies its output file, updates the manifest, and stops with an actionable message on failure — realizing FR-24 resume/`--from`/`--redo`/`--continue`.

**Tech Stack:** Python 3.10+, stdlib only (subprocess, pathlib, dataclasses). Builds on the Plan-1 foundation modules (`workspace`, `manifest`, `config`, `catalog`, `preflight`, `cli`). pytest for tests.

## Global Constraints

Copied verbatim from `REQUIREMENTS.md` — every task implicitly includes these:

- **Cross-platform (NFR-10):** `pathlib`/`os.path` only; per-OS tool paths via discovery/config; no drive letters. `siril-cli` is always invoked with an **absolute path to the `.ssf`** and `-d <workdir>` (siril-cli's default CWD is elsewhere; relative paths fail — FR-13).
- **Teaching codebase (NFR-9):** every function + non-obvious block gets a brief plain-language comment (*what & why*). Small named functions; each module opens with a one-line purpose header.
- **Stage vocabulary & I/O (§4.4b):** IDs `stage → convert → calibrate → register → stack → mirrorx → spcc → …`; sequence basename `light`; files under `_work/<target>/` as per the §4.4b table.
- **Golden anchor (FR-12c):** one canonical file `02_linear/<TARGET>_Linear.fit`. **mosaic & reflection → post-SPCC**; **emission & star-cluster → post-stack + post-mirrorx, pre-SPCC.** Manifest records the current anchor. Never delete it (NFR-4).
- **Per-mode preprocess sequence (FR-12d):**
  - mosaic: `convert → calibrate → register(WCS,framing=max) → stack(feather=100) → spcc`
  - reflection: `convert → calibrate → register(-2pass) → stack → mirrorx → spcc`
  - emission: `convert → calibrate → register(-2pass) → stack → mirrorx`
  - star-cluster: `convert → calibrate → register(-2pass,+wfwhm cull) → stack → mirrorx`
- **Gotchas (§10) that bind preprocess:** `-feather=100` mandatory for mosaic (#1); local-Gaia SPCC with both catalog paths + `-catalog=localgaia` on platesolve AND spcc, OSC args quoted whole-token `"-oscsensor=Sony IMX662"` (#2/#3, FR-16); `mirrorx` single-panel only (#8); `seqplatesolve` false-negative → verify by solved-frame count, not exit code (#12, FR-26); no darks/flats (Seestar). SPCC region is per-target (#17).
- **Save scripts to `logs/` (FR-12):** every generated `.ssf` is written into `_work/<target>/logs/` before running, for reproducibility.
- **Fail loud (NFR-3):** every SIRIL call is checked; a stage is `done` only after its output file is verified present + non-zero (FR-24b).

---

## File Structure

```
aporntool/
  tools/
    __init__.py
    siril.py              # .ssf builder, run_siril() wrapper, spcc/catalog command helpers
  stages/
    __init__.py
    engine.py             # Stage dataclass + run_pipeline() (resume/--from/--redo/--force)
    preprocess.py         # per-mode preprocess stage list → golden anchor
  cli.py                  # MODIFY: cmd_mode runs the preprocess pipeline (replaces the Plan-1 stub)
tests/
  tools/test_siril.py
  stages/test_engine.py
  stages/test_preprocess.py
  test_cli_preprocess.py
```

Each new file has one responsibility. SIRIL is only ever invoked through `tools/siril.run_siril`, so tests mock exactly one seam.

---

### Task 1: SIRIL `.ssf` builder + `run_siril` wrapper

**Files:**
- Create: `aporntool/tools/__init__.py` (empty package marker)
- Create: `aporntool/tools/siril.py`
- Create: `tests/tools/__init__.py` (empty), `tests/tools/test_siril.py`

**Interfaces:**
- Produces:
  - `build_ssf(commands: list[str], *, requires: str = "1.3.6", cd: str | None = None) -> str`
  - `write_ssf(text: str, path) -> Path`
  - `SirilResult` dataclass (`returncode: int`, `stdout: str`, `stderr: str`)
  - `run_siril(script_path, *, workdir, siril_exe, runner=subprocess.run, log_path=None) -> SirilResult`

- [ ] **Step 1: Write the failing test**

`tests/tools/test_siril.py`:
```python
from pathlib import Path
from aporntool.tools.siril import build_ssf, write_ssf, run_siril, SirilResult


def test_build_ssf_has_requires_header_and_commands():
    text = build_ssf(["calibrate light -debayer", "close"], requires="1.3.6")
    lines = text.splitlines()
    assert lines[0] == "requires 1.3.6"          # SIRIL scripts must declare a version floor
    assert "calibrate light -debayer" in lines
    assert lines[-1] == "close"


def test_build_ssf_optional_cd_is_quoted():
    text = build_ssf(["link light"], cd=r"C:\Astro\M 31")
    assert 'cd "C:\\Astro\\M 31"' in text     # spaced paths must be quoted


def test_write_ssf_roundtrips(tmp_path):
    p = write_ssf("requires 1.3.6\nclose\n", tmp_path / "s.ssf")
    assert p.read_text(encoding="utf-8").startswith("requires 1.3.6")


def test_run_siril_invokes_cli_with_abs_script_and_workdir(tmp_path):
    calls = {}
    def fake_runner(cmd, **kw):
        calls["cmd"] = cmd
        class R: returncode = 0; stdout = "ok"; stderr = ""
        return R()
    script = tmp_path / "s.ssf"; script.write_text("requires 1.3.6\n", encoding="utf-8")
    res = run_siril(script, workdir=tmp_path, siril_exe="/usr/bin/siril-cli", runner=fake_runner)
    assert isinstance(res, SirilResult) and res.returncode == 0
    # siril-cli needs -d <workdir> and -s <absolute script path>
    assert calls["cmd"][0] == "/usr/bin/siril-cli"
    assert "-d" in calls["cmd"] and str(tmp_path) in calls["cmd"]
    assert "-s" in calls["cmd"] and str(script.resolve()) in calls["cmd"]


def test_run_siril_writes_log(tmp_path):
    def fake_runner(cmd, **kw):
        class R: returncode = 0; stdout = "SIRIL says hi"; stderr = ""
        return R()
    script = tmp_path / "s.ssf"; script.write_text("requires 1.3.6\n", encoding="utf-8")
    log = tmp_path / "stage.log"
    run_siril(script, workdir=tmp_path, siril_exe="siril-cli", runner=fake_runner, log_path=log)
    assert "SIRIL says hi" in log.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_siril.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aporntool.tools'`.

- [ ] **Step 3: Write minimal implementation**

`aporntool/tools/__init__.py`:
```python
"""External-tool wrappers (SIRIL, GraXpert, StarNet2)."""
```

`tests/tools/__init__.py`: (empty file)

`aporntool/tools/siril.py`:
```python
"""Build and run SIRIL headless scripts (.ssf) via siril-cli."""
import subprocess
from dataclasses import dataclass
from pathlib import Path


def build_ssf(commands, *, requires: str = "1.3.6", cd: str | None = None) -> str:
    # Every SIRIL script must declare a version floor first; then an optional working dir,
    # then the commands, one per line.
    lines = [f"requires {requires}"]
    if cd is not None:
        lines.append(f'cd "{cd}"')   # quote so paths with spaces survive
    lines.extend(commands)
    return "\n".join(lines) + "\n"


def write_ssf(text: str, path) -> Path:
    # Persist the script (we keep every generated .ssf in logs/ for reproducibility, FR-12).
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@dataclass
class SirilResult:
    returncode: int
    stdout: str
    stderr: str


def run_siril(script_path, *, workdir, siril_exe, runner=subprocess.run, log_path=None) -> SirilResult:
    # siril-cli's default CWD is elsewhere, so we pass -d <workdir> and an ABSOLUTE script path.
    script_path = Path(script_path).resolve()
    cmd = [str(siril_exe), "-d", str(workdir), "-s", str(script_path)]
    # `runner` is injectable so tests never launch a real SIRIL.
    proc = runner(cmd, capture_output=True, text=True)
    result = SirilResult(proc.returncode, proc.stdout or "", proc.stderr or "")
    if log_path is not None:
        # Keep the console output next to the script for debugging a failed stage.
        Path(log_path).write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/tools/test_siril.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add aporntool/tools/__init__.py aporntool/tools/siril.py tests/tools/__init__.py tests/tools/test_siril.py
git commit -m "feat: SIRIL .ssf builder + run_siril wrapper (injectable runner)"
```

---

### Task 2: SPCC + local-Gaia command helpers (FR-16, gotchas #2/#3)

**Files:**
- Modify: `aporntool/tools/siril.py`
- Modify: `tests/tools/test_siril.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `gaia_catalog_cmds(astro_path: str, photo_path: str) -> list[str]`
  - `platesolve_cmd(*, coords: str | None = None, focal: float | None = None, pixel: float | None = None, catalog: str = "localgaia") -> str`
  - `spcc_cmd(*, sensor: str = "Sony IMX662", osc_filter: str = "UV/IR Block", whiteref: str = "Average Spiral Galaxy", catalog: str = "localgaia") -> str`

- [ ] **Step 1: Write the failing test**

Append to `tests/tools/test_siril.py`:
```python
from aporntool.tools.siril import gaia_catalog_cmds, platesolve_cmd, spcc_cmd


def test_gaia_catalog_cmds_set_both_paths():
    cmds = gaia_catalog_cmds("/g/astro.dat", "/g/xpsamp")
    assert any("catalogue_gaia_astro=/g/astro.dat" in c for c in cmds)
    assert any("catalogue_gaia_photo=/g/xpsamp" in c for c in cmds)


def test_platesolve_uses_localgaia_and_coords():
    c = platesolve_cmd(coords="11.25,41.4", focal=150, pixel=2.9)
    assert c.startswith("platesolve 11.25,41.4")
    assert "-focal=150" in c and "-pixelsize=2.9" in c and "-catalog=localgaia" in c


def test_platesolve_blind_when_no_coords():
    # In finish we platesolve the already-framed image with no seed coords.
    assert platesolve_cmd() == "platesolve -catalog=localgaia"


def test_spcc_quotes_whole_token_including_flag_name():
    c = spcc_cmd()
    # CRITICAL gotcha #3: the WHOLE space-containing token is quoted, flag name included.
    assert '"-oscsensor=Sony IMX662"' in c
    assert '"-oscfilter=UV/IR Block"' in c
    assert '"-whiteref=Average Spiral Galaxy"' in c
    assert "-catalog=localgaia" in c
    assert '-oscsensor="Sony IMX662"' not in c   # the WRONG form must never appear
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_siril.py -v`
Expected: FAIL — `ImportError: cannot import name 'gaia_catalog_cmds'`.

- [ ] **Step 3: Write minimal implementation**

Append to `aporntool/tools/siril.py`:
```python
def gaia_catalog_cmds(astro_path: str, photo_path: str) -> list:
    # siril-cli does NOT auto-read the local Gaia catalogs — set both paths in-script or it
    # falls back to the dead online server. _astro is a FILE, _photo is a FOLDER.
    return [
        f"set core.catalogue_gaia_astro={astro_path}",
        f"set core.catalogue_gaia_photo={photo_path}",
    ]


def platesolve_cmd(*, coords=None, focal=None, pixel=None, catalog="localgaia") -> str:
    # With coords we seed the solve (mosaic stack); blind (no coords) re-solves a framed image.
    parts = ["platesolve"]
    if coords:
        parts.append(coords)
    if focal is not None:
        parts.append(f"-focal={focal:g}")
    if pixel is not None:
        parts.append(f"-pixelsize={pixel:g}")
    parts.append(f"-catalog={catalog}")
    return " ".join(parts)


def spcc_cmd(*, sensor="Sony IMX662", osc_filter="UV/IR Block",
             whiteref="Average Spiral Galaxy", catalog="localgaia") -> str:
    # Quote the WHOLE token, flag name included ("-oscsensor=Sony IMX662") — the other form
    # ("-oscsensor=...") makes siril-cli error "Invalid argument". (gotcha #3)
    return (f'spcc "-oscsensor={sensor}" "-oscfilter={osc_filter}" '
            f'"-whiteref={whiteref}" -catalog={catalog}')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/tools/test_siril.py -v`
Expected: PASS (9 passed total in this file).

- [ ] **Step 5: Commit**

```bash
git add aporntool/tools/siril.py tests/tools/test_siril.py
git commit -m "feat: SPCC + local-Gaia + platesolve command builders (whole-token quoting)"
```

---

### Task 3: Stage engine — resume, `--from`, `--redo`, `--force` (FR-24/24a/24b)

**Files:**
- Create: `aporntool/stages/__init__.py` (empty), `aporntool/stages/engine.py`
- Create: `tests/stages/__init__.py` (empty), `tests/stages/test_engine.py`

**Interfaces:**
- Consumes: `Manifest`, `StageStatus`, `save_manifest` (Plan 1 `aporntool.manifest`).
- Produces:
  - `Stage` dataclass: `id: str`, `run: Callable[[], None]`, `produces: Callable[[], bool]`
  - `run_pipeline(manifest, stages, *, save, from_stage=None, redo=None, force=False, log=print) -> bool` — runs stages in `manifest.order`, skipping `done` ones (unless forced/redone-from); returns `True` iff all stages ended `done`.

- [ ] **Step 1: Write the failing test**

`tests/stages/__init__.py`: (empty)

`tests/stages/test_engine.py`:
```python
from aporntool.manifest import Manifest, StageStatus
from aporntool.stages.engine import Stage, run_pipeline


def _mk(order):
    m = Manifest(mode="dso-emission-nebula", target="M8", order=order)
    return m


def _saver():
    saves = []
    return saves, (lambda m, *a, **k: saves.append(m.next_pending()))


def test_runs_all_and_marks_done():
    ran = []
    m = _mk(["a", "b"])
    stages = [Stage("a", lambda: ran.append("a"), lambda: True),
              Stage("b", lambda: ran.append("b"), lambda: True)]
    _, save = _saver()
    ok = run_pipeline(m, stages, save=save)
    assert ok is True and ran == ["a", "b"]
    assert m.stage("a").status == StageStatus.DONE.value
    assert m.stage("b").status == StageStatus.DONE.value


def test_skips_already_done_stages():
    ran = []
    m = _mk(["a", "b"])
    m.mark("a", StageStatus.DONE)               # a already done (resume)
    stages = [Stage("a", lambda: ran.append("a"), lambda: True),
              Stage("b", lambda: ran.append("b"), lambda: True)]
    _, save = _saver()
    run_pipeline(m, stages, save=save)
    assert ran == ["b"]                         # a was skipped


def test_stops_and_marks_failed_when_output_missing():
    ran = []
    m = _mk(["a", "b"])
    stages = [Stage("a", lambda: ran.append("a"), lambda: False),   # produces nothing
              Stage("b", lambda: ran.append("b"), lambda: True)]
    _, save = _saver()
    ok = run_pipeline(m, stages, save=save)
    assert ok is False
    assert m.stage("a").status == StageStatus.FAILED.value
    assert ran == ["a"]                         # b never runs after a fails


def test_redo_reruns_a_done_stage_and_downstream():
    ran = []
    m = _mk(["a", "b", "c"])
    for s in ("a", "b", "c"):
        m.mark(s, StageStatus.DONE)
    stages = [Stage(s, (lambda s=s: ran.append(s)), lambda: True) for s in ("a", "b", "c")]
    _, save = _saver()
    run_pipeline(m, stages, save=save, redo="b")
    assert ran == ["b", "c"]                    # b + downstream re-run; a untouched


def test_force_reruns_everything():
    ran = []
    m = _mk(["a", "b"])
    m.mark("a", StageStatus.DONE); m.mark("b", StageStatus.DONE)
    stages = [Stage("a", lambda: ran.append("a"), lambda: True),
              Stage("b", lambda: ran.append("b"), lambda: True)]
    _, save = _saver()
    run_pipeline(m, stages, save=save, force=True)
    assert ran == ["a", "b"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/stages/test_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aporntool.stages'`.

- [ ] **Step 3: Write minimal implementation**

`aporntool/stages/__init__.py`:
```python
"""Pipeline stages and the engine that runs/resumes them."""
```

`aporntool/stages/engine.py`:
```python
"""Run pipeline stages with checkpoint/resume: skip done stages, verify output, stop on failure."""
from dataclasses import dataclass
from typing import Callable

from aporntool.manifest import StageStatus


@dataclass
class Stage:
    id: str
    run: Callable[[], None]        # does the work (e.g. runs a SIRIL script)
    produces: Callable[[], bool]   # returns True iff this stage's output now exists + is valid


def run_pipeline(manifest, stages, *, save, from_stage=None, redo=None, force=False, log=print) -> bool:
    # Decide where to (re)start. --force reruns all; --redo/--from reset from a named stage
    # downstream (invalidation, FR-24e); otherwise resume at the first not-done stage.
    if redo or from_stage:
        manifest.invalidate_from(redo or from_stage)
    by_id = {s.id: s for s in stages}
    for sid in manifest.order:
        rec = manifest.stage(sid)
        if rec.status == StageStatus.DONE.value and not force:
            continue                                  # already done → skip (resume)
        stage = by_id[sid]
        manifest.mark(sid, StageStatus.RUNNING); save(manifest)
        stage.run()
        if stage.produces():
            manifest.mark(sid, StageStatus.DONE, error=""); save(manifest)
        else:
            manifest.mark(sid, StageStatus.FAILED,
                          error=f"stage '{sid}' produced no valid output")
            save(manifest)
            log(f"FAILED at stage '{sid}': no valid output. Fix, then re-run to continue.")
            return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/stages/test_engine.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add aporntool/stages/__init__.py aporntool/stages/engine.py tests/stages/__init__.py tests/stages/test_engine.py
git commit -m "feat: stage engine with resume/--from/--redo/--force + output verification"
```

---

### Task 4: Per-mode preprocess command generators (§4.4b/§4.4a, FR-12d)

**Files:**
- Create: `aporntool/stages/preprocess.py`
- Create: `tests/stages/test_preprocess.py`

**Interfaces:**
- Consumes: `Workspace` (Plan 1), the `siril` command helpers (Task 2).
- Produces pure command-list functions (each returns `list[str]` of SIRIL commands):
  - `convert_cmds() -> list[str]`
  - `calibrate_cmds() -> list[str]`
  - `register_cmds(mode: str) -> list[str]`
  - `stack_cmds(mode: str) -> list[str]`
  - `mirrorx_cmds() -> list[str]`
  - `is_single_panel(mode: str) -> bool`
  - `spcc_in_preprocess(mode: str) -> bool`  (True for mosaic/reflection)

- [ ] **Step 1: Write the failing test**

`tests/stages/test_preprocess.py`:
```python
from aporntool.stages.preprocess import (
    convert_cmds, calibrate_cmds, register_cmds, stack_cmds, mirrorx_cmds,
    is_single_panel, spcc_in_preprocess,
)


def test_calibrate_debayers_no_darks():
    assert calibrate_cmds() == ["calibrate light -debayer"]


def test_mosaic_register_uses_wcs_and_framing_max():
    cmds = register_cmds("dso-mosaic")
    joined = " ".join(cmds)
    assert "seqplatesolve pp_light" in joined      # WCS assembly path
    assert "-framing=max" in joined


def test_single_panel_register_uses_2pass():
    cmds = register_cmds("dso-emission-nebula")
    joined = " ".join(cmds)
    assert "register pp_light -2pass" in joined
    assert "-framing=max" not in joined


def test_star_cluster_adds_wfwhm_cull():
    joined = " ".join(register_cmds("dso-star-cluster"))
    assert "-filter-round=2.5k" in joined and "-filter-wfwhm=2.5k" in joined


def test_mosaic_stack_has_feather_100():
    joined = " ".join(stack_cmds("dso-mosaic"))
    assert "-feather=100" in joined and "-out=result" in joined


def test_single_panel_stack_has_no_feather():
    joined = " ".join(stack_cmds("dso-emission-nebula"))
    assert "-feather" not in joined


def test_mirrorx_only_single_panel():
    assert is_single_panel("dso-emission-nebula") is True
    assert is_single_panel("dso-mosaic") is False
    assert mirrorx_cmds() == ["mirrorx_single result"]


def test_spcc_in_preprocess_flags():
    assert spcc_in_preprocess("dso-mosaic") is True
    assert spcc_in_preprocess("dso-reflection-nebula") is True
    assert spcc_in_preprocess("dso-emission-nebula") is False   # emission SPCCs in finish
    assert spcc_in_preprocess("dso-star-cluster") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/stages/test_preprocess.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aporntool.stages.preprocess'`.

- [ ] **Step 3: Write minimal implementation**

`aporntool/stages/preprocess.py`:
```python
"""Per-mode SIRIL command lists for the preprocess core (§4.4b). Pure — no I/O, easy to test."""

_SINGLE_PANEL = {"dso-emission-nebula", "dso-reflection-nebula", "dso-star-cluster"}
_SPCC_IN_PREPROCESS = {"dso-mosaic", "dso-reflection-nebula"}   # others SPCC in the finish phase


def is_single_panel(mode: str) -> bool:
    # Mosaic assembles via WCS (no flip); single-panel modes need mirrorx.
    return mode in _SINGLE_PANEL


def spcc_in_preprocess(mode: str) -> bool:
    # Mosaic/reflection color-calibrate before the golden anchor; emission/cluster do it in finish.
    return mode in _SPCC_IN_PREPROCESS


def convert_cmds() -> list:
    # Link all staged .fit in the lights dir into a SIRIL sequence named "light".
    return ["link light -out=../01_process"]


def calibrate_cmds() -> list:
    # Debayer only — the Seestar already calibrated internally, so no darks/flats/bias.
    return ["calibrate light -debayer"]


def register_cmds(mode: str) -> list:
    if mode == "dso-mosaic":
        # WCS-based assembly: plate-solve every frame, then reproject to a common max frame.
        return ["seqplatesolve pp_light -force -nocache",
                "seqapplyreg pp_light -filter-round=2.5k -framing=max"]
    if mode == "dso-star-cluster":
        # Tight round stars are the payoff → also cull the worst FWHM (authored -wfwhm=2.5k).
        return ["register pp_light -2pass",
                "seqapplyreg pp_light -filter-round=2.5k -filter-wfwhm=2.5k"]
    # emission / reflection: star-based 2-pass registration.
    return ["register pp_light -2pass",
            "seqapplyreg pp_light -filter-round=2.5k"]


def stack_cmds(mode: str) -> list:
    # Sigma-clip stack. feather=100 is MANDATORY for mosaics or panel seams are permanent (#1).
    feather = " -feather=100" if mode == "dso-mosaic" else ""
    return [f"stack r_pp_light rej 3 3 -norm=addscale -output_norm -rgb_equal{feather} -out=result"]


def mirrorx_cmds() -> list:
    # Seestar frames are vertically flipped; correct single-panel stacks (mosaic uses WCS instead).
    return ["mirrorx_single result"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/stages/test_preprocess.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add aporntool/stages/preprocess.py tests/stages/test_preprocess.py
git commit -m "feat: per-mode preprocess command generators (feather/framing/mirrorx/spcc rules)"
```

---

### Task 5: Assemble the preprocess Stage list → golden anchor

**Files:**
- Modify: `aporntool/stages/preprocess.py`
- Modify: `tests/stages/test_preprocess.py`

**Interfaces:**
- Consumes: `Workspace` (Plan 1: `.lights/.process/.linear/.logs`, `.target`), `Config` (Plan 1: `catalog_astro/catalog_photo`, `seestar_focal_mm/pixel_um`), `Target` (Plan 1: `ra/dec`), `build_ssf`/`write_ssf`/`run_siril`/`gaia_catalog_cmds`/`platesolve_cmd`/`spcc_cmd` (Tasks 1-2), `Stage` (Task 3).
- Produces: `build_preprocess_stages(mode, ws, cfg, target, *, siril_exe, runner=subprocess.run) -> list[Stage]` — the ordered `Stage`s from `convert` to the golden-anchor save. Each `Stage.run` writes its `.ssf` into `ws.logs`, runs it, and `Stage.produces` verifies the expected output file exists.

- [ ] **Step 1: Write the failing test**

Append to `tests/stages/test_preprocess.py`:
```python
from pathlib import Path
from aporntool.workspace import Workspace
from aporntool.config import Config
from aporntool.catalog import resolve_target
from aporntool.stages.preprocess import build_preprocess_stages


def _fake_runner_factory(record):
    # A stand-in for siril-cli: records the script it "ran" and simulates the output file
    # the real SIRIL would have produced, so Stage.produces() passes.
    def run(cmd, **kw):
        script = Path(cmd[cmd.index("-s") + 1])
        record.append(script.read_text(encoding="utf-8"))
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    return run


def test_mosaic_stage_ids_and_order(tmp_path):
    ws = Workspace(tmp_path, "M31"); ws.create()
    stages = build_preprocess_stages("dso-mosaic", ws, Config.default(),
                                     resolve_target("M31"), siril_exe="siril-cli")
    assert [s.id for s in stages] == ["convert", "calibrate", "register", "stack", "spcc"]


def test_emission_stage_ids_include_mirrorx_and_no_spcc(tmp_path):
    ws = Workspace(tmp_path, "M8"); ws.create()
    stages = build_preprocess_stages("dso-emission-nebula", ws, Config.default(),
                                     resolve_target("M8"), siril_exe="siril-cli")
    assert [s.id for s in stages] == ["convert", "calibrate", "register", "stack", "mirrorx"]


def test_emission_mirrorx_stage_saves_golden_anchor(tmp_path):
    ws = Workspace(tmp_path, "M8"); ws.create()
    scripts = []
    stages = build_preprocess_stages("dso-emission-nebula", ws, Config.default(),
                                     resolve_target("M8"), siril_exe="siril-cli",
                                     runner=_fake_runner_factory(scripts))
    mirrorx = next(s for s in stages if s.id == "mirrorx")
    mirrorx.run()
    # emission's mirrorx is the LAST preprocess stage → its .ssf mirrors AND saves <TARGET>_Linear.
    assert any("mirrorx_single result" in s and "M8_Linear" in s for s in scripts)
    assert (ws.logs / "mirrorx.ssf").exists()


def test_spcc_stage_uses_local_gaia_paths_when_configured(tmp_path):
    ws = Workspace(tmp_path, "M31"); ws.create()
    cfg = Config.default()
    cfg.catalog_astro = "/g/astro.dat"; cfg.catalog_photo = "/g/xpsamp"
    scripts = []
    stages = build_preprocess_stages("dso-mosaic", ws, cfg, resolve_target("M31"),
                                     siril_exe="siril-cli", runner=_fake_runner_factory(scripts))
    spcc = next(s for s in stages if s.id == "spcc")
    spcc.run()
    text = (ws.logs / "spcc.ssf").read_text(encoding="utf-8")
    assert "catalogue_gaia_astro=/g/astro.dat" in text
    assert '"-oscsensor=Sony IMX662"' in text and "platesolve 11.25,41.4" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/stages/test_preprocess.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_preprocess_stages'`.

- [ ] **Step 3: Write minimal implementation**

Append to `aporntool/stages/preprocess.py` (add imports at top of file):
```python
from pathlib import Path

from aporntool.stages.engine import Stage
from aporntool.tools.siril import (
    build_ssf, write_ssf, run_siril, gaia_catalog_cmds, platesolve_cmd, spcc_cmd,
)


def _nonzero(path) -> bool:
    # A stage counts as done only if its output file exists and isn't empty (FR-24b).
    p = Path(path)
    return p.exists() and p.stat().st_size > 0


def build_preprocess_stages(mode, ws, cfg, target, *, siril_exe, runner=None):
    # Build the ordered preprocess stages for this mode, each wired to a SIRIL script that is
    # written into logs/ then run. `runner` is injectable so tests never launch real SIRIL.
    import subprocess
    runner = runner or subprocess.run
    proc = ws.process
    anchor = ws.linear / f"{ws.target}_Linear.fit"

    def _run(stage_id, commands, cd=None):
        # Generate the .ssf, save it to logs/ (reproducibility), run it, log the console output.
        text = build_ssf(commands, cd=cd)
        script = write_ssf(text, ws.logs / f"{stage_id}.ssf")
        run_siril(script, workdir=ws.work, siril_exe=siril_exe, runner=runner,
                  log_path=ws.logs / f"{stage_id}.log")

    stages = []

    # convert: link the staged lights into a sequence (run from the lights dir).
    stages.append(Stage(
        "convert",
        lambda: _run("convert", convert_cmds(), cd=str(ws.lights)),
        lambda: (proc / "light_.seq").exists()))

    # calibrate: debayer (run from the process dir where the sequence now lives).
    stages.append(Stage(
        "calibrate",
        lambda: _run("calibrate", calibrate_cmds(), cd=str(proc)),
        lambda: (proc / "pp_light_.seq").exists()))

    # register: WCS (mosaic) or 2-pass (single-panel), then apply registration.
    stages.append(Stage(
        "register",
        lambda: _run("register", register_cmds(mode), cd=str(proc)),
        lambda: (proc / "r_pp_light_.seq").exists()))

    anchor_noext = anchor.with_suffix("").as_posix()   # SIRIL `save` appends .fit itself

    # stack: sigma-clip the registered sequence → result.fit (linear). No mirror/anchor here.
    stages.append(Stage(
        "stack",
        lambda: _run("stack", stack_cmds(mode), cd=str(proc)),
        lambda: (proc / "result.fit").exists()))

    if is_single_panel(mode):
        # mirrorx: undo the Seestar vertical flip. For emission/star-cluster (no SPCC in
        # preprocess) mirrorx is the LAST preprocess stage, so it also SAVES the golden anchor;
        # for reflection it just mirrors result in place (SPCC saves the anchor next).
        def _mirrorx_run():
            if spcc_in_preprocess(mode):
                _run("mirrorx", ["mirrorx_single result"], cd=str(proc))
            else:
                _run("mirrorx",
                     ["mirrorx_single result", "load result", f"save {anchor_noext}", "close"],
                     cd=str(proc))
        stages.append(Stage(
            "mirrorx", _mirrorx_run,
            (lambda: _nonzero(anchor)) if not spcc_in_preprocess(mode)
            else (lambda: (proc / "result.fit").exists())))

    if spcc_in_preprocess(mode):
        # spcc: platesolve + SPCC on result (already mirrored for reflection), then SAVE the anchor.
        def _spcc_run():
            cmds = []
            if cfg.catalog_astro and cfg.catalog_photo:
                cmds += gaia_catalog_cmds(cfg.catalog_astro, cfg.catalog_photo)
            cmds += [
                "load result",
                platesolve_cmd(coords=f"{target.ra},{target.dec}",
                               focal=cfg.seestar_focal_mm, pixel=cfg.seestar_pixel_um),
                spcc_cmd(),
                f"save {anchor_noext}",
                "close",
            ]
            _run("spcc", cmds, cd=str(proc))
        stages.append(Stage("spcc", _spcc_run, lambda: _nonzero(anchor)))

    return stages
```

> Note for implementer: SIRIL's `save <name>` appends `.fit`, so we pass the anchor path **without** the `.fit` suffix (`anchor_noext`); the `produces` verifiers look for the full `.fit`. The golden anchor is saved by each mode's **last** preprocess stage: `mirrorx` for emission/star-cluster, `spcc` for mosaic/reflection.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/stages/test_preprocess.py -v`
Expected: PASS (12 passed in this file).

- [ ] **Step 5: Commit**

```bash
git add aporntool/stages/preprocess.py tests/stages/test_preprocess.py
git commit -m "feat: assemble per-mode preprocess Stage list → golden anchor (SIRIL mocked)"
```

---

### Task 6: Wire preprocess into `cmd_mode` + `--from`/`--redo`/`--force` (FR-24a)

**Files:**
- Modify: `aporntool/cli.py`
- Create: `tests/test_cli_preprocess.py`

**Interfaces:**
- Consumes: everything above + Plan-1 `cmd_mode` (which currently stops after preflight/manifest).
- Produces: `cmd_mode` now, after preflight + staging + manifest, resolves `siril-cli` via config/discovery and runs `run_pipeline(manifest, build_preprocess_stages(...), ...)` to the golden anchor; new flags `--from`, `--redo`, `--force` are parsed and threaded through. Exit `0` when the anchor is produced, `2` when preflight fails, `1` on a stage failure.

- [ ] **Step 1: Write the failing test**

`tests/test_cli_preprocess.py`:
```python
from pathlib import Path
from aporntool.cli import main


def _install_fake_siril(monkeypatch, tmp_home):
    # Pretend all tools are found, and make run_siril a no-op that fabricates each stage's output
    # so the pipeline advances to the golden anchor without real SIRIL.
    monkeypatch.setattr("aporntool.cli.discover_tool", lambda name, **kw: "/usr/bin/" + name)

    import aporntool.stages.preprocess as pp

    def fake_run_siril(script_path, *, workdir, siril_exe, runner=None, log_path=None):
        # Read which stage this is from the script filename and touch its expected output.
        proc = Path(workdir) / "01_process"
        proc.mkdir(parents=True, exist_ok=True)
        name = Path(script_path).stem
        {
            "convert": proc / "light_.seq",
            "calibrate": proc / "pp_light_.seq",
            "register": proc / "r_pp_light_.seq",
        }.get(name, proc / "result.fit").write_text("x", encoding="utf-8")
        (proc / "result.fit").write_text("x", encoding="utf-8")
        # Emulate the anchor save that the last preprocess stage performs.
        linear = Path(workdir) / "02_linear"
        linear.mkdir(parents=True, exist_ok=True)
        target = Path(workdir).name           # workdir == _work/<target>
        (linear / f"{target}_Linear.fit").write_text("x", encoding="utf-8")
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()

    monkeypatch.setattr(pp, "run_siril", fake_run_siril)


def test_emission_run_reaches_golden_anchor(capsys, tmp_path, monkeypatch):
    _install_fake_siril(monkeypatch, tmp_path)
    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    out = tmp_path / "out"
    code = main(["dso-emission-nebula", "--in", str(subs), "--out", str(out), "--target", "M8"])
    assert code == 0
    assert (out / "_work" / "M8" / "02_linear" / "M8_Linear.fit").exists()
    assert "anchor" in capsys.readouterr().out.lower()


def test_rerun_is_idempotent_and_resumes(capsys, tmp_path, monkeypatch):
    _install_fake_siril(monkeypatch, tmp_path)
    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    out = tmp_path / "out"
    args = ["dso-emission-nebula", "--in", str(subs), "--out", str(out), "--target", "M8"]
    assert main(args) == 0
    # Second run: all stages already done → still exits 0 (resume, nothing to redo).
    assert main(args) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli_preprocess.py -v`
Expected: FAIL — `cmd_mode` still prints the "Plan 2" stub and never creates the anchor.

- [ ] **Step 3: Write minimal implementation**

In `aporntool/cli.py`: add imports near the top —
```python
from aporntool.stages.preprocess import build_preprocess_stages
from aporntool.stages.engine import run_pipeline
```
> Note: `build_preprocess_stages` internally calls `run_siril` (imported into `preprocess`'s namespace in Task 5), so the Task-6 test monkeypatches `aporntool.stages.preprocess.run_siril` — `cli` only needs `build_preprocess_stages`, not `run_siril`.

Add the three flags in `build_parser`'s per-mode loop (alongside `--preflight-only`):
```python
        pm.add_argument("--from", dest="from_stage", default=None, help="restart at this stage id")
        pm.add_argument("--redo", default=None, help="re-run this stage id and everything downstream")
        pm.add_argument("--force", action="store_true", help="re-run all stages, ignore checkpoints")
```

Replace the OLD tail of `cmd_mode` — from the existing `m = Manifest(...)` creation through the
`"Preflight OK. (Pipeline stages land in Plan 2.)"` print and its `return 0` — with:
```python
    # Build this mode's preprocess stages, record their ids as the manifest order, and run the
    # pipeline to the golden anchor. Each stage checkpoints so a failure can be fixed + resumed.
    siril = _resolve_tool(cfg, "siril")
    stages = build_preprocess_stages(mode, ws, cfg, target, siril_exe=siril)
    m = Manifest(mode=mode, target=ws.target, order=[s.id for s in stages],
                 input_fingerprint=input_fingerprint(iter_fits(ws.lights)))
    save_manifest(m, ws.manifest_path)
    ok = run_pipeline(m, stages, save=lambda mm: save_manifest(mm, ws.manifest_path),
                      from_stage=args.from_stage, redo=args.redo, force=args.force)
    if not ok:
        return 1
    anchor = ws.linear / f"{ws.target}_Linear.fit"
    print(f"Preprocess complete. Golden anchor: {anchor}")
    print("(Finishing stages land in Plan 4.)")
    return 0
```
Keep the existing preflight / `--preflight-only` / input-validation / staging logic above this
unchanged. **Also delete the now-unused `MODE_ORDER` dict** from `cli.py` — the manifest order now
comes from the stage list; `cmd_status` reads `order` from the saved manifest, so it is unaffected.

- [ ] **Step 4: Run the full suite to verify everything passes**

Run: `python -m pytest -v`
Expected: PASS — the Plan-1 suite (now 46) plus the new Plan-2 tests, all green.

- [ ] **Step 5: Commit**

```bash
git add aporntool/cli.py tests/test_cli_preprocess.py
git commit -m "feat: run preprocess core to golden anchor from cmd_mode (+ --from/--redo/--force)"
```

---

## Self-Review

**1. Spec coverage:** §4.4b stage vocabulary + I/O (Tasks 4/5), FR-12d per-mode sequences (Task 4/5), FR-12c golden anchor filename+state (Task 5), FR-13 abs-path/`-d` (Task 1), FR-16 + gotchas #2/#3 SPCC quoting/local-Gaia (Task 2), gotcha #1 feather (Task 4), #8 mirrorx single-panel (Task 4/5), #12/FR-26 seqplatesolve false-negative → **partially: Task 5 verifies `register` by the `.seq` file existing, which is the count-not-exit-code spirit; a stricter solved-frame count is a follow-up** (see gaps), FR-12 scripts saved to `logs/` (Task 5), FR-24/24a/24b resume/from/redo/force/verify (Task 3 + Task 6). Preflight already gates SIRIL presence (Plan 1).

**2. Placeholder scan:** none — every step has complete code + exact commands. The one prose note (SIRIL `save` suffix behavior) is guidance, not a placeholder.

**3. Type consistency:** `Stage(id, run, produces)`, `run_pipeline(manifest, stages, *, save, from_stage, redo, force)`, `build_preprocess_stages(mode, ws, cfg, target, *, siril_exe, runner)`, `spcc_cmd()`/`platesolve_cmd()`/`gaia_catalog_cmds()` are used identically between defining and consuming tasks.

**Known gaps (intentional, for a follow-up or Plan 3):**
- **FR-26 strict solved-frame count:** Task 5 verifies `register` via the `r_pp_light_.seq` file; a dedicated "count solved `pp_light_*.fit` frames and warn if many failed" check (the M31-script behavior) is a small hardening follow-up.
- **Real-SIRIL integration test** is manual (SIRIL absent on the dev box) — the user runs one real M31/M8 pass and confirms `<TARGET>_Linear.fit` looks right.
- Deferred Plan-1 minors (config value validation, mtime fingerprint) still open.

---

## After Plan 2 — next plans

- **Plan 3 — GraXpert + StarNet2 wrappers:** `bge`/`denoise` stages (GraXpert CLI, `.fits.fits` rename, size-stable poll) and StarNet2 (grid fix). Reflection's effective anchor advances to `_clean`.
- **Plan 4 — the four finishers + `--profile` + previews + deliverables (FR-25/27/29):** crop stage (auto + `--pause-crop`), mosaic/emission/reflection finishes ported from the `/dso-*` skills, star-cluster finish per §4.8. Reconcile the deferred foundation minors here.
- **Phase 2 — planetary.**
