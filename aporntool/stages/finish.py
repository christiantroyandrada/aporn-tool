"""Assemble per-mode finish stages: golden anchor → deliverables at the --out root."""
import glob
import subprocess
from dataclasses import asdict
from pathlib import Path

from aporntool.stages.engine import Stage
from aporntool.tools.siril import build_ssf, write_ssf, run_siril, spcc_cmd, gaia_catalog_cmds, platesolve_cmd
from aporntool.tools.graxpert import bge_cmd, denoise_cmd, run_graxpert
from aporntool.stages.finish_cmds import crop_cmds, cluster_finish_cmds, milkyway_finish_cmds
from aporntool.stages.composite_finish import run_composite_finish
from aporntool.stages.reflection_finish import run_reflection_finish
from aporntool.stages.foreground import run_foreground_deghost
from aporntool.stages.crop import resolve_crop


def _nonzero(p) -> bool:
    p = Path(p)
    return p.exists() and p.stat().st_size > 0


def _all_deliverables(ws) -> bool:
    # FR-4/FR-27: all four deliverables must exist (and be non-empty) at the --out root.
    base = ws.out_root / f"{ws.target}_final"
    return all(_nonzero(f"{base}.{e}") for e in ("fits", "tif", "png", "jpg"))


def _promote_fit_to_fits(ws) -> None:
    # Emission/cluster save straight to the --out root; SIRIL's `save` writes .fit, but the
    # FR-27 deliverable name is .fits — rename in place.
    base = ws.out_root / f"{ws.target}_final"
    fit = base.with_suffix(".fit")
    if fit.exists():
        fit.replace(base.with_suffix(".fits"))


