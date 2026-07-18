"""Command-line entry point: parse args and dispatch to config / status / a processing mode."""
import argparse
import os
import platform
from pathlib import Path

import aporntool
from aporntool.discovery import discover_tool
from aporntool.config import Config, load_config, save_config
from aporntool.detect import resolve_target_auto, resolve_target_wide, detect_mosaic
from aporntool.workspace import (
    Workspace, stage_fits, count_fits, iter_fits, stage_images, count_images, iter_images,
)
from aporntool.manifest import Manifest, input_fingerprint, load_manifest, save_manifest
from aporntool.preflight import run_preflight, MODE_TOOLS
from aporntool.paths import sanitize_dropped_path, to_input_dir
from aporntool.locations import graxpert_model_root, siril_starnet_exe
from aporntool.stages.preprocess import build_preprocess_stages
from aporntool.stages.finish import build_finish_stages
from aporntool.stages.engine import run_pipeline

DSO_MODES = ["dso-galaxy", "dso-emission-nebula", "dso-reflection-nebula", "dso-star-cluster"]
# Wide-field modes ingest camera/phone stills (JPEG/HEIC/PNG/TIFF), not raw FITS subs.
WIDE_MODES = ["dso-milky-way"]
MODES = DSO_MODES + WIDE_MODES
ALL_TOOLS = ["siril", "graxpert", "starnet2", "ffmpeg"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aporntool", description="Astropornography tool")
    parser.add_argument("--version", action="version",
                        version=f"aporntool {aporntool.__version__}")
    sub = parser.add_subparsers(dest="command")

    p_cfg = sub.add_parser("config", help="inspect/verify tool configuration")
    p_cfg.add_argument("--check", action="store_true", help="verify all tools are discoverable")
    p_cfg.add_argument("--init", action="store_true",
                       help="write a config file pre-filled with every pipeline default to edit")
    p_cfg.add_argument("--config", default="aporntool.config.json")

    p_status = sub.add_parser("status", help="show the resume ledger for a target")
    p_status.add_argument("--out", required=True)
    p_status.add_argument("--target", required=True)

    for mode in MODES:
        pm = sub.add_parser(mode, help=f"process a {mode} target")
        pm.add_argument("--in", dest="inputs", action="append", required=True,
                        help="subs folder (repeatable for multi-night)")
        pm.add_argument("--out", default=None,
                        help="output root (default: a <TARGET> folder beside the input subs)")
        pm.add_argument("--target", default=None,
                        help="object name (default: auto-detected from the subs' FITS OBJECT header)")
        pm.add_argument("--config", default="aporntool.config.json")
        pm.add_argument("--preflight-only", action="store_true")
        pm.add_argument("--from", dest="from_stage", default=None, help="restart at this stage id")
        pm.add_argument("--redo", default=None, help="re-run this stage id and everything downstream")
        pm.add_argument("--force", action="store_true", help="re-run all stages, ignore checkpoints")
        pm.add_argument("--crop", default=None,
                        help="explicit SIRIL crop box 'X Y W H' (default: auto-crop)")
        pm.add_argument("--no-crop", action="store_true",
                        help="disable auto-crop; use the full frame")
        pm.add_argument("--star-reduce", type=float, default=None,
                        help="composite star-layer strength 0..1 (galaxy/emission/reflection): "
                             "1.0 keeps all stars, lower reduces them. Overrides the per-mode "
                             "default (galaxy 0.5, emission/reflection 1.0)")
        pm.add_argument("--profile", default=None, help="color/stretch preset override")
        # Mosaic is a capture attribute, auto-detected from the subs' pointing spread; these force it.
        pm.add_argument("--mosaic", action="store_true",
                        help="force multi-panel mosaic assembly (galaxy; default: auto-detect)")
        pm.add_argument("--single", action="store_true",
                        help="force single-panel assembly (galaxy; default: auto-detect)")
        pm.add_argument("--clean", action="store_true",
                        help="on success, delete working files except the golden anchor "
                             "(reclaims disk; re-finish still works via --from bge/--from finish)")
    return parser


def _tool_candidates(tool: str) -> list[str]:
    """Return known install locations for a tool, per OS."""
    system = platform.system()
    candidates: list[str] = []
    if tool == "siril":
        if system == "Windows":
            pf = os.environ.get("ProgramFiles", r"C:\Program Files")
            candidates.append(os.path.join(pf, "Siril", "bin", "siril-cli.exe"))
        elif system == "Darwin":
            candidates.extend([
                "/Applications/Siril.app/Contents/MacOS/siril-cli",
                "/opt/homebrew/bin/siril-cli",
                "/usr/local/bin/siril-cli",
            ])
        else:
            candidates.extend(["/usr/bin/siril-cli", "/usr/local/bin/siril-cli"])
    elif tool == "graxpert":
        if system == "Windows":
            lad = os.environ.get("LOCALAPPDATA", "")
            if lad:
                candidates.append(os.path.join(lad, "Programs", "GraXpert", "GraXpert.exe"))
        elif system == "Darwin":
            candidates.append("/Applications/GraXpert.app/Contents/MacOS/GraXpert")
    elif tool == "starnet2":
        # No standard install dir; fall back to whatever StarNet is configured inside SIRIL.
        exe = siril_starnet_exe()
        if exe:
            candidates.append(exe)
    return candidates


def _resolve_tool(cfg: Config, tool: str):
    found = discover_tool(tool, config_path=cfg.tool_paths.get(tool),
                          candidates=_tool_candidates(tool))
    return str(found) if found else None


def cmd_config(args) -> int:
    cfg = load_config(args.config)
    if getattr(args, "init", False):
        # Materialise the full config (preserving any values already set) so every pipeline knob is
        # visible to edit. Unset keys keep their built-in default; deleting the file restores all.
        save_config(cfg, args.config)
        print(f"Wrote config with all pipeline defaults to {args.config}")
        print("  Edit any value under \"pipeline\" to override just that knob; unset keys keep the")
        print("  built-in default, and deleting the file restores every default.")
        return 0
    print("Tool discovery:")
    ok = True
    for tool in ALL_TOOLS:
        path = _resolve_tool(cfg, tool)
        print(f"  [{'OK ' if path else 'MISSING'}] {tool}: {path or 'not found'}")
        if path:
            cfg.tool_paths.setdefault(tool, path)
        else:
            ok = False
    save_config(cfg, args.config)          # write a starter config the user can edit
    print(f"\nConfig written to {args.config} (includes an editable 'pipeline' defaults block).")
    return 0 if ok else 2


def cmd_status(args) -> int:
    ws = Workspace(Path(args.out), args.target)
    if not ws.manifest_path.exists():
        print(f"No run found for {args.target} under {args.out}.")
        return 1
    m = load_manifest(ws.manifest_path)
    print(f"{m.mode} / {m.target}  (fingerprint {m.input_fingerprint or '-'})")
    for sid in m.order:
        print(f"  {sid:<10} {m.stage(sid).status}")
    nxt = m.next_pending()
    print(f"\nResume at: {nxt or 'complete'}")
    return 0


def _ensure_config_file(cfg, path) -> None:
    # Out of the box: on the first valid run, drop a fully-populated config next to the user so every
    # knob is visible to tweak — no command to run, no code to edit. Never overwrites an existing
    # file; a read-only location just means the run proceeds on defaults (no crash).
    p = Path(path)
    if p.exists():
        return
    try:
        save_config(cfg, path)
        print(f'Wrote {path} with all default settings — edit any value under "pipeline" to tune '
              f"the look (or delete it to restore defaults).")
    except OSError:
        pass


def _resolve_assembly(mode, in_dir, args) -> bool:
    # Decide multi-panel mosaic vs single-panel assembly and ALWAYS print it (FR-10a: never a silent
    # guess). Only galaxy captures assemble as mosaics for now; nebula/cluster mosaics are a planned
    # follow-up, so for those we stay single-panel and just warn if the data looks like a mosaic.
    force_mosaic = getattr(args, "mosaic", False)
    force_single = getattr(args, "single", False)
    if force_mosaic:
        if mode != "dso-galaxy":
            print(f"  note: --mosaic is only supported for dso-galaxy; processing {mode} single-panel.")
            return False
        print("  Assembly: MOSAIC (forced via --mosaic).")
        return True
    if force_single:
        print("  Assembly: single-panel (forced via --single).")
        return False
    det = detect_mosaic(in_dir)
    if mode != "dso-galaxy":
        if det.is_mosaic:
            print(f"  note: {det.reason}; multi-panel assembly is only supported for dso-galaxy "
                  "right now -- processing single-panel (panel seams may show).")
        return False
    print(f"  Assembly: {'MOSAIC' if det.is_mosaic else 'single-panel'} (auto) -- {det.reason}")
    print("           override with --mosaic / --single if this is wrong.")
    return det.is_mosaic


def cmd_mode(args, mode: str) -> int:
    # Resolve inputs (drag-and-drop friendly), preflight the environment, then stage + run the
    # preprocess pipeline through to the golden anchor (finishing stages land in Plan 4).
    cfg = load_config(args.config)
    if args.crop and args.no_crop:
        print("ERROR: --crop and --no-crop are mutually exclusive. Pass one, or neither "
              "for the default auto-crop.")
        return 1
    if getattr(args, "mosaic", False) and getattr(args, "single", False):
        print("ERROR: --mosaic and --single are mutually exclusive. Pass one, or neither "
              "to auto-detect the assembly from the subs.")
        return 1
    in_dirs = [to_input_dir(sanitize_dropped_path(p)) for p in args.inputs]
    for d in in_dirs:
        if not d.is_dir():
            print(f"ERROR: input folder does not exist: {d}")
            return 1
    try:
        if mode in WIDE_MODES:
            # Wide-field stills have no FITS OBJECT header and the mode never plate-solves, so just
            # name the run ("MilkyWay" by default; --target overrides).
            target = resolve_target_wide(args.target)
        else:
            # --target/--coords are optional: fall back to the subs' FITS OBJECT + RA/DEC header.
            target = resolve_target_auto(args.target, in_dirs[0])
    except (KeyError, ValueError) as e:
        print(f"ERROR: {e}")
        return 1

    target_key = target.name.upper().replace(" ", "")
    # --out is optional: default to a folder named after the target, right beside the input subs.
    out_root = Path(args.out) if args.out else in_dirs[0].parent / target_key
    ws = Workspace(out_root, target_key)
    if " " in str(ws.out_root):
        print("ERROR: --out path must not contain spaces (SIRIL path limitation). "
              "Choose a space-free output folder. (Full spaced-path support is planned.)")
        return 1

    _ensure_config_file(cfg, args.config)   # materialise the editable config on first run

    # Preflight is environment validation — run it before any staging/compute (FR-PF1).
    tool_paths = {t: _resolve_tool(cfg, t) for t in MODE_TOOLS.get(mode, [])}
    results = run_preflight(mode, tool_paths=tool_paths,
                            graxpert_model_root=graxpert_model_root(),
                            siril_starnet_exe=siril_starnet_exe())
    failed = [r for r in results if not r.ok]
    print("Preflight:")
    for r in results:
        print(f"  [{'OK ' if r.ok else 'FAIL'}] {r.name}: {r.detail}")
        if not r.ok:
            print(f"       -> {r.remediation}")
    if failed:
        print("\nPreflight failed - fix the above, then re-run the same command to continue.")
        return 2
    if args.preflight_only:                       # FR-PF3: validate only, no processing
        print("\nPreflight OK (--preflight-only).")
        return 0

    ws.create()
    if mode in WIDE_MODES:
        staged = stage_images(in_dirs, ws.lights)
        n_staged = count_images(ws.lights)
    else:
        staged = stage_fits(in_dirs, ws.lights)
        n_staged = count_fits(ws.lights)
    print(f"Staged {staged} frames into {ws.lights}")
    if n_staged < 1:
        if mode in WIDE_MODES:
            print("ERROR: No image frames found in the given folder(s).\n"
                  "  dso-milky-way reads camera/phone stills: .jpg .jpeg .png .tif .tiff .heic\n"
                  "  Make sure --in points to the folder holding your Milky Way frames.")
        else:
            print("ERROR: No .fit or .fits sub-exposure files found in the given folder(s).\n"
                  "  Make sure --in points to the folder containing your raw FITS frames\n"
                  "  (e.g. the 'lights' folder from your telescope).")
        return 1
    if mode in WIDE_MODES and any(f.suffix.lower() == ".heic" for f in iter_images(ws.lights)):
        # HEIC (iPhone's default) only decodes if SIRIL was built with libheif — most current builds
        # are, but flag it up front so a decode failure isn't misread as "too few stars" mid-run.
        print("  note: HEIC frames detected. SIRIL decodes these only if built with HEIF support "
              "(most current builds are). If registration reports no frames, export to JPEG/TIFF first.")

    # Build the FULL pipeline (preprocess → finish) up front so resume spans the whole run.
    siril = _resolve_tool(cfg, "siril")
    graxpert = _resolve_tool(cfg, "graxpert")
    starnet = _resolve_tool(cfg, "starnet2")
    # Auto-crop by default (FR-20): trims ragged registration/mosaic borders. An explicit --crop
    # box always wins; --no-crop disables cropping entirely (use the full frame).
    crop = args.crop if args.crop else (None if args.no_crop else "auto")
    # Mosaic vs single-panel is a capture attribute (orthogonal to target type). Only galaxies can
    # be mosaics for now; auto-detect from the subs' pointing spread unless --mosaic/--single forces
    # it. Always print the decision so the user can confirm or override (never a silent guess).
    is_mosaic = False if mode in WIDE_MODES else _resolve_assembly(mode, in_dirs[0], args)
    stages = build_preprocess_stages(mode, ws, cfg, target, siril_exe=siril, is_mosaic=is_mosaic)
    stages += build_finish_stages(mode, ws, cfg, target, siril_exe=siril, graxpert_exe=graxpert,
                                  starnet_exe=starnet, crop=crop, star_reduce=args.star_reduce)
    order = [s.id for s in stages]
    lights = iter_images(ws.lights) if mode in WIDE_MODES else iter_fits(ws.lights)
    fp = input_fingerprint(lights)
    # Resume from the on-disk manifest when it still matches (mode/order/fingerprint); else fresh.
    if ws.manifest_path.exists():
        m = load_manifest(ws.manifest_path)
        if m.mode != mode or m.order != order or m.input_fingerprint != fp:
            m = Manifest(mode=mode, target=ws.target, order=order, input_fingerprint=fp)
    else:
        m = Manifest(mode=mode, target=ws.target, order=order, input_fingerprint=fp)
    save_manifest(m, ws.manifest_path)
    ok = run_pipeline(m, stages, save=lambda mm: save_manifest(mm, ws.manifest_path),
                      from_stage=args.from_stage, redo=args.redo, force=args.force,
                      log_dir=ws.logs)
    if not ok:
        return 1
    anchor = ws.linear / f"{ws.target}_Linear.fit"
    tif = ws.out_root / f"{ws.target}_final.tif"
    if tif.exists():
        print(f"Done. Deliverables at {ws.out_root}: {ws.target}_final.(fits|tif|png|jpg)")
        # --clean only fires here, i.e. after a fully successful run that produced all deliverables
        # (a failed run returns above, so working files survive for resume).
        if args.clean:
            freed = ws.clean()
            print(f"  Cleaned working files (~{_human(freed)} reclaimed); kept the golden anchor "
                  f"{anchor.name}. Re-finish later with --from bge (mosaic/reflection) or "
                  f"--from finish (emission/cluster) -- no re-stack needed.")
    else:
        print(f"Preprocess complete. Golden anchor: {anchor}  (finish stages: see mode)")
    return 0


def _human(n: int) -> str:
    # Human-readable byte size for the --clean summary.
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "config":
        return cmd_config(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command in MODES:
        return cmd_mode(args, args.command)
    parser.print_help()
    return 1
