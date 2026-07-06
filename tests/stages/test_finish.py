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
