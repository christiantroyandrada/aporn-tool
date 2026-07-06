"""Auto-detect the target (name + coordinates) from a sub's FITS header, so --target/--coords are
optional. Seestar and most smart scopes stamp OBJECT + RA/DEC into every light frame, which is all
the pipeline needs to name the run and seed the plate solve."""
from astropy.io import fits

from aporntool.catalog import resolve_target
from aporntool.workspace import iter_fits


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

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    obj = header.get("OBJECT")
    return (str(obj).strip() if obj else None, _num(header.get("RA")), _num(header.get("DEC")))


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
