# aPornTool Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pure-Python, cross-platform foundation of aPornTool — CLI dispatch, tool discovery, drag-and-drop input handling, the `_work/` I/O contract, the manifest/resume state machine, and the preflight validator — so `aporntool config --check`, `aporntool status`, and per-mode preflight all run end-to-end with no external astro tools installed.

**Architecture:** A single Python package `aporntool/`. Small, single-responsibility modules (paths, locations, discovery, config, catalog, workspace, manifest, preflight) glued by `cli.py`. Every module is stdlib-only and unit-tested with external tools *mocked/injected* — the heavy tools (SIRIL/GraXpert/StarNet2) are only *discovered and preflighted* here, not run (that's Plan 2+). All logic uses `pathlib`; nothing assumes Windows.

**Tech Stack:** Python 3.10+, stdlib only (argparse, pathlib, dataclasses, json, hashlib, shutil, platform, re, urllib), pytest for tests. Scientific deps (numpy/astropy/scipy/Pillow/tifffile) are declared later, in the plan that first runs a finisher.

## Global Constraints

Copied verbatim from `REQUIREMENTS.md` — every task implicitly includes these:

- **Cross-platform (NFR-10):** Windows / macOS (incl. Apple Silicon) / Debian-Linux. Use `pathlib`/`os.path` only — never hard-coded separators or drive letters. Per-OS location resolution (§6a).
- **Config over code (NFR-7):** tool paths, Seestar defaults, catalog paths live in one `aporntool.config.json`.
- **Path portability (NFR-1):** resolve tools PATH → known locations → config → clear error. No hard-coded absolute paths in logic.
- **Fail loud, fail early (NFR-3):** every precondition checked; partial failure never masquerades as success.
- **Non-destructive (NFR-4):** never delete/overwrite the user's raw subs or the golden anchor.
- **Teaching codebase (NFR-9):** every function + non-obvious block carries a brief, plain-language comment (*what & why*, not restating syntax). Small named functions over clever one-liners. Each module opens with a one-line purpose header.
- **Seestar defaults (FR-11):** focal 150 mm, pixel 2.9 µm — overridable.
- **`_work/` namespacing (O2, FR-4):** intermediates live under `<OUT>/_work/<target>/`; deliverables sit at `<OUT>/` root.
- **Canonical stage IDs (FR-24d):** `stage → register → stack → [spcc] → crop → [bge] → [denoise] → [starnet] → finish`; presence + order per-mode; manifest is source of truth.

---

## File Structure

```
pyproject.toml                 # package metadata + console entry point + pytest config
aporntool/
  __init__.py                  # __version__
  __main__.py                  # `python -m aporntool` → cli.main()
  paths.py                     # sanitize dropped paths (drag-and-drop) → Path
  locations.py                 # per-OS app-data dirs (GraXpert models, SIRIL config)
  discovery.py                 # discover_tool(): PATH → known locations → config
  config.py                    # Config dataclass + load/save
  catalog.py                   # Target dataclass + TARGETS table + resolve_target()
  workspace.py                 # Workspace layout, .fit-only staging, sub counting
  manifest.py                  # StageStatus/StageRecord/Manifest + fingerprint + resume
  preflight.py                 # CheckResult + per-mode precondition checks
  cli.py                       # argparse dispatch: config / status / <mode>
tests/
  test_paths.py  test_locations.py  test_discovery.py  test_config.py
  test_catalog.py  test_workspace.py  test_manifest.py  test_preflight.py  test_cli.py
```

Each `aporntool/*.py` has one responsibility. `cli.py` is the only module that imports many others.

---

### Task 1: Project scaffold + package + CLI entry

**Files:**
- Create: `pyproject.toml`
- Create: `aporntool/__init__.py`
- Create: `aporntool/__main__.py`
- Create: `aporntool/cli.py` (minimal, grows in Task 10)
- Create: `tests/test_cli.py`
- Create: `.gitignore`

**Interfaces:**
- Produces: `aporntool.__version__: str`; `aporntool.cli.main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
import aporntool
from aporntool.cli import main


def test_version_string_exists():
    # The package must expose a version we can show with --version.
    assert isinstance(aporntool.__version__, str) and aporntool.__version__


def test_main_version_flag_returns_zero(capsys):
    # `aporntool --version` prints the version and exits cleanly.
    code = main(["--version"])
    assert code == 0
    assert aporntool.__version__ in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aporntool'`.

- [ ] **Step 3: Write minimal implementation**

`pyproject.toml`:
```toml
[project]
name = "aporntool"
version = "0.1.0"
description = "Astropornography tool — one command from raw subs to a finished astrophoto"
requires-python = ">=3.10"
dependencies = []                      # stdlib-only for the foundation; finishers add numpy/astropy later

[project.scripts]
aporntool = "aporntool.cli:main"       # installs an `aporntool` command

[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`aporntool/__init__.py`:
```python
"""aPornTool — turn raw astro subs into a finished image, one command per mode."""
__version__ = "0.1.0"
```

`aporntool/__main__.py`:
```python
"""Lets `python -m aporntool ...` work the same as the installed `aporntool` command."""
import sys
from aporntool.cli import main

if __name__ == "__main__":
    sys.exit(main())
```

`aporntool/cli.py`:
```python
"""Command-line entry point. Parses args and dispatches to a subcommand."""
import argparse
import aporntool


def build_parser() -> argparse.ArgumentParser:
    # Top-level parser; subcommands (config/status/<mode>) are added in later tasks.
    parser = argparse.ArgumentParser(prog="aporntool", description="Astropornography tool")
    parser.add_argument("--version", action="version",
                        version=f"aporntool {aporntool.__version__}")
    return parser


def main(argv=None) -> int:
    # Returns a process exit code (0 = success) so tests can assert on it.
    parser = build_parser()
    parser.parse_args(argv)
    return 0
```

`.gitignore`:
```gitignore
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
.venv/
.superpowers/
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS (2 passed). `argparse` `--version` calls `SystemExit(0)`; if the test needs it, wrap in `pytest.raises` — but `action="version"` exits, so adjust: see note.

> Note for implementer: `action="version"` raises `SystemExit`. Update `test_main_version_flag_returns_zero` to:
> ```python
> import pytest
> def test_main_version_flag_returns_zero(capsys):
>     with pytest.raises(SystemExit) as exc:
>         main(["--version"])
>     assert exc.value.code == 0
>     assert aporntool.__version__ in capsys.readouterr().out
> ```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml aporntool/__init__.py aporntool/__main__.py aporntool/cli.py tests/test_cli.py .gitignore
git commit -m "feat: project scaffold + CLI entry point with --version"
```

---

### Task 2: Drag-and-drop path sanitization (FR-2a)

**Files:**
- Create: `aporntool/paths.py`
- Create: `tests/test_paths.py`

**Interfaces:**
- Produces: `sanitize_dropped_path(raw: str) -> pathlib.Path` (pure string cleaning, no existence check); `to_input_dir(path: pathlib.Path) -> pathlib.Path` (a dropped file → its parent folder).

- [ ] **Step 1: Write the failing test**

`tests/test_paths.py`:
```python
from pathlib import Path
from aporntool.paths import sanitize_dropped_path, to_input_dir


def test_strips_double_quotes_and_trailing_space():
    # Windows wraps spaced paths in quotes; a drop often leaves a trailing space.
    assert sanitize_dropped_path('"C:\\Astro\\M 31 subs" ') == Path("C:\\Astro\\M 31 subs")


def test_strips_single_quotes():
    assert sanitize_dropped_path("'/home/me/subs'") == Path("/home/me/subs")


def test_strips_trailing_separator():
    assert sanitize_dropped_path("/home/me/subs/") == Path("/home/me/subs")


def test_expands_env_var(monkeypatch):
    monkeypatch.setenv("MYDIR", "/data/lights")
    assert sanitize_dropped_path("$MYDIR") == Path("/data/lights")


def test_decodes_linux_file_uri():
    # GNOME/Konsole hand over percent-encoded file:// URIs on drop.
    assert sanitize_dropped_path("file:///home/me/M%2031") == Path("/home/me/M 31")


def test_decodes_windows_file_uri():
    assert sanitize_dropped_path("file:///C:/Astro/M%2031") == Path("C:/Astro/M 31")


def test_to_input_dir_maps_file_to_parent(tmp_path):
    # Dragging one .fit instead of the folder → use its parent.
    f = tmp_path / "Light_0001.fit"
    f.write_bytes(b"x")
    assert to_input_dir(f) == tmp_path


def test_to_input_dir_keeps_folder(tmp_path):
    assert to_input_dir(tmp_path) == tmp_path
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_paths.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aporntool.paths'`.

- [ ] **Step 3: Write minimal implementation**

`aporntool/paths.py`:
```python
"""Clean a path the way a drag-and-drop hands it over, across Windows/macOS/Linux."""
import os
import re
from pathlib import Path
from urllib.parse import urlparse, unquote


def _uri_to_path(uri: str) -> str:
    # Linux terminals drop a file:// URI, percent-encoded (e.g. spaces as %20).
    parsed = urlparse(uri)
    path = unquote(parsed.path)
    # Windows file URIs look like file:///C:/... — drop the slash before the drive letter.
    if re.match(r"/[A-Za-z]:", path):
        path = path[1:]
    return path


def sanitize_dropped_path(raw: str) -> Path:
    s = raw.strip()
    # Peel one layer of matching surrounding quotes (Windows adds them for spaced paths).
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1].strip()
    # Turn a file:// URI back into a normal filesystem path.
    if s.startswith("file://"):
        s = _uri_to_path(s)
    # Expand %VARS%/$VARS and a leading ~ so config-style paths resolve.
    s = os.path.expanduser(os.path.expandvars(s))
    # Drop a trailing separator, but never strip a bare root ("/" or "C:\\").
    stripped = s.rstrip("/\\")
    if stripped and not stripped.endswith(":"):
        s = stripped
    return Path(s)


def to_input_dir(path: Path) -> Path:
    # If the user dropped a single file, the folder they meant is its parent.
    return path.parent if path.is_file() else path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_paths.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add aporntool/paths.py tests/test_paths.py
git commit -m "feat: drag-and-drop path sanitization (quotes, file:// URIs, env vars)"
```

---

### Task 3: Per-OS location resolution (§6a, NFR-10)

**Files:**
- Create: `aporntool/locations.py`
- Create: `tests/test_locations.py`

**Interfaces:**
- Produces: `user_data_dir(app: str) -> Path`; `graxpert_model_root() -> Path`; `siril_config_dir() -> Path`.

- [ ] **Step 1: Write the failing test**

`tests/test_locations.py`:
```python
from pathlib import Path
import aporntool.locations as loc


def test_windows_data_dir(monkeypatch):
    monkeypatch.setattr(loc.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\me\\AppData\\Local")
    assert loc.user_data_dir("GraXpert") == Path("C:\\Users\\me\\AppData\\Local") / "GraXpert"


def test_macos_data_dir(monkeypatch):
    monkeypatch.setattr(loc.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(loc.Path, "home", classmethod(lambda cls: Path("/Users/me")))
    assert loc.user_data_dir("GraXpert") == Path("/Users/me/Library/Application Support/GraXpert")


def test_linux_data_dir_uses_xdg(monkeypatch):
    monkeypatch.setattr(loc.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_DATA_HOME", "/home/me/.local/share")
    assert loc.user_data_dir("GraXpert") == Path("/home/me/.local/share/GraXpert")


def test_graxpert_model_root_nests_graxpert(monkeypatch):
    monkeypatch.setattr(loc.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_DATA_HOME", "/x")
    # GraXpert nests models under <data>/GraXpert/GraXpert/.
    assert loc.graxpert_model_root() == Path("/x/GraXpert/GraXpert")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_locations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aporntool.locations'`.

- [ ] **Step 3: Write minimal implementation**

`aporntool/locations.py`:
```python
"""Resolve per-OS application-data directories (GraXpert models, SIRIL config)."""
import os
import platform
from pathlib import Path


def user_data_dir(app: str) -> Path:
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / app
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / app
    # Linux / other: follow the XDG base-directory spec.
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / app


def graxpert_model_root() -> Path:
    # GraXpert stores AI models under <data>/GraXpert/GraXpert/{bge,denoise}-ai-models/<ver>/.
    return user_data_dir("GraXpert") / "GraXpert"


def siril_config_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / "siril"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "siril"
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "siril"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_locations.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add aporntool/locations.py tests/test_locations.py
git commit -m "feat: per-OS app-data dir resolution for GraXpert/SIRIL"
```

---

### Task 4: Tool discovery (NFR-1, D6)

**Files:**
- Create: `aporntool/discovery.py`
- Create: `tests/test_discovery.py`

**Interfaces:**
- Produces: `discover_tool(name, *, config_path=None, candidates=(), which=shutil.which, exists=None) -> Path | None`.
- Consumes: nothing (injectable `which`/`exists` keep it testable without a real PATH).

- [ ] **Step 1: Write the failing test**

`tests/test_discovery.py`:
```python
from pathlib import Path
from aporntool.discovery import discover_tool


def test_config_path_wins_when_it_exists():
    got = discover_tool("siril", config_path="/opt/siril",
                        which=lambda n: "/usr/bin/siril", exists=lambda p: True)
    assert got == Path("/opt/siril")


def test_falls_back_to_path():
    got = discover_tool("siril", which=lambda n: "/usr/bin/siril", exists=lambda p: False)
    assert got == Path("/usr/bin/siril")


def test_falls_back_to_known_candidate():
    got = discover_tool("siril", candidates=["/A", "/B"],
                        which=lambda n: None, exists=lambda p: p == "/B")
    assert got == Path("/B")


def test_returns_none_when_nowhere():
    assert discover_tool("nope", which=lambda n: None, exists=lambda p: False) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_discovery.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aporntool.discovery'`.

- [ ] **Step 3: Write minimal implementation**

`aporntool/discovery.py`:
```python
"""Find an external tool: an explicit config path, then PATH, then known install spots."""
import shutil
from pathlib import Path


def discover_tool(name, *, config_path=None, candidates=(), which=shutil.which, exists=None):
    # `exists` is injectable so tests don't depend on the real filesystem.
    exists = exists or (lambda p: Path(p).exists())
    # 1) An explicit path from the user's config wins — but only if it's really there.
    if config_path and exists(config_path):
        return Path(config_path)
    # 2) Anything on PATH (the normal case once a tool is installed).
    found = which(name)
    if found:
        return Path(found)
    # 3) Known per-machine install locations (filled from config/registry by the caller).
    for candidate in candidates:
        if exists(candidate):
            return Path(candidate)
    # 4) Nowhere — caller turns this into an actionable preflight failure.
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_discovery.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add aporntool/discovery.py tests/test_discovery.py
git commit -m "feat: tool discovery (config -> PATH -> known locations)"
```

---

### Task 5: Config load/save (NFR-7, FR-11)

**Files:**
- Create: `aporntool/config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `Config` dataclass (`tool_paths: dict`, `seestar_focal_mm: float = 150.0`, `seestar_pixel_um: float = 2.9`, `catalog_astro: str | None`, `catalog_photo: str | None`); `load_config(path) -> Config`; `save_config(cfg: Config, path) -> None`.

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
from aporntool.config import Config, load_config, save_config


def test_defaults_are_seestar():
    c = Config.default()
    assert c.seestar_focal_mm == 150.0 and c.seestar_pixel_um == 2.9
    assert c.tool_paths == {}


def test_missing_file_returns_defaults(tmp_path):
    c = load_config(tmp_path / "nope.json")
    assert c.seestar_focal_mm == 150.0


def test_roundtrip_and_override(tmp_path):
    p = tmp_path / "aporntool.config.json"
    c = Config.default()
    c.tool_paths["siril"] = "/opt/siril"
    c.seestar_focal_mm = 250.0
    save_config(c, p)
    loaded = load_config(p)
    assert loaded.tool_paths["siril"] == "/opt/siril"
    assert loaded.seestar_focal_mm == 250.0
    # Unspecified fields keep their defaults.
    assert loaded.seestar_pixel_um == 2.9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aporntool.config'`.

- [ ] **Step 3: Write minimal implementation**

`aporntool/config.py`:
```python
"""Load/save the single aporntool.config.json (tool paths + Seestar defaults + catalogs)."""
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class Config:
    tool_paths: dict = field(default_factory=dict)   # e.g. {"siril": "/opt/siril"}
    seestar_focal_mm: float = 150.0                   # Seestar S30 default optics
    seestar_pixel_um: float = 2.9
    catalog_astro: str | None = None                  # local Gaia astrometry catalog (file)
    catalog_photo: str | None = None                  # local Gaia SPCC catalog (folder)

    @classmethod
    def default(cls) -> "Config":
        return cls()


def load_config(path) -> Config:
    cfg = Config.default()
    path = Path(path)
    if path.exists():
        # Overlay saved values onto defaults; unknown keys are ignored (forward-compatible).
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in data.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
    return cfg


def save_config(cfg: Config, path) -> None:
    Path(path).write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add aporntool/config.py tests/test_config.py
git commit -m "feat: config load/save with Seestar defaults"
```

---

### Task 6: Target catalog (FR-10, §9)

**Files:**
- Create: `aporntool/catalog.py`
- Create: `tests/test_catalog.py`

**Interfaces:**
- Produces: `Target` frozen dataclass (`name, ra, dec, mode, notes`); `TARGETS: dict[str, Target]`; `resolve_target(name: str, coords: str | None = None) -> Target`.

- [ ] **Step 1: Write the failing test**

`tests/test_catalog.py`:
```python
import pytest
from aporntool.catalog import resolve_target, TARGETS


def test_known_target_case_and_space_insensitive():
    t = resolve_target("m 31")
    assert t.ra == 11.25 and t.dec == 41.4 and t.mode == "mosaic"


def test_cluster_present():
    assert resolve_target("M13").mode == "star-cluster"


def test_unknown_without_coords_raises():
    with pytest.raises(KeyError):
        resolve_target("NGC9999")


def test_unknown_with_coords_builds_target():
    t = resolve_target("NGC9999", coords="12.5,-3.25")
    assert t.ra == 12.5 and t.dec == -3.25 and t.mode == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aporntool.catalog'`.

- [ ] **Step 3: Write minimal implementation**

`aporntool/catalog.py` (RA/DEC in decimal degrees; full table per REQUIREMENTS §9):
```python
"""Known targets → RA/DEC + which mode processes them. Data mirrors REQUIREMENTS §9."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    name: str
    ra: float
    dec: float
    mode: str
    notes: str = ""


def _t(name, ra, dec, mode, notes=""):
    return (name.upper().replace(" ", ""), Target(name, ra, dec, mode, notes))


TARGETS = dict([
    _t("M31", 11.25, 41.4, "mosaic", "M32,M110"),
    _t("M33", 23.46, 30.66, "mosaic", "boost Ha"),
    _t("M51", 202.47, 47.20, "mosaic", "NGC5195"),
    _t("M101", 210.80, 54.35, "mosaic", "low surface brightness"),
    _t("M81", 148.89, 69.07, "mosaic"),
    _t("NGC7000", 314.68, 44.53, "mosaic", "Pelican IC5070"),
    _t("M8", 271.43, -24.41, "emission", "hourglass core"),
    _t("M20", 270.6, -23.03, "emission", "Ha + reflection lobe"),
    _t("M42", 83.82, -5.39, "emission", "very bright core"),
    _t("M16", 274.7, -13.8, "emission"),
    _t("NGC6960", 311.6, 30.9, "emission", "Veil SNR"),
    _t("M13", 250.42, 36.46, "star-cluster", "globular; protect highlights"),
    _t("M22", 279.10, -23.90, "star-cluster", "globular; MW region"),
    _t("M4", 245.90, -26.53, "star-cluster", "globular"),
    _t("M5", 229.64, 2.08, "star-cluster", "globular; high latitude"),
    _t("M92", 259.28, 43.14, "star-cluster", "globular"),
    _t("M15", 322.49, 12.17, "star-cluster", "globular; compact core"),
    _t("M3", 205.55, 28.38, "star-cluster", "globular; high latitude"),
    _t("M45", 56.87, 24.12, "star-cluster", "open + reflection: use reflection finish"),
    _t("M44", 130.05, 19.98, "star-cluster", "open; sparse"),
    _t("NGC869", 34.74, 57.13, "star-cluster", "Double Cluster"),
    _t("M11", 282.77, -6.27, "star-cluster", "open; dense"),
    _t("M6", 265.08, -32.22, "star-cluster", "open; MW region"),
    _t("M7", 268.46, -34.79, "star-cluster", "open; MW region"),
])


def _norm(name: str) -> str:
    # Match "m 31", "M31", "m31" all to the same key.
    return name.strip().upper().replace(" ", "")


def resolve_target(name: str, coords: str | None = None) -> Target:
    key = _norm(name)
    if key in TARGETS:
        return TARGETS[key]
    if coords:
        # User supplied RA,DEC for a target we don't know — build one on the fly.
        ra_str, dec_str = coords.split(",")
        return Target(name.strip(), float(ra_str), float(dec_str), "unknown", "user coords")
    raise KeyError(f"Unknown target '{name}'. Pass --coords RA,DEC (decimal degrees).")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add aporntool/catalog.py tests/test_catalog.py
git commit -m "feat: target catalog + resolve_target with coords fallback"
```

---

### Task 7: Workspace layout + `.fit`-only staging (FR-4, FR-7, FR-8, O2)

**Files:**
- Create: `aporntool/workspace.py`
- Create: `tests/test_workspace.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Workspace(out_root: Path, target: str)` with properties `work, lights, process, linear, previews, logs, manifest_path` and methods `create()`, `deliverable(ext: str) -> Path`; module functions `iter_fits(folder) -> list[Path]`, `count_fits(folder) -> int`, `stage_fits(sources: list[Path], dest: Path) -> int`.

- [ ] **Step 1: Write the failing test**

`tests/test_workspace.py`:
```python
from pathlib import Path
from aporntool.workspace import Workspace, iter_fits, count_fits, stage_fits


def test_layout_is_namespaced_under_target(tmp_path):
    ws = Workspace(tmp_path, "M31")
    assert ws.work == tmp_path / "_work" / "M31"
    assert ws.lights == tmp_path / "_work" / "M31" / "00_lights"
    assert ws.deliverable("tif") == tmp_path / "M31_final.tif"


def test_create_makes_dirs(tmp_path):
    ws = Workspace(tmp_path, "M31")
    ws.create()
    assert ws.lights.is_dir() and ws.logs.is_dir()


def test_iter_fits_ignores_jpg_and_thumbnails(tmp_path):
    (tmp_path / "Light_0001.fit").write_bytes(b"x")
    (tmp_path / "Light_0002.fits").write_bytes(b"x")
    (tmp_path / "Light_0001.jpg").write_bytes(b"x")       # Seestar preview — must be ignored
    (tmp_path / "Light_0001_thn.jpg").write_bytes(b"x")   # thumbnail — must be ignored
    names = [f.name for f in iter_fits(tmp_path)]
    assert names == ["Light_0001.fit", "Light_0002.fits"]
    assert count_fits(tmp_path) == 2


def test_stage_fits_copies_only_fits(tmp_path):
    src = tmp_path / "night1"; src.mkdir()
    (src / "a.fit").write_bytes(b"x")
    (src / "a.jpg").write_bytes(b"x")
    dest = tmp_path / "_work" / "M31" / "00_lights"
    n = stage_fits([src], dest)
    assert n == 1
    assert (dest / "a.fit").exists() and not (dest / "a.jpg").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_workspace.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aporntool.workspace'`.

- [ ] **Step 3: Write minimal implementation**

`aporntool/workspace.py`:
```python
"""The <OUT>/_work/<target>/ layout, deliverable naming, and .fit-only sub staging."""
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

_FIT_SUFFIXES = (".fit", ".fits")


@dataclass
class Workspace:
    out_root: Path      # user-chosen; ONLY deliverables live at this level
    target: str

    @property
    def work(self) -> Path:        # everything scratch is namespaced per target (O2)
        return self.out_root / "_work" / self.target

    @property
    def lights(self) -> Path:      # hardlinked raw .fit subs
        return self.work / "00_lights"

    @property
    def process(self) -> Path:     # SIRIL sequences + calibrated/registered frames
        return self.work / "01_process"

    @property
    def linear(self) -> Path:      # the golden linear stack lives here
        return self.work / "02_linear"

    @property
    def previews(self) -> Path:
        return self.work / "previews"

    @property
    def logs(self) -> Path:        # generated .ssf/.py + per-stage stdout
        return self.work / "logs"

    @property
    def manifest_path(self) -> Path:
        return self.work / "aporntool.json"

    def create(self) -> None:
        for d in (self.lights, self.process, self.linear, self.previews, self.logs):
            d.mkdir(parents=True, exist_ok=True)

    def deliverable(self, ext: str) -> Path:
        # Final images sit at the OUT root, e.g. M31_final.tif.
        return self.out_root / f"{self.target}_final.{ext}"


def iter_fits(folder) -> list:
    # Only real FITS subs — Seestar folders also hold .jpg + _thn.jpg that SIRIL would wrongly ingest.
    out = []
    for f in sorted(Path(folder).iterdir()):
        if f.is_file() and f.suffix.lower() in _FIT_SUFFIXES:
            out.append(f)
    return out


def count_fits(folder) -> int:
    return len(iter_fits(folder))


def stage_fits(sources, dest) -> int:
    # Bring every .fit from each source into one clean lights dir. Hardlink (instant, no extra
    # disk); fall back to a copy across drives/filesystems that can't hardlink.
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    staged = 0
    for src in sources:
        for f in iter_fits(src):
            target = dest / f.name
            if target.exists():
                continue
            try:
                os.link(f, target)
            except OSError:
                shutil.copy2(f, target)
            staged += 1
    return staged
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_workspace.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add aporntool/workspace.py tests/test_workspace.py
git commit -m "feat: _work/<target> layout + .fit-only staging (hardlink w/ copy fallback)"
```

---

### Task 8: Manifest + resume state machine (FR-23, FR-24, FR-24d/e/f)

**Files:**
- Create: `aporntool/manifest.py`
- Create: `tests/test_manifest.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `StageStatus` (Enum: PENDING/RUNNING/DONE/FAILED with `.value` strings); `StageRecord(id, status, params_key, outputs, error)`; `Manifest(mode, target, input_fingerprint, order, stages)` with `stage(id)`, `mark(id, status, **kw)`, `next_pending() -> str | None`, `invalidate_from(id)`; module functions `input_fingerprint(files) -> str`, `load_manifest(path) -> Manifest`, `save_manifest(m, path) -> None`.

- [ ] **Step 1: Write the failing test**

`tests/test_manifest.py`:
```python
from aporntool.manifest import (
    Manifest, StageStatus, input_fingerprint, load_manifest, save_manifest,
)


def _demo():
    m = Manifest(mode="dso-mosaic", target="M31",
                 order=["stage", "register", "stack", "spcc", "crop", "finish"])
    return m


def test_next_pending_is_first_not_done():
    m = _demo()
    m.mark("stage", StageStatus.DONE)
    m.mark("register", StageStatus.DONE)
    assert m.next_pending() == "stack"


def test_failed_stage_is_next():
    m = _demo()
    m.mark("stage", StageStatus.DONE)
    m.mark("register", StageStatus.FAILED)
    assert m.next_pending() == "register"


def test_invalidate_from_resets_downstream_only():
    m = _demo()
    for s in ["stage", "register", "stack", "spcc"]:
        m.mark(s, StageStatus.DONE)
    m.invalidate_from("stack")               # e.g. feather changed
    assert m.stage("register").status == StageStatus.DONE.value   # upstream untouched
    assert m.stage("stack").status == StageStatus.PENDING.value   # this + downstream reset
    assert m.stage("spcc").status == StageStatus.PENDING.value


def test_fingerprint_changes_when_a_sub_is_added(tmp_path):
    a = tmp_path / "a.fit"; a.write_bytes(b"12345")
    fp1 = input_fingerprint([a])
    b = tmp_path / "b.fit"; b.write_bytes(b"67890")
    fp2 = input_fingerprint([a, b])
    assert fp1 != fp2


def test_manifest_roundtrip(tmp_path):
    m = _demo()
    m.input_fingerprint = "abc123"
    m.mark("stage", StageStatus.DONE, outputs=["x.fit"])
    p = tmp_path / "aporntool.json"
    save_manifest(m, p)
    loaded = load_manifest(p)
    assert loaded.mode == "dso-mosaic"
    assert loaded.input_fingerprint == "abc123"
    assert loaded.stage("stage").status == StageStatus.DONE.value
    assert loaded.stage("stage").outputs == ["x.fit"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aporntool.manifest'`.

- [ ] **Step 3: Write minimal implementation**

`aporntool/manifest.py`:
```python
"""Run manifest + resume logic: which stages are done, and what re-running should recompute."""
import hashlib
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class StageRecord:
    id: str
    status: str = StageStatus.PENDING.value
    params_key: str = ""          # hash of the params this stage depends on (FR-24e)
    outputs: list = field(default_factory=list)
    error: str = ""


@dataclass
class Manifest:
    mode: str
    target: str
    input_fingerprint: str = ""   # detects repointed/grown inputs (FR-24f)
    order: list = field(default_factory=list)   # active stage sequence for THIS run (FR-24d)
    stages: dict = field(default_factory=dict)

    def stage(self, sid: str) -> StageRecord:
        # Auto-create a pending record the first time we touch a stage.
        return self.stages.setdefault(sid, StageRecord(sid))

    def mark(self, sid: str, status, **kw) -> StageRecord:
        rec = self.stage(sid)
        rec.status = status.value if isinstance(status, StageStatus) else status
        for key, value in kw.items():
            setattr(rec, key, value)
        return rec

    def next_pending(self):
        # Resume point: the first stage in order that isn't DONE (failed/pending both qualify).
        for sid in self.order:
            if self.stage(sid).status != StageStatus.DONE.value:
                return sid
        return None

    def invalidate_from(self, sid: str) -> None:
        # A change at `sid` forces it + everything downstream to re-run; upstream stays DONE.
        start = self.order.index(sid)
        for s in self.order[start:]:
            self.stage(s).status = StageStatus.PENDING.value


def input_fingerprint(files) -> str:
    # A stable signature of the input set — name + size + mtime of each sub.
    digest = hashlib.sha256()
    for f in sorted(Path(x) for x in files):
        st = f.stat()
        digest.update(f"{f.name}|{st.st_size}|{int(st.st_mtime)}\n".encode())
    return digest.hexdigest()[:16]


def save_manifest(m: Manifest, path) -> None:
    data = {
        "mode": m.mode, "target": m.target,
        "input_fingerprint": m.input_fingerprint, "order": m.order,
        "stages": {sid: asdict(rec) for sid, rec in m.stages.items()},
    }
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_manifest(path) -> Manifest:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    m = Manifest(mode=data["mode"], target=data["target"],
                 input_fingerprint=data.get("input_fingerprint", ""),
                 order=data.get("order", []))
    for sid, rec in data.get("stages", {}).items():
        m.stages[sid] = StageRecord(**rec)
    return m
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_manifest.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add aporntool/manifest.py tests/test_manifest.py
git commit -m "feat: manifest + resume state machine (fingerprint, invalidate-downstream)"
```

---

### Task 9: Preflight validator (FR-PF1/2/3, gotcha #14)

**Files:**
- Create: `aporntool/preflight.py`
- Create: `tests/test_preflight.py`

**Interfaces:**
- Consumes: `Path`-like tool paths dict from config (Task 5), `graxpert_model_root()` (Task 3).
- Produces: `CheckResult(name, ok, detail, remediation)`; `check_binary(name, path) -> CheckResult`; `check_graxpert_models(model_root, need=("bge","denoise")) -> CheckResult`; `MODE_TOOLS: dict[str, list[str]]`; `MODE_NEEDS_GRAXPERT: set[str]`; `run_preflight(mode, *, tool_paths, graxpert_model_root=None) -> list[CheckResult]`.

- [ ] **Step 1: Write the failing test**

`tests/test_preflight.py`:
```python
from aporntool.preflight import (
    check_binary, check_graxpert_models, run_preflight, CheckResult,
)


def test_check_binary_ok_and_missing():
    assert check_binary("siril", "/usr/bin/siril").ok is True
    missing = check_binary("siril", None)
    assert missing.ok is False and missing.remediation   # has actionable text


def test_graxpert_models_missing(tmp_path):
    # Empty model root → both bge + denoise reported missing, with remediation.
    r = check_graxpert_models(tmp_path)
    assert r.ok is False
    assert "bge" in r.detail and "denoise" in r.detail
    assert "Model Manager" in r.remediation or "download" in r.remediation.lower()


def test_graxpert_models_present(tmp_path):
    for kind in ("bge", "denoise"):
        d = tmp_path / f"{kind}-ai-models" / "1.0.0"
        d.mkdir(parents=True)
        (d / "model.onnx").write_bytes(b"x")
    assert check_graxpert_models(tmp_path).ok is True


def test_run_preflight_emission_needs_only_siril(tmp_path):
    results = run_preflight("dso-emission-nebula",
                            tool_paths={"siril": "/usr/bin/siril"},
                            graxpert_model_root=tmp_path)
    names = {r.name for r in results}
    assert names == {"siril"}                # emission does NOT need GraXpert/StarNet


def test_run_preflight_mosaic_flags_missing_graxpert_model(tmp_path):
    results = run_preflight("dso-mosaic",
                            tool_paths={"siril": "/s", "graxpert": "/g", "starnet2": "/n"},
                            graxpert_model_root=tmp_path)   # empty → model check fails
    assert any(r.name == "graxpert-models" and not r.ok for r in results)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_preflight.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aporntool.preflight'`.

- [ ] **Step 3: Write minimal implementation**

`aporntool/preflight.py`:
```python
"""Validate ALL preconditions for a mode up front, so a stage-4 blocker fails at second zero."""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    remediation: str = ""     # what the user should do; empty when ok


# Which external binaries each mode needs (emission/cluster stay on SIRIL only).
MODE_TOOLS = {
    "dso-mosaic": ["siril", "graxpert", "starnet2"],
    "dso-emission-nebula": ["siril"],
    "dso-reflection-nebula": ["siril", "graxpert", "starnet2"],
    "dso-star-cluster": ["siril"],
}
# Only these modes run GraXpert, so only they need its AI models present.
MODE_NEEDS_GRAXPERT = {"dso-mosaic", "dso-reflection-nebula"}


def check_binary(name: str, path) -> CheckResult:
    if path:
        return CheckResult(name, True, f"found: {path}")
    return CheckResult(name, False, "not found on PATH or known locations",
                       f"Install {name}, or set its path in aporntool.config.json, then re-run.")


def check_graxpert_models(model_root, need=("bge", "denoise")) -> CheckResult:
    # GraXpert's CLI won't download models on a fresh machine — verify they already exist.
    missing = []
    for kind in need:
        d = Path(model_root) / f"{kind}-ai-models"
        if not (d.exists() and any(d.rglob("*.onnx"))):
            missing.append(kind)
    if not missing:
        return CheckResult("graxpert-models", True, "bge + denoise models present")
    return CheckResult(
        "graxpert-models", False,
        f"missing model(s): {', '.join(missing)}",
        "Open GraXpert once and run Background Extraction + Denoise on any image (or use its "
        "Model Manager) to download the AI models, then re-run the same command to continue.")


def run_preflight(mode, *, tool_paths, graxpert_model_root=None) -> list:
    # Build the full check list for the mode; the caller prints failures + remediations.
    results = [check_binary(t, tool_paths.get(t)) for t in MODE_TOOLS.get(mode, [])]
    if mode in MODE_NEEDS_GRAXPERT and graxpert_model_root is not None:
        results.append(check_graxpert_models(graxpert_model_root))
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_preflight.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add aporntool/preflight.py tests/test_preflight.py
git commit -m "feat: mode-aware preflight (binaries + GraXpert model cache)"
```

---

### Task 10: CLI wiring — `config --check`, `status`, mode preflight (FR-1, FR-24c)

**Files:**
- Modify: `aporntool/cli.py` (grow from Task 1)
- Modify: `tests/test_cli.py` (add dispatch tests)

**Interfaces:**
- Consumes: everything above — `discover_tool` (T4), `Config/load_config/save_config` (T5), `resolve_target` (T6), `Workspace/stage_fits/count_fits` (T7), `Manifest/input_fingerprint/save_manifest/load_manifest` (T8), `run_preflight` (T9), `sanitize_dropped_path/to_input_dir` (T2), `graxpert_model_root` (T3).
- Produces: full `build_parser()` with subcommands; `main(argv) -> int` returning `0` ok / `2` preflight-failed / `1` usage error.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:
```python
import json
from aporntool.cli import main


def test_config_check_reports_missing_tools(capsys, tmp_path, monkeypatch):
    # No tools discoverable → config --check lists them and exits non-zero.
    monkeypatch.setattr("aporntool.cli.discover_tool", lambda name, **kw: None)
    cfg = tmp_path / "aporntool.config.json"
    code = main(["config", "--check", "--config", str(cfg)])
    out = capsys.readouterr().out
    assert code == 2
    assert "siril" in out and "graxpert" in out and "starnet2" in out
    assert cfg.exists()                     # a starter config is written


def test_mode_preflight_only_passes_when_tools_found(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr("aporntool.cli.discover_tool", lambda name, **kw: "/usr/bin/" + name)
    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    code = main(["dso-emission-nebula", "--in", str(subs),
                 "--out", str(tmp_path / "out"), "--target", "M8", "--preflight-only"])
    assert code == 0
    assert "preflight" in capsys.readouterr().out.lower()


def test_status_reads_manifest(capsys, tmp_path):
    from aporntool.workspace import Workspace
    from aporntool.manifest import Manifest, StageStatus, save_manifest
    ws = Workspace(tmp_path / "out", "M8"); ws.create()
    m = Manifest(mode="dso-emission-nebula", target="M8",
                 order=["stage", "stack", "finish"])
    m.mark("stage", StageStatus.DONE)
    save_manifest(m, ws.manifest_path)
    code = main(["status", "--out", str(tmp_path / "out"), "--target", "M8"])
    out = capsys.readouterr().out
    assert code == 0 and "stage" in out and "done" in out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — new tests error (`discover_tool` not importable from `aporntool.cli`, subcommands missing).

- [ ] **Step 3: Write minimal implementation**

Replace `aporntool/cli.py` with:
```python
"""Command-line entry point: parse args and dispatch to config / status / a processing mode."""
import argparse
from pathlib import Path

import aporntool
from aporntool.discovery import discover_tool
from aporntool.config import Config, load_config, save_config
from aporntool.catalog import resolve_target
from aporntool.workspace import Workspace, stage_fits, count_fits, iter_fits
from aporntool.manifest import Manifest, input_fingerprint, load_manifest, save_manifest
from aporntool.preflight import run_preflight, MODE_TOOLS
from aporntool.paths import sanitize_dropped_path, to_input_dir
from aporntool.locations import graxpert_model_root

DSO_MODES = ["dso-mosaic", "dso-emission-nebula", "dso-reflection-nebula", "dso-star-cluster"]
# The stage order the manifest tracks per mode (finish/details land in Plan 2).
MODE_ORDER = {
    "dso-mosaic": ["stage", "register", "stack", "spcc", "crop", "bge", "denoise", "starnet", "finish"],
    "dso-emission-nebula": ["stage", "register", "stack", "crop", "spcc", "denoise", "finish"],
    "dso-reflection-nebula": ["stage", "register", "stack", "spcc", "crop", "bge", "denoise", "finish"],
    "dso-star-cluster": ["stage", "register", "stack", "crop", "spcc", "denoise", "finish"],
}
ALL_TOOLS = ["siril", "graxpert", "starnet2", "ffmpeg"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aporntool", description="Astropornography tool")
    parser.add_argument("--version", action="version",
                        version=f"aporntool {aporntool.__version__}")
    sub = parser.add_subparsers(dest="command")

    p_cfg = sub.add_parser("config", help="inspect/verify tool configuration")
    p_cfg.add_argument("--check", action="store_true", help="verify all tools are discoverable")
    p_cfg.add_argument("--config", default="aporntool.config.json")

    p_status = sub.add_parser("status", help="show the resume ledger for a target")
    p_status.add_argument("--out", required=True)
    p_status.add_argument("--target", required=True)

    for mode in DSO_MODES:
        pm = sub.add_parser(mode, help=f"process a {mode} target")
        pm.add_argument("--in", dest="inputs", action="append", required=True,
                        help="subs folder (repeatable for multi-night)")
        pm.add_argument("--out", required=True)
        pm.add_argument("--target", required=True)
        pm.add_argument("--coords", default=None, help="RA,DEC if target is unknown")
        pm.add_argument("--config", default="aporntool.config.json")
        pm.add_argument("--preflight-only", action="store_true")
    return parser


def _resolve_tool(cfg: Config, tool: str):
    # Discover one tool as a plain str path (or None) — used by config-check and preflight.
    found = discover_tool(tool, config_path=cfg.tool_paths.get(tool))
    return str(found) if found else None


def cmd_config(args) -> int:
    cfg = load_config(args.config)
    print("Tool discovery:")
    ok = True
    for tool in ALL_TOOLS:
        path = _resolve_tool(cfg, tool)
        print(f"  [{'OK ' if path else 'MISSING'}] {tool}: {path or 'not found'}")
        if path:
            cfg.tool_paths.setdefault(tool, path)
        else:
            ok = False
    save_config(cfg, args.config)          # write a starter config the user can edit
    print(f"\nConfig written to {args.config}")
    return 0 if ok else 2


def cmd_status(args) -> int:
    ws = Workspace(Path(args.out), args.target)
    if not ws.manifest_path.exists():
        print(f"No run found for {args.target} under {args.out}.")
        return 1
    m = load_manifest(ws.manifest_path)
    print(f"{m.mode} / {m.target}  (fingerprint {m.input_fingerprint or '-'})")
    for sid in m.order:
        print(f"  {sid:<10} {m.stage(sid).status}")
    nxt = m.next_pending()
    print(f"\nResume at: {nxt or 'complete'}")
    return 0


def cmd_mode(args, mode: str) -> int:
    # Resolve inputs (drag-and-drop friendly), preflight the environment, then stage + checkpoint.
    # Pipeline stages themselves arrive in Plan 2 — this proves the skeleton + preflight gate.
    cfg = load_config(args.config)
    in_dirs = [to_input_dir(sanitize_dropped_path(p)) for p in args.inputs]
    for d in in_dirs:
        if not d.is_dir():
            print(f"ERROR: input folder does not exist: {d}")
            return 1
    target = resolve_target(args.target, args.coords)

    # Preflight is environment validation — run it before any staging/compute (FR-PF1).
    tool_paths = {t: _resolve_tool(cfg, t) for t in MODE_TOOLS.get(mode, [])}
    results = run_preflight(mode, tool_paths=tool_paths,
                            graxpert_model_root=graxpert_model_root())
    failed = [r for r in results if not r.ok]
    print("Preflight:")
    for r in results:
        print(f"  [{'OK ' if r.ok else 'FAIL'}] {r.name}: {r.detail}")
        if not r.ok:
            print(f"       -> {r.remediation}")
    if failed:
        print("\nPreflight failed - fix the above, then re-run the same command to continue.")
        return 2
    if args.preflight_only:                       # FR-PF3: validate only, no processing
        print("\nPreflight OK (--preflight-only).")
        return 0

    ws = Workspace(Path(args.out), target.name.upper().replace(" ", ""))
    ws.create()
    staged = stage_fits(in_dirs, ws.lights)
    print(f"Staged {staged} subs into {ws.lights}")
    if count_fits(ws.lights) < 1:
        print("ERROR: no .fit subs found in the given folder(s).")
        return 1

    m = Manifest(mode=mode, target=ws.target, order=MODE_ORDER[mode],
                 input_fingerprint=input_fingerprint(iter_fits(ws.lights)))
    save_manifest(m, ws.manifest_path)
    print("Preflight OK. (Pipeline stages land in Plan 2.)")
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "config":
        return cmd_config(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command in DSO_MODES:
        return cmd_mode(args, args.command)
    parser.print_help()
    return 1
```

- [ ] **Step 4: Run the full suite to verify everything passes**

Run: `python -m pytest -v`
Expected: PASS (all tasks' tests green).

- [ ] **Step 5: Smoke-test the real command, then commit**

```bash
pip install -e .
aporntool --version
aporntool config --check          # lists your SIRIL/GraXpert/StarNet2/ffmpeg discovery
git add aporntool/cli.py tests/test_cli.py
git commit -m "feat: CLI dispatch — config --check, status, per-mode preflight gate"
```

---

## Self-Review

**1. Spec coverage (Plan 1 scope):** FR-1 (subcommands ✓ T10), FR-2/2a (drag-drop ✓ T2+T10), FR-4/O2 (`_work/<target>` ✓ T7), FR-5 (fail-fast ✓ T10), FR-7/8 (`.fit`-staging + count ✓ T7), FR-9a (repeatable `--in` ✓ T10), FR-10/11 (catalog + Seestar defaults ✓ T5/T6), FR-23/24c/24d/24e/24f (manifest/resume/fingerprint/invalidate ✓ T8), FR-PF1/2/3 (preflight ✓ T9/T10), NFR-1/7/9/10 (discovery/config/comments/cross-platform ✓ throughout). **Deferred to Plan 2+ (correctly out of scope here):** FR-12–22 (SIRIL/GraXpert/StarNet execution, crop, finishers), FR-25/26 (previews + seqplatesolve false-neg), FR-27/28/29 (deliverable production + profiles). `--from`/`--redo`/`--continue` flags (FR-24/24a) are wired in Plan 2 when stages actually run.

**2. Placeholder scan:** none — every step has complete code and exact commands. The only forward reference ("Pipeline stages land in Plan 2") is an intentional skeleton message, not a code placeholder.

**3. Type consistency:** `Workspace(out_root, target)`, `run_preflight(mode, *, tool_paths, graxpert_model_root=)`, `Manifest(mode, target, input_fingerprint, order, stages)`, `discover_tool(name, *, config_path, ...)`, `resolve_target(name, coords)` — all used consistently between their defining task and `cli.py` (T10).

---

## After Plan 1 — next plans (not built here)

- **Plan 2 — SIRIL preprocess core (§4.4a):** the parameterized `preprocess` (link → calibrate → register → stack → [spcc] → golden anchor), `.ssf` generation into `logs/`, `seqplatesolve` false-negative handling (FR-26), stage execution wired into the manifest with `--from`/`--redo`/`--continue`.
  - **Finding #9 — RESOLVED (see spec FR-12b):** reflection performs star handling *inside* its Python dual-layer `finish` (calls StarNet2 CLI directly), so it correctly has no separate `starnet` stage while still requiring the binary in preflight. `MODE_ORDER` and `MODE_TOOLS` need not be 1:1. The current foundation code already matches this (reflection `MODE_ORDER` has no `starnet`); no code change needed — just build reflection's `finish` to invoke StarNet2. Also revisit the deferred foundation Minors: config value-type validation, `input_fingerprint` sub-second mtime, bare `list`/`dict` type hints, and `siril_config_dir`/env-fallback test coverage.
- **Plan 3 — GraXpert + StarNet2 wrappers:** BGE + linear denoise (`.fits.fits` rename, size-stable poll), StarNet2 two-pass + grid fix.
- **Plan 4 — the four DSO finishers:** mosaic, emission (Route A), reflection (Python dual-layer), star-cluster (§4.8) + `--profile` (FR-29) + previews (FR-25) + deliverables (FR-27/28).
- **Phase 2 — planetary:** ffmpeg → AutoStakkert hand-off → Python finish.
