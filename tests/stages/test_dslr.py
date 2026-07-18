"""DSLR DSO preprocess: master-frame builders, calibration-aware calibrate, and stage assembly."""
from pathlib import Path

from aporntool.workspace import Workspace
from aporntool.config import Config
from aporntool.catalog import resolve_target
from aporntool.stages.preprocess import (
    convert_and_calibrate_cmds, calibrate_light_cmds,
    master_bias_cmds, master_dark_cmds, master_flat_cmds, build_preprocess_stages,
)


def _rec(scripts):
    def run(cmd, **kw):
        try:
            script = Path(cmd[cmd.index("-s") + 1])
            scripts.append(script.read_text(encoding="utf-8"))
        except (ValueError, IndexError):
            pass
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    return run


# --- command builders --------------------------------------------------------

def test_calibrate_light_fits_no_masters_is_byte_identical_to_seestar():
    # The whole DSLR generalisation must NOT change the Seestar path: kind=fits, debayer, no masters.
    assert calibrate_light_cmds("fits", True) == convert_and_calibrate_cmds()


def test_calibrate_light_raw_full_calibration():
    cmds = calibrate_light_cmds("raw", True, bias=True, dark=True, flat=True)
    assert cmds[0] == "convert light -out=../01_process"      # raw → convert, not link
    joined = cmds[-1]
    assert joined.startswith("calibrate light")
    assert "-bias=master_bias" in joined and "-dark=master_dark" in joined
    assert "-cc=dark" in joined and "-flat=master_flat" in joined and "-debayer" in joined


def test_calibrate_light_jpeg_skips_debayer():
    cmds = calibrate_light_cmds("jpeg", False)
    assert cmds[0] == "convert light -out=../01_process"
    assert "-debayer" not in cmds[-1]                          # already RGB


def test_master_bias_and_dark_are_nonorm_stacks():
    assert master_bias_cmds("raw")[0] == "convert bias -out=../01_process"
    assert "stack bias rej 3 3 -nonorm -out=master_bias" in master_bias_cmds("raw")
    assert "stack dark rej 3 3 -nonorm -out=master_dark" in master_dark_cmds("raw")
    # FITS calibration frames link instead of convert
    assert master_dark_cmds("fits")[0] == "link dark -out=../01_process"


def test_master_flat_uses_bias_then_mul_norm():
    with_bias = master_flat_cmds("raw", bias=True)
    assert "calibrate flat -bias=master_bias" in with_bias
    assert "stack pp_flat rej 3 3 -norm=mul -out=master_flat" in with_bias
    no_bias = master_flat_cmds("raw", bias=False)
    assert not any("calibrate flat" in c for c in no_bias)
    assert "stack flat rej 3 3 -norm=mul -out=master_flat" in no_bias


# --- stage assembly ----------------------------------------------------------

def test_dslr_galaxy_full_calibration_stage_ids(tmp_path):
    # RAW galaxy with darks/flats/bias: masters stage prepended, SPCC finish (no mirrorx flip).
    ws = Workspace(tmp_path, "M31"); ws.create()
    stages = build_preprocess_stages("dso-galaxy", ws, Config.default(), resolve_target("M31"),
                                     siril_exe="siril-cli", light_kind="raw", light_debayer=True,
                                     cal={"bias": "raw", "dark": "raw", "flat": "raw"})
    assert [s.id for s in stages] == ["masters", "calibrate", "register", "stack", "spcc"]


def test_dslr_galaxy_no_mirror_in_spcc(tmp_path):
    # A DSLR frame is not vertically flipped, so the SPCC stage must NOT emit mirrorx.
    ws = Workspace(tmp_path, "M31"); ws.create()
    scripts = []
    stages = build_preprocess_stages("dso-galaxy", ws, Config.default(), resolve_target("M31"),
                                     siril_exe="siril-cli", light_kind="raw", light_debayer=True,
                                     cal={"dark": "raw"}, runner=_rec(scripts))
    next(s for s in stages if s.id == "spcc").run()
    text = (ws.logs / "spcc.ssf").read_text(encoding="utf-8")
    assert "mirrorx" not in text


def test_dslr_emission_saves_anchor_not_mirrorx(tmp_path):
    # DSLR emission: no SPCC in preprocess AND no flip → a plain anchor-save stage (not mirrorx).
    ws = Workspace(tmp_path, "M8"); ws.create()
    stages = build_preprocess_stages("dso-emission-nebula", ws, Config.default(), resolve_target("M8"),
                                     siril_exe="siril-cli", light_kind="raw", light_debayer=True,
                                     cal={"dark": "raw"})
    ids = [s.id for s in stages]
    assert ids == ["masters", "calibrate", "register", "stack", "anchor"]
    assert "mirrorx" not in ids


