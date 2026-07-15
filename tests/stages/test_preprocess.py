from aporntool.stages.preprocess import (
    convert_and_calibrate_cmds, register_cmds, stack_cmds,
    needs_mirrorx, spcc_in_preprocess,
)


def test_convert_and_calibrate_merged():
    cmds = convert_and_calibrate_cmds()
    assert "link light -out=../01_process" in cmds
    assert "calibrate light -debayer" in cmds


def test_mosaic_assembly_register_uses_wcs_and_framing_max():
    # Assembly (not target type) drives registration: a mosaic plate-solves + reprojects.
    joined = " ".join(register_cmds("dso-galaxy", True))
    assert "seqplatesolve pp_light" in joined      # WCS assembly path
    assert "-framing=max" in joined


def test_single_panel_register_uses_2pass():
    # A single-panel capture (any type, incl. a single-panel galaxy) uses star-based 2-pass.
    for mode in ("dso-emission-nebula", "dso-galaxy"):
        joined = " ".join(register_cmds(mode, False))
        assert "register pp_light -2pass" in joined
        assert "-framing=max" not in joined


def test_star_cluster_adds_wfwhm_cull():
    joined = " ".join(register_cmds("dso-star-cluster", False))
    assert "-filter-round=2.5k" in joined and "-filter-wfwhm=2.5k" in joined


def test_mosaic_stack_has_feather_100():
    joined = " ".join(stack_cmds(True))
    assert "-feather=100" in joined and "-out=result" in joined


def test_single_panel_stack_has_no_feather():
    joined = " ".join(stack_cmds(False))
    assert "-feather" not in joined


def test_needs_mirrorx_only_for_single_panel():
    # Single-panel captures inherit the Seestar vertical flip → mirror; a mosaic gets orientation
    # from WCS → must NOT be flipped.
    assert needs_mirrorx(False) is True       # single panel
    assert needs_mirrorx(True) is False       # mosaic


def test_spcc_in_preprocess_flags():
    assert spcc_in_preprocess("dso-galaxy") is True
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


def test_galaxy_mosaic_stage_ids_and_order(tmp_path):
    # A galaxy captured as a MOSAIC: WCS assembly (no separate mirrorx stage), SPCC in preprocess.
    ws = Workspace(tmp_path, "M31"); ws.create()
    stages = build_preprocess_stages("dso-galaxy", ws, Config.default(),
                                     resolve_target("M31"), siril_exe="siril-cli", is_mosaic=True)
    assert [s.id for s in stages] == ["calibrate", "register", "stack", "spcc"]


def test_galaxy_single_panel_registers_2pass_and_mirrors(tmp_path):
    # A galaxy captured as a SINGLE panel (M51/M33/M101): 2-pass registration + mirrorx (done inside
    # the SPCC stage, since galaxies SPCC in preprocess), same stage IDs as the mosaic case.
    ws = Workspace(tmp_path, "M33"); ws.create()
    scripts = []
    stages = build_preprocess_stages("dso-galaxy", ws, Config.default(), resolve_target("M33"),
                                     siril_exe="siril-cli", is_mosaic=False,
                                     runner=_fake_runner_factory(scripts))
    assert [s.id for s in stages] == ["calibrate", "register", "stack", "spcc"]
    next(s for s in stages if s.id == "register").run()
    assert any("register pp_light -2pass" in s for s in scripts)   # NOT WCS seqplatesolve
    scripts.clear()
    next(s for s in stages if s.id == "spcc").run()
    assert any("mirrorx" in s and "M33_Linear" in s for s in scripts)  # single-panel flip + anchor


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
    stages = build_preprocess_stages("dso-galaxy", ws, cfg, resolve_target("M31"),
                                     siril_exe="siril-cli", runner=_fake_runner_factory(scripts))
    spcc = next(s for s in stages if s.id == "spcc")
    spcc.run()
    text = (ws.logs / "spcc.ssf").read_text(encoding="utf-8")
    assert "catalogue_gaia_astro=/g/astro.dat" in text
    assert '"-oscsensor=Sony IMX662"' in text and "platesolve 11.25,41.4" in text


def test_spcc_stage_surfaces_online_fallback_and_imprecise_notes(tmp_path, capsys):
    # When SPCC succeeds but SIRIL falls back to online Gaia or reports an imprecise fit, those
    # notices should reach the user's stdout, not just the per-stage log.
    ws = Workspace(tmp_path, "M31"); ws.create()

    def fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = ("Local Gaia catalog is unavailable, reverting to online Gaia catalog via ESA\n"
                      "The photometric color calibration seems to have found an imprecise solution\n"
                      "Spectrophotometric Color Calibration succeeded.")
            stderr = ""
        return R()

    stages = build_preprocess_stages("dso-galaxy", ws, Config.default(), resolve_target("M31"),
                                     siril_exe="siril-cli", runner=fake_run)
    next(s for s in stages if s.id == "spcc").run()
    out = capsys.readouterr().out.lower()
    assert "online esa gaia" in out            # local-unavailable fallback surfaced
    assert "imprecise color solution" in out    # imprecise-fit warning surfaced


def test_spcc_stage_quiet_when_no_warnings(tmp_path, capsys):
    # A clean SPCC run prints no notes.
    ws = Workspace(tmp_path, "M31"); ws.create()

    def fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = "Spectrophotometric Color Calibration succeeded."
            stderr = ""
        return R()

    stages = build_preprocess_stages("dso-galaxy", ws, Config.default(), resolve_target("M31"),
                                     siril_exe="siril-cli", runner=fake_run)
    next(s for s in stages if s.id == "spcc").run()
    out = capsys.readouterr().out.lower()
    assert "note:" not in out
