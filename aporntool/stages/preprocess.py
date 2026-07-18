"""Per-mode SIRIL command lists for the preprocess core (§4.4b). Pure — no I/O, easy to test."""
from pathlib import Path

from aporntool.stages.engine import Stage
from aporntool.tools.siril import (
    build_ssf, write_ssf, run_siril, gaia_catalog_cmds, platesolve_cmd, spcc_cmd, _g,
)
from aporntool.config import StackParams

# Which target TYPES colour-calibrate (SPCC) before the golden anchor. Galaxies and reflection
# nebulae do it in preprocess; emission and star-cluster do it later, in the finish phase.
_SPCC_IN_PREPROCESS = {"dso-galaxy", "dso-reflection-nebula"}


def spcc_in_preprocess(mode: str) -> bool:
    # Galaxy/reflection color-calibrate before the golden anchor; emission/cluster do it in finish.
    return mode in _SPCC_IN_PREPROCESS


def needs_mirrorx(is_mosaic: bool) -> bool:
    # Single-panel captures inherit the Seestar's vertical flip and must be mirrored; a mosaic gets
    # its orientation from WCS reprojection during assembly, so it must NOT be flipped.
    return not is_mosaic


def convert_and_calibrate_cmds() -> list:
    # SIRIL 1.4.3 `link -out=` does NOT write a .seq file, so the calibrate step must
    # run in the SAME siril-cli invocation where the sequence is still in memory.
    return [
        "link light -out=../01_process",
        "cd ../01_process",
        "calibrate light -debayer",
    ]


def _ingest_verb(kind: str) -> str:
    # FITS subs already are FITS → symlink (`link`, instant). Everything else (DSLR raw, TIFF, JPEG)
    # must be transcoded to FITS → `convert`. Both write frames into ../01_process; neither persists a
    # .seq via -out=, so the consuming command must share the same SIRIL session (see the stages).
    return "link" if kind == "fits" else "convert"


def _master_stack(set_name: str, out: str, stack, *, norm: str) -> str:
    sp = stack or StackParams()
    return f"stack {set_name} rej {_g(sp.sigma_low)} {_g(sp.sigma_high)} {norm} -out={out}"


def master_bias_cmds(kind: str, stack=None) -> list:
    # Master bias/offset: plain sigma-clip stack, no normalisation.
    return [f"{_ingest_verb(kind)} bias -out=../01_process", "cd ../01_process",
            _master_stack("bias", "master_bias", stack, norm="-nonorm")]


def master_dark_cmds(kind: str, stack=None) -> list:
    # Master dark: plain sigma-clip stack, no normalisation (darks must not be scaled).
    return [f"{_ingest_verb(kind)} dark -out=../01_process", "cd ../01_process",
            _master_stack("dark", "master_dark", stack, norm="-nonorm")]


def master_flat_cmds(kind: str, *, bias: bool = False, stack=None) -> list:
    # Master flat: bias-subtract each flat (if a master bias exists) then multiplicative-norm stack.
    cmds = [f"{_ingest_verb(kind)} flat -out=../01_process", "cd ../01_process"]
    if bias:
        cmds += ["calibrate flat -bias=master_bias",
                 _master_stack("pp_flat", "master_flat", stack, norm="-norm=mul")]
    else:
        cmds.append(_master_stack("flat", "master_flat", stack, norm="-norm=mul"))
    return cmds


def calibrate_light_cmds(kind: str, debayer: bool, *, bias=False, dark=False, flat=False) -> list:
    # Convert/link the lights then calibrate with whatever masters were built. With kind="fits",
    # debayer=True and no masters this is byte-identical to convert_and_calibrate_cmds() (the Seestar
    # path). DSLR raw/TIFF/JPEG use `convert`; already-RGB TIFF/JPEG skip -debayer.
    cal = ["calibrate light"]
    if bias:
        cal.append("-bias=master_bias")
    if dark:
        cal.append("-dark=master_dark")
        cal.append("-cc=dark")          # cosmetic (hot/cold pixel) correction from the master dark
    if flat:
        cal.append("-flat=master_flat")
    if debayer:
        cal.append("-debayer")
    return [f"{_ingest_verb(kind)} light -out=../01_process", "cd ../01_process", " ".join(cal)]


