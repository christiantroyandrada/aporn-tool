"""Assemble per-mode finish stages: golden anchor → deliverables at the --out root."""
import subprocess
from pathlib import Path

from aporntool.stages.engine import Stage
from aporntool.tools.siril import build_ssf, write_ssf, run_siril, spcc_cmd, gaia_catalog_cmds
from aporntool.tools.graxpert import bge_cmd, denoise_cmd, run_graxpert
from aporntool.stages.finish_cmds import (
    mosaic_finish_cmds, emission_finish_cmds, cluster_finish_cmds,
)
from aporntool.stages.preprocess import spcc_in_preprocess


def _nonzero(p) -> bool:
    p = Path(p)
    return p.exists() and p.stat().st_size > 0


def build_finish_stages(mode, ws, cfg, target, *, siril_exe, graxpert_exe=None,
                        crop=None, star_reduce=0.5, runner=None):
    runner = runner or subprocess.run
    anchor = ws.linear / f"{ws.target}_Linear"          # SIRIL load name (no .fit)
    out_name = str((ws.out_root / f"{ws.target}_final").as_posix())
    stages = []

    def _siril(stage_id, commands, cd):
        text = build_ssf(commands, cd=cd)
        script = write_ssf(text, ws.logs / f"{stage_id}.ssf")
        run_siril(script, workdir=ws.work, siril_exe=siril_exe, runner=runner,
                  log_path=ws.logs / f"{stage_id}.log")

    spcc = _spcc_string(cfg)

    if mode == "dso-mosaic":
        cropped = ws.linear / f"{ws.target}_cropped"
        bge_out = ws.graxpert / f"{ws.target}_bge"
        clean = ws.graxpert / f"{ws.target}_clean"
        # bge: crop (SIRIL) then GraXpert BGE on the cropped linear.
        def _bge():
            _siril("crop", [f"load {anchor.as_posix()}",
                            *( [f"crop {crop}"] if crop else [] ),
                            f"save {cropped.as_posix()}", "close"], cd=str(ws.linear))
            run_graxpert(bge_cmd(graxpert_exe, f"{cropped.as_posix()}.fit",
                                 str(bge_out), gpu=True), bge_out, runner=runner, settle=3.0)
        stages.append(Stage("bge", _bge, lambda: _nonzero(f"{bge_out}.fits")))

        def _denoise():
            run_graxpert(denoise_cmd(graxpert_exe, f"{bge_out}.fits", str(clean),
                                     gpu=True, strength=0.8), clean, runner=runner, settle=3.0)
        stages.append(Stage("denoise", _denoise, lambda: _nonzero(f"{clean}.fits")))

        def _finish():
            _siril("finish", mosaic_finish_cmds(clean.as_posix(), out_name,
                                                star_reduce=star_reduce), cd=str(ws.graxpert))
        stages.append(Stage("finish", _finish, lambda: _nonzero(out_name + ".tif")))

    elif mode in ("dso-emission-nebula", "dso-star-cluster"):
        gen = emission_finish_cmds if mode == "dso-emission-nebula" else cluster_finish_cmds
        def _finish():
            cmds = gaia_catalog_cmds(cfg.catalog_astro, cfg.catalog_photo) if (
                cfg.catalog_astro and cfg.catalog_photo) else []
            cmds += gen(anchor.as_posix(), out_name, box=crop, spcc=spcc)
            _siril("finish", cmds, cd=str(ws.linear))
        stages.append(Stage("finish", _finish, lambda: _nonzero(out_name + ".tif")))

    # reflection handled in Task 5.
    return stages


def _spcc_string(cfg) -> str:
    # Whole-token-quoted SPCC (gotcha #3); whiteref/region resolution is a later enhancement.
    return spcc_cmd()
