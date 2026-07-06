"""Reflection-nebula dual-layer finish (pure numpy), ported from the /dso-reflection-nebula skill."""
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter, median_filter


def mtf(m, v):
    # Midtones transfer function (SIRIL/PixInsight-style) — the stretch primitive.
    v = np.asarray(v, dtype=np.float64)
    return np.where(v <= 0, 0.0, np.where(v >= 1, 1.0,
                    ((m - 1) * v) / ((2 * m - 1) * v - m)))


def find_m(xmed, target):
    # Bisect for the m that maps median xmed → target brightness.
    lo, hi = 1e-7, 1 - 1e-7
    for _ in range(64):
        mid = (lo + hi) / 2
        if mtf(mid, np.array([xmed]))[0] < target:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def autostretch(rgb, target_bg=0.25, shadows_clip=-2.8):
    # Luminance-linked autostretch: clip shadows, then MTF each channel so the bg sits at target_bg.
    x = np.clip(np.asarray(rgb, np.float64), 0, 1)
    lum = x.mean(2)
    med = np.median(lum)
    madN = 1.4826 * np.median(np.abs(lum - med)) or 1e-6
    c = np.clip(med + shadows_clip * madN, 0, 1)
    medp = (med - c) / (1 - c) if c < 1 else 0.0
    m = find_m(medp, target_bg)
    normed = np.clip((x - c) / (1 - c if c < 1 else 1), 0, 1)
    return np.clip(np.stack([mtf(m, normed[..., i]) for i in range(3)], -1), 0, 1)


def fix_starnet_grid(starless_rgb):
    # StarNet2 leaves a checkerboard; kill it at the source (median5 + gaussian1.5) — gotcha #9.
    out = np.asarray(starless_rgb, np.float64).copy()
    for ch in range(3):
        out[..., ch] = median_filter(out[..., ch], size=5)
    return gaussian_filter(out, sigma=(1.5, 1.5, 0))


def screen_blend(a, b):
    # Composite stars over starless without blowing highlights: 1-(1-a)(1-b).
    return np.clip(1 - (1 - np.asarray(a, np.float64)) * (1 - np.asarray(b, np.float64)), 0, 1)


def save_deliverables(rgb01, out_stem) -> None:
    # Write the finished composite as a PNG preview (8-bit, for quick viewing) and a
    # 16-bit TIFF (the actual deliverable — the user does final curves/crop in Canva/Photoshop
    # from this file, per the /dso-reflection-nebula skill's "16-bit TIFF is the deliverable" rule).
    from PIL import Image
    import tifffile

    stem = Path(out_stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    arr = np.clip(np.asarray(rgb01, np.float64), 0, 1)

    a8 = (arr * 255 + 0.5).astype(np.uint8)
    Image.fromarray(a8).save(str(stem.with_suffix(".png")))

    a16 = (arr * 65535 + 0.5).astype(np.uint16)
    tifffile.imwrite(str(stem.with_suffix(".tif")), a16, photometric="rgb")
