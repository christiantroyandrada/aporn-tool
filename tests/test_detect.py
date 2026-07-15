import numpy as np
import pytest
from astropy.io import fits

from aporntool.detect import read_header_target, resolve_target_auto, detect_mosaic


def _sub(path, obj="M 31", ra=11.25, dec=41.4):
    # A minimal but valid Seestar-style sub: real FITS with OBJECT + RA/DEC in the header.
    hdu = fits.PrimaryHDU(np.zeros((4, 4), np.float32))
    if obj is not None:
        hdu.header["OBJECT"] = obj
    if ra is not None:
        hdu.header["RA"] = ra
    if dec is not None:
        hdu.header["DEC"] = dec
    hdu.writeto(str(path))


def _panel_subs(d, centers, per=4):
    # Write `per` dithered subs around each (ra, dec) panel center — mimics a Seestar capture.
    n = 0
    for (ra, dec) in centers:
        for i in range(per):
            _sub(d / f"Light_{n:04d}.fit", "M 31", ra + i * 0.003, dec + i * 0.002)
            n += 1


def test_read_header_target_reads_object_and_coords(tmp_path):
    _sub(tmp_path / "Light_0001.fit", "M 31", 11.25, 41.4)
    assert read_header_target(tmp_path) == ("M 31", 11.25, 41.4)


def test_read_header_target_empty_dir_is_all_none(tmp_path):
    assert read_header_target(tmp_path) == (None, None, None)


def test_read_header_target_ignores_unreadable_fits(tmp_path):
    (tmp_path / "Light_0001.fit").write_bytes(b"not a real fits")
    assert read_header_target(tmp_path) == (None, None, None)


def test_auto_detect_known_object_uses_catalog(tmp_path):
    _sub(tmp_path / "Light_0001.fit", "M 31", 11.25, 41.4)
    t = resolve_target_auto(None, tmp_path)
    assert t.name.upper().replace(" ", "") == "M31" and t.mode == "galaxy"


def test_auto_detect_unknown_object_falls_back_to_header_coords(tmp_path):
    _sub(tmp_path / "Light_0001.fit", "VdB 106", 246.775, -23.47)
    t = resolve_target_auto(None, tmp_path)
    assert t.ra == 246.775 and t.dec == -23.47 and "VdB" in t.name


def test_explicit_target_name_overrides_header(tmp_path):
    _sub(tmp_path / "Light_0001.fit", "M 31", 11.25, 41.4)
    t = resolve_target_auto("M33", tmp_path)          # user override wins for the name
    assert t.name.upper().replace(" ", "") == "M33"


def test_no_target_and_no_object_raises(tmp_path):
    _sub(tmp_path / "Light_0001.fit", obj=None, ra=None, dec=None)
    with pytest.raises((ValueError, KeyError)):
        resolve_target_auto(None, tmp_path)


# ---- detect_mosaic: multi-panel vs single-panel from pointing spread ----

def test_detect_single_panel_when_subs_share_one_pointing(tmp_path):
    # All subs cluster within dither jitter (< a few arcmin) → single panel.
    _panel_subs(tmp_path, [(271.06, -22.96)], per=8)
    d = detect_mosaic(tmp_path)
    assert d.is_mosaic is False
    assert d.ra_spread_deg < 0.1 and d.dec_spread_deg < 0.1


def test_detect_mosaic_when_pointing_spreads_beyond_one_fov(tmp_path):
    # A 2x2 tile spanning ~2 deg (like the real M31 mosaic) → mosaic.
    _panel_subs(tmp_path, [(10.0, 40.0), (11.3, 40.0), (10.0, 41.0), (11.3, 41.0)], per=4)
    d = detect_mosaic(tmp_path)
    assert d.is_mosaic is True
    assert d.dec_spread_deg > 0.5 or d.ra_spread_deg > 0.5
    assert "spread" in d.reason.lower()


def test_detect_mosaic_defaults_to_single_when_no_coords(tmp_path):
    # No RA/DEC in headers → can't measure spread → assume single (safe default), say so.
    _sub(tmp_path / "Light_0001.fit", "M 31", ra=None, dec=None)
    d = detect_mosaic(tmp_path)
    assert d.is_mosaic is False
    assert "no" in d.reason.lower()
