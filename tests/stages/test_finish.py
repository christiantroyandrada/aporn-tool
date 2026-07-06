from pathlib import Path
from aporntool.workspace import Workspace
from aporntool.config import Config
from aporntool.catalog import resolve_target
from aporntool.stages.finish import build_finish_stages


def _rec(scripts):
    def run(cmd, **kw):
        # SIRIL fake: record script text; fabricate any saved deliverable as needed.
        try:
            script = Path(cmd[cmd.index("-s") + 1]); scripts.append(script.read_text(encoding="utf-8"))
        except (ValueError, IndexError):
            pass
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    return run


def test_mosaic_finish_stage_ids(tmp_path):
    ws = Workspace(tmp_path, "M31"); ws.create()
    stages = build_finish_stages("dso-mosaic", ws, Config.default(), resolve_target("M31"),
                                 siril_exe="siril-cli", graxpert_exe="GraXpert.exe")
    assert [s.id for s in stages] == ["bge", "denoise", "finish"]


def test_emission_finish_is_single_stage(tmp_path):
    ws = Workspace(tmp_path, "M8"); ws.create()
    stages = build_finish_stages("dso-emission-nebula", ws, Config.default(), resolve_target("M8"),
                                 siril_exe="siril-cli")
    assert [s.id for s in stages] == ["finish"]


def test_emission_finish_writes_deliverables_and_spcc(tmp_path):
    ws = Workspace(tmp_path, "M8"); ws.create()
    scripts = []
    stages = build_finish_stages("dso-emission-nebula", ws, Config.default(), resolve_target("M8"),
                                 siril_exe="siril-cli", runner=_rec(scripts))
    finish = next(s for s in stages if s.id == "finish")
    finish.run()
    text = (ws.logs / "finish.ssf").read_text(encoding="utf-8")
    assert 'spcc "-oscsensor=Sony IMX662"' in text
    assert "savetif" in text and "M8_final" in text


def test_reflection_finish_stage_ids(tmp_path):
    ws = Workspace(tmp_path, "M78"); ws.create()
    stages = build_finish_stages("dso-reflection-nebula", ws, Config.default(),
                                 resolve_target("M78", coords="0,0"),
                                 siril_exe="siril-cli", graxpert_exe="GraXpert.exe", starnet_exe="starnet2")
    assert [s.id for s in stages] == ["bge", "denoise", "finish"]


def _fake_run_siril_mosaic_finish(scripts):
    # Fabricate the mosaic finish deliverables under ws.finish (bare names, cwd=ws.finish),
    # exactly like real SIRIL would when `cd` points there and names are bare.
    def run(script_path, *, workdir, siril_exe, runner=None, log_path=None):
        text = Path(script_path).read_text(encoding="utf-8")
        scripts.append(text)
        if "starnet -starmask" in text:
            # workdir passed to run_siril is ws.work; the script's own `cd` line names the
            # real scratch dir SIRIL executes in — parse it out.
            import re
            m = re.search(r'cd "([^"]+)"', text)
            finish_dir = Path(m.group(1))
            # Determine the bare out name from a `save <name>_stretched` line.
            m2 = re.search(r"save (\S+)_stretched", text)
            bare = m2.group(1)
            for ext in ("fit", "tif", "png", "jpg"):
                (finish_dir / f"{bare}.{ext}").write_text("x", encoding="utf-8")
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    return run


def test_mosaic_finish_runs_in_scratch_cwd_with_bare_names_and_publishes_four_deliverables(tmp_path, monkeypatch):
    import aporntool.stages.finish as fin
    ws = Workspace(tmp_path, "M31"); ws.create()
    # Fabricate the GraXpert _clean.fits the finish stage loads via a relative path.
    clean = ws.graxpert / "M31_clean.fits"
    clean.write_text("x", encoding="utf-8")

    scripts = []
    monkeypatch.setattr(fin, "run_siril", _fake_run_siril_mosaic_finish(scripts))

    stages = build_finish_stages("dso-mosaic", ws, Config.default(), resolve_target("M31"),
                                 siril_exe="siril-cli", graxpert_exe="GraXpert.exe")
    finish = next(s for s in stages if s.id == "finish")
    finish.run()

    text = scripts[-1]
    assert f'cd "{ws.finish}"' in text
    assert "../03_graxpert/M31_clean" in text
    # bare out name only in the command lines (everything after the `cd` line) — no absolute
    # out_root path baked into save/starnet/pm commands.
    body = text.split("\n", 2)[-1]
    assert str(ws.out_root) not in body
    assert "M31_final" in body

    base = ws.out_root / "M31_final"
    for ext in ("fits", "tif", "png", "jpg"):
        assert (base.parent / f"M31_final.{ext}").exists(), f"missing {ext}"
    assert finish.produces()


def test_emission_finish_renames_fit_to_fits_for_produces(tmp_path, monkeypatch):
    import aporntool.stages.finish as fin
    ws = Workspace(tmp_path, "M8"); ws.create()

    def fake_run_siril(script_path, *, workdir, siril_exe, runner=None, log_path=None):
        # SIRIL only ever writes .fit; deliverable lands directly at the --out root.
        (ws.out_root / "M8_final.fit").write_text("x", encoding="utf-8")
        for ext in ("tif", "png", "jpg"):
            (ws.out_root / f"M8_final.{ext}").write_text("x", encoding="utf-8")
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    monkeypatch.setattr(fin, "run_siril", fake_run_siril)

    stages = build_finish_stages("dso-emission-nebula", ws, Config.default(), resolve_target("M8"),
                                 siril_exe="siril-cli")
    finish = next(s for s in stages if s.id == "finish")
    finish.run()

    assert (ws.out_root / "M8_final.fits").exists()
    assert not (ws.out_root / "M8_final.fit").exists()
    assert finish.produces()
