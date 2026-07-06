import numpy as np
from astropy.io import fits
from aporntool.stages.crop import auto_crop_box, resolve_crop


def test_auto_crop_trims_black_border(tmp_path):
    # 100x100 frame, signal only in the central 60x60 → box should be ~inside that region.
    arr = np.zeros((3, 100, 100), np.float32)
    arr[:, 20:80, 20:80] = 0.5
    p = tmp_path / "a.fits"; fits.writeto(str(p), arr)
    box = auto_crop_box(p, margin_frac=0.0)
    x, y, w, h = map(int, box.split())
    assert 18 <= x <= 22 and 18 <= y <= 22 and 58 <= w <= 62 and 58 <= h <= 62


def test_auto_crop_none_when_full_frame(tmp_path):
    # Use a realistic-size frame: the near-full-frame guard bug only reproduces once the 2% margin
    # rounds to >=1px (i.e. dim >~50), so a 50x50 frame would pass even with the bug present.
    arr = np.full((3, 600, 600), 0.5, np.float32)
    p = tmp_path / "b.fits"; fits.writeto(str(p), arr)
    assert auto_crop_box(p) is None


def test_resolve_crop_passthrough_and_skip(tmp_path):
    arr = np.full((3, 10, 10), 0.5, np.float32); p = tmp_path / "c.fits"; fits.writeto(str(p), arr)
    assert resolve_crop("10 10 100 100", p) == "10 10 100 100"   # explicit box passes through
    assert resolve_crop(None, p) is None                          # skip


def test_auto_crop_flips_y_to_siril_top_down_origin(tmp_path):
    # Signal only in the astropy TOP half (data rows 50-99); the bottom half is black border.
    # SIRIL's crop y is measured from the TOP, so the box must sit at y=0 (not astropy row 50).
    # A symmetric border can't catch this — the branch's original test used one, so the y-axis
    # flip went unverified. This asymmetric case pins the convention.
    arr = np.zeros((3, 100, 100), np.float32)
    arr[:, 50:100, :] = 0.5
    p = tmp_path / "top.fits"; fits.writeto(str(p), arr)
    box = auto_crop_box(p, margin_frac=0.0)
    x, y, w, h = map(int, box.split())
    assert h == 50 and y == 0, box          # covered 50 rows, pinned to the SIRIL top
