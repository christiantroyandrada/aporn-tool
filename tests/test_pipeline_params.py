"""Centralised pipeline params: (1) defaults are byte-identical to the historical literals, so no
config file == no behaviour change; (2) overrides actually flow through to the emitted commands;
(3) the file->load_config->cfg->command chain works end to end."""
import json
from dataclasses import asdict
from pathlib import Path

from aporntool.config import (
    Config, load_config, StackParams, MosaicFinishParams, EmissionFinishParams,
    ClusterFinishParams, ReflectionFinishParams, NoTripodParams,
)
from aporntool.stages.preprocess import register_cmds, stack_cmds, build_preprocess_stages
from aporntool.stages.finish_cmds import mosaic_finish_cmds, emission_finish_cmds, cluster_finish_cmds
from aporntool.stages.finish import build_finish_stages, _spcc_string
from aporntool.tools.siril import spcc_cmd
from aporntool.tools.graxpert import bge_cmd, denoise_cmd
from aporntool.workspace import Workspace
from aporntool.catalog import resolve_target


# ---- 1. defaults byte-identical (regression lock on the proven pipeline) ----

def test_stack_register_defaults_identical():
    assert stack_cmds(True) == [
        "stack r_pp_light rej 3 3 -norm=addscale -output_norm -rgb_equal -feather=100 -out=result"]
    assert stack_cmds(False) == [
        "stack r_pp_light rej 3 3 -norm=addscale -output_norm -rgb_equal -out=result"]
    assert register_cmds("dso-galaxy", True)[1] == "seqapplyreg pp_light -filter-round=2.5k -framing=max"
    assert register_cmds("dso-star-cluster", False)[1] == "seqapplyreg pp_light -filter-round=2.5k -filter-wfwhm=2.5k"
    assert register_cmds("dso-emission-nebula", False)[1] == "seqapplyreg pp_light -filter-round=2.5k"


def test_finish_defaults_identical():
    m = mosaic_finish_cmds("C", "O", star_reduce=0.5)
    assert m[1] == "autostretch -linked -2.8 0.15"
    assert m[2] == "ght -D=0.8 -B=3 -SP=0.15 -HP=0.85 -human"
    assert m[3] == "rmgreen 1"
    assert m[4] == "satu 0.7"
    assert m[9] == 'pm "$O_starless$+$starmask_O_stretched$*0.5"'
    assert emission_finish_cmds("A", "O", box=None, spcc="S")[1:3] == ["subsky 1", "platesolve -catalog=localgaia"]
    assert emission_finish_cmds("A", "O", box=None, spcc="S")[6] == "satu 0.7 0.1"
    c = cluster_finish_cmds("A", "O", box=None, spcc="S", solve="P")
    assert c[4] == "denoise -mod=0.5" and c[6] == "ght -D=0.7 -B=3 -HP=0.9 -human" and c[7] == "satu 0.6 0.1"


def test_graxpert_spcc_defaults_identical():
    assert bge_cmd("gx", "i", "o")[6:8] == ["-smoothing", "0.0"]
    assert bge_cmd("gx", "i", "o")[8:10] == ["-correction", "Subtraction"]
    assert denoise_cmd("gx", "i", "o")[6:8] == ["-strength", "0.8"]
    assert spcc_cmd() == ('spcc "-oscsensor=Sony IMX662" "-oscfilter=UV/IR Block" '
                          '"-whiteref=Average Spiral Galaxy" -catalog=localgaia')
    assert _spcc_string(Config.default()) == spcc_cmd()


# ---- 2. overrides flow through ----

def test_stack_register_overrides():
    sp = StackParams(sigma_low=2, sigma_high=4, feather_mosaic=80, filter_round="3k", filter_wfwhm="2k")
    assert stack_cmds(True, sp)[0] == (
        "stack r_pp_light rej 2 4 -norm=addscale -output_norm -rgb_equal -feather=80 -out=result")
    assert register_cmds("dso-galaxy", True, sp)[1] == "seqapplyreg pp_light -filter-round=3k -framing=max"
    assert register_cmds("dso-star-cluster", False, sp)[1] == "seqapplyreg pp_light -filter-round=3k -filter-wfwhm=2k"


def test_mosaic_finish_overrides():
    p = MosaicFinishParams(autostretch_clip=-3.0, autostretch_bg=0.2, ght_d=1.2, ght_b=2,
                           ght_sp=0.2, ght_hp=0.9, satu=0.9, star_reduce=0.3)
    m = mosaic_finish_cmds("C", "O", params=p)
    assert m[1] == "autostretch -linked -3 0.2"
    assert m[2] == "ght -D=1.2 -B=2 -SP=0.2 -HP=0.9 -human"
    assert m[4] == "satu 0.9"
    assert m[9] == 'pm "$O_starless$+$starmask_O_stretched$*0.3"'


