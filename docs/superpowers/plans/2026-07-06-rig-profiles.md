# aPornTool Rig Profiles + Calibration Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development. Steps use `- [ ]`.
> **Isolation note:** built on branch `feat/rig-profiles` (worktree), based on `main` (shipped MVP). The
> mainline is being actively edited in another session (`cli.py`/`preprocess.py`/`finish_cmds.py` dirty),
> so **Task 1 is a new, additive module with ZERO conflict**; Tasks 2–4 (wiring) are STAGED to apply
> after those in-flight edits land, to avoid clobbering live test-fixes.

**Goal:** Generalize aPornTool beyond the Seestar S30 to any smart scope (and, via calibration frames, DSLRs / custom OSC rigs) through a **rig profile** that parameterizes focal length, pixel size, SPCC sensor, orientation flip, and calibration — reusing the existing pipeline unchanged.

**Architecture:** A new `aporntool/rigs.py` holds `RigProfile` + a `PROFILES` table + `resolve_profile()` + `detect_profile(header)`. The pipeline reads focal/pixel/sensor/`mirrorx`/calibration from the active profile instead of hardcoded Seestar constants. Smart scopes calibrate internally (no master frames); DSLR/custom OSC profiles carry master dark/flat/bias support.

## Key insight
**Every smart scope the user listed calibrates internally and outputs OSC FITS — exactly like the Seestar.** So they differ from the current path only in: **focal length, pixel size, SPCC sensor, and orientation flip.** No new pipeline is needed for them — just a profile lookup. Calibration-frame support is the *separate* piece that unlocks DSLRs / uncalibrated custom rigs.

## Global Constraints
- Cross-platform `pathlib`; teaching comments (NFR-9); stdlib for `rigs.py`.
- **Bayer pattern is read from the FITS header** (SIRIL `calibrate -debayer` honors `BAYERPAT`) — do NOT hardcode per scope.
- Profile values are **authored from published specs (July 2026) — flagged for per-unit validation**; `mirrorx` and the exact SPCC sensor name especially need a real-run check per scope.

---

## Rig profile table (researched specs)

| profile key | model | focal mm | pixel µm | sensor | f/ | mirrorx | internal calib | SPCC sensor (SIRIL) |
|---|---|---|---|---|---|---|---|---|
| `seestar-s30` | ZWO Seestar S30 | 150 | 2.9 | IMX662 | 5 | **yes** | yes | `ZWO Seestar S30` |
| `seestar-s30pro` | ZWO Seestar S30 Pro | 160 | 2.9 | IMX585 | 5.3 | yes† | yes | *(IMX585 / generic OSC)* |
| `seestar-s50` | ZWO Seestar S50 | 250 | 2.9 | IMX462 | 5 | yes | yes | `ZWO Seestar S50` |
| `dwarf3` | DwarfLab Dwarf 3 | 150 | 2.0 | IMX678 | 4.3 | no† | yes | *(IMX678 / generic)* |
| `dwarf-mini` | DwarfLab Dwarf Mini | 150 | 2.9 | IMX662 | 5 | no† | yes | *(IMX662 / generic)* |
| `vespera-ii` | Vaonis Vespera II | 250 | 2.9 | IMX585 | 5 | no† | yes | *(generic OSC)* |
| `vespera-pro` | Vaonis Vespera Pro | 250 | 2.0 | IMX676 | 5 | no† | yes | *(generic OSC)* |
| `stellina` | Vaonis Stellina | 400 | 2.4 | IMX178 | 5 | no† | yes | *(generic OSC)* |
| `evscope2` | Unistellar eVscope 2 | 450 | 2.9 | IMX347 | 4 | no† | yes | *(generic OSC)* |
| `odyssey` | Unistellar Odyssey | 320 | 1.45 | IMX415 | 3.9 | no† | yes | *(generic OSC)* |
| `dslr` | Generic DSLR (OSC) | *user* | *user* | *user* | — | no | **no → needs masters** | *(user / generic)* |
| `custom-osc` | Generic cooled OSC | *user* | *user* | *user* | — | no | **no → needs masters** | *(user / generic)* |

† `mirrorx` and SPCC-sensor for non-Seestar scopes are **best-guess defaults to validate on a real run** (orientation flip is empirical; SPCC sensor depends on what SIRIL's `spcc_list` recognizes — fall back to a bare `spcc` / default OSC if the exact model isn't in the DB).

