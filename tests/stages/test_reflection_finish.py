import numpy as np
import tifffile
from pathlib import Path
from astropy.io import fits
from aporntool.stages.reflection_finish import (
    mtf, autostretch, screen_blend, fix_starnet_grid,
    save_deliverables, run_reflection_finish, desaturate_background,
)


def test_desaturate_background_neutralizes_dark_colored_noise():
    # A dark bluish pixel (low luminance = sky noise) should collapse to neutral gray.
    dark_blue = np.array([[[0.02, 0.02, 0.10]]])
    out = desaturate_background(dark_blue, threshold=0.12, softness=0.12)
    assert abs(out[0, 0, 2] - out[0, 0, 0]) < 0.01     # blue ≈ red -> neutral


def test_desaturate_background_keeps_bright_color():
    # A bright blue pixel (the nebula) must keep its colour.
    bright_blue = np.array([[[0.20, 0.20, 0.80]]])
    out = desaturate_background(bright_blue, threshold=0.12, softness=0.12)
    assert (out[0, 0, 2] - out[0, 0, 0]) > 0.4         # still clearly blue


def test_desaturate_background_preserves_luminance():
    # Desaturation only touches chroma; per-pixel channel mean (luminance) is unchanged.
    x = np.array([[[0.02, 0.02, 0.10]], [[0.20, 0.20, 0.80]]])
    out = desaturate_background(x, threshold=0.12, softness=0.12)
    assert np.allclose(out.mean(2), x.mean(2), atol=1e-9)


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


def test_run_reflection_finish_writes_starnet_scratch_to_given_scratch_dir(tmp_path):
    # The StarNet2 temp tifs must NOT be written next to the deliverables (--out root, FR-4);
    # they belong in a caller-supplied scratch dir under _work.
    clean = tmp_path / "clean.fits"
    fits.writeto(str(clean), np.random.RandomState(2).rand(3, 16, 16).astype(np.float32))

    scratch = tmp_path / "_work" / "M78" / "05_finish"
    scratch.mkdir(parents=True)
    out_root = tmp_path / "out"
    out_root.mkdir()

    def fake_starnet(cmd, **kw):
        i = cmd[cmd.index("-i") + 1]
        o = cmd[cmd.index("-o") + 1]
        # StarNet2 scratch files must land in the scratch dir, not the --out root.
        assert Path(i).parent == scratch
        assert Path(o).parent == scratch
        tifffile.imwrite(o, tifffile.imread(i))

        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    run_reflection_finish(clean, str(out_root / "M78_final"),
                          starnet_exe="starnet2", runner=fake_starnet, scratch_dir=scratch)
    assert (out_root / "M78_final.tif").exists()
    assert not (out_root / "_sn_in.tif").exists()
    assert not (out_root / "_sn_out.tif").exists()


def test_scnr_reduces_green():
    import numpy as np
    from aporntool.stages.reflection_finish import scnr_green
    a = np.zeros((4, 4, 3)); a[..., 1] = 0.8; a[..., 0] = 0.2; a[..., 2] = 0.2
    assert scnr_green(a)[..., 1].mean() < 0.8


def test_saturate_pushes_blue_out():
    import numpy as np
    from aporntool.stages.reflection_finish import saturate
    a = np.full((4, 4, 3), 0.3); a[..., 2] = 0.5
    assert saturate(a, 0.3, 1.3, 4.5)[..., 2].max() >= 0.5


def test_darken_background_lowers_median():
    import numpy as np
    from aporntool.stages.reflection_finish import darken_background
    assert float(np.median(darken_background(np.full((8, 8, 3), 0.4), 0.08, 0.85))) < 0.4


def test_process_stars_brightens_bright_pixel():
    import numpy as np
    from aporntool.stages.reflection_finish import process_stars
    st = np.zeros((8, 8, 3)); st[4, 4, :] = 0.7
    assert process_stars(st, 1.5, 1.2)[4, 4, :].mean() >= 0.7


def test_run_reflection_finish_v2_isolated_scratch_and_all_deliverables(tmp_path):
    import numpy as np, tifffile
    from astropy.io import fits
    from aporntool.stages.reflection_finish import run_reflection_finish
    clean = tmp_path / "clean.fits"
    fits.writeto(str(clean), (np.random.RandomState(3).rand(3, 32, 32) * 0.3).astype(np.float32))
    def fake(cmd, **kw):
        i = cmd[cmd.index("-i") + 1]; o = cmd[cmd.index("-o") + 1]; tifffile.imwrite(o, tifffile.imread(i))
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    run_reflection_finish(clean, str(tmp_path / "M78_final"), starnet_exe="s", runner=fake,
                          scratch_dir=str(tmp_path / "scratch"))
    for ext in ("fits", "tif", "png", "jpg"):
        assert (tmp_path / f"M78_final.{ext}").exists()
    assert not (tmp_path / "_sn_in.tif").exists()   # scratch went to scratch_dir, not the out root
