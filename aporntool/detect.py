"""Auto-detect the target (name + coordinates) from a sub's FITS header, so --target/--coords are
optional. Seestar and most smart scopes stamp OBJECT + RA/DEC into every light frame, which is all
the pipeline needs to name the run and seed the plate solve.

Also auto-detects whether a capture is a multi-panel MOSAIC (see `detect_mosaic`): a mosaic is a
capture technique (many panels tiled across the sky), orthogonal to the target *type*. We tell the
two apart from how far the per-sub pointing spreads."""
import math
from dataclasses import dataclass

from astropy.io import fits

from aporntool.catalog import Target, resolve_target
from aporntool.workspace import iter_fits


def resolve_target_wide(name_arg):
    # Wide-field (dso-milky-way) stills carry no FITS OBJECT/RA/DEC, and the mode never plate-solves,
    # so there is nothing to look up: just name the run. --target overrides the default "MilkyWay".
    # ra/dec are unused (no platesolve/SPCC in wide-field) but Target requires them.
    return Target((name_arg or "MilkyWay").strip(), 0.0, 0.0, "milky-way", "wide-field")

# Seestar S30 field of view (degrees): 150 mm focal, IMX662 sensor → ~1.29° x 0.73°.
SEESTAR_FOV_DEG = (1.29, 0.73)


def _num(v):
    # Parse a FITS header value as a float, or None if it's absent/non-numeric (never raises).
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read_header_target(in_dir):
    # Read OBJECT + RA/DEC from the FIRST sub in the folder. Returns (name, ra, dec) with any field
    # None when it is absent. Never raises -- a missing folder or a garbled header just yields Nones
    # so the caller can fall back to an explicit --target.
    files = iter_fits(in_dir)
    if not files:
        return (None, None, None)
    try:
        header = fits.getheader(str(files[0]))
    except Exception:
        return (None, None, None)

    obj = header.get("OBJECT")
    return (str(obj).strip() if obj else None, _num(header.get("RA")), _num(header.get("DEC")))


@dataclass(frozen=True)
class MosaicDetection:
    """Result of sniffing a folder of subs for multi-panel capture.

    Attributes:
        is_mosaic: True if the pointing spreads across more than one FOV (tile the sky).
        ra_spread_deg: max−min of the true-angle RA pointing (cos(dec)-corrected), degrees.
        dec_spread_deg: max−min of the DEC pointing, degrees.
        n_sampled: how many subs actually contributed a pointing.
        reason: one-line human explanation, printed for the user to confirm/override.
    """
    is_mosaic: bool
    ra_spread_deg: float
    dec_spread_deg: float
    n_sampled: int
    reason: str


def detect_mosaic(in_dir, *, fov_deg=SEESTAR_FOV_DEG, overlap_frac=0.5, max_sample=80) -> MosaicDetection:
    # Decide single-panel vs multi-panel from the per-sub pointing spread. A single panel's subs sit
    # on top of each other (only dither jitter, arcminutes); a mosaic tiles panels across degrees.
    # We call it a mosaic when the spread in either axis exceeds half a FOV — i.e. the frames can't
    # all be one panel. Coordinates come from each sub's RA/DEC (fall back to OBJCTRA/OBJCTDEC).
    # A missing/uniform pointing can't prove a mosaic, so we default to single (the safe assembly)
    # and say why — the caller always prints this and honours an explicit --mosaic/--single override.
    files = iter_fits(in_dir)
    ras, decs = [], []
    step = max(1, len(files) // max_sample)          # sample evenly; 922 headers is slow to read all
    for path in files[::step]:
        try:
            h = fits.getheader(str(path))
        except Exception:
            continue
        ra = _num(h.get("RA", h.get("OBJCTRA")))
        dec = _num(h.get("DEC", h.get("OBJCTDEC")))
        if ra is not None and dec is not None:
            ras.append(ra); decs.append(dec)

    if len(ras) < 2:
        return MosaicDetection(False, 0.0, 0.0, len(ras),
                               "no per-sub RA/DEC in headers -> assuming single panel")

    mean_dec = sum(decs) / len(decs)
    # RA degrees shrink toward the pole, so scale by cos(dec) to get a true on-sky angle.
    ra_spread = (max(ras) - min(ras)) * math.cos(math.radians(mean_dec))
    dec_spread = max(decs) - min(decs)
    ra_thresh, dec_thresh = fov_deg[0] * overlap_frac, fov_deg[1] * overlap_frac
    is_mosaic = ra_spread > ra_thresh or dec_spread > dec_thresh
    reason = (f"pointing spread {ra_spread:.2f}deg x {dec_spread:.2f}deg across {len(ras)} subs "
              f"{'exceeds' if is_mosaic else 'fits within'} ~half a FOV "
              f"({ra_thresh:.2f} x {dec_thresh:.2f}) -> {'mosaic' if is_mosaic else 'single panel'}")
    return MosaicDetection(is_mosaic, ra_spread, dec_spread, len(ras), reason)


def resolve_target_auto(name_arg, in_dir):
    # Resolve the Target for a run. An explicit --target wins for the NAME; otherwise the header's
    # OBJECT names it. Coordinates come from the built-in catalog for known targets, else straight
    # from the header's RA/DEC -- so the everyday command needs neither --target nor --coords.
    obj, ra, dec = read_header_target(in_dir)
    name = name_arg or obj
    if not name:
        raise ValueError(
            "Could not determine the target: no --target given and the first sub's FITS header has "
            "no OBJECT keyword. Pass --target NAME.")
    coords = f"{ra},{dec}" if (ra is not None and dec is not None) else None
    return resolve_target(name, coords)
