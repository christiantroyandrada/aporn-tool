import numpy as np
import tifffile
from pathlib import Path
from astropy.io import fits
from aporntool.stages.reflection_finish import (
    mtf, autostretch, screen_blend, fix_starnet_grid,
    save_deliverables, run_reflection_finish,
)


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


def test_save_deliverables_writes_all(tmp_path):
    img = np.clip(np.random.RandomState(0).rand(8, 8, 3), 0, 1).astype(np.float32)
    save_deliverables(img, str(tmp_path / "M78_final"))
    for ext in ("png", "tif", "jpg", "fits"):
        assert (tmp_path / f"M78_final.{ext}").exists()


def test_run_reflection_finish_produces_deliverables(tmp_path):
    # Fake StarNet2: copy input tif to output (no stars removed) so the layer math runs.
    clean = tmp_path / "clean.fits"
    fits.writeto(str(clean), np.random.RandomState(1).rand(3, 16, 16).astype(np.float32))

    def fake_starnet(cmd, **kw):
        i = cmd[cmd.index("-i") + 1]
        o = cmd[cmd.index("-o") + 1]
        tifffile.imwrite(o, tifffile.imread(i))

        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    out = run_reflection_finish(clean, str(tmp_path / "M78_final"),
                                starnet_exe="starnet2", runner=fake_starnet)
    assert Path(str(out)).exists() or (tmp_path / "M78_final.tif").exists()