def convert_cmds() -> list:
    # Wide-field (dso-milky-way): phone/camera stills are already debayered 8-bit RGB, so there is
    # nothing to calibrate — just transcode them to a FITS sequence named `pp_light` so the shared
    # register/stack steps (which reference pp_light) work unchanged.
    return ["convert pp_light -out=../01_process"]


def wide_register_cmds() -> list:
    # Wide-field: single-pass global star registration (no roundness cull). Phone/camera frames vary
    # a lot in star quality frame-to-frame, and the DSO 2-pass + `-filter-round` cull can drop the
    # reference frame and abort seqapplyreg — we want to keep every frame that aligns anyway. One-pass
    # `register` both aligns AND applies, writing r_pp_light directly (no separate seqapplyreg step).
    return ["register pp_light"]


def register_cmds(mode: str, is_mosaic: bool, stack=None) -> list:
    # Registration depends on the ASSEMBLY (mosaic vs single), not the target type — except that
    # star clusters also cull the worst FWHM (tight round stars are the whole point there).
    sp = stack or StackParams()
    if is_mosaic:
        # WCS-based assembly: plate-solve every frame, then reproject to a common max frame.
        return ["seqplatesolve pp_light -force -nocache",
                f"seqapplyreg pp_light -filter-round={sp.filter_round} -framing=max"]
    if mode == "dso-star-cluster":
        # Tight round stars are the payoff → also cull the worst FWHM (authored -wfwhm=2.5k).
        return ["register pp_light -2pass",
                f"seqapplyreg pp_light -filter-round={sp.filter_round} -filter-wfwhm={sp.filter_wfwhm}"]
    # single-panel galaxy / emission / reflection: star-based 2-pass registration.
    return ["register pp_light -2pass",
            f"seqapplyreg pp_light -filter-round={sp.filter_round}"]


def stack_cmds(is_mosaic: bool, stack=None) -> list:
    # Sigma-clip stack. feather is MANDATORY for mosaics or panel seams are permanent (#1); a
    # single-panel stack has no seams to blend, so no feather.
    sp = stack or StackParams()
    feather = f" -feather={_g(sp.feather_mosaic)}" if is_mosaic else ""
    return [f"stack r_pp_light rej {_g(sp.sigma_low)} {_g(sp.sigma_high)} -norm=addscale -output_norm -rgb_equal{feather} -out=result"]


def _nonzero(path) -> bool:
    # A stage counts as done only if its output file exists and isn't empty (FR-24b).
    p = Path(path)
    return p.exists() and p.stat().st_size > 0


