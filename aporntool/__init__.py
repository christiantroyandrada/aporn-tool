"""aPornTool — turn raw astro subs into a finished image, one command per mode."""
from importlib.metadata import PackageNotFoundError, version

try:
    # Single source of truth: the installed distribution's version (from pyproject), so `--version`
    # can never drift from what `pip install` gave you.
    __version__ = version("aporn-tool")
except PackageNotFoundError:      # running from a source tree that isn't pip-installed
    __version__ = "0.0.0+dev"
