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


import json
from aporntool.cli import main


def test_config_check_reports_missing_tools(capsys, tmp_path, monkeypatch):
    # No tools discoverable → config --check lists them and exits non-zero.
    monkeypatch.setattr("aporntool.cli.discover_tool", lambda name, **kw: None)
    cfg = tmp_path / "aporntool.config.json"
    code = main(["config", "--check", "--config", str(cfg)])
    out = capsys.readouterr().out
    assert code == 2
    assert "siril" in out and "graxpert" in out and "starnet2" in out
    assert cfg.exists()                     # a starter config is written


def test_mode_preflight_only_passes_when_tools_found(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr("aporntool.cli.discover_tool", lambda name, **kw: "/usr/bin/" + name)
    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    code = main(["dso-emission-nebula", "--in", str(subs),
                 "--out", str(tmp_path / "out"), "--target", "M8", "--preflight-only"])
    assert code == 0
    assert "preflight" in capsys.readouterr().out.lower()


def test_status_reads_manifest(capsys, tmp_path):
    from aporntool.workspace import Workspace
    from aporntool.manifest import Manifest, StageStatus, save_manifest
    ws = Workspace(tmp_path / "out", "M8"); ws.create()
    m = Manifest(mode="dso-emission-nebula", target="M8",
                 order=["stage", "stack", "finish"])
    m.mark("stage", StageStatus.DONE)
    save_manifest(m, ws.manifest_path)
    code = main(["status", "--out", str(tmp_path / "out"), "--target", "M8"])
    out = capsys.readouterr().out
    assert code == 0 and "stage" in out and "done" in out.lower()
