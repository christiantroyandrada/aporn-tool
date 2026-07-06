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
        # User supplied RA,DEC for a target we don't know — parse defensively for a clean error.
        parts = coords.split(",")
        if len(parts) != 2:
            raise ValueError(f"--coords must be 'RA,DEC' in decimal degrees, got '{coords}'")
        try:
            ra, dec = float(parts[0]), float(parts[1])
        except ValueError:
            raise ValueError(f"--coords must be numeric 'RA,DEC' decimal degrees, got '{coords}'")
        return Target(name.strip(), ra, dec, "unknown", "user coords")
    raise KeyError(f"Unknown target '{name}'. Pass --coords RA,DEC (decimal degrees).")
