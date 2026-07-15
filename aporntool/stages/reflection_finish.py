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


def save_deliverables(rgb01, out_stem, jpeg_quality=95):
    # Write the four FR-27 deliverables sharing one base name: .fits/.tif(16-bit)/.png/.jpg.
    from PIL import Image
    import tifffile
    from astropy.io import fits

    out = Path(out_stem)
    out.parent.mkdir(parents=True, exist_ok=True)
    a = np.clip(np.asarray(rgb01, np.float64), 0, 1)
    a8 = (a * 255 + 0.5).astype(np.uint8)
    Image.fromarray(a8).save(str(out) + ".png")
    Image.fromarray(a8).save(str(out) + ".jpg", quality=int(jpeg_quality))
    tifffile.imwrite(str(out) + ".tif", (a * 65535 + 0.5).astype(np.uint16), photometric="rgb")
    fits.writeto(str(out) + ".fits", np.moveaxis(a.astype(np.float32), -1, 0), overwrite=True)  # FITS = [C,H,W]
    return Path(str(out) + ".tif")


def scnr_green(rgb):
    # Remove residual green (reflection nebulae have none) via the average-neutral SCNR rule.
    out = np.array(rgb, np.float64, copy=True)
    g = out[..., 1]
    out[..., 1] = g - np.clip(g - np.maximum(out[..., 0], out[..., 2]), 0, None) * 0.95
    return np.clip(out, 0, 1)


def saturate(rgb, sat_r, sat_g, sat_b):
    # Per-channel saturation about luminance: suppress red, boost blue for scattered starlight.
    L = np.asarray(rgb, np.float64).mean(2, keepdims=True)
    return np.clip(L + (np.asarray(rgb, np.float64) - L) * np.array([sat_r, sat_g, sat_b]), 0, 1)


def midtone_boost(rgb, boost):
    # Two-pass MTF lift of the nebula midtones (gentle fixed 2nd pass).
    rgb = np.clip(np.asarray(rgb, np.float64), 0, 1)
    med = float(np.median(rgb.mean(2)))
    t1 = med + (0.5 - med) * boost
    rgb = np.clip(np.stack([mtf(find_m(med, t1), rgb[..., i]) for i in range(3)], -1), 0, 1)
    med2 = float(np.median(rgb.mean(2)))
    t2 = med2 + (0.55 - med2) * 0.3
    return np.clip(np.stack([mtf(find_m(med2, t2), rgb[..., i]) for i in range(3)], -1), 0, 1)


def local_contrast(rgb, amount):
    # Large-radius unsharp on luminance to bring out dust structure.
    rgb = np.asarray(rgb, np.float64)
    L = rgb.mean(2, keepdims=True)
    hp = L - gaussian_filter(L, (16, 16, 0))
    Lc = np.clip(L + hp * amount * np.clip(L, 0, 1), 0, 1)
    return np.clip(rgb * np.divide(Lc, np.clip(L, 1e-5, None)), 0, 1)


def darken_background(rgb, bgpull, gamma):
    # Pull background median down to `bgpull`, then gamma-compress shadows → deep black sky.
    rgb = np.clip(np.asarray(rgb, np.float64), 0, 1)
    med = float(np.median(rgb.mean(2)))
    return np.clip(np.clip(mtf(find_m(med, bgpull), rgb), 0, 1) ** gamma, 0, 1)


def desaturate_background(rgb, threshold, softness):
    # Selective background desaturation: fade chroma to neutral in low-signal pixels so the coloured
    # sky noise (the blue×4.5 boost amplifies it everywhere) collapses to clean neutral black, while
    # brighter pixels — the nebula and stars — keep full colour. Luminance is untouched; only the
    # per-pixel colour-vs-grey distance is scaled by a smooth ramp: 0 below `threshold` (grey),
    # rising to 1 by `threshold + softness` (full colour).
    rgb = np.clip(np.asarray(rgb, np.float64), 0, 1)
    L = rgb.mean(2, keepdims=True)
    w = np.clip((L - threshold) / max(softness, 1e-6), 0.0, 1.0)
    return np.clip(L + (rgb - L) * w, 0, 1)


def process_stars(stars, brightness, saturation):
    # Star layer: boost colour + nonlinear brightness curve + a tight two-scale bloom.
    st = np.clip(np.asarray(stars, np.float64), 0, 1)
    L = st.mean(2, keepdims=True)
    st = np.clip(L + (st - L) * saturation, 0, 1)
    st = np.clip(st + (st ** 2) * (brightness - 1.0), 0, 1)
    bright = np.clip(st - 0.40, 0, None)
    bloom = gaussian_filter(bright, (1.5, 1.5, 0)) * 0.8 + gaussian_filter(bright, (4, 4, 0)) * 0.2
    return np.clip(st + bloom, 0, 1)


REFLECTION_DEFAULTS = dict(target_bg=0.35, shadows_clip=-2.8, sat_r=0.30, sat_g=1.3, sat_b=4.5,
                           midboost=0.55, lc=1.3, bgpull=0.08, gamma=0.85,
                           bg_desat=0.14, bg_desat_soft=0.14,
                           st_bright=1.5, st_sat=1.2)


def run_reflection_finish(clean_fits, out_stem, *, starnet_exe, runner=subprocess.run,
                          scratch_dir=None, params=None, jpeg_quality=95):
    # Reflection is now the shared composite core with the reflection profile — kept as a named
    # entry point for the reflection finish stage (and its regression tests). The dual-layer chain
    # (stretch -> StarNet -> process starless + stars -> screen-blend) lives in composite_finish.
    # Cropping is NOT done here — the bge stage already cropped the linear anchor before GraXpert.
    from aporntool.stages.composite_finish import run_composite_finish   # lazy: avoid import cycle
    return run_composite_finish(clean_fits, out_stem, mode="dso-reflection-nebula",
                                starnet_exe=starnet_exe, runner=runner, scratch_dir=scratch_dir,
                                params=params, jpeg_quality=jpeg_quality)
