"""Reflection-nebula dual-layer finish (pure numpy), ported from the /dso-reflection-nebula skill."""
import subprocess
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


def save_deliverables(rgb01, out_stem):
    # Write the four FR-27 deliverables sharing one base name: .fits/.tif(16-bit)/.png/.jpg.
    from PIL import Image
    import tifffile
    from astropy.io import fits

    out = Path(out_stem)
    out.parent.mkdir(parents=True, exist_ok=True)
    a = np.clip(np.asarray(rgb01, np.float64), 0, 1)
    a8 = (a * 255 + 0.5).astype(np.uint8)
    Image.fromarray(a8).save(str(out) + ".png")
    Image.fromarray(a8).save(str(out) + ".jpg", quality=95)
    tifffile.imwrite(str(out) + ".tif", (a * 65535 + 0.5).astype(np.uint16), photometric="rgb")
    fits.writeto(str(out) + ".fits", np.moveaxis(a.astype(np.float32), -1, 0), overwrite=True)  # FITS = [C,H,W]
    return Path(str(out) + ".tif")


def run_reflection_finish(clean_fits, out_stem, *, starnet_exe, runner=subprocess.run,
                          target_bg=0.35, scratch_dir=None):
    # Load the GraXpert _clean linear, autostretch, remove stars with StarNet2, fix the grid artifact,
    # rebuild the star layer, screen-blend it back over the starless layer, and write deliverables.
    import tifffile
    from astropy.io import fits

    d = fits.getdata(str(clean_fits)).astype(np.float64)
    img = np.moveaxis(d, 0, -1) if d.ndim == 3 else np.stack([d] * 3, -1)   # [C,H,W]->HWC
    img = np.clip(img, 0, None)
    mx = np.percentile(img, 99.995) or 1.0
    stretched = autostretch(np.clip(img / mx, 0, 1), target_bg=target_bg)
    # StarNet2 scratch tifs must NOT leak into the --out root (FR-4); default to the caller's
    # scratch dir, falling back to out_stem's parent so the pre-existing unit test still works.
    work = Path(scratch_dir) if scratch_dir is not None else Path(out_stem).parent
    work.mkdir(parents=True, exist_ok=True)
    tin, tout = work / "_sn_in.tif", work / "_sn_out.tif"
    tifffile.imwrite(str(tin), (stretched * 65535 + 0.5).astype(np.uint16), photometric="rgb")
    runner([str(starnet_exe), "-i", str(tin), "-o", str(tout)], capture_output=True, text=True)
    starless = fix_starnet_grid(tifffile.imread(str(tout)).astype(np.float64) / 65535.0)
    stars = np.clip(stretched - starless, 0, 1)          # what StarNet removed = the star layer
    combined = screen_blend(starless, stars)             # stars back on top, no blown highlights (#10)
    save_deliverables(combined, out_stem)
    return Path(str(out_stem) + ".tif")