def build_finish_stages(mode, ws, cfg, target, *, siril_exe, graxpert_exe=None,
                        starnet_exe=None, crop=None, star_reduce=None, runner=None,
                        focal=None, pixel=None, no_tripod=False, light_kind="fits", stacked=False):
    # `light_kind`/`stacked` describe the input source. They drive the cluster dark-background gate:
    # a light-polluted DSLR/--stacked cluster stack needs the dark autostretch target, while a clean
    # Seestar FITS cluster keeps its proven bare autostretch (byte-identical). Default to the Seestar
    # case so callers that don't pass them are unchanged.
    cluster_dark_bg = (light_kind != "fits") or stacked
    runner = runner or subprocess.run
    anchor = ws.linear / f"{ws.target}_Linear"          # SIRIL load name (no .fit)
    out_name = str((ws.out_root / f"{ws.target}_final").as_posix())
    # Seed the finish plate solve (emission/cluster SPCC) with the target's coords + optics. A blind
    # solve fails on wide DSLR fields and already-stacked frames; a seeded solve locks reliably. focal/
    # pixel come from --focal/--pixel (DSLR) or the Seestar defaults.
    solve = platesolve_cmd(coords=f"{target.ra},{target.dec}",
                           focal=focal or cfg.seestar_focal_mm, pixel=pixel or cfg.seestar_pixel_um,
                           catalog=cfg.pipeline.spcc.catalog)
    stages = []

    def _siril(stage_id, commands, cd):
        text = build_ssf(commands, cd=cd)
        script = write_ssf(text, ws.logs / f"{stage_id}.ssf")
        run_siril(script, workdir=ws.work, siril_exe=siril_exe, runner=runner,
                  log_path=ws.logs / f"{stage_id}.log")

    spcc = _spcc_string(cfg)

    if mode == "dso-galaxy":
        cropped = ws.linear / f"{ws.target}_cropped"
        bge_out = ws.graxpert / f"{ws.target}_bge"
        clean = ws.graxpert / f"{ws.target}_clean"
        # bge: crop (SIRIL) then GraXpert BGE on the cropped linear.
        def _bge():
            # Resolve at RUN time (not build_finish_stages call time) — the anchor .fit only
            # exists once preprocess stages have actually produced it.
            box = resolve_crop(crop, f"{anchor.as_posix()}.fit", cfg.pipeline.crop)
            _siril("crop", [f"load {anchor.as_posix()}",
                            *( [f"crop {box}"] if box else [] ),
                            f"save {cropped.as_posix()}", "close"], cd=str(ws.linear))
            run_graxpert(bge_cmd(graxpert_exe, f"{cropped.as_posix()}.fit",
                                 str(bge_out), gpu=True, smoothing=cfg.pipeline.graxpert.bge_smoothing,
                                 correction=cfg.pipeline.graxpert.bge_correction),
                         bge_out, runner=runner, settle=3.0)
        stages.append(Stage("bge", _bge, lambda: _nonzero(f"{bge_out}.fits")))

        def _denoise():
            run_graxpert(denoise_cmd(graxpert_exe, f"{bge_out}.fits", str(clean),
                                     gpu=True, strength=cfg.pipeline.graxpert.denoise_strength),
                         clean, runner=runner, settle=3.0)
        stages.append(Stage("denoise", _denoise, lambda: _nonzero(f"{clean}.fits")))

        def _finish():
            # Composite dual-layer finish on the GraXpert-cleaned linear: stretch -> StarNet ->
            # process starless (galaxy/nebula) + stars -> screen-blend. StarNet scratch stays under
            # ws.finish (never beside the deliverables, FR-4). star_reduce (default 0.5) blends only
            # a fraction of the stars back (#10 — full removal looks AI-generated).
            strength = star_reduce if star_reduce is not None else cfg.pipeline.mosaic_finish.star_reduce
            run_composite_finish(f"{clean.as_posix()}.fits", out_name, mode="dso-galaxy",
                                 starnet_exe=starnet_exe, runner=runner, scratch_dir=str(ws.finish),
                                 star_strength=strength, jpeg_quality=cfg.pipeline.jpeg_quality)
        stages.append(Stage("finish", _finish, lambda: _all_deliverables(ws)))

    elif mode == "dso-emission-nebula":
        def _finish():
            # SIRIL prep: crop -> gradient -> local-Gaia platesolve + SPCC -> denoise, saved as a
            # linear _clean.fit. Then the composite dual-layer finish (stretch -> StarNet -> starless
            # nebula + stars -> screen-blend). SPCC may fail to calibrate on reddened galactic-plane
            # fields (benign) — the composite's SCNR + red-preserving saturation gives crimson Halpha
            # regardless. Rich Milky-Way fields keep all stars (star_strength default 1.0).
            box = resolve_crop(crop, f"{anchor.as_posix()}.fit", cfg.pipeline.crop)
            clean = ws.finish / f"{ws.target}_clean"
            gaia = gaia_catalog_cmds(cfg.catalog_astro, cfg.catalog_photo) if (
                cfg.catalog_astro and cfg.catalog_photo) else []
            base = [f"load {anchor.as_posix()}", *crop_cmds(box),
                    f"subsky {cfg.pipeline.emission_finish.subsky_degree}"]
            # Try SPCC (seeded plate solve so it locks on DSLR/stacked frames); if it still can't
            # solve, fall back to no-SPCC so the finish delivers — the composite's SCNR + red-
            # preserving saturation render the nebula either way. SIRIL uses the local Gaia catalog
            # if present and auto-reverts to the online catalogue otherwise.
            _siril("finish", gaia + base + [solve, spcc, "denoise", f"save {clean.as_posix()}"],
                   cd=str(ws.linear))
            if not _nonzero(f"{clean.as_posix()}.fit"):
                print("  WARNING: plate solve / SPCC failed in finish -- proceeding without colour "
                      "calibration (the composite still renders the nebula).")
                _siril("finish_nospcc", base + ["denoise", f"save {clean.as_posix()}"],
                       cd=str(ws.linear))
            run_composite_finish(f"{clean.as_posix()}.fit", out_name, mode="dso-emission-nebula",
                                 starnet_exe=starnet_exe, runner=runner, scratch_dir=str(ws.finish),
                                 star_strength=star_reduce, jpeg_quality=cfg.pipeline.jpeg_quality)
        stages.append(Stage("finish", _finish, lambda: _all_deliverables(ws)))

    elif mode == "dso-star-cluster":
        # Star clusters are the ONE mode that never uses the composite — the stars ARE the subject,
        # so no StarNet removal. Straight SIRIL finish (SPCC + light denoise + highlight-protected).
        def _finish():
            box = resolve_crop(crop, f"{anchor.as_posix()}.fit", cfg.pipeline.crop)
            gaia = gaia_catalog_cmds(cfg.catalog_astro, cfg.catalog_photo) if (
                cfg.catalog_astro and cfg.catalog_photo) else []
            # Try SPCC; fall back to no-SPCC if the plate solve can't lock, so the finish still
            # delivers (the highlight-protected stretch carries the cluster without colour calibration).
            _siril("finish", gaia + cluster_finish_cmds(
                anchor.as_posix(), out_name, box=box, spcc=spcc, solve=solve,
                params=cfg.pipeline.cluster_finish, jpeg_quality=cfg.pipeline.jpeg_quality,
                dark_background=cluster_dark_bg),
                cd=str(ws.linear))
            _promote_fit_to_fits(ws)   # SIRIL `save` writes .fit; FR-27 deliverable name is .fits
            if not _all_deliverables(ws):
                print("  WARNING: plate solve / SPCC failed in finish -- retrying without colour "
                      "calibration.")
                _siril("finish_nospcc", gaia + cluster_finish_cmds(
                    anchor.as_posix(), out_name, box=box, spcc=spcc, solve=solve,
                    params=cfg.pipeline.cluster_finish, jpeg_quality=cfg.pipeline.jpeg_quality,
                    calibrate=False, dark_background=cluster_dark_bg), cd=str(ws.linear))
                _promote_fit_to_fits(ws)
        stages.append(Stage("finish", _finish, lambda: _all_deliverables(ws)))

    elif mode == "dso-reflection-nebula":
        cropped = ws.linear / f"{ws.target}_cropped"
        bge_out = ws.graxpert / f"{ws.target}_bge"
        clean = ws.graxpert / f"{ws.target}_clean"
        # bge: crop (SIRIL) then GraXpert BGE on the cropped linear (same as the mosaic branch).
        def _bge():
            box = resolve_crop(crop, f"{anchor.as_posix()}.fit", cfg.pipeline.crop)
            _siril("crop", [f"load {anchor.as_posix()}",
                            *( [f"crop {box}"] if box else [] ),
                            f"save {cropped.as_posix()}", "close"], cd=str(ws.linear))
            run_graxpert(bge_cmd(graxpert_exe, f"{cropped.as_posix()}.fit",
                                 str(bge_out), gpu=True, smoothing=cfg.pipeline.graxpert.bge_smoothing,
                                 correction=cfg.pipeline.graxpert.bge_correction),
                         bge_out, runner=runner, settle=3.0)
        stages.append(Stage("bge", _bge, lambda: _nonzero(f"{bge_out}.fits")))

        def _denoise():
            run_graxpert(denoise_cmd(graxpert_exe, f"{bge_out}.fits", str(clean),
                                     gpu=True, strength=cfg.pipeline.graxpert.denoise_strength),
                         clean, runner=runner, settle=3.0)
        stages.append(Stage("denoise", _denoise, lambda: _nonzero(f"{clean}.fits")))

        def _finish():
            # StarNet2 scratch tifs must not leak into the --out root (FR-4) — keep them under
            # the target's own _work/05_finish scratch dir. Cropping is NOT repeated here: the bge
            # stage already cropped the linear anchor before GraXpert, so re-cropping would apply
            # the crop twice (an explicit --crop box especially would be wrong on the already
            # -cropped frame). run_reflection_finish therefore takes no crop argument.
            run_reflection_finish(f"{clean}.fits", out_name, starnet_exe=starnet_exe,
                                  runner=runner, scratch_dir=ws.finish,
                                  params=asdict(cfg.pipeline.reflection_finish),
                                  jpeg_quality=cfg.pipeline.jpeg_quality)
        stages.append(Stage("finish", _finish, lambda: _all_deliverables(ws)))

    elif mode == "dso-milky-way":
        cropped = ws.linear / f"{ws.target}_cropped"
        bge_out = ws.graxpert / f"{ws.target}_bge"
        clean = ws.graxpert / f"{ws.target}_clean"
        mw = cfg.pipeline.milkyway_finish
        # bge: crop (SIRIL, trims the rotation-blurred registration border) then GraXpert BGE. High
        # bge_smoothing keeps the large-scale Milky Way band from being subtracted as "background".
        # The de-ghost stage below MUST resolve the SAME crop (cfg.pipeline.crop) so its mask and
        # foreground line up pixel-for-pixel with this cropped sky.
        def _bge():
            box = resolve_crop(crop, f"{anchor.as_posix()}.fit", cfg.pipeline.crop)
            _siril("crop", [f"load {anchor.as_posix()}",
                            *( [f"crop {box}"] if box else [] ),
                            f"save {cropped.as_posix()}", "close"], cd=str(ws.linear))
            run_graxpert(bge_cmd(graxpert_exe, f"{cropped.as_posix()}.fit",
                                 str(bge_out), gpu=True, smoothing=mw.bge_smoothing,
                                 correction=mw.bge_correction),
                         bge_out, runner=runner, settle=3.0)
        stages.append(Stage("bge", _bge, lambda: _nonzero(f"{bge_out}.fits")))

        def _denoise():
            run_graxpert(denoise_cmd(graxpert_exe, f"{bge_out}.fits", str(clean),
                                     gpu=True, strength=mw.denoise_strength),
                         clean, runner=runner, settle=3.0)
        stages.append(Stage("denoise", _denoise, lambda: _nonzero(f"{clean}.fits")))

        def _finish():
            # No StarNet (stars are the subject) and no SPCC (no plate solve at a phone field): just
            # stretch + gentle colour on the GraXpert-cleaned linear, then save the four deliverables.
            _siril("finish", milkyway_finish_cmds(f"{clean.as_posix()}.fits", out_name,
                                                  params=mw, jpeg_quality=cfg.pipeline.jpeg_quality),
                   cd=str(ws.linear))
            _promote_fit_to_fits(ws)   # SIRIL `save` writes .fit; FR-27 deliverable name is .fits
        stages.append(Stage("finish", _finish, lambda: _all_deliverables(ws)))

        if no_tripod:
            # Handheld capture: the finished deliverables have a sharp DEEP SKY but a GHOSTED
            # foreground (star-aligned stacking smears the fixed house/trees/wires). Recover a sharp
            # foreground from a single frame while keeping the stacked sky. Runs after 'finish' and
            # overwrites the four deliverables. A marker gates resume (this stage edits, not creates,
            # so it can't use _all_deliverables as its done-check — those already exist from finish).
            done_marker = ws.finish / ".deghost_done"

            def _deghost():
                regs = sorted(glob.glob(str(ws.process / "r_pp_light_*.fit")))
                ref = ws.process / "r_pp_light_00001.fit"
                ws.finish.mkdir(parents=True, exist_ok=True)
                if len(regs) < 2 or not ref.exists():
                    # No registered frames (e.g. --stacked input, or a --clean'd workspace on resume):
                    # nothing to de-ghost against. Leave the deliverables as-is and say why (P2).
                    print("  note: --no-tripod needs the registered frames (r_pp_light_*.fit) and "
                          "found none; keeping the stacked result unchanged. (Not applicable to "
                          "--stacked input or a cleaned workspace.)")
                    done_marker.write_text("skipped: no registered frames")
                    return
                box = resolve_crop(crop, f"{anchor.as_posix()}.fit", cfg.pipeline.crop)
                cov = run_foreground_deghost(
                    f"{out_name}.tif", regs, str(ref), crop_box=box, out_stem=out_name,
                    params=asdict(cfg.pipeline.no_tripod), jpeg_quality=cfg.pipeline.jpeg_quality)
                print(f"  --no-tripod: recovered a sharp foreground ({cov * 100:.0f}% of frame) "
                      f"from one frame; deep sky kept from the {len(regs)}-frame stack.")
                done_marker.write_text("done")
            stages.append(Stage("deghost", _deghost, done_marker.exists))

    return stages


def _spcc_string(cfg) -> str:
    # Whole-token-quoted SPCC (gotcha #3), built from the configured SpccParams.
    sp = cfg.pipeline.spcc
    return spcc_cmd(sensor=sp.sensor, osc_filter=sp.osc_filter, whiteref=sp.whiteref, catalog=sp.catalog)
