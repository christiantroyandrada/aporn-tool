from pathlib import Path
import numpy as np
from astropy.io import fits
from aporntool.workspace import Workspace
from aporntool.config import Config
from aporntool.catalog import resolve_target
from aporntool.stages.finish import build_finish_stages


def _write_bordered_fits(path):
    # 100x100 frame, signal only in the central 60x60 → auto-crop has something to trim.
    arr = np.zeros((3, 100, 100), np.float32)
    arr[:, 20:80, 20:80] = 0.5
    fits.writeto(str(path), arr, overwrite=True)


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


def _capture_composite(calls, fabricate_out=False):
    # Stand in for run_composite_finish: record how the finish stage called it (mode, paths,
    # star strength, scratch dir) and optionally fabricate the four deliverables so produces() passes.
    def fake(clean_fits, out_stem, *, mode, starnet_exe, runner=None, scratch_dir=None,
             params=None, star_strength=None, jpeg_quality=95):
        calls.append(dict(clean=str(clean_fits), out=str(out_stem), mode=mode,
                          star_strength=star_strength, scratch_dir=str(scratch_dir)))
        if fabricate_out:
            for ext in ("fits", "tif", "png", "jpg"):
                p = Path(f"{out_stem}.{ext}")
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("x", encoding="utf-8")
    return fake


def test_mosaic_finish_stage_ids(tmp_path):
    ws = Workspace(tmp_path, "M31"); ws.create()
    stages = build_finish_stages("dso-galaxy", ws, Config.default(), resolve_target("M31"),
                                 siril_exe="siril-cli", graxpert_exe="GraXpert.exe")
    assert [s.id for s in stages] == ["bge", "denoise", "finish"]


def test_emission_finish_is_single_stage(tmp_path):
    ws = Workspace(tmp_path, "M8"); ws.create()
    stages = build_finish_stages("dso-emission-nebula", ws, Config.default(), resolve_target("M8"),
                                 siril_exe="siril-cli")
    assert [s.id for s in stages] == ["finish"]


def test_emission_finish_preps_spcc_then_runs_composite(tmp_path, monkeypatch):
    # Emission now: a SIRIL prep (crop/subsky/SPCC/denoise -> _clean.fit) THEN the composite
    # dual-layer finish. The prep ssf carries the SPCC; deliverables come from the composite.
    import aporntool.stages.finish as fin
    ws = Workspace(tmp_path, "M8"); ws.create()
    calls = []
    monkeypatch.setattr(fin, "run_composite_finish", _capture_composite(calls))
    stages = build_finish_stages("dso-emission-nebula", ws, Config.default(), resolve_target("M8"),
                                 siril_exe="siril-cli", starnet_exe="starnet2", runner=_rec([]))
    next(s for s in stages if s.id == "finish").run()
    prep = (ws.logs / "finish.ssf").read_text(encoding="utf-8")
    assert 'spcc "-oscsensor=Sony IMX662"' in prep and "subsky 1" in prep
    assert "denoise" in prep and "M8_clean" in prep
    assert calls and calls[0]["mode"] == "dso-emission-nebula"
    assert calls[0]["out"].endswith("M8_final")
    assert str(ws.finish) in calls[0]["scratch_dir"]     # StarNet scratch stays under _work (FR-4)


def test_reflection_finish_stage_ids(tmp_path):
    ws = Workspace(tmp_path, "M78"); ws.create()
    stages = build_finish_stages("dso-reflection-nebula", ws, Config.default(),
                                 resolve_target("M78", coords="0,0"),
                                 siril_exe="siril-cli", graxpert_exe="GraXpert.exe", starnet_exe="starnet2")
    assert [s.id for s in stages] == ["bge", "denoise", "finish"]


