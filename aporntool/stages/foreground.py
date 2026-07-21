"""Handheld (--no-tripod) foreground de-ghost for the wide-field Milky Way mode.

Star-aligned stacking sharpens the sky but SMEARS the fixed foreground (house / trees / wires)
into a ghost, because a hand-held camera drifts between frames. This module recovers a sharp
foreground WITHOUT touching the deep stacked sky:

  1. The per-pixel variance ACROSS the registered frames is the ghost signal — the sky is aligned
     frame-to-frame (low variance) while the foreground moves (high variance). No horizon or
     brightness assumption is made.
  2. High-variance ridges (rooflines, wires, lights) are a BARRIER; the sky is the connected
     low-variance region flood-filled from the image centre (the Milky Way target is always roughly
     centred). Building interiors are flat (low variance) but are walled off by their own roofline
     ridge, so they fall OUTSIDE the sky region — correctly classified as foreground.
  3. Composite: the deep stacked sky where the sky-mask ~ 1, a single sharp frame where ~ 0,
     feathered across the transition.

Pure numpy + scipy, mirroring reflection_finish / composite_finish (both already do raster work in
the finish phase). `sky_mask` is deliberately I/O-free so it can be unit-tested on synthetic frames.
"""
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter, binary_dilation, label

from aporntool.stages.reflection_finish import autostretch, save_deliverables


def _load_fits_rgb_topdown(path):
    # Registered frames are FITS (astropy reads them bottom-up); the finished sky deliverable is a
    # SIRIL-saved TIF (top-down). Flip the FITS to top-down so mask/foreground line up with the sky.
    from astropy.io import fits
    d = fits.getdata(str(path)).astype(np.float64)
    img = np.moveaxis(d, 0, -1) if d.ndim == 3 else np.stack([d] * 3, -1)
    return np.flipud(np.clip(img, 0, None))


def _crop_slices(crop_box, h, w):
    # SIRIL "x y w h" crop string (x from left, y from TOP) -> row/col slices on a top-down array.
    # None / "" -> the whole frame (no crop applied).
    if not crop_box:
        return slice(0, h), slice(0, w)
    x, y, cw, ch = (int(round(float(v))) for v in str(crop_box).split())
    return slice(y, y + ch), slice(x, x + cw)


def sky_mask(lumas, *, barrier_pct=88.0, barrier_dilate=8, feather=35.0, min_island_frac=0.002):
    # lumas: array-like [N, H, W] of per-frame normalised luminance. Returns a feathered sky mask
    # [H, W] in 0..1 (1 = deep sky to keep from the stack, 0 = foreground to take from one frame).
    std = gaussian_filter(np.asarray(lumas, np.float64).std(0), sigma=6)
    h, w = std.shape
    barrier = std > np.percentile(std, barrier_pct)
    if barrier_dilate:
        barrier = binary_dilation(barrier, iterations=int(barrier_dilate))

    # Sky = the connected low-variance component containing the image centre.
    lbl, n = label(~barrier)
    sky_lbl = int(lbl[h // 2, w // 2])
    if sky_lbl == 0:
        # Centre landed on a barrier pixel (rare) -> fall back to the largest low-variance component.
        sizes = np.bincount(lbl.ravel())
        sizes[0] = 0
        sky_lbl = int(sizes.argmax()) if sizes.size > 1 else 0
    sky = lbl == sky_lbl if sky_lbl else np.ones_like(std, dtype=bool)

    # Clean up the foreground: a component is REAL foreground only if it is both large enough AND
    # touches the frame border. Two false positives get folded back into sky:
    #   * tiny islands  -> registration-jittered stars, not foreground (min_island_frac);
    #   * interior blobs that don't reach any edge -> a sky patch walled off from the centre seed by a
    #     spurious variance ridge (a cloud band, or an over-tight crop clipping the ragged registration
    #     border). Real foreground (ground / buildings) always sits against a frame edge, so an
    #     interior "island" is sky, not foreground. Without this, such a patch renders as a black blob.
    fg_lbl, fn = label(~sky)
    if fn:
        min_area = max(1, int(min_island_frac * h * w))
        sizes = np.bincount(fg_lbl.ravel())
        on_border = np.zeros(sizes.size, dtype=bool)
        for edge in (fg_lbl[0, :], fg_lbl[-1, :], fg_lbl[:, 0], fg_lbl[:, -1]):
            on_border[np.unique(edge)] = True
        fold = np.array([(s < min_area) or (not on_border[i]) for i, s in enumerate(sizes)])
        fold[0] = False                          # label 0 is the sky itself, never fold it in as fg
        if fold.any():
            sky |= np.isin(fg_lbl, np.flatnonzero(fold))

    return np.clip(gaussian_filter(sky.astype(np.float64), sigma=feather), 0, 1)


def run_foreground_deghost(sky_deliverable, registered_paths, reference_path, *, crop_box,
                           out_stem, params=None, jpeg_quality=95):
    # Overwrite the four MW deliverables with a foreground-de-ghosted composite: the finished stacked
    # sky where the sky-mask ~ 1, a single sharp frame where ~ 0. Returns the foreground coverage
    # fraction (for logging / tests). Everything is aligned in the finished sky's cropped, top-down
    # coordinate system (registered FITS flipped + cropped with the same box the crop stage used).
    import tifffile
    p = dict(params or {})

    sky01 = np.clip(tifffile.imread(str(sky_deliverable)).astype(np.float64) / 65535.0, 0, 1)
    sky01 = sky01[..., :3] if sky01.ndim == 3 else np.stack([sky01] * 3, -1)
    H, W = sky01.shape[:2]

    ys = xs = None
    lumas = []
    for rp in registered_paths:
        img = _load_fits_rgb_topdown(rp)
        if ys is None:
            ys, xs = _crop_slices(crop_box, *img.shape[:2])
        c = img[ys, xs]
        lumas.append((c / (np.percentile(c, 99.5) or 1.0)).mean(2))

    mask = sky_mask(np.stack(lumas, 0),
                    barrier_pct=p.get("barrier_pct", 88.0),
                    barrier_dilate=p.get("barrier_dilate", 8),
                    feather=p.get("feather", 35.0),
                    min_island_frac=p.get("min_island_frac", 0.002))
    if mask.shape != (H, W):
        # The mask is built from the registered frames cropped with the SAME box the crop stage used,
        # so a shape mismatch means the box and the finished sky disagree — surface it, don't guess.
        raise ValueError(f"de-ghost mask {mask.shape} != finished sky {(H, W)}; crop box mismatch")

    fg = _load_fits_rgb_topdown(reference_path)[ys, xs]
    fg01 = autostretch(np.clip(fg / (np.percentile(fg, 99.7) or 1.0), 0, 1),
                       target_bg=p.get("fg_target_bg", 0.10),
                       shadows_clip=p.get("fg_shadows_clip", -1.8))
    fg01 = np.clip(fg01 * p.get("fg_gain", 1.0), 0, 1)

    m3 = mask[:, :, None]
    comp = np.clip(sky01 * m3 + fg01 * (1 - m3), 0, 1)
    Path(out_stem).parent.mkdir(parents=True, exist_ok=True)
    save_deliverables(comp, out_stem, jpeg_quality)
    return float(1.0 - mask.mean())
