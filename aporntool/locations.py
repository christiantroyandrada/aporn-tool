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
    """Return the GraXpert AI models root directory.

    GraXpert stores AI models under <data>/GraXpert/GraXpert/{bge,denoise}-ai-models/<ver>/.
    """
    return user_data_dir("GraXpert") / "GraXpert"


def siril_config_dir() -> Path:
    """Return the OS-specific SIRIL configuration directory.

    - Windows: LOCALAPPDATA/siril
    - macOS: ~/Library/Application Support/siril
    - Linux/other: $XDG_CONFIG_HOME/siril (defaults to ~/.config/siril)
    """
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / "siril"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "siril"
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "siril"
