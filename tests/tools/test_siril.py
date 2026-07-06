from pathlib import Path
from aporntool.tools.siril import build_ssf, write_ssf, run_siril, SirilResult


def test_build_ssf_has_requires_header_and_commands():
    text = build_ssf(["calibrate light -debayer", "close"], requires="1.3.6")
    lines = text.splitlines()
    assert lines[0] == "requires 1.3.6"          # SIRIL scripts must declare a version floor
    assert "calibrate light -debayer" in lines
    assert lines[-1] == "close"


def test_build_ssf_optional_cd_is_quoted():
    text = build_ssf(["link light"], cd=r"C:\Astro\M 31")
    assert 'cd "C:\\Astro\\M 31"' in text     # spaced paths must be quoted


def test_write_ssf_roundtrips(tmp_path):
    p = write_ssf("requires 1.3.6\nclose\n", tmp_path / "s.ssf")
    assert p.read_text(encoding="utf-8").startswith("requires 1.3.6")


def test_run_siril_invokes_cli_with_abs_script_and_workdir(tmp_path):
    calls = {}
    def fake_runner(cmd, **kw):
        calls["cmd"] = cmd
        class R: returncode = 0; stdout = "ok"; stderr = ""
        return R()
    script = tmp_path / "s.ssf"; script.write_text("requires 1.3.6\n", encoding="utf-8")
    res = run_siril(script, workdir=tmp_path, siril_exe="/usr/bin/siril-cli", runner=fake_runner)
    assert isinstance(res, SirilResult) and res.returncode == 0
    # siril-cli needs -d <workdir> and -s <absolute script path>
    assert calls["cmd"][0] == "/usr/bin/siril-cli"
    assert "-d" in calls["cmd"] and str(tmp_path) in calls["cmd"]
    assert "-s" in calls["cmd"] and str(script.resolve()) in calls["cmd"]


def test_run_siril_writes_log(tmp_path):
    def fake_runner(cmd, **kw):
        class R: returncode = 0; stdout = "SIRIL says hi"; stderr = ""
        return R()
    script = tmp_path / "s.ssf"; script.write_text("requires 1.3.6\n", encoding="utf-8")
    log = tmp_path / "stage.log"
    run_siril(script, workdir=tmp_path, siril_exe="siril-cli", runner=fake_runner, log_path=log)
    assert "SIRIL says hi" in log.read_text(encoding="utf-8")
