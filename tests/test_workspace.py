from pathlib import Path
from aporntool.workspace import Workspace, iter_fits, count_fits, stage_fits


def test_layout_is_namespaced_under_target(tmp_path):
    ws = Workspace(tmp_path, "M31")
    assert ws.work == tmp_path / "_work" / "M31"
    assert ws.lights == tmp_path / "_work" / "M31" / "00_lights"
    assert ws.deliverable("tif") == tmp_path / "M31_final.tif"


def test_create_makes_dirs(tmp_path):
    ws = Workspace(tmp_path, "M31")
    ws.create()
    assert ws.lights.is_dir() and ws.logs.is_dir()


def test_iter_fits_ignores_jpg_and_thumbnails(tmp_path):
    (tmp_path / "Light_0001.fit").write_bytes(b"x")
    (tmp_path / "Light_0002.fits").write_bytes(b"x")
    (tmp_path / "Light_0001.jpg").write_bytes(b"x")       # Seestar preview — must be ignored
    (tmp_path / "Light_0001_thn.jpg").write_bytes(b"x")   # thumbnail — must be ignored
    names = [f.name for f in iter_fits(tmp_path)]
    assert names == ["Light_0001.fit", "Light_0002.fits"]
    assert count_fits(tmp_path) == 2


def test_stage_fits_copies_only_fits(tmp_path):
    src = tmp_path / "night1"; src.mkdir()
    (src / "a.fit").write_bytes(b"x")
    (src / "a.jpg").write_bytes(b"x")
    dest = tmp_path / "_work" / "M31" / "00_lights"
    n = stage_fits([src], dest)
    assert n == 1
    assert (dest / "a.fit").exists() and not (dest / "a.jpg").exists()
