"""Data-driven auto-crop: trim ragged registration/mosaic borders (no WCS needed)."""
import numpy as np
from astropy.io import fits


def auto_crop_box(fits_path, *, cov_thresh=0.5, margin_frac=0.02):
    # Rows/cols where fewer than `cov_thresh` of pixels carry real signal are empty/low-coverage
    # edges (SIRIL fills uncovered mosaic/registration area with ~0). Return the well-covered
    # rectangle, shrunk inward by margin_frac, as a SIRIL "x y w h" string. None if (nearly) the
    # whole frame is covered (nothing to trim).
    #
    # COORDINATE CONVENTION: the returned box is in SIRIL's `crop` convention — x from the left,
    # y from the TOP. astropy reads FITS bottom-up (data row 0 = bottom of the image), but SIRIL's
    # crop measures y downward from the top (empirically verified: `crop 0 0 50 50` keeps the
    # top-left quadrant). We therefore flip the vertical axis below, or an asymmetric top/bottom
    # border would be trimmed on the wrong side. x needs no flip (SIRIL x0 == astropy column 0).
    d = fits.getdata(str(fits_path)).astype(np.float64)
    lum = np.moveaxis(d, 0, -1).mean(2) if d.ndim == 3 else d
    peak = float(lum.max()) or 1.0
    covered = lum > peak * 1e-4
    rows = np.where(covered.mean(axis=1) >= cov_thresh)[0]
    cols = np.where(covered.mean(axis=0) >= cov_thresh)[0]
    if rows.size == 0 or cols.size == 0:
        return None
    y0, y1, x0, x1 = int(rows.min()), int(rows.max()), int(cols.min()), int(cols.max())
    H, W = lum.shape
    cov_w, cov_h = x1 - x0 + 1, y1 - y0 + 1          # covered extent, BEFORE any margin
    # If the covered region already spans (nearly) the whole frame, there is no ragged border to
    # trim — return None. This check must use the pre-margin covered extent: checking the
    # post-margin box against 98% never fires at real resolutions (the margin alone shaves >2%
    # off each axis), so a pristine full frame would get cosmetically cropped by ~2% per side.
    if cov_w >= W * 0.98 and cov_h >= H * 0.98:
        return None
    mh, mw = int((y1 - y0) * margin_frac), int((x1 - x0) * margin_frac)
    x, y = x0 + mw, y0 + mh          # x, y in astropy (bottom-up) coordinates for now
    w, h = cov_w - 2 * mw, cov_h - 2 * mh
    if w <= 0 or h <= 0:
        return None
    # Flip the box's top edge into SIRIL's top-down y (see COORDINATE CONVENTION above).
    y_siril = H - y - h
    return f"{x} {y_siril} {w} {h}"


def resolve_crop(crop, fits_path):
    # crop is "auto" (compute from the image), an explicit "x y w h" string, or None (skip).
    if crop == "auto":
        return auto_crop_box(fits_path)
    return crop or None
