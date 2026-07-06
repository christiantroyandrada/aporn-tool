"""Find an external tool: an explicit config path, then PATH, then known install spots."""
import shutil
from pathlib import Path


def discover_tool(name, *, config_path=None, candidates=(), which=shutil.which, exists=None):
    # `exists` is injectable so tests don't depend on the real filesystem.
    exists = exists or (lambda p: Path(p).exists())
    # 1) An explicit path from the user's config wins — but only if it's really there.
    if config_path and exists(config_path):
        return Path(config_path)
    # 2) Anything on PATH (the normal case once a tool is installed).
    found = which(name)
    if found:
        return Path(found)
    # 3) Known per-machine install locations (filled from config/registry by the caller).
    for candidate in candidates:
        if exists(candidate):
            return Path(candidate)
    # 4) Nowhere — caller turns this into an actionable preflight failure.
    return None
