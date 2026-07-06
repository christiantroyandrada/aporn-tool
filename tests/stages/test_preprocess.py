from aporntool.stages.preprocess import (
    convert_and_calibrate_cmds, register_cmds, stack_cmds, mirrorx_cmds,
    is_single_panel, spcc_in_preprocess,
)


def test_convert_and_calibrate_merged():
    cmds = convert_and_calibrate_cmds()
    assert "link light -out=../01_process" in cmds
    assert "calibrate light -debayer" in cmds


def test_mosaic_register_uses_wcs_and_framing_max():
    cmds = register_cmds("dso-mosaic")
    joined = " ".join(cmds)
    assert "seqplatesolve pp_light" in joined      # WCS assembly path
    assert "-framing=max" in joined


def test_single_panel_register_uses_2pass():
    cmds = register_cmds("dso-emission-nebula")
    joined = " ".join(cmds)
    assert "register pp_light -2pass" in joined
    assert "-framing=max" not in joined


def test_star_cluster_adds_wfwhm_cull():
    joined = " ".join(register_cmds("dso-star-cluster"))
    assert "-filter-round=2.5k" in joined and "-filter-wfwhm=2.5k" in joined


def test_mosaic_stack_has_feather_100():
    joined = " ".join(stack_cmds("dso-mosaic"))
    assert "-feather=100" in joined and "-out=result" in joined


def test_single_panel_stack_has_no_feather():
    joined = " ".join(stack_cmds("dso-emission-nebula"))
    assert "-feather" not in joined


def test_mirrorx_only_single_panel():
    assert is_single_panel("dso-emission-nebula") is True
    assert is_single_panel("dso-mosaic") is False
    assert mirrorx_cmds() == ["mirrorx_single result"]


def test_spcc_in_preprocess_flags():
    assert spcc_in_preprocess("dso-mosaic") is True
    assert spcc_in_preprocess("dso-reflection-nebula") is True
    assert spcc_in_preprocess("dso-emission-nebula") is False   # emission SPCCs in finish
    assert spcc_in_preprocess("dso-star-cluster") is False


from pathlib import Path
from aporntool.workspace import Workspace
from aporntool.config import Config
from aporntool.catalog import resolve_target
from aporntool.stages.preprocess import build_preprocess_stages


def _fake_runner_factory(record):
    # A stand-in for siril-cli: records the script it "ran" and simulates the output file
    # the real SIRIL would have produced, so Stage.produces() passes.
    def run(cmd, **kw):
        script = Path(cmd[cmd.index("-s") + 1])
        record.append(script.read_text(encoding="utf-8"))
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    return run


def test_mosaic_stage_ids_and_order(tmp_path):
    ws = Workspace(tmp_path, "M31"); ws.create()
    stages = build_preprocess_stages("dso-mosaic", ws, Config.default(),
                                     resolve_target("M31"), siril_exe="siril-cli")
    assert [s.id for s in stages] == ["calibrate", "register", "stack", "spcc"]


def test_emission_stage_ids_include_mirrorx_and_no_spcc(tmp_path):
    ws = Workspace(tmp_path, "M8"); ws.create()
    stages = build_preprocess_stages("dso-emission-nebula", ws, Config.default(),
                                     resolve_target("M8"), siril_exe="siril-cli")
    assert [s.id for s in stages] == ["calibrate", "register", "stack", "mirrorx"]


def test_emission_mirrorx_stage_saves_golden_anchor(tmp_path):
    ws = Workspace(tmp_path, "M8"); ws.create()
    scripts = []
    stages = build_preprocess_stages("dso-emission-nebula", ws, Config.default(),
                                     resolve_target("M8"), siril_exe="siril-cli",
                                     runner=_fake_runner_factory(scripts))
    mirrorx = next(s for s in stages if s.id == "mirrorx")
    mirrorx.run()
    # emission's mirrorx is the LAST preprocess stage → its .ssf mirrors AND saves <TARGET>_Linear.
    assert any("mirrorx_single result" in s and "M8_Linear" in s for s in scripts)
    assert (ws.logs / "mirrorx.ssf").exists()


def test_spcc_stage_uses_local_gaia_paths_when_configured(tmp_path):
    ws = Workspace(tmp_path, "M31"); ws.create()
    cfg = Config.default()
    cfg.catalog_astro = "/g/astro.dat"; cfg.catalog_photo = "/g/xpsamp"
    scripts = []
    stages = build_preprocess_stages("dso-mosaic", ws, cfg, resolve_target("M31"),
                                     siril_exe="siril-cli", runner=_fake_runner_factory(scripts))
    spcc = next(s for s in stages if s.id == "spcc")
    spcc.run()
    text = (ws.logs / "spcc.ssf").read_text(encoding="utf-8")
    assert "catalogue_gaia_astro=/g/astro.dat" in text
    assert '"-oscsensor=Sony IMX662"' in text and "platesolve 11.25,41.4" in text
