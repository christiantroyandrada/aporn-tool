"""Command-line entry point: parse args and dispatch to config / status / a processing mode."""
import argparse
from pathlib import Path

import aporntool
from aporntool.discovery import discover_tool
from aporntool.config import Config, load_config, save_config
from aporntool.catalog import resolve_target
from aporntool.workspace import Workspace, stage_fits, count_fits, iter_fits
from aporntool.manifest import Manifest, input_fingerprint, load_manifest, save_manifest
from aporntool.preflight import run_preflight, MODE_TOOLS
from aporntool.paths import sanitize_dropped_path, to_input_dir
from aporntool.locations import graxpert_model_root

DSO_MODES = ["dso-mosaic", "dso-emission-nebula", "dso-reflection-nebula", "dso-star-cluster"]
# The stage order the manifest tracks per mode (finish/details land in Plan 2).
MODE_ORDER = {
    "dso-mosaic": ["stage", "register", "stack", "spcc", "crop", "bge", "denoise", "starnet", "finish"],
    "dso-emission-nebula": ["stage", "register", "stack", "crop", "spcc", "denoise", "finish"],
    "dso-reflection-nebula": ["stage", "register", "stack", "spcc", "crop", "bge", "denoise", "finish"],
    "dso-star-cluster": ["stage", "register", "stack", "crop", "spcc", "denoise", "finish"],
}
ALL_TOOLS = ["siril", "graxpert", "starnet2", "ffmpeg"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aporntool", description="Astropornography tool")
    parser.add_argument("--version", action="version",
                        version=f"aporntool {aporntool.__version__}")
    sub = parser.add_subparsers(dest="command")

    p_cfg = sub.add_parser("config", help="inspect/verify tool configuration")
    p_cfg.add_argument("--check", action="store_true", help="verify all tools are discoverable")
    p_cfg.add_argument("--config", default="aporntool.config.json")

    p_status = sub.add_parser("status", help="show the resume ledger for a target")
    p_status.add_argument("--out", required=True)
    p_status.add_argument("--target", required=True)

    for mode in DSO_MODES:
        pm = sub.add_parser(mode, help=f"process a {mode} target")
        pm.add_argument("--in", dest="inputs", action="append", required=True,
                        help="subs folder (repeatable for multi-night)")
        pm.add_argument("--out", required=True)
        pm.add_argument("--target", required=True)
        pm.add_argument("--coords", default=None, help="RA,DEC if target is unknown")
        pm.add_argument("--config", default="aporntool.config.json")
        pm.add_argument("--preflight-only", action="store_true")
    return parser


def _resolve_tool(cfg: Config, tool: str):
    # Discover one tool as a plain str path (or None) — used by config-check and preflight.
    found = discover_tool(tool, config_path=cfg.tool_paths.get(tool))
    return str(found) if found else None


def cmd_config(args) -> int:
    cfg = load_config(args.config)
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
    print(f"\nConfig written to {args.config}")
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


def cmd_mode(args, mode: str) -> int:
    # Resolve inputs (drag-and-drop friendly), preflight the environment, then stage + checkpoint.
    # Pipeline stages themselves arrive in Plan 2 — this proves the skeleton + preflight gate.
    cfg = load_config(args.config)
    in_dirs = [to_input_dir(sanitize_dropped_path(p)) for p in args.inputs]
    for d in in_dirs:
        if not d.is_dir():
            print(f"ERROR: input folder does not exist: {d}")
            return 1
    target = resolve_target(args.target, args.coords)

    # Preflight is environment validation — run it before any staging/compute (FR-PF1).
    tool_paths = {t: _resolve_tool(cfg, t) for t in MODE_TOOLS.get(mode, [])}
    results = run_preflight(mode, tool_paths=tool_paths,
                            graxpert_model_root=graxpert_model_root())
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

    ws = Workspace(Path(args.out), target.name.upper().replace(" ", ""))
    ws.create()
    staged = stage_fits(in_dirs, ws.lights)
    print(f"Staged {staged} subs into {ws.lights}")
    if count_fits(ws.lights) < 1:
        print("ERROR: no .fit subs found in the given folder(s).")
        return 1

    m = Manifest(mode=mode, target=ws.target, order=MODE_ORDER[mode],
                 input_fingerprint=input_fingerprint(iter_fits(ws.lights)))
    save_manifest(m, ws.manifest_path)
    print("Preflight OK. (Pipeline stages land in Plan 2.)")
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "config":
        return cmd_config(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command in DSO_MODES:
        return cmd_mode(args, args.command)
    parser.print_help()
    return 1
