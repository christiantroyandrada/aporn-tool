"""Assemble per-mode finish stages: golden anchor → deliverables at the --out root."""
import shutil
import subprocess
from pathlib import Path

from aporntool.stages.engine import Stage
from aporntool.tools.siril import build_ssf, write_ssf, run_siril, spcc_cmd, gaia_catalog_cmds
from aporntool.tools.graxpert import bge_cmd, denoise_cmd, run_graxpert
from aporntool.stages.finish_cmds import (
    mosaic_finish_cmds, emission_finish_cmds, cluster_finish_cmds,
)
from aporntool.stages.reflection_finish import run_reflection_finish
from aporntool.stages.crop import resolve_crop


def _nonzero(p) -> bool:
    p = Path(p)
    return p.exists() and p.stat().st_size > 0


def _all_deliverables(ws) -> bool:
    # FR-4/FR-27: all four deliverables must exist (and be non-empty) at the --out root.
    base = ws.out_root / f"{ws.target}_final"
    return all(_nonzero(f"{base}.{e}") for e in ("fits", "tif", "png", "jpg"))


def _publish(scratch_dir, ws) -> None:
    # Copy the four deliverables SIRIL wrote (bare names) in the finish scratch cwd out to the
    # --out root, renaming SIRIL's .fit to the .fits deliverable name.
    base = ws.out_root / f"{ws.target}_final"
    base.parent.mkdir(parents=True, exist_ok=True)
    for src_ext, dst_ext in ((".fit", ".fits"), (".tif", ".tif"), (".png", ".png"), (".jpg", ".jpg")):
        src = Path(scratch_dir) / f"{ws.target}_final{src_ext}"
        if src.exists():
            shutil.copy2(src, f"{base}{dst_ext}")


def _promote_fit_to_fits(ws) -> None:
    # Emission/cluster save straight to the --out root; SIRIL's `save` writes .fit, but the
    # FR-27 deliverable name is .fits — rename in place.
    base = ws.out_root / f"{ws.target}_final"
    fit = base.with_suffix(".fit")
    if fit.exists():
        fit.replace(base.with_suffix(".fits"))


def build_finish_stages(mode, ws, cfg, target, *, siril_exe, graxpert_exe=None,
                        starnet_exe=None, crop=None, star_reduce=0.5, runner=None):
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
            # Resolve at RUN time (not build_finish_stages call time) — the anchor .fit only
            # exists once preprocess stages have actually produced it.
            box = resolve_crop(crop, f"{anchor.as_posix()}.fit")
            _siril("crop", [f"load {anchor.as_posix()}",
                            *( [f"crop {box}"] if box else [] ),
                            f"save {cropped.as_posix()}", "close"], cd=str(ws.linear))
            run_graxpert(bge_cmd(graxpert_exe, f"{cropped.as_posix()}.fit",
                                 str(bge_out), gpu=True), bge_out, runner=runner, settle=3.0)
        stages.append(Stage("bge", _bge, lambda: _nonzero(f"{bge_out}.fits")))

        def _denoise():
            run_graxpert(denoise_cmd(graxpert_exe, f"{bge_out}.fits", str(clean),
                                     gpu=True, strength=0.8), clean, runner=runner, settle=3.0)
        stages.append(Stage("denoise", _denoise, lambda: _nonzero(f"{clean}.fits")))

        def _finish():
            # SIRIL's `pm`/`starnet -starmask` only resolve BARE names in the current working
            # dir — run this script with cd=ws.finish, load the _clean image via a path relative
            # to that scratch dir, and save under a bare out name so every SIRIL command in
            # mosaic_finish_cmds stays bare. Then copy the real deliverables out to --out root.
            bare_out = f"{ws.target}_final"
            rel_clean = f"../03_graxpert/{ws.target}_clean"
            _siril("finish", mosaic_finish_cmds(rel_clean, bare_out,
                                                star_reduce=star_reduce), cd=str(ws.finish))
            _publish(ws.finish, ws)
        stages.append(Stage("finish", _finish, lambda: _all_deliverables(ws)))

    elif mode in ("dso-emission-nebula", "dso-star-cluster"):
        gen = emission_finish_cmds if mode == "dso-emission-nebula" else cluster_finish_cmds
        def _finish():
            # Resolve at RUN time — the anchor .fit only exists once preprocess has produced it.
            box = resolve_crop(crop, f"{anchor.as_posix()}.fit")
            cmds = gaia_catalog_cmds(cfg.catalog_astro, cfg.catalog_photo) if (
                cfg.catalog_astro and cfg.catalog_photo) else []
            cmds += gen(anchor.as_posix(), out_name, box=box, spcc=spcc)
            _siril("finish", cmds, cd=str(ws.linear))
            # SIRIL's `save` writes .fit; the FR-27 deliverable name is .fits.
            _promote_fit_to_fits(ws)
        stages.append(Stage("finish", _finish, lambda: _all_deliverables(ws)))

    elif mode == "dso-reflection-nebula":
        cropped = ws.linear / f"{ws.target}_cropped"
        bge_out = ws.graxpert / f"{ws.target}_bge"
        clean = ws.graxpert / f"{ws.target}_clean"
        # bge: crop (SIRIL) then GraXpert BGE on the cropped linear (same as the mosaic branch).
        def _bge():
            box = resolve_crop(crop, f"{anchor.as_posix()}.fit")
            _siril("crop", [f"load {anchor.as_posix()}",
                            *( [f"crop {box}"] if box else [] ),
                            f"save {cropped.as_posix()}", "close"], cd=str(ws.linear))
            run_graxpert(bge_cmd(graxpert_exe, f"{cropped.as_posix()}.fit",
                                 str(bge_out), gpu=True), bge_out, runner=runner, settle=3.0)
        stages.append(Stage("bge", _bge, lambda: _nonzero(f"{bge_out}.fits")))

        def _denoise():
            run_graxpert(denoise_cmd(graxpert_exe, f"{bge_out}.fits", str(clean),
                                     gpu=True, strength=0.8), clean, runner=runner, settle=3.0)
        stages.append(Stage("denoise", _denoise, lambda: _nonzero(f"{clean}.fits")))

        def _finish():
            # StarNet2 scratch tifs must not leak into the --out root (FR-4) — keep them under
            # the target's own _work/05_finish scratch dir. Cropping is NOT repeated here: the bge
            # stage already cropped the linear anchor before GraXpert, so re-cropping would apply
            # the crop twice (an explicit --crop box especially would be wrong on the already
            # -cropped frame). run_reflection_finish therefore takes no crop argument.
            run_reflection_finish(f"{clean}.fits", out_name, starnet_exe=starnet_exe,
                                  runner=runner, scratch_dir=ws.finish)
        stages.append(Stage("finish", _finish, lambda: _all_deliverables(ws)))

    return stages


def _spcc_string(cfg) -> str:
    # Whole-token-quoted SPCC (gotcha #3); whiteref/region resolution is a later enhancement.
    return spcc_cmd()
