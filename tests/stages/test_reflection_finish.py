import numpy as np
from aporntool.stages.reflection_finish import mtf, autostretch, screen_blend, fix_starnet_grid


def test_mtf_endpoints():
    assert mtf(0.5, np.array([0.0]))[0] == 0.0
    assert mtf(0.5, np.array([1.0]))[0] == 1.0


def test_autostretch_brightens_midtones_and_stays_bounded():
    img = np.full((8, 8, 3), 0.05, np.float32)   # dark linear
    out = autostretch(img, target_bg=0.25)
    assert out.shape == img.shape
    assert 0.0 <= out.min() and out.max() <= 1.0
    assert out.mean() > img.mean()               # midtones lifted


def test_screen_blend_never_darkens():
    a = np.full((4, 4, 3), 0.4, np.float32)
    b = np.full((4, 4, 3), 0.5, np.float32)
    out = screen_blend(a, b)
    assert (out >= a - 1e-6).all() and out.max() <= 1.0


def test_fix_starnet_grid_smooths(tmp_path):
    rng = np.zeros((16, 16, 3), np.float32)
    rng[::2, ::2, :] = 1.0                        # checkerboard artifact
    out = fix_starnet_grid(rng)
    assert out.shape == rng.shape
    assert out.std() < rng.std()                  # grid smoothed away
