"""Clean a path the way a drag-and-drop hands it over, across Windows/macOS/Linux."""
import os
import re
from pathlib import Path
from urllib.parse import urlparse, unquote


def _uri_to_path(uri: str) -> str:
    # Linux terminals drop a file:// URI, percent-encoded (e.g. spaces as %20).
    parsed = urlparse(uri)
    path = unquote(parsed.path)
    # Windows file URIs look like file:///C:/... — drop the slash before the drive letter.
    if re.match(r"/[A-Za-z]:", path):
        path = path[1:]
    return path


def sanitize_dropped_path(raw: str) -> Path:
    s = raw.strip()
    # Peel one layer of matching surrounding quotes (Windows adds them for spaced paths).
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1].strip()
    # Turn a file:// URI back into a normal filesystem path.
    if s.startswith("file://"):
        s = _uri_to_path(s)
    # Expand %VARS%/$VARS and a leading ~ so config-style paths resolve.
    s = os.path.expanduser(os.path.expandvars(s))
    # Drop a trailing separator, but never strip a bare root ("/" or "C:\\").
    stripped = s.rstrip("/\\")
    if stripped and not stripped.endswith(":"):
        s = stripped
    return Path(s)


def to_input_dir(path: Path) -> Path:
    # If the user dropped a single file, the folder they meant is its parent.
    return path.parent if path.is_file() else path
