"""Data-driven auto-crop: trim ragged/low-signal registration & mosaic borders (no WCS needed)."""
from pathlib import Path

import numpy as np
from astropy.io import fits

_TARGET_BLOCKS = 700   # downsample large frames to ~this many cells/axis so the search stays fast


def _largest_true_rectangle(mask):
    # Largest axis-aligned all-True rectangle in a 2-D boolean mask, via the classic "largest
    # rectangle in a histogram" scan applied row by row. Returns (x0, y0, x1, y1) inclusive, or
    # None if the mask has no True cell. O(rows * cols).
    H, W = mask.shape
    heights = np.zeros(W, dtype=np.int64)
    best_area = 0
    best = None
    for y in range(H):
        # heights[x] = length of the run of covered cells ending at row y in column x.
        heights = np.where(mask[y], heights + 1, 0)
        hh = heights.tolist()
        stack = []                      # (start_col, height), heights strictly increasing
        for x in range(W + 1):
            cur = hh[x] if x < W else 0
            start = x
            while stack and stack[-1][1] > cur:
                s_col, s_h = stack.pop()
                area = s_h * (x - s_col)
                if area > best_area:
                    best_area = area
                    best = (s_col, y - s_h + 1, x - 1, y)   # x0, y0(top), x1, y1(bottom = y)
                start = s_col
            stack.append((start, cur))
    return best


def auto_crop_box(fits_path, *, bg_frac=0.25, margin_frac=0.02):
    # Find the largest rectangle that holds ONLY real signal and return it as a SIRIL "x y w h"
    # crop string, or None if the frame is already full (nothing worth trimming).
    #
    # WHY a rectangle search, not a row/col bounding box: a mosaic assembled with framing=max has an
    # irregular (staircase) coverage region, so black CORNERS survive a bounding box. The largest
    # all-covered rectangle removes them without cutting into the data.
    #
    # WHAT counts as border: SIRIL leaves uncovered mosaic/registration area either at ~0
    # (registration shifts) or, after -norm=addscale, as a low-signal plateau well below the sky
    # background; non-finite (NaN/inf) pixels can also appear at mosaic edges or from tool output.
    # A pixel is "real signal" if it is finite AND exceeds max(peak*1e-4, bg_frac*median): the peak
    # term catches zero-filled borders, the median term catches the low-signal plateau, and
    # non-finite pixels are treated as border. Peak/median are computed over finite pixels only, so
    # a single NaN/inf can't poison the threshold. Real targets sit at or above the sky median, so
    # this does not eat into them.
    #
    # COORDINATE CONVENTION: the box is in SIRIL's `crop` convention -- x from the left, y from the
    # TOP. astropy reads FITS bottom-up (data row 0 = bottom), but SIRIL's crop measures y from the
    # top (verified: `crop 0 0 50 50` keeps the top-left quadrant), so we flip y below. x needs no
    # flip (SIRIL x0 == astropy column 0).
    d = fits.getdata(str(fits_path)).astype(np.float64)
    lum = np.moveaxis(d, 0, -1).mean(2) if d.ndim == 3 else d
    H, W = lum.shape
    finite = np.isfinite(lum)
    vals = lum[finite]
    if vals.size == 0:
        return None
    peak = float(vals.max()) or 1.0
    med = float(np.median(vals))
    thr = max(peak * 1e-4, bg_frac * med)
    signal = finite & (lum > thr)        # non-finite pixels are treated as border

    # Downsample big frames so the rectangle search is fast. A coarse cell counts as covered only
    # if EVERY full-resolution pixel in its block is signal (block-all), so the box scaled back up
    # can never contain a border/black pixel. Pad with False to a whole number of blocks so no edge
    # rows/cols go unscanned (a partial edge block holds padding -> not all-True -> excluded, which
    # is the safe direction: it may leave a few signal px near the edge, never includes black).
    block = max(1, max(H, W) // _TARGET_BLOCKS)
    if block > 1:
        hb, wb = -(-H // block), -(-W // block)      # ceil division
        padded = np.zeros((hb * block, wb * block), dtype=bool)
        padded[:H, :W] = signal
        coarse = padded.reshape(hb, block, wb, block).all(axis=(1, 3))
    else:
        coarse = signal

    rect = _largest_true_rectangle(coarse)
    if rect is None:
        return None
    # Scale the coarse-grid rectangle back to full-resolution pixel coords (inclusive box); clamp
    # into the real frame in case the last block edge lands in the padding.
    cx0, cy0, cx1, cy1 = rect
    x0, y0 = cx0 * block, cy0 * block
    x1 = min((cx1 + 1) * block - 1, W - 1)
    y1 = min((cy1 + 1) * block - 1, H - 1)

    cov_w, cov_h = x1 - x0 + 1, y1 - y0 + 1
    # Already (nearly) the whole frame -> nothing ragged to trim.
    if cov_w >= W * 0.98 and cov_h >= H * 0.98:
        return None
    mh, mw = int(cov_h * margin_frac), int(cov_w * margin_frac)
    x, y = x0 + mw, y0 + mh          # astropy (bottom-up) coords for now
    w, h = cov_w - 2 * mw, cov_h - 2 * mh
    if w <= 0 or h <= 0:
        return None
    y_siril = H - y - h              # flip the top edge into SIRIL's top-down y
    return f"{x} {y_siril} {w} {h}"


def resolve_crop(crop, fits_path):
    # crop is "auto" (compute from the image), an explicit "x y w h" string, or None (skip).
    if crop == "auto":
        # Auto-crop reads the golden anchor at stage run time. If it's absent (e.g. resuming a
        # finish/bge stage with --from/--redo before preprocess has produced it), fail with an
        # actionable message instead of a bare astropy FileNotFoundError. An explicit --crop box
        # skips this read entirely.
        if not Path(fits_path).exists():
            raise FileNotFoundError(
                f"golden anchor not found: {fits_path}. Auto-crop needs it. Run the full pipeline "
                f"first (drop --from/--redo so preprocess produces the anchor), then resume; or "
                f"pass an explicit --crop \"X Y W H\" box.")
        return auto_crop_box(fits_path)
    return crop or None