def test_seestar_emission_still_uses_mirrorx(tmp_path):
    # Regression: the Seestar (fits) emission path is unchanged — mirrorx flip, no masters.
    ws = Workspace(tmp_path, "M8"); ws.create()
    stages = build_preprocess_stages("dso-emission-nebula", ws, Config.default(), resolve_target("M8"),
                                     siril_exe="siril-cli")
    assert [s.id for s in stages] == ["calibrate", "register", "stack", "mirrorx"]


def test_dslr_no_calibration_frames_skips_masters(tmp_path):
    # RAW lights but no darks/flats/bias: no masters stage, but still convert (not link) + debayer.
    ws = Workspace(tmp_path, "M31"); ws.create()
    scripts = []
    stages = build_preprocess_stages("dso-galaxy", ws, Config.default(), resolve_target("M31"),
                                     siril_exe="siril-cli", light_kind="raw", light_debayer=True,
                                     cal={}, runner=_rec(scripts))
    assert [s.id for s in stages] == ["calibrate", "register", "stack", "spcc"]
    next(s for s in stages if s.id == "calibrate").run()
    text = (ws.logs / "calibrate.ssf").read_text(encoding="utf-8")
    assert "convert light -out=../01_process" in text and "-debayer" in text


def test_dslr_focal_pixel_override_reaches_platesolve(tmp_path):
    # --focal/--pixel must actually reach the SPCC plate solve (else DSLR SPCC solves with Seestar
    # optics and fails). Regression guard for the `focal or cfg.seestar_focal_mm` wiring.
    ws = Workspace(tmp_path, "M31"); ws.create()
    scripts = []
    stages = build_preprocess_stages("dso-galaxy", ws, Config.default(), resolve_target("M31"),
                                     siril_exe="siril-cli", light_kind="raw", light_debayer=True,
                                     cal={"dark": "raw"}, focal=530.0, pixel=3.76, runner=_rec(scripts))
    next(s for s in stages if s.id == "spcc").run()
    text = (ws.logs / "spcc.ssf").read_text(encoding="utf-8")
    assert "-focal=530" in text and "-pixelsize=3.76" in text


def test_fits_lights_with_calibration_uses_link_masters(tmp_path):
    # A cooled astro-camera (FITS) run WITH darks must still calibrate; FITS masters `link`, not convert.
    ws = Workspace(tmp_path, "M31"); ws.create()
    scripts = []
    stages = build_preprocess_stages("dso-galaxy", ws, Config.default(), resolve_target("M31"),
                                     siril_exe="siril-cli", light_kind="fits", light_debayer=True,
                                     cal={"dark": "fits"}, runner=_rec(scripts))
    assert [s.id for s in stages] == ["masters", "calibrate", "register", "stack", "spcc"]
    next(s for s in stages if s.id == "masters").run()
    assert any("link dark -out=../01_process" in s for s in scripts)   # FITS → link


def test_mixed_format_calibration_uses_each_sets_verb(tmp_path):
    # FITS lights but raw flats: the flat master must CONVERT (raw), independent of the lights' format.
    ws = Workspace(tmp_path, "M31"); ws.create()
    scripts = []
    stages = build_preprocess_stages("dso-galaxy", ws, Config.default(), resolve_target("M31"),
                                     siril_exe="siril-cli", light_kind="fits", light_debayer=True,
                                     cal={"flat": "raw"}, runner=_rec(scripts))
    next(s for s in stages if s.id == "masters").run()
    assert any("convert flat -out=../01_process" in s for s in scripts)   # raw flat → convert


def test_dslr_masters_stage_builds_provided_masters(tmp_path):
    ws = Workspace(tmp_path, "M31"); ws.create()
    scripts = []
    stages = build_preprocess_stages("dso-galaxy", ws, Config.default(), resolve_target("M31"),
                                     siril_exe="siril-cli", light_kind="raw", light_debayer=True,
                                     cal={"bias": "raw", "dark": "raw", "flat": "raw"}, runner=_rec(scripts))
    next(s for s in stages if s.id == "masters").run()
    text = "".join(scripts)
    assert "-out=master_bias" in text and "-out=master_dark" in text and "-out=master_flat" in text
    assert "calibrate flat -bias=master_bias" in text     # flat bias-subtracted before stacking
