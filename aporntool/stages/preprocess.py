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


def convert_cmds() -> list:
    # Link all staged .fit in the lights dir into a SIRIL sequence named "light".
    return ["link light -out=../01_process"]


def calibrate_cmds() -> list:
    # Debayer only — the Seestar already calibrated internally, so no darks/flats/bias.
    return ["calibrate light -debayer"]


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
        run_siril(script, workdir=ws.work, siril_exe=siril_exe, runner=runner,
                  log_path=ws.logs / f"{stage_id}.log")

    stages = []

    # convert: link the staged lights into a sequence (run from the lights dir).
    stages.append(Stage(
        "convert",
        lambda: _run("convert", convert_cmds(), cd=str(ws.lights)),
        lambda: (proc / "light_.seq").exists()))

    # calibrate: debayer (run from the process dir where the sequence now lives).
    stages.append(Stage(
        "calibrate",
        lambda: _run("calibrate", calibrate_cmds(), cd=str(proc)),
        lambda: (proc / "pp_light_.seq").exists()))

    # register: WCS (mosaic) or 2-pass (single-panel), then apply registration.
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

    if is_single_panel(mode):
        # mirrorx: undo the Seestar vertical flip. For emission/star-cluster (no SPCC in
        # preprocess) mirrorx is the LAST preprocess stage, so it also SAVES the golden anchor;
        # for reflection it just mirrors result in place (SPCC saves the anchor next).
        def _mirrorx_run():
            if spcc_in_preprocess(mode):
                _run("mirrorx", ["mirrorx_single result"], cd=str(proc))
            else:
                _run("mirrorx",
                     ["mirrorx_single result", "load result", f"save {anchor_noext}", "close"],
                     cd=str(proc))
        stages.append(Stage(
            "mirrorx", _mirrorx_run,
            (lambda: _nonzero(anchor)) if not spcc_in_preprocess(mode)
            else (lambda: (proc / "result.fit").exists())))

    if spcc_in_preprocess(mode):
        # spcc: platesolve + SPCC on result (already mirrored for reflection), then SAVE the anchor.
        def _spcc_run():
            cmds = []
            if cfg.catalog_astro and cfg.catalog_photo:
                cmds += gaia_catalog_cmds(cfg.catalog_astro, cfg.catalog_photo)
            cmds += [
                "load result",
                platesolve_cmd(coords=f"{target.ra},{target.dec}",
                               focal=cfg.seestar_focal_mm, pixel=cfg.seestar_pixel_um),
                spcc_cmd(),
                f"save {anchor_noext}",
                "close",
            ]
            _run("spcc", cmds, cd=str(proc))
        stages.append(Stage("spcc", _spcc_run, lambda: _nonzero(anchor)))

    return stages
