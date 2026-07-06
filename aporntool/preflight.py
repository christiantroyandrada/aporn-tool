"""Validate ALL preconditions for a mode up front, so a stage-4 blocker fails at second zero."""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    remediation: str = ""     # what the user should do; empty when ok


# Which external binaries each mode needs (emission/cluster stay on SIRIL only).
MODE_TOOLS = {
    "dso-mosaic": ["siril", "graxpert", "starnet2"],
    "dso-emission-nebula": ["siril"],
    "dso-reflection-nebula": ["siril", "graxpert", "starnet2"],
    "dso-star-cluster": ["siril"],
}
# Only these modes run GraXpert, so only they need its AI models present.
MODE_NEEDS_GRAXPERT = {"dso-mosaic", "dso-reflection-nebula"}


_TOOL_HELP = {
    "siril": "Download SIRIL from https://siril.org/download/ and install it. "
             "On Windows the installer puts siril-cli.exe in Program Files automatically.",
    "graxpert": "Download GraXpert from https://github.com/Stuermer/GraXpert/releases and install it. "
                "After installing, open it once so it creates its config folder.",
    "starnet2": "StarNet2 is configured inside SIRIL: open SIRIL > Preferences > External Programs "
                "and set the StarNet2 executable path. Download from https://www.starnetastro.com/ "
                "if you don't have it yet.",
}


def check_binary(name: str, path) -> CheckResult:
    if path:
        return CheckResult(name, True, f"found: {path}")
    help_text = _TOOL_HELP.get(name, f"Install {name}.")
    return CheckResult(name, False, "not found on PATH or known locations",
                       f"{help_text}\n         Or set its path manually in aporntool.config.json "
                       f'under tool_paths.{name}, then re-run.')


def check_graxpert_models(model_root, need=("bge", "denoise")) -> CheckResult:
    # GraXpert's CLI won't download models on a fresh machine — verify they already exist.
    missing = []
    for kind in need:
        d = Path(model_root) / f"{kind}-ai-models"
        if not (d.exists() and any(d.rglob("*.onnx"))):
            missing.append(kind)
    if not missing:
        return CheckResult("graxpert-models", True, "bge + denoise models present")
    return CheckResult(
        "graxpert-models", False,
        f"missing model(s): {', '.join(missing)}",
        "Open GraXpert once and run Background Extraction + Denoise on any image (or use its "
        "Model Manager) to download the AI models, then re-run the same command to continue.")


def run_preflight(mode, *, tool_paths, graxpert_model_root=None) -> list:
    # Build the full check list for the mode; the caller prints failures + remediations.
    results = [check_binary(t, tool_paths.get(t)) for t in MODE_TOOLS.get(mode, [])]
    if mode in MODE_NEEDS_GRAXPERT and graxpert_model_root is not None:
        results.append(check_graxpert_models(graxpert_model_root))
    return results