def build_preprocess_stages(mode, ws, cfg, target, *, siril_exe, runner=None, is_mosaic=False,
                            light_kind="fits", light_debayer=True, cal=None, focal=None, pixel=None):
    # Build the ordered preprocess stages for this mode, each wired to a SIRIL script that is
    # written into logs/ then run. `runner` is injectable so tests never launch real SIRIL.
    # `is_mosaic` selects the assembly (WCS+feather, no flip) vs single-panel (2-pass + mirrorx);
    # it is auto-detected by the caller (detect.detect_mosaic) and only true for galaxy captures
    # that span more than one FOV.
    # `light_kind`/`light_debayer` describe the input source (fits Seestar sub vs DSLR raw/TIFF/JPEG);
    # `cal` is {"bias","dark","flat": bool} for DSLR master calibration; `focal`/`pixel` override the
    # Seestar optics for the SPCC plate solve. All default to the Seestar-FITS behaviour unchanged.
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
    is_wide = mode == "dso-milky-way"
    cal = cal or {}
    has_cal = any(cal.get(k) for k in ("bias", "dark", "flat"))
    # A DSLR/mirrorless/phone frame is not vertically flipped like a Seestar sub, so ONLY FITS
    # (Seestar) input gets the mirrorx flip. This also drives whether a non-SPCC mode still needs a
    # plain anchor-save stage (DSLR emission/cluster have no mirrorx to double as the anchor save).
    mirror = (light_kind == "fits") and needs_mirrorx(is_mosaic)

    if not is_wide and has_cal:
        # masters: build the provided master calibration frames (bias -> dark -> flat) into
        # 01_process. Each is its own SIRIL session (convert+stack, since -out= drops the .seq),
        # and flat calibration reuses the master bias, so ordering matters. Each set uses ITS OWN
        # format verb (cal[kind] is the detected format of that folder) — a FITS-lights run can still
        # have raw calibration frames and vice versa.
        def _masters_run():
            if cal.get("bias"):
                _run("master_bias", master_bias_cmds(cal["bias"], cfg.pipeline.stack), cd=str(ws.bias))
            if cal.get("dark"):
                _run("master_dark", master_dark_cmds(cal["dark"], cfg.pipeline.stack), cd=str(ws.darks))
            if cal.get("flat"):
                _run("master_flat", master_flat_cmds(cal["flat"], bias=bool(cal.get("bias")),
                                                     stack=cfg.pipeline.stack), cd=str(ws.flats))

        def _masters_done():
            for kind_key, fname in (("bias", "master_bias.fit"), ("dark", "master_dark.fit"),
                                    ("flat", "master_flat.fit")):
                if cal.get(kind_key) and not (proc / fname).exists():
                    return False
            return True
        stages.append(Stage("masters", _masters_run, _masters_done))

    if not is_wide:
        if has_cal or light_kind != "fits":
            # DSLR / still input, or any run with calibration masters: convert (or link) the lights
            # then calibrate with whatever masters exist. Byte-identical to convert_and_calibrate_cmds
            # when kind="fits", debayer=True and no masters (the Seestar path).
            stages.append(Stage(
                "calibrate",
                lambda: _run("calibrate", calibrate_light_cmds(
                    light_kind, light_debayer, bias=bool(cal.get("bias")),
                    dark=bool(cal.get("dark")), flat=bool(cal.get("flat"))), cd=str(ws.lights)),
                lambda: (proc / "pp_light_.seq").exists()))
        else:
            # Seestar FITS, no calibration frames: unchanged link + debayer in one SIRIL session
            # (SIRIL 1.4.3 link -out= doesn't write a .seq, so calibrate must share the process).
            stages.append(Stage(
                "calibrate",
                lambda: _run("calibrate", convert_and_calibrate_cmds(), cd=str(ws.lights)),
                lambda: (proc / "pp_light_.seq").exists()))

    # register: WCS (mosaic) or 2-pass (single-panel), then apply registration.
    if is_wide:
        # Wide-field has no separate calibrate stage: transcode the stills AND register in ONE SIRIL
        # session. `convert -out=` (like `link -out=`) does NOT persist a .seq, so the sequence must
        # be consumed in the same process that created it (same reason calibrate absorbs `link`).
        def _wide_register():
            _run("register",
                 convert_cmds() + ["cd ../01_process"] + wide_register_cmds(),
                 cd=str(ws.lights))
        stages.append(Stage("register", _wide_register,
                            lambda: (proc / "r_pp_light_.seq").exists()))
    elif is_mosaic:
        # seqplatesolve has a known false-negative in SIRIL 1.4 (reports failure even when every
        # frame solved), which aborts the script before seqapplyreg. Work around by running them
        # in separate SIRIL processes within a single stage.
        def _register_mosaic():
            _run("platesolve", ["seqplatesolve pp_light -force -nocache"], cd=str(proc))
            _run("applyreg", [f"seqapplyreg pp_light -filter-round={cfg.pipeline.stack.filter_round} -framing=max"], cd=str(proc))
        stages.append(Stage("register", _register_mosaic,
                            lambda: (proc / "r_pp_light_.seq").exists()))
    else:
        stages.append(Stage(
            "register",
            lambda: _run("register", register_cmds(mode, is_mosaic, cfg.pipeline.stack), cd=str(proc)),
            lambda: (proc / "r_pp_light_.seq").exists()))

    anchor_noext = anchor.with_suffix("").as_posix()   # SIRIL `save` appends .fit itself

    def _anchor_stage():
        # Save the stacked result straight to the golden anchor — no flip, no SPCC. Used by the
        # wide-field path and by DSLR emission/cluster (neither is vertically flipped).
        return Stage("anchor",
                     lambda: _run("anchor", ["load result", f"save {anchor_noext}", "close"],
                                  cd=str(proc)),
                     lambda: _nonzero(anchor))

    # stack: sigma-clip the registered sequence → result.fit (linear). No mirror/anchor here.
    stages.append(Stage(
        "stack",
        lambda: _run("stack", stack_cmds(is_mosaic, cfg.pipeline.stack), cd=str(proc)),
        lambda: (proc / "result.fit").exists()))

    if is_wide:
        # Wide-field: no Seestar flip (a phone/camera isn't mirrored) and no SPCC — just save the
        # stacked result as the golden anchor for the finish phase.
        stages.append(_anchor_stage())
    elif spcc_in_preprocess(mode):
        # spcc: platesolve + SPCC on the UN-FLIPPED result (the solver needs original orientation),
        # then mirrorx for Seestar single-panel, then save the anchor. focal/pixel come from the DSLR
        # overrides when set, else the Seestar defaults. Falls back to no-SPCC if the solve fails
        # (dense MW fields, faint targets, or a wrong DSLR focal/pixel).
        def _spcc_run():
            cmds = []
            if cfg.catalog_astro and cfg.catalog_photo:
                cmds += gaia_catalog_cmds(cfg.catalog_astro, cfg.catalog_photo)
            cmds += [
                "load result",
                platesolve_cmd(coords=f"{target.ra},{target.dec}",
                               focal=focal or cfg.seestar_focal_mm,
                               pixel=pixel or cfg.seestar_pixel_um),
                spcc_cmd(sensor=cfg.pipeline.spcc.sensor, osc_filter=cfg.pipeline.spcc.osc_filter,
                         whiteref=cfg.pipeline.spcc.whiteref, catalog=cfg.pipeline.spcc.catalog),
            ]
            if mirror:
                cmds.append("mirrorx")
            cmds += [f"save {anchor_noext}", "close"]
            result = _run("spcc", cmds, cd=str(proc))
            if result.returncode != 0 and not _nonzero(anchor):
                print("  WARNING: Plate solving failed -- saving linear stack without SPCC color "
                      "calibration. Colors may need manual correction in post-processing.")
                fallback = ["load result"]
                if mirror:
                    fallback.append("mirrorx")
                fallback += [f"save {anchor_noext}", "close"]
                _run("spcc_fallback", fallback, cd=str(proc))
            else:
                # SPCC succeeded -- surface SIRIL's soft warnings that otherwise reach only the
                # per-stage log, so the user sees HOW the calibration actually ran (FR-PF2 spirit).
                out = (result.stdout + result.stderr).lower()
                if "reverting to online" in out or "catalog is unavailable" in out:
                    print("  note: local Gaia catalog not found -- SPCC used the online ESA Gaia "
                          "catalog. Install the local catalog for offline/faster runs.")
                if "imprecise solution" in out:
                    print("  note: SPCC reported an imprecise color solution (galaxy/reflection "
                          "calibrate before gradient removal); colors may need a tweak, or re-run "
                          "--redo spcc after installing the local catalog.")
        stages.append(Stage("spcc", _spcc_run, lambda: _nonzero(anchor)))
    elif mirror:
        # mirrorx: undo the Seestar vertical flip and save the golden anchor.
        # (Seestar emission/star-cluster — no SPCC in preprocess, so this is the final stage.)
        def _mirrorx_run():
            _run("mirrorx",
                 ["mirrorx_single result", "load result", f"save {anchor_noext}", "close"],
                 cd=str(proc))
        stages.append(Stage("mirrorx", _mirrorx_run, lambda: _nonzero(anchor)))
    else:
        # DSLR/still emission or star-cluster: not vertically flipped and no SPCC here, so save the
        # stacked result straight to the golden anchor.
        stages.append(_anchor_stage())

    return stages