Sources: Seestar S50 250mm/IMX462; S30 Pro 160mm/IMX585; Dwarf 3 150mm/IMX678/2µm; Dwarf Mini 150mm/IMX662; Vespera II 250mm/IMX585, Vespera Pro 250mm/IMX676/2µm; Stellina 400mm/IMX178; eVscope 2 450mm/IMX347; Odyssey 320mm/IMX415/1.45µm.

---

### Task 1 (BUILD NOW — additive, zero conflict): `rigs.py` profile module

**Files:** Create `aporntool/rigs.py`, `tests/test_rigs.py`.

**Interfaces:**
- `@dataclass(frozen=True) RigProfile`: `key, model, focal_mm, pixel_um, sensor, osc_filter="UV/IR Block", mirrorx=False, internal_calibration=True, spcc_sensor=None` (spcc_sensor None → bare/default SPCC).
- `PROFILES: dict[str, RigProfile]` — all rows above (dslr/custom-osc have `focal_mm=None`/`pixel_um=None`, `internal_calibration=False`).
- `resolve_profile(key: str) -> RigProfile` — normalize (lowercase, strip), lookup; KeyError with the list of valid keys if unknown.
- `detect_profile(header: dict) -> RigProfile | None` — match `INSTRUME`/`TELESCOP` header value (case-insensitive substring) to a profile (e.g. "Seestar S30"→seestar-s30, "DWARF3"→dwarf3, "Vespera"→vespera-ii, "Stellina", "eVscope"→evscope2, "Odyssey"). None if no match.

- [ ] **Step 1: failing test** — `tests/test_rigs.py`:
```python
import pytest
from aporntool.rigs import RigProfile, PROFILES, resolve_profile, detect_profile


def test_seestar_s30_specs():
    p = resolve_profile("seestar-s30")
    assert (p.focal_mm, p.pixel_um, p.sensor) == (150.0, 2.9, "IMX662")
    assert p.mirrorx is True and p.internal_calibration is True


def test_case_insensitive_lookup():
    assert resolve_profile("Seestar-S50").focal_mm == 250.0


def test_all_smart_scopes_present():
    for k in ("seestar-s30", "seestar-s30pro", "seestar-s50", "dwarf3", "dwarf-mini",
              "vespera-ii", "vespera-pro", "stellina", "evscope2", "odyssey"):
        assert k in PROFILES and PROFILES[k].internal_calibration is True


def test_dslr_needs_calibration_and_has_no_fixed_optics():
    p = resolve_profile("dslr")
    assert p.internal_calibration is False and p.focal_mm is None


def test_unknown_profile_lists_valid_keys():
    with pytest.raises(KeyError) as e:
        resolve_profile("nikon-p1000")
    assert "seestar-s30" in str(e.value)


def test_detect_from_instrume_header():
    assert detect_profile({"INSTRUME": "Seestar S30"}).key == "seestar-s30"
    assert detect_profile({"TELESCOP": "DWARF3"}).key == "dwarf3"
    assert detect_profile({"INSTRUME": "Vaonis Vespera"}).key == "vespera-ii"
    assert detect_profile({"INSTRUME": "Canon EOS 6D"}) is None
```

- [ ] **Step 2: verify RED** — `python -m pytest tests/test_rigs.py -v` → ModuleNotFoundError.

