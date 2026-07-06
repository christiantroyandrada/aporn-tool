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
