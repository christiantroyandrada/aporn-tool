"""Tests for the aporntool CLI entry point (package version + --version flag)."""
import pytest

import aporntool
from aporntool.cli import main


def test_version_string_exists():
    # The package must expose a version we can show with --version.
    assert isinstance(aporntool.__version__, str) and aporntool.__version__


def test_main_version_flag_returns_zero(capsys):
    # `aporntool --version` prints the version and exits cleanly.
    # argparse's action="version" prints and raises SystemExit(0) rather than returning,
    # so we must catch that exit instead of asserting on a return value.
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert aporntool.__version__ in capsys.readouterr().out
