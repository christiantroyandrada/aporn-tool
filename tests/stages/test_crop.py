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


def test_auto_crop_handles_mosaic_cross_shape(tmp_path):
    # framing=max mosaics leave black CORNERS while the row/col bands stay covered — a bounding box
    # would keep the whole frame (corners and all). The largest-signal rectangle must instead return
    # a box that contains ONLY covered pixels. Frame: everything covered except four 30x30 corners.
    arr = np.full((3, 120, 120), 0.5, np.float32)
    for ys in (slice(0, 30), slice(90, 120)):
        for xs in (slice(0, 30), slice(90, 120)):
            arr[:, ys, xs] = 0.0
    p = tmp_path / "cross.fits"; fits.writeto(str(p), arr)
    box = auto_crop_box(p, margin_frac=0.0)
    assert box is not None
    x, y_siril, w, h = map(int, box.split())
    assert w < 120 or h < 120                      # not the full frame
    # Map the SIRIL (top-down) box back to astropy rows and confirm it holds only signal.
    lum = np.moveaxis(fits.getdata(str(p)).astype(float), 0, -1).mean(2)
    H = lum.shape[0]
    y0 = H - y_siril - h
    region = lum[y0:y0 + h, x:x + w]
    assert (region > 0).all()                      # crop excludes every black corner


def test_resolve_crop_auto_missing_anchor_raises_actionable(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError, match="golden anchor not found"):
        resolve_crop("auto", tmp_path / "missing_Linear.fit")


def test_auto_crop_no_black_at_block_boundary(tmp_path):
    # Regression: on a downsampled (block>1) frame, a border that ends mid-block must not leak black
    # pixels into the crop. Frame 1500x1500 (block=2), left border of width 101 (odd -> mid-block).
    arr = np.full((3, 1500, 1500), 0.5, np.float32)
    arr[:, :, :101] = 0.0
    p = tmp_path / "midblock.fits"; fits.writeto(str(p), arr)
    box = auto_crop_box(p, margin_frac=0.0)
    assert box is not None
    x, y_siril, w, h = map(int, box.split())
    lum = np.moveaxis(fits.getdata(str(p)).astype(float), 0, -1).mean(2)
    H = lum.shape[0]; y0 = H - y_siril - h
    assert (lum[y0:y0 + h, x:x + w] > 0).all()     # no black pixel inside the crop


def test_auto_crop_survives_nan_and_inf(tmp_path):
    # Regression: a NaN/inf pixel must NOT poison peak/median into a silent no-crop. Border is black
    # + non-finite; the crop should still trim the border and contain only finite signal.
    arr = np.zeros((3, 1000, 1000), np.float32)
    arr[:, 200:800, 200:800] = 0.5          # central signal square, black border
    arr[:, 0, 0] = np.inf                   # inf hot pixel in the border
    arr[:, 5, 5] = np.nan                   # NaN in the border
    p = tmp_path / "nan.fits"; fits.writeto(str(p), arr)
    box = auto_crop_box(p, margin_frac=0.0)
    assert box is not None                  # not the silent-None poison
    x, y_siril, w, h = map(int, box.split())
    lum = np.moveaxis(fits.getdata(str(p)).astype(float), 0, -1).mean(2)
    H = lum.shape[0]; y0 = H - y_siril - h
    region = lum[y0:y0 + h, x:x + w]
    assert np.isfinite(region).all() and (region > 0).all()   # only finite signal in the crop
