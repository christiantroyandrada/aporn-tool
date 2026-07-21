"""--no-tripod foreground de-ghost: variance sky-mask (pure) + the composite I/O path."""
import numpy as np
import tifffile
from astropy.io import fits

from aporntool.stages.foreground import sky_mask, run_foreground_deghost


# --- sky_mask: the pure variance -> flood-fill segmentation --------------------

def _frames_with_varying_top(n=6, h=100, w=100, top=20):
    # Sky (everywhere) is constant across frames -> low variance. A top strip alternates
    # brightly frame-to-frame -> high variance -> foreground.
    frames = np.full((n, h, w), 0.2, np.float64)
    for i in range(n):
        frames[i, :top, :] = 0.15 + 0.5 * (i % 2)   # alternating -> high variance in the strip
    return frames


def test_sky_mask_keeps_low_variance_centre_drops_high_variance_strip():
    m = sky_mask(_frames_with_varying_top(), barrier_dilate=1, feather=2.0, min_island_frac=0.0)
    assert m[50, 50] > 0.9      # centre sky kept from the stack
    assert m[5, 50] < 0.1       # moving top strip -> foreground (taken from a single frame)


def test_sky_mask_walls_off_flat_foreground_interior():
    # A "building" touching the top edge: its roofline/edges vary (barrier), its interior is flat
    # (low variance). The interior must still be foreground — walled off from the centre sky.
    n, h, w = 6, 100, 100
    frames = np.full((n, h, w), 0.2, np.float64)
    # high-variance border of a box rows[0:30] cols[30:70] (bottom edge + two sides)
    for i in range(n):
        v = 0.15 + 0.5 * (i % 2)
        frames[i, 29:31, 30:70] = v      # roofline (bottom edge of the building)
        frames[i, 0:30, 29:31] = v       # left side
        frames[i, 0:30, 69:71] = v       # right side
    # interior rows[1:29] cols[31:69] stays flat 0.2 (low variance) -> looks like sky, but is walled off
    m = sky_mask(frames, barrier_dilate=1, feather=2.0, min_island_frac=0.0)
    assert m[50, 50] > 0.9      # centre = sky
    assert m[15, 50] < 0.2      # building interior = foreground despite being flat


def test_sky_mask_folds_interior_walled_blob_back_into_sky():
    # A high-variance patch that does NOT touch any frame edge is a sky region walled off from the
    # centre seed (spurious ridge / over-tight crop), not foreground. It must be reclassified as sky,
    # or it renders as a black blob. Real foreground still touches the border and stays foreground.
    n, h, w = 6, 120, 120
    frames = np.full((n, h, w), 0.2, np.float64)
    for i in range(n):
        v = 0.15 + 0.5 * (i % 2)
        frames[i, 20:35, 50:70] = v      # INTERIOR moving blob (touches no edge) -> should become sky
        frames[i, h - 12:, :] = v        # bottom strip touches the border -> real foreground
    m = sky_mask(frames, barrier_dilate=1, feather=2.0, min_island_frac=0.0)
    assert m[27, 60] > 0.8       # interior blob folded back into sky (not a black hole)
    assert m[h - 4, 60] < 0.2    # border-touching foreground stays foreground
    assert m[60, 60] > 0.9       # open centre is sky


def test_sky_mask_folds_tiny_star_islands_back_into_sky():
    # A 2x2 high-variance dot in open sky (a registration-jittered star) is far too small to be
    # foreground; min_island_frac must fold it back into the sky so it isn't punched out.
    frames = _frames_with_varying_top()
    frames[:, 60, 80] = np.linspace(0.1, 0.9, frames.shape[0])   # a flickering "star"
    frames[:, 61, 81] = np.linspace(0.9, 0.1, frames.shape[0])
    m = sky_mask(frames, barrier_dilate=1, feather=2.0, min_island_frac=0.01)
    assert m[60, 80] > 0.9      # the star island is reclassified as sky, not a foreground hole


# --- run_foreground_deghost: the cropping / orientation / composite I/O --------

def _write_reg_fits(path, strip_rgb, h=60, w=80, sky=0.5):
    # SIRIL-style registered frame FITS [C,H,W], stored bottom-up. Bright, consistent sky (so per-
    # frame percentile normalisation is stable, as with real same-exposure subs); the "foreground" is
    # a top-down TOP strip = the LAST array rows (FITS is bottom-up). strip_rgb sets its 3 channels.
    arr = np.full((3, h, w), float(sky), np.float32)
    for c in range(3):
        arr[c, h - 15:, :] = strip_rgb[c]
    fits.writeto(str(path), arr, overwrite=True)


def test_run_foreground_deghost_writes_deliverables_and_replaces_foreground(tmp_path):
    h, w = 60, 80
    # A distinctive finished "sky": uniform blue so we can tell foreground pixels were replaced.
    sky = np.zeros((h, w, 3), np.float64)
    sky[..., 2] = 0.6
    tif = tmp_path / "OUT_final.tif"
    tifffile.imwrite(str(tif), (sky * 65535 + 0.5).astype(np.uint16), photometric="rgb")

    regs = []
    for i in range(4):
        p = tmp_path / f"r_pp_light_{i + 1:05d}.fit"
        v = 0.1 + 0.2 * (i % 2)                                  # dark foreground that SHIFTS in value
        _write_reg_fits(p, strip_rgb=(v, v, v), h=h, w=w)        # -> high variance in the top strip
        regs.append(str(p))
    ref = tmp_path / "r_pp_light_00001.fit"                      # sharp reference: RED foreground
    _write_reg_fits(ref, strip_rgb=(0.8, 0.1, 0.1), h=h, w=w)

    out_stem = str(tmp_path / "OUT_final")
    cov = run_foreground_deghost(str(tif), regs, str(ref), crop_box=None, out_stem=out_stem,
                                 params={"feather": 2.0, "barrier_dilate": 1, "min_island_frac": 0.0,
                                         "fg_target_bg": 0.5, "fg_gain": 1.0},
                                 jpeg_quality=90)
    for ext in ("fits", "tif", "png", "jpg"):
        assert (tmp_path / f"OUT_final.{ext}").exists()
    assert 0.0 < cov < 0.6                              # a top strip, not the whole frame

    out = tifffile.imread(str(tmp_path / "OUT_final.tif")).astype(np.float64) / 65535.0
    # Top rows (foreground) should no longer be the pure-blue sky — the sharp RED frame was painted in.
    assert out[3, w // 2, 0] > out[3, w // 2, 2]        # red now dominates blue in the foreground
    # Bottom-centre stays the deep blue sky (kept from the stack).
    assert out[h - 3, w // 2, 2] > 0.4 and out[h - 3, w // 2, 0] < 0.1
