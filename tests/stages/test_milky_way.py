"""dso-milky-way: wide-field preprocess + finish stage assembly and SIRIL command content."""
from pathlib import Path

import numpy as np
from astropy.io import fits

from aporntool.workspace import Workspace
from aporntool.config import Config
from aporntool.detect import resolve_target_wide
from aporntool.stages.preprocess import convert_cmds, build_preprocess_stages
from aporntool.stages.finish import build_finish_stages
from aporntool.stages.finish_cmds import milkyway_finish_cmds


def _rec(scripts):
    # SIRIL fake: record the .ssf text each stage runs; never launches real SIRIL.
    def run(cmd, **kw):
        try:
            script = Path(cmd[cmd.index("-s") + 1])
            scripts.append(script.read_text(encoding="utf-8"))
        except (ValueError, IndexError):
            pass
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    return run


def _write_bordered_fits(path):
    arr = np.zeros((3, 100, 100), np.float32)
    arr[:, 20:80, 20:80] = 0.5
    fits.writeto(str(path), arr, overwrite=True)


# --- convert (no calibrate) --------------------------------------------------

def test_convert_cmds_transcodes_to_pp_light_without_calibrate():
    cmds = convert_cmds()
    joined = " ".join(cmds)
    assert "convert pp_light -out=../01_process" in joined
    assert "calibrate" not in joined      # phone stills are already debayered — nothing to calibrate
    assert "debayer" not in joined


# --- preprocess stage assembly ----------------------------------------------

def test_milky_way_preprocess_stage_ids(tmp_path):
    # Wide-field: register (convert+register merged, no calibrate) -> stack -> anchor (no mirrorx/spcc).
    ws = Workspace(tmp_path, "MilkyWay"); ws.create()
    stages = build_preprocess_stages("dso-milky-way", ws, Config.default(),
                                     resolve_target_wide(None), siril_exe="siril-cli")
    assert [s.id for s in stages] == ["register", "stack", "anchor"]


def test_milky_way_register_stage_merges_convert_no_calibrate(tmp_path):
    # `convert -out=` doesn't persist a .seq, so convert must share the register session (mirrors
    # how calibrate absorbs `link`). One SIRIL script: convert -> cd -> register -> seqapplyreg.
    ws = Workspace(tmp_path, "MilkyWay"); ws.create()
    scripts = []
    stages = build_preprocess_stages("dso-milky-way", ws, Config.default(),
                                     resolve_target_wide(None), siril_exe="siril-cli",
                                     runner=_rec(scripts))
    next(s for s in stages if s.id == "register").run()
    text = "".join(scripts)
    assert "convert pp_light -out=../01_process" in text
    assert "cd ../01_process" in text
    assert "register pp_light" in text
    assert "calibrate" not in text          # phone stills are already debayered


def test_milky_way_register_is_single_pass_no_roundness_cull(tmp_path):
    # Single-pass global registration: no WCS solve, no -2pass, and crucially NO -filter-round cull
    # (which can drop the reference frame and abort seqapplyreg on variable phone data).
    ws = Workspace(tmp_path, "MilkyWay"); ws.create()
    scripts = []
    stages = build_preprocess_stages("dso-milky-way", ws, Config.default(),
                                     resolve_target_wide(None), siril_exe="siril-cli",
                                     runner=_rec(scripts))
    next(s for s in stages if s.id == "register").run()
    text = "".join(scripts)
    assert "register pp_light" in text
    assert "seqplatesolve" not in text
    assert "-2pass" not in text
    assert "filter-round" not in text and "seqapplyreg" not in text


def test_milky_way_anchor_stage_saves_without_mirror_or_spcc(tmp_path):
    # A phone/camera is not mirrored (unlike the Seestar) and there's no plate solve → the anchor
    # stage just saves the stacked result. Regression guard: no mirrorx, no spcc, no platesolve.
    ws = Workspace(tmp_path, "MilkyWay"); ws.create()
    scripts = []
    stages = build_preprocess_stages("dso-milky-way", ws, Config.default(),
                                     resolve_target_wide(None), siril_exe="siril-cli",
                                     runner=_rec(scripts))
    next(s for s in stages if s.id == "anchor").run()
    text = "".join(scripts)
    assert "load result" in text and "MilkyWay_Linear" in text
    assert "mirrorx" not in text
    assert "spcc" not in text and "platesolve" not in text


# --- finish stage assembly ---------------------------------------------------

def test_milky_way_finish_stage_ids(tmp_path):
    ws = Workspace(tmp_path, "MilkyWay"); ws.create()
    stages = build_finish_stages("dso-milky-way", ws, Config.default(), resolve_target_wide(None),
                                 siril_exe="siril-cli", graxpert_exe="GraXpert")
    assert [s.id for s in stages] == ["bge", "denoise", "finish"]


def test_milky_way_bge_uses_high_smoothing_to_protect_the_band(tmp_path, monkeypatch):
    # GraXpert BGE on a wide MW must run with the milkyway_finish smoothing (high by default), or it
    # subtracts the Milky Way itself as "background". Capture the bge command GraXpert is handed.
    import aporntool.stages.finish as fin
    captured = {}

    def fake_bge_cmd(exe, src, out, *, gpu=True, smoothing=None, correction=None):
        captured["smoothing"] = smoothing
        captured["correction"] = correction
        return ["graxpert", "stub"]

    monkeypatch.setattr(fin, "bge_cmd", fake_bge_cmd)
    monkeypatch.setattr(fin, "run_graxpert", lambda *a, **k: None)
    ws = Workspace(tmp_path, "MilkyWay"); ws.create()
    _write_bordered_fits(ws.linear / "MilkyWay_Linear.fit")
    cfg = Config.default()
    stages = build_finish_stages("dso-milky-way", ws, cfg, resolve_target_wide(None),
                                 siril_exe="siril-cli", graxpert_exe="GraXpert",
                                 crop=None, runner=_rec([]))
    next(s for s in stages if s.id == "bge").run()
    assert captured["smoothing"] == cfg.pipeline.milkyway_finish.bge_smoothing
    assert captured["smoothing"] >= 1.0     # high on purpose


def test_milky_way_finish_stretches_and_saves_no_starnet(tmp_path, monkeypatch):
    import aporntool.stages.finish as fin
    monkeypatch.setattr(fin, "run_graxpert", lambda *a, **k: None)
    ws = Workspace(tmp_path, "MilkyWay"); ws.create()
    _write_bordered_fits(ws.linear / "MilkyWay_Linear.fit")
    scripts = []
    stages = build_finish_stages("dso-milky-way", ws, Config.default(), resolve_target_wide(None),
                                 siril_exe="siril-cli", graxpert_exe="GraXpert",
                                 crop=None, runner=_rec(scripts))
    next(s for s in stages if s.id == "finish").run()
    text = (ws.logs / "finish.ssf").read_text(encoding="utf-8")
    assert "load" in text and "MilkyWay_clean.fits" in text
    assert "autostretch -linked" in text
    assert "rmgreen" in text and "satu" in text
    assert "savetif" in text and "savepng" in text and "savejpg" in text
    assert "starnet" not in text            # stars are the subject — never removed


# --- finish command builder --------------------------------------------------

def test_milkyway_finish_cmds_shape():
    cmds = milkyway_finish_cmds("clean.fits", "out", jpeg_quality=90)
    assert cmds[0] == "load clean.fits"
    joined = " ".join(cmds)
    assert "autostretch -linked -2.5 0.2" in joined      # config defaults, _g-formatted
    assert "savejpg out 90" in joined
    assert "starnet" not in joined
