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


def test_finish_scratch_dir_is_namespaced_and_created(tmp_path):
    ws = Workspace(tmp_path, "M31")
    assert ws.finish == tmp_path / "_work" / "M31" / "05_finish"
    ws.create()
    assert ws.finish.is_dir()


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


def test_stage_fits_keeps_both_on_cross_source_name_collision(tmp_path):
    # Two nights each export Light_0001.fit (Seestar resets counters) — both must survive.
    n1 = tmp_path / "night1"; n1.mkdir()
    n2 = tmp_path / "night2"; n2.mkdir()
    (n1 / "Light_0001.fit").write_bytes(b"one")
    (n2 / "Light_0001.fit").write_bytes(b"two")
    dest = tmp_path / "_work" / "M31" / "00_lights"
    n = stage_fits([n1, n2], dest)
    assert n == 2
    assert (dest / "Light_0001.fit").exists()
    assert (dest / "s1_Light_0001.fit").exists()


def test_stage_fits_is_idempotent_on_rerun(tmp_path):
    # Re-running the same command must not re-stage or double-count.
    src = tmp_path / "night1"; src.mkdir()
    (src / "Light_0001.fit").write_bytes(b"x")
    dest = tmp_path / "_work" / "M31" / "00_lights"
    assert stage_fits([src], dest) == 1
    assert stage_fits([src], dest) == 0


def _populate_work(ws):
    # A realistic post-run _work tree: golden anchor + disposable cropped + bulky stage dirs.
    ws.create()
    (ws.linear / "M31_Linear.fit").write_bytes(b"anchor")          # golden anchor -> KEEP
    (ws.linear / "M31_cropped.fit").write_bytes(b"cropped")        # disposable  -> DELETE
    (ws.lights / "Light_0001.fit").write_bytes(b"x")
    (ws.process / "r_pp_light_00001.fit").write_bytes(b"y" * 5000)
    (ws.graxpert / "M31_clean.fits").write_bytes(b"z" * 3000)
    (ws.finish / "M31_final.fit").write_bytes(b"w" * 1000)
    (ws.previews / "p.jpg").write_bytes(b"x")
    ws.manifest_path.write_text("{}")
    (ws.logs / "stack.log").write_text("log")


def test_clean_keeps_anchor_manifest_logs(tmp_path):
    ws = Workspace(tmp_path, "M31")
    _populate_work(ws)
    ws.clean()
    assert (ws.linear / "M31_Linear.fit").exists()   # golden anchor survives
    assert ws.manifest_path.exists()                 # resume state survives
    assert (ws.logs / "stack.log").exists()          # audit trail survives


def test_clean_deletes_bulky_dirs_and_cropped(tmp_path):
    ws = Workspace(tmp_path, "M31")
    _populate_work(ws)
    ws.clean()
    assert not ws.lights.exists()
    assert not ws.process.exists()
    assert not ws.graxpert.exists()
    assert not ws.finish.exists()
    assert not ws.previews.exists()
    assert not (ws.linear / "M31_cropped.fit").exists()   # cropped anchor is disposable


def test_clean_reports_bytes_freed(tmp_path):
    ws = Workspace(tmp_path, "M31")
    _populate_work(ws)
    freed = ws.clean()
    # 5000 (process) + 3000 (graxpert) + 1000 (finish) + tiny cropped/previews; anchor NOT counted.
    assert freed >= 9000
    assert freed < 9000 + 500      # the 6-byte anchor must not be counted


def test_clean_is_idempotent(tmp_path):
    ws = Workspace(tmp_path, "M31")
    _populate_work(ws)
    ws.clean()
    ws.clean()   # second call must not raise even though dirs are gone
    assert (ws.linear / "M31_Linear.fit").exists()