def test_mosaic_finish_runs_composite_on_graxpert_clean(tmp_path, monkeypatch):
    # Mosaic finish is now the composite dual-layer on the GraXpert _clean.fits (not a SIRIL
    # stretch/starnet/pm script). Deliverables come from the composite.
    import aporntool.stages.finish as fin
    ws = Workspace(tmp_path, "M31"); ws.create()
    calls = []
    monkeypatch.setattr(fin, "run_composite_finish", _capture_composite(calls, fabricate_out=True))
    stages = build_finish_stages("dso-galaxy", ws, Config.default(), resolve_target("M31"),
                                 siril_exe="siril-cli", graxpert_exe="GraXpert.exe", starnet_exe="starnet2")
    finish = next(s for s in stages if s.id == "finish")
    finish.run()

    assert calls and calls[0]["mode"] == "dso-galaxy"
    assert "M31_clean" in calls[0]["clean"]                # loads the GraXpert-cleaned linear
    assert str(ws.finish) in calls[0]["scratch_dir"]       # StarNet scratch stays under _work (FR-4)
    assert calls[0]["star_strength"] == 0.5                # mosaic reduces stars to config default
    for ext in ("fits", "tif", "png", "jpg"):
        assert (ws.out_root / f"M31_final.{ext}").exists(), f"missing {ext}"
    assert finish.produces()


def test_emission_finish_produces_deliverables_via_composite(tmp_path, monkeypatch):
    # The composite writes the four deliverables directly at the --out root (no .fit->.fits rename).
    import aporntool.stages.finish as fin
    ws = Workspace(tmp_path, "M8"); ws.create()
    monkeypatch.setattr(fin, "run_composite_finish", _capture_composite([], fabricate_out=True))
    stages = build_finish_stages("dso-emission-nebula", ws, Config.default(), resolve_target("M8"),
                                 siril_exe="siril-cli", starnet_exe="starnet2", runner=_rec([]))
    finish = next(s for s in stages if s.id == "finish")
    finish.run()
    for ext in ("fits", "tif", "png", "jpg"):
        assert (ws.out_root / f"M8_final.{ext}").exists()
    assert finish.produces()


def test_mosaic_bge_stage_auto_crop_emits_crop_command(tmp_path, monkeypatch):
    # crop="auto" (the default) must be resolved against the real anchor .fit at stage RUN time
    # (not at build_finish_stages call time, before the anchor exists).
    import aporntool.stages.finish as fin
    # This test only cares about the SIRIL crop .ssf the bge stage writes; stub GraXpert so the
    # stage doesn't invoke the real run_graxpert, which would poll ~600s for an output file the
    # fake SIRIL runner never creates.
    monkeypatch.setattr(fin, "run_graxpert", lambda *a, **k: None)
    ws = Workspace(tmp_path, "M31"); ws.create()
    anchor = ws.linear / "M31_Linear.fit"
    _write_bordered_fits(anchor)

    scripts = []
    stages = build_finish_stages("dso-galaxy", ws, Config.default(), resolve_target("M31"),
                                 siril_exe="siril-cli", graxpert_exe="GraXpert.exe",
                                 crop="auto", runner=_rec(scripts))
    bge = next(s for s in stages if s.id == "bge")
    bge.run()
    text = (ws.logs / "crop.ssf").read_text(encoding="utf-8")
    assert "crop " in text


def test_mosaic_bge_stage_no_crop_skips_crop_command(tmp_path, monkeypatch):
    import aporntool.stages.finish as fin
    monkeypatch.setattr(fin, "run_graxpert", lambda *a, **k: None)  # see auto-crop test above
    ws = Workspace(tmp_path, "M31"); ws.create()
    anchor = ws.linear / "M31_Linear.fit"
    _write_bordered_fits(anchor)

    scripts = []
    stages = build_finish_stages("dso-galaxy", ws, Config.default(), resolve_target("M31"),
                                 siril_exe="siril-cli", graxpert_exe="GraXpert.exe",
                                 crop=None, runner=_rec(scripts))
    bge = next(s for s in stages if s.id == "bge")
    bge.run()
    text = (ws.logs / "crop.ssf").read_text(encoding="utf-8")
    assert "crop " not in text


