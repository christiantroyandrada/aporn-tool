from pathlib import Path
from aporntool.cli import main


def _install_fake_siril(monkeypatch, tmp_home):
    # Pretend all tools are found, and make run_siril a no-op that fabricates each stage's output
    # so the pipeline advances to the golden anchor without real SIRIL.
    monkeypatch.setattr("aporntool.cli.discover_tool", lambda name, **kw: "/usr/bin/" + name)

    import aporntool.stages.preprocess as pp

    def fake_run_siril(script_path, *, workdir, siril_exe, runner=None, log_path=None):
        # Read which stage this is from the script filename and touch its expected output.
        proc = Path(workdir) / "01_process"
        proc.mkdir(parents=True, exist_ok=True)
        name = Path(script_path).stem
        {
            "convert": proc / "light_.seq",
            "calibrate": proc / "pp_light_.seq",
            "register": proc / "r_pp_light_.seq",
        }.get(name, proc / "result.fit").write_text("x", encoding="utf-8")
        (proc / "result.fit").write_text("x", encoding="utf-8")
        # Emulate the anchor save that the last preprocess stage performs.
        linear = Path(workdir) / "02_linear"
        linear.mkdir(parents=True, exist_ok=True)
        target = Path(workdir).name           # workdir == _work/<target>
        (linear / f"{target}_Linear.fit").write_text("x", encoding="utf-8")
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()

    monkeypatch.setattr(pp, "run_siril", fake_run_siril)


def test_emission_run_reaches_golden_anchor(capsys, tmp_path, monkeypatch):
    _install_fake_siril(monkeypatch, tmp_path)
    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    out = tmp_path / "out"
    code = main(["dso-emission-nebula", "--in", str(subs), "--out", str(out), "--target", "M8"])
    assert code == 0
    assert (out / "_work" / "M8" / "02_linear" / "M8_Linear.fit").exists()
    assert "anchor" in capsys.readouterr().out.lower()


def test_rerun_is_idempotent_and_resumes(capsys, tmp_path, monkeypatch):
    _install_fake_siril(monkeypatch, tmp_path)
    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    out = tmp_path / "out"
    args = ["dso-emission-nebula", "--in", str(subs), "--out", str(out), "--target", "M8"]
    assert main(args) == 0
    # Second run: all stages already done → still exits 0 (resume, nothing to redo).
    assert main(args) == 0
