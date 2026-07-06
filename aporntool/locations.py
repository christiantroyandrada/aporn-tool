"""Resolve per-OS application-data directories (GraXpert models, SIRIL config)."""
import os
import platform
from pathlib import Path


def user_data_dir(app: str) -> Path:
    """Return the OS-specific app-data directory for the given app name.

    - Windows: LOCALAPPDATA/<app>
    - macOS: ~/Library/Application Support/<app>
    - Linux/other: $XDG_DATA_HOME/<app> (defaults to ~/.local/share/<app>)
    """
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / app
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / app
    # Linux / other: follow the XDG base-directory spec.
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / app


def graxpert_model_root() -> Path:
    """Return the GraXpert AI models root directory (the dir holding {bge,denoise}-ai-models/).

    GraXpert's layout differs per OS: on Windows the model dirs live in a *second*, nested
    GraXpert folder (%LOCALAPPDATA%\\GraXpert\\GraXpert\\{bge,denoise}-ai-models\\), while on
    macOS and Linux they sit directly under the app-data dir (no double nesting). Rather than
    hardcode one layout, detect whichever location actually holds the model dirs; if none exist
    yet (fresh machine), return the OS default so the preflight message points at the right place.
    """
    base = user_data_dir("GraXpert")
    nested = base / "GraXpert"
    for cand in (base, nested):
        if (cand / "bge-ai-models").exists() or (cand / "denoise-ai-models").exists():
            return cand
    return nested if platform.system() == "Windows" else base


def siril_config_dir() -> Path:
    """Return the OS-specific SIRIL configuration directory (the folder holding config*.ini).

    - Windows: LOCALAPPDATA/siril
    - macOS: the 1.4.x .app uses ~/Library/Application Support/org.siril.Siril/siril/; older or
      Homebrew builds used ~/Library/Application Support/siril/ — prefer whichever holds a config.
    - Linux/other: $XDG_CONFIG_HOME/siril (defaults to ~/.config/siril)
    """
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        candidates = [Path(base) / "siril"]
    elif system == "Darwin":
        appsup = Path.home() / "Library" / "Application Support"
        candidates = [appsup / "org.siril.Siril" / "siril", appsup / "siril"]
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
        candidates = [Path(base) / "siril"]
    # Use whichever candidate actually contains a SIRIL config; else the first (OS default).
    for c in candidates:
        if c.is_dir() and any(c.glob("config*.ini")):
            return c
    return candidates[0]


def siril_starnet_exe() -> str:
    """Return the StarNet executable configured INSIDE SIRIL (config key starnet_exe), or ''.

    The mosaic finish uses SIRIL's built-in `starnet` command, which runs whatever is set here —
    StarNet being on PATH is not enough. Reads the newest config*.ini in siril_config_dir().
    """
    try:
        inis = sorted(siril_config_dir().glob("config*.ini"), reverse=True)
    except OSError:
        return ""
    for ini in inis:
        try:
            for line in ini.read_text(errors="replace").splitlines():
                if line.startswith("starnet_exe="):
                    return line.split("=", 1)[1].strip().replace("\\\\", "\\")
        except OSError:
            continue
    return ""