def test_emission_finish_auto_crop_emits_crop_command(tmp_path, monkeypatch):
    import aporntool.stages.finish as fin
    monkeypatch.setattr(fin, "run_composite_finish", _capture_composite([]))   # stub the numpy finish
    ws = Workspace(tmp_path, "M8"); ws.create()
    anchor = ws.linear / "M8_Linear.fit"
    _write_bordered_fits(anchor)

    stages = build_finish_stages("dso-emission-nebula", ws, Config.default(), resolve_target("M8"),
                                 siril_exe="siril-cli", starnet_exe="starnet2", crop="auto", runner=_rec([]))
    finish = next(s for s in stages if s.id == "finish")
    finish.run()
    text = (ws.logs / "finish.ssf").read_text(encoding="utf-8")
    assert "crop " in text     # crop is in the SIRIL prep script


def test_emission_finish_platesolve_is_seeded(tmp_path, monkeypatch):
    # The finish plate solve must be SEEDED with the target coords + optics (a blind solve fails on
    # DSLR/stacked frames). Regression guard for the emission/cluster finish SPCC fix.
    import aporntool.stages.finish as fin
    monkeypatch.setattr(fin, "run_composite_finish", _capture_composite([]))
    ws = Workspace(tmp_path, "M8"); ws.create()
    _write_bordered_fits(ws.linear / "M8_Linear.fit")
    stages = build_finish_stages("dso-emission-nebula", ws, Config.default(), resolve_target("M8"),
                                 siril_exe="siril-cli", starnet_exe="starnet2", crop=None,
                                 focal=300, pixel=4.29, runner=_rec([]))
    next(s for s in stages if s.id == "finish").run()
    text = (ws.logs / "finish.ssf").read_text(encoding="utf-8")
    assert "platesolve 271.43,-24.41" in text          # M8 catalog coords -> seeded, not blind
    assert "-focal=300" in text and "-pixelsize=4.29" in text


def test_emission_finish_falls_back_without_spcc_when_solve_fails(tmp_path, monkeypatch):
    # If the plate solve can't lock, the prep produces no _clean.fit -> the finish must retry WITHOUT
    # platesolve/SPCC (a no-SPCC prep) so it still delivers, rather than aborting the whole run.
    import aporntool.stages.finish as fin
    monkeypatch.setattr(fin, "run_composite_finish", _capture_composite([]))
    ws = Workspace(tmp_path, "M8"); ws.create()
    _write_bordered_fits(ws.linear / "M8_Linear.fit")
    stages = build_finish_stages("dso-emission-nebula", ws, Config.default(), resolve_target("M8"),
                                 siril_exe="siril-cli", starnet_exe="starnet2", crop=None, runner=_rec([]))
    next(s for s in stages if s.id == "finish").run()
    # The fake runner never writes _clean.fit, so the fallback fires and writes a no-SPCC prep.
    first = (ws.logs / "finish.ssf").read_text(encoding="utf-8")
    fallback = (ws.logs / "finish_nospcc.ssf").read_text(encoding="utf-8")
    assert "platesolve" in first                        # first attempt tries to solve
    assert "platesolve" not in fallback and "spcc" not in fallback   # fallback skips SPCC
    assert "denoise" in fallback and "M8_clean" in fallback


def test_reflection_finish_stage_does_not_recrop(tmp_path, monkeypatch):
    # Cropping happens once, in the bge stage (SIRIL) before GraXpert. The reflection finish must
    # NOT crop again — an explicit --crop box re-applied to the already-cropped frame would be
    # wrong. Regression: the finish stage passes NO crop argument to run_reflection_finish.
    import aporntool.stages.finish as fin
    captured = {}

    def fake_reflection_finish(clean_fits, out_stem, *, starnet_exe, runner=None,
                               scratch_dir=None, **kwargs):
        captured["called"] = True
        captured["kwargs"] = kwargs

    monkeypatch.setattr(fin, "run_reflection_finish", fake_reflection_finish)
    ws = Workspace(tmp_path, "M78"); ws.create()
    stages = build_finish_stages("dso-reflection-nebula", ws, Config.default(),
                                 resolve_target("M78", coords="0,0"),
                                 siril_exe="siril-cli", graxpert_exe="GraXpert.exe",
                                 starnet_exe="starnet2", crop="100 100 200 200")
    finish = next(s for s in stages if s.id == "finish")
    finish.run()
    assert captured.get("called") and "crop" not in captured["kwargs"]
