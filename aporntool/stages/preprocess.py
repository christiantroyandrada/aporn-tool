"""Per-mode SIRIL command lists for the preprocess core (§4.4b). Pure — no I/O, easy to test."""
from pathlib import Path

from aporntool.stages.engine import Stage
from aporntool.tools.siril import (
    build_ssf, write_ssf, run_siril, gaia_catalog_cmds, platesolve_cmd, spcc_cmd,
)

_SINGLE_PANEL = {"dso-emission-nebula", "dso-reflection-nebula", "dso-star-cluster"}
_SPCC_IN_PREPROCESS = {"dso-mosaic", "dso-reflection-nebula"}   # others SPCC in the finish phase


def is_single_panel(mode: str) -> bool:
    # Mosaic assembles via WCS (no flip); single-panel modes need mirrorx.
    return mode in _SINGLE_PANEL


def spcc_in_preprocess(mode: str) -> bool:
    # Mosaic/reflection color-calibrate before the golden anchor; emission/cluster do it in finish.
    return mode in _SPCC_IN_PREPROCESS


def convert_and_calibrate_cmds() -> list:
    # SIRIL 1.4.3 `link -out=` does NOT write a .seq file, so the calibrate step must
    # run in the SAME siril-cli invocation where the sequence is still in memory.
    return [
        "link light -out=../01_process",
        "cd ../01_process",
        "calibrate light -debayer",
    ]


def register_cmds(mode: str) -> list:
    if mode == "dso-mosaic":
        # WCS-based assembly: plate-solve every frame, then reproject to a common max frame.
        return ["seqplatesolve pp_light -force -nocache",
                "seqapplyreg pp_light -filter-round=2.5k -framing=max"]
    if mode == "dso-star-cluster":
        # Tight round stars are the payoff → also cull the worst FWHM (authored -wfwhm=2.5k).
        return ["register pp_light -2pass",
                "seqapplyreg pp_light -filter-round=2.5k -filter-wfwhm=2.5k"]
    # emission / reflection: star-based 2-pass registration.
    return ["register pp_light -2pass",
            "seqapplyreg pp_light -filter-round=2.5k"]


def stack_cmds(mode: str) -> list:
    # Sigma-clip stack. feather=100 is MANDATORY for mosaics or panel seams are permanent (#1).
    feather = " -feather=100" if mode == "dso-mosaic" else ""
    return [f"stack r_pp_light rej 3 3 -norm=addscale -output_norm -rgb_equal{feather} -out=result"]


def mirrorx_cmds() -> list:
    # Seestar frames are vertically flipped; correct single-panel stacks (mosaic uses WCS instead).
    return ["mirrorx_single result"]


def _nonzero(path) -> bool:
    # A stage counts as done only if its output file exists and isn't empty (FR-24b).
    p = Path(path)
    return p.exists() and p.stat().st_size > 0


def build_preprocess_stages(mode, ws, cfg, target, *, siril_exe, runner=None):
    # Build the ordered preprocess stages for this mode, each wired to a SIRIL script that is
    # written into logs/ then run. `runner` is injectable so tests never launch real SIRIL.
    import subprocess
    runner = runner or subprocess.run
    proc = ws.process
    anchor = ws.linear / f"{ws.target}_Linear.fit"

    def _run(stage_id, commands, cd=None):
        # Generate the .ssf, save it to logs/ (reproducibility), run it, log the console output.
        text = build_ssf(commands, cd=cd)
        script = write_ssf(text, ws.logs / f"{stage_id}.ssf")
        return run_siril(script, workdir=ws.work, siril_exe=siril_exe, runner=runner,
                         log_path=ws.logs / f"{stage_id}.log")

    stages = []

    # convert+calibrate: link staged lights and debayer in a single SIRIL session
    # (SIRIL 1.4.3 link -out= doesn't write a .seq, so calibrate must share the process).
    stages.append(Stage(
        "calibrate",
        lambda: _run("calibrate", convert_and_calibrate_cmds(), cd=str(ws.lights)),
        lambda: (proc / "pp_light_.seq").exists()))

    # register: WCS (mosaic) or 2-pass (single-panel), then apply registration.
    if mode == "dso-mosaic":
        # seqplatesolve has a known false-negative in SIRIL 1.4 (reports failure even when every
        # frame solved), which aborts the script before seqapplyreg. Work around by running them
        # in separate SIRIL processes within a single stage.
        def _register_mosaic():
            _run("platesolve", ["seqplatesolve pp_light -force -nocache"], cd=str(proc))
            _run("applyreg", ["seqapplyreg pp_light -filter-round=2.5k -framing=max"], cd=str(proc))
        stages.append(Stage("register", _register_mosaic,
                            lambda: (proc / "r_pp_light_.seq").exists()))
    else:
        stages.append(Stage(
            "register",
            lambda: _run("register", register_cmds(mode), cd=str(proc)),
            lambda: (proc / "r_pp_light_.seq").exists()))

    anchor_noext = anchor.with_suffix("").as_posix()   # SIRIL `save` appends .fit itself

    # stack: sigma-clip the registered sequence → result.fit (linear). No mirror/anchor here.
    stages.append(Stage(
        "stack",
        lambda: _run("stack", stack_cmds(mode), cd=str(proc)),
        lambda: (proc / "result.fit").exists()))

    if is_single_panel(mode) and not spcc_in_preprocess(mode):
        # mirrorx: undo the Seestar vertical flip and save the golden anchor.
        # (Emission/star-cluster — no SPCC in preprocess, so this is the final preprocess stage.)
        def _mirrorx_run():
            _run("mirrorx",
                 ["mirrorx_single result", "load result", f"save {anchor_noext}", "close"],
                 cd=str(proc))
        stages.append(Stage("mirrorx", _mirrorx_run, lambda: _nonzero(anchor)))

    if spcc_in_preprocess(mode):
        # spcc: platesolve + SPCC on the UN-FLIPPED result (the solver needs original orientation),
        # then mirrorx for single-panel modes, then save the anchor.
        # If plate solving fails (dense MW fields, faint targets), fall back to saving without SPCC.
        def _spcc_run():
            cmds = []
            if cfg.catalog_astro and cfg.catalog_photo:
                cmds += gaia_catalog_cmds(cfg.catalog_astro, cfg.catalog_photo)
            cmds += [
                "load result",
                platesolve_cmd(coords=f"{target.ra},{target.dec}",
                               focal=cfg.seestar_focal_mm, pixel=cfg.seestar_pixel_um),
                spcc_cmd(),
            ]
            if is_single_panel(mode):
                cmds.append("mirrorx")
            cmds += [f"save {anchor_noext}", "close"]
            result = _run("spcc", cmds, cd=str(proc))
            if result.returncode != 0 and not _nonzero(anchor):
                print("  WARNING: Plate solving failed -- saving linear stack without SPCC color "
                      "calibration. Colors may need manual correction in post-processing.")
                fallback = ["load result"]
                if is_single_panel(mode):
                    fallback.append("mirrorx")
                fallback += [f"save {anchor_noext}", "close"]
                _run("spcc_fallback", fallback, cd=str(proc))
        stages.append(Stage("spcc", _spcc_run, lambda: _nonzero(anchor)))

    return stages
