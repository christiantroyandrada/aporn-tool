from pathlib import Path
from aporntool.tools.siril import build_ssf, write_ssf, run_siril, SirilResult, gaia_catalog_cmds, platesolve_cmd, spcc_cmd


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


def test_gaia_catalog_cmds_set_both_paths():
    cmds = gaia_catalog_cmds("/g/astro.dat", "/g/xpsamp")
    assert any("catalogue_gaia_astro=/g/astro.dat" in c for c in cmds)
    assert any("catalogue_gaia_photo=/g/xpsamp" in c for c in cmds)


def test_platesolve_uses_localgaia_and_coords():
    c = platesolve_cmd(coords="11.25,41.4", focal=150, pixel=2.9)
    assert c.startswith("platesolve 11.25,41.4")
    assert "-focal=150" in c and "-pixelsize=2.9" in c and "-catalog=localgaia" in c


def test_platesolve_blind_when_no_coords():
    # In finish we platesolve the already-framed image with no seed coords.
    assert platesolve_cmd() == "platesolve -catalog=localgaia"


def test_spcc_quotes_whole_token_including_flag_name():
    c = spcc_cmd()
    # CRITICAL gotcha #3: the WHOLE space-containing token is quoted, flag name included.
    assert '"-oscsensor=Sony IMX662"' in c
    assert '"-oscfilter=UV/IR Block"' in c
    assert '"-whiteref=Average Spiral Galaxy"' in c
    assert "-catalog=localgaia" in c
    assert '-oscsensor="Sony IMX662"' not in c   # the WRONG form must never appear
