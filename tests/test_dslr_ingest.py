"""DSLR DSO ingest: format-priority light detection (FITS > raw > TIFF > JPEG), one format per folder."""
import pytest

from aporntool.workspace import detect_light_kind, iter_lights, count_lights, stage_lights
from aporntool.cli import build_parser


def test_dso_modes_accept_calibration_args():
    args = build_parser().parse_args(
        ["dso-galaxy", "--in", "/d", "--target", "M31",
         "--darks", "/dk", "--flats", "/fl", "--bias", "/bi", "--focal", "530", "--pixel", "3.76"])
    assert args.darks == "/dk" and args.flats == "/fl" and args.bias == "/bi"
    assert args.focal == 530 and args.pixel == 3.76


def test_wide_mode_rejects_calibration_args():
    # --darks etc. are DSO-only; a phone Milky Way run has no calibration frames.
    with pytest.raises(SystemExit):
        build_parser().parse_args(["dso-milky-way", "--in", "/d", "--darks", "/dk"])


def test_dso_modes_accept_coords():
    # --coords lets a DSLR user shoot a target that isn't in the built-in catalog.
    args = build_parser().parse_args(
        ["dso-galaxy", "--in", "/d", "--target", "Sh2-155", "--coords", "350.2,61.2"])
    assert args.coords == "350.2,61.2"


def test_stacked_flag_available_on_all_modes():
    # --stacked (finish-only, pre-stacked image) applies to every mode, including Milky Way.
    for mode in ("dso-galaxy", "dso-emission-nebula", "dso-reflection-nebula",
                 "dso-star-cluster", "dso-milky-way"):
        args = build_parser().parse_args([mode, "--in", "/d", "--stacked"])
        assert args.stacked is True, mode


def test_fits_wins_and_ignores_preview_jpg(tmp_path):
    # A Seestar folder holds FITS subs + .jpg previews — must ingest only the FITS (unchanged behavior).
    (tmp_path / "Light_0001.fit").write_bytes(b"x")
    (tmp_path / "Light_0002.fits").write_bytes(b"x")
    (tmp_path / "Light_0001.jpg").write_bytes(b"x")
    (tmp_path / "Light_0001_thn.jpg").write_bytes(b"x")
    assert detect_light_kind(tmp_path) == ("fits", True)
    assert [f.name for f in iter_lights(tmp_path)] == ["Light_0001.fit", "Light_0002.fits"]


def test_raw_wins_over_incamera_jpeg(tmp_path):
    # A DSLR folder with RAW + in-camera JPEG pairs — prefer the RAW, drop the JPEGs.
    for n in (1, 2, 3):
        (tmp_path / f"IMG_{n}.CR2").write_bytes(b"x")
        (tmp_path / f"IMG_{n}.JPG").write_bytes(b"x")
    kind, debayer = detect_light_kind(tmp_path)
    assert kind == "raw" and debayer is True          # CFA raw needs debayering
    assert [f.name for f in iter_lights(tmp_path)] == ["IMG_1.CR2", "IMG_2.CR2", "IMG_3.CR2"]


def test_various_raw_extensions_detected(tmp_path):
    for name in ("a.nef", "b.arw", "c.dng", "d.raf", "e.orf", "f.rw2"):
        (tmp_path / name).write_bytes(b"x")
    assert detect_light_kind(tmp_path)[0] == "raw"
    assert count_lights(tmp_path) == 6


def test_tiff_is_rgb_no_debayer(tmp_path):
    (tmp_path / "a.tif").write_bytes(b"x")
    (tmp_path / "b.tiff").write_bytes(b"x")
    kind, debayer = detect_light_kind(tmp_path)
    assert kind == "tiff" and debayer is False        # already-debayered RGB export


def test_jpeg_only_no_debayer(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    kind, debayer = detect_light_kind(tmp_path)
    assert kind == "jpeg" and debayer is False


def test_empty_folder_is_none(tmp_path):
    (tmp_path / "notes.txt").write_bytes(b"x")
    assert detect_light_kind(tmp_path) == (None, False)
    assert iter_lights(tmp_path) == []


def test_sidecars_excluded_from_detection(tmp_path):
    # A folder holding ONLY our own outputs must not be seen as ingestable JPEG/TIFF light frames.
    (tmp_path / "M31_final.jpg").write_bytes(b"x")
    (tmp_path / "M31_final.tif").write_bytes(b"x")
    assert detect_light_kind(tmp_path) == (None, False)


def test_stage_lights_stages_dominant_format(tmp_path):
    src = tmp_path / "night"; src.mkdir()
    (src / "IMG_1.CR2").write_bytes(b"raw")
    (src / "IMG_1.JPG").write_bytes(b"jpg")
    dest = tmp_path / "_work" / "M31" / "00_lights"
    assert stage_lights([src], dest) == 1
    assert (dest / "IMG_1.CR2").exists() and not (dest / "IMG_1.JPG").exists()