- [ ] **Step 3: GREEN** — `aporntool/rigs.py`:
```python
"""Rig profiles: per-instrument optics/sensor/orientation so the pipeline isn't Seestar-hardwired."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RigProfile:
    key: str
    model: str
    focal_mm: float | None
    pixel_um: float | None
    sensor: str | None            # sensor model (IMXxxx) — informational + SPCC hint
    osc_filter: str = "UV/IR Block"
    mirrorx: bool = False          # vertical flip needed? (Seestar yes; others validate per unit)
    internal_calibration: bool = True   # smart scopes self-calibrate; DSLR/custom need masters
    spcc_sensor: str | None = None      # exact SIRIL spcc_list name, else None → bare/default SPCC


def _p(key, model, focal, pixel, sensor, **kw):
    return (key, RigProfile(key, model, focal, pixel, sensor, **kw))


PROFILES = dict([
    _p("seestar-s30", "ZWO Seestar S30", 150.0, 2.9, "IMX662", mirrorx=True, spcc_sensor="ZWO Seestar S30"),
    _p("seestar-s30pro", "ZWO Seestar S30 Pro", 160.0, 2.9, "IMX585", mirrorx=True),
    _p("seestar-s50", "ZWO Seestar S50", 250.0, 2.9, "IMX462", mirrorx=True, spcc_sensor="ZWO Seestar S50"),
    _p("dwarf3", "DwarfLab Dwarf 3", 150.0, 2.0, "IMX678"),
    _p("dwarf-mini", "DwarfLab Dwarf Mini", 150.0, 2.9, "IMX662"),
    _p("vespera-ii", "Vaonis Vespera II", 250.0, 2.9, "IMX585"),
    _p("vespera-pro", "Vaonis Vespera Pro", 250.0, 2.0, "IMX676"),
    _p("stellina", "Vaonis Stellina", 400.0, 2.4, "IMX178"),
    _p("evscope2", "Unistellar eVscope 2", 450.0, 2.9, "IMX347"),
    _p("odyssey", "Unistellar Odyssey", 320.0, 1.45, "IMX415"),
    _p("dslr", "Generic DSLR (OSC)", None, None, None, internal_calibration=False),
    _p("custom-osc", "Generic cooled OSC", None, None, None, internal_calibration=False),
])

# Substrings matched (case-insensitive) against INSTRUME/TELESCOP → profile key.
_DETECT = [
    ("seestar s30 pro", "seestar-s30pro"), ("s30 pro", "seestar-s30pro"),
    ("seestar s50", "seestar-s50"), ("seestar s30", "seestar-s30"), ("seestar", "seestar-s30"),
    ("dwarf3", "dwarf3"), ("dwarf 3", "dwarf3"), ("dwarf mini", "dwarf-mini"),
    ("vespera pro", "vespera-pro"), ("vespera", "vespera-ii"),
    ("stellina", "stellina"), ("evscope", "evscope2"), ("odyssey", "odyssey"),
]


def resolve_profile(key: str) -> RigProfile:
    norm = key.strip().lower()
    if norm in PROFILES:
        return PROFILES[norm]
    raise KeyError(f"Unknown rig '{key}'. Valid: {', '.join(sorted(PROFILES))}")


def detect_profile(header):
    # Match the FITS INSTRUME/TELESCOP string to a known scope; most specific patterns first.
    text = " ".join(str(header.get(k, "")) for k in ("INSTRUME", "TELESCOP")).lower()
    for needle, key in _DETECT:
        if needle in text:
            return PROFILES[key]
    return None
```

- [ ] **Step 4: verify GREEN** — `python -m pytest tests/test_rigs.py -v` (6 passed); full suite.
- [ ] **Step 5: commit** — `feat: rig profiles module (10 smart scopes + DSLR/custom-osc) + detect-from-header`

---

### Task 2 (STAGED — apply after mainline test-edits land): wire profile into config + preprocess + SPCC + CLI

Replace the Seestar-hardcoded values with profile-driven ones. Touches files under active edit — apply after they're committed, then reconcile.
- `config.py`: add `rig: str = "seestar-s30"` (default keeps current behavior). Keep `seestar_focal_mm/pixel_um` as per-run overrides.
- `cli.py`: add `--rig <key>` (per-mode); resolve `RigProfile` (explicit `--rig` > `detect_profile(first sub header)` > config default). Pass focal/pixel from `profile` (overridable) into preprocess platesolve.
- `preprocess.py`: `mirrorx` stage runs only when `profile.mirrorx`; `platesolve` uses `profile.focal_mm/pixel_um`.
- `tools/siril.py` `spcc_cmd`: take `sensor`/`osc_filter` from the profile (fall back to bare `spcc` when `spcc_sensor is None`).
- `finish.py`: emission/cluster SPCC uses the profile's sensor.
- Detection ties into FR-10a (`auto` mode already reads headers — reuse for rig detection).

### Task 3 (STAGED): calibration frames for `internal_calibration=False` rigs (DSLR/custom OSC)
- `cli.py`: `--dark <master> --flat <master> --bias <master>`.
- `preprocess.calibrate_cmds`: emit `calibrate light -dark=… -flat=… -bias= … -debayer` when masters given; preflight requires them (or warns) when `profile.internal_calibration is False`.
- Keep the no-masters path for smart scopes unchanged.

### Task 4 (STAGED, smaller): DSLR raw ingest
- `workspace.iter_fits` → also accept `.cr2/.cr3/.nef/.arw` for DSLR profiles (SIRIL `convert` handles raw→FITS). Mono LRGB/narrowband is explicitly OUT of scope (needs a per-channel workflow — future).

---

## Self-Review / Notes
- Task 1 is fully self-contained (new module) — safe to build and merge independent of the mainline edits.
- Tasks 2–4 deliberately deferred because they edit files the test session is changing live; sequencing them after those edits land avoids destroying real test-fixes.
- Profile numbers are authored from published specs; `mirrorx`/SPCC-sensor for non-Seestar scopes are the two fields most likely to need a real-run tweak (surface them as easily-overridable).
