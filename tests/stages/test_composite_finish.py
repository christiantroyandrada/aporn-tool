"""Composite dual-layer finish — shared star/nebula separate-and-recombine core.

The composite finish generalises the proven reflection dual-layer to every non-cluster DSO mode
(mosaic / emission / reflection): stretch -> StarNet -> process the starless (nebula) layer +
process the stars layer -> screen-blend them back with a tunable strength -> deliverables.
"""
import numpy as np
import tifffile
from pathlib import Path
from astropy.io import fits

from aporntool.stages.composite_finish import (
    composite_layers, run_composite_finish, PROFILES,
)
from aporntool.stages.reflection_finish import screen_blend


# ---- composite_layers: the star-strength blend primitive ----

def test_star_strength_zero_returns_starless_unchanged():
    sl = np.full((4, 4, 3), 0.3)
    st = np.full((4, 4, 3), 0.6)
    assert np.allclose(composite_layers(sl, st, star_strength=0.0), sl)


def test_star_strength_one_is_full_screen_blend():
    sl = np.full((4, 4, 3), 0.3)
    st = np.full((4, 4, 3), 0.6)
    assert np.allclose(composite_layers(sl, st, star_strength=1.0), screen_blend(sl, st))


def test_star_strength_half_sits_between_starless_and_full():
    sl = np.full((4, 4, 3), 0.3)
    st = np.full((4, 4, 3), 0.6)
    full = composite_layers(sl, st, star_strength=1.0)
    half = composite_layers(sl, st, star_strength=0.5)
    assert (half >= sl - 1e-9).all()
    assert (half <= full + 1e-9).all()
    assert half.mean() < full.mean()


# ---- per-mode profiles ----

def test_profiles_cover_the_three_non_cluster_modes():
    for mode in ("dso-galaxy", "dso-emission-nebula", "dso-reflection-nebula"):
        assert mode in PROFILES


def test_emission_profile_keeps_all_stars_by_default():
    # Rich Milky-Way emission fields (M8/M20): stars kept at full strength (recipe rule).
    assert PROFILES["dso-emission-nebula"]["star_strength"] == 1.0


# ---- run_composite_finish: end-to-end (fake StarNet) ----

def _fake_starnet(cmd, **kw):
    i = cmd[cmd.index("-i") + 1]
    o = cmd[cmd.index("-o") + 1]
    tifffile.imwrite(o, tifffile.imread(i))   # remove no stars; layer math still runs

    class R:
        returncode = 0
        stdout = ""
        stderr = ""
    return R()


def test_run_composite_finish_writes_all_deliverables(tmp_path):
    clean = tmp_path / "clean.fits"
    fits.writeto(str(clean), (np.random.RandomState(1).rand(3, 16, 16) * 0.3).astype(np.float32))
    scratch = tmp_path / "scratch"
    run_composite_finish(clean, str(tmp_path / "M20_final"), mode="dso-emission-nebula",
                         starnet_exe="s", runner=_fake_starnet, scratch_dir=str(scratch))
    for ext in ("fits", "tif", "png", "jpg"):
        assert (tmp_path / f"M20_final.{ext}").exists()
    assert not (tmp_path / "_sn_in.tif").exists()   # scratch stayed in scratch_dir (FR-4)


def test_emission_profile_makes_halpha_read_crimson(tmp_path):
    # A reddish emission blob (R>G,B) must stay red-DOMINANT after the emission finish — the whole
    # point of the mode (crimson Halpha, not muddy pink/brown or green-cast).
    rng = np.random.RandomState(7)
    d = (0.08 + rng.rand(3, 24, 24) * 0.01).astype(np.float32)   # realistic noisy sky floor
    d[:, 1, 1] = 1.0             # a bright star sets the white point (so the nebula isn't the max)
    d[0, 8:16, 8:16] += 0.10     # R  } a reddish blob modestly above the sky -> lands in the
    d[1, 8:16, 8:16] += 0.02     # G  } midtones after stretch, where colour is meaningful
    d[2, 8:16, 8:16] += 0.015    # B    (not clipped to white)
    clean = tmp_path / "clean.fits"
    fits.writeto(str(clean), d)
    run_composite_finish(clean, str(tmp_path / "M20_final"), mode="dso-emission-nebula",
                         starnet_exe="s", runner=_fake_starnet, scratch_dir=str(tmp_path / "s"))
    out = tifffile.imread(str(tmp_path / "M20_final.tif")).astype(np.float64) / 65535.0
    blob = out[8:16, 8:16, :].reshape(-1, 3).mean(0)
    assert blob[0] > blob[1] and blob[0] > blob[2]     # red dominant
