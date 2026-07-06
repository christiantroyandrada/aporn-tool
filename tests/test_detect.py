import numpy as np
import pytest
from astropy.io import fits

from aporntool.detect import read_header_target, resolve_target_auto


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
    assert t.name.upper().replace(" ", "") == "M31" and t.mode == "mosaic"


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