def test_explicit_star_reduce_beats_config():
    m = mosaic_finish_cmds("C", "O", star_reduce=0.7, params=MosaicFinishParams(star_reduce=0.3))
    assert m[9].endswith('*0.7"')


def test_emission_cluster_overrides():
    e = emission_finish_cmds("A", "O", box=None, spcc="S",
                             params=EmissionFinishParams(satu=0.4, satu_bg=0.2))
    assert e[6] == "satu 0.4 0.2"
    c = cluster_finish_cmds("A", "O", box=None, spcc="S", solve="P",
                            params=ClusterFinishParams(denoise_mod=0.9, ght_d=0.6, ght_b=4,
                                                       ght_hp=0.8, satu=0.5, satu_bg=0.3))
    assert c[4] == "denoise -mod=0.9" and c[6] == "ght -D=0.6 -B=4 -HP=0.8 -human" and c[7] == "satu 0.5 0.3"


def test_graxpert_spcc_overrides():
    assert bge_cmd("gx", "i", "o", smoothing=0.3)[7] == "0.3"
    assert bge_cmd("gx", "i", "o", correction="Division")[9] == "Division"
    assert denoise_cmd("gx", "i", "o", strength=0.6)[7] == "0.6"
    assert 'X-CAM' in spcc_cmd(sensor="X-CAM")


def test_newly_centralized_param_overrides():
    m = mosaic_finish_cmds("C", "O", params=MosaicFinishParams(rmgreen=0.5), jpeg_quality=80)
    assert m[3] == "rmgreen 0.5" and m[-1] == "savejpg O 80"
    e = emission_finish_cmds("A", "O", box=None, spcc="S",
                             params=EmissionFinishParams(subsky_degree=3), catalog="mycat")
    assert e[1] == "subsky 3" and e[2] == "platesolve -catalog=mycat"


def test_reflection_params_mirror_defaults_no_drift():
    from aporntool.stages.reflection_finish import REFLECTION_DEFAULTS
    assert asdict(ReflectionFinishParams()) == REFLECTION_DEFAULTS


def test_no_tripod_params_default_and_overlay_from_file(tmp_path):
    # Default config carries a no_tripod block; a partial file overlays onto it without disturbing
    # the rest (same partial-overlay guarantee every other params block has).
    assert isinstance(Config.default().pipeline.no_tripod, NoTripodParams)
    cfgpath = tmp_path / "c.json"
    cfgpath.write_text(json.dumps({"pipeline": {"no_tripod": {"feather": 12.0, "fg_gain": 0.5}}}))
    cfg = load_config(cfgpath)
    assert cfg.pipeline.no_tripod.feather == 12.0
    assert cfg.pipeline.no_tripod.fg_gain == 0.5
    assert cfg.pipeline.no_tripod.barrier_pct == NoTripodParams().barrier_pct   # untouched default


def test_target_blocks_zero_is_floored_not_fatal(tmp_path):
    import numpy as np
    from astropy.io import fits
    from aporntool.stages.crop import auto_crop_box
    arr = np.zeros((3, 800, 800), np.float32); arr[:, 200:600, 200:600] = 0.5
    fp = tmp_path / "z.fits"; fits.writeto(str(fp), arr)
    auto_crop_box(fp, target_blocks=0)   # must not raise ZeroDivisionError


# ---- 3. end-to-end: a config file on disk changes the emitted SIRIL script ----

def _rec(scripts):
    def run(cmd, **kw):
        scripts.append(Path(cmd[cmd.index("-s") + 1]).read_text(encoding="utf-8"))
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    return run


def test_config_file_flows_into_emitted_commands(tmp_path, monkeypatch):
    cfgpath = tmp_path / "aporntool.config.json"
    json.dump({"pipeline": {"emission_finish": {"subsky_degree": 2},
                            "stack": {"sigma_low": 2, "sigma_high": 5}}}, open(cfgpath, "w"))
    cfg = load_config(cfgpath)

    ws = Workspace(tmp_path / "out", "M8"); ws.create()
    scripts = []
    pre = build_preprocess_stages("dso-emission-nebula", ws, cfg, resolve_target("M8"),
                                  siril_exe="siril-cli", runner=_rec(scripts))
    next(s for s in pre if s.id == "stack").run()
    assert any("rej 2 5" in s for s in scripts), scripts

    # Emission finish is now a SIRIL prep (config subsky degree flows here) + the numpy composite
    # dual-layer (stubbed); assert the config value reaches the emitted prep script.
    import aporntool.stages.finish as finmod
    monkeypatch.setattr(finmod, "run_composite_finish", lambda *a, **k: None)
    scripts.clear()
    fin = build_finish_stages("dso-emission-nebula", ws, cfg, resolve_target("M8"),
                              siril_exe="siril-cli", starnet_exe="starnet2", crop=None, runner=_rec(scripts))
    next(s for s in fin if s.id == "finish").run()
    assert any("subsky 2" in s for s in scripts), scripts
