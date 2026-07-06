"""End-to-end cmd_mode: preprocess + finish stages combined into one pipeline (Task 3)."""
from pathlib import Path
from aporntool.cli import main


def _install_fakes(monkeypatch):
    # Pretend every tool is discoverable, and fake both run_siril (preprocess + finish) and
    # run_graxpert so a full mode run reaches real deliverables without launching real tools.
    monkeypatch.setattr("aporntool.cli.discover_tool", lambda name, **kw: "/usr/bin/" + name)

    import aporntool.stages.preprocess as pp
    import aporntool.stages.finish as fin

    def fake_run_siril(script_path, *, workdir, siril_exe, runner=None, log_path=None):
        name = Path(script_path).stem
        proc = Path(workdir) / "01_process"
        proc.mkdir(parents=True, exist_ok=True)
        {
            "calibrate": proc / "pp_light_.seq",
            "platesolve": proc / "pp_light_.seq",
            "applyreg": proc / "r_pp_light_.seq",
            "register": proc / "r_pp_light_.seq",
        }.get(name, proc / "result.fit").write_text("x", encoding="utf-8")
        (proc / "result.fit").write_text("x", encoding="utf-8")
        # Emulate the anchor save that the last preprocess stage performs.
        linear = Path(workdir) / "02_linear"
        linear.mkdir(parents=True, exist_ok=True)
        target = Path(workdir).name           # workdir == _work/<target>
        (linear / f"{target}_Linear.fit").write_text("x", encoding="utf-8")
        if name == "crop":
            # mosaic bge stage: SIRIL crop writes <TARGET>_cropped.fit into 02_linear.
            (linear / f"{target}_cropped.fit").write_text("x", encoding="utf-8")
        if name == "finish":
            script_text = Path(script_path).read_text(encoding="utf-8")
            if "starnet" in script_text:
                # mosaic finish: runs in the ws.finish scratch cwd with BARE names; the real
                # stage copies deliverables out to the --out root afterward.
                scratch = Path(workdir) / "05_finish"
                scratch.mkdir(parents=True, exist_ok=True)
                for ext in ("fit", "tif", "png", "jpg"):
                    (scratch / f"{target}_final.{ext}").write_text("x", encoding="utf-8")
            else:
                # emission/cluster finish writes deliverables directly at the --out root
                # (SIRIL only ever produces .fit; the stage renames it to .fits).
                out_root = Path(workdir).parent.parent
                (out_root / f"{target}_final.fit").write_text("x", encoding="utf-8")
                for ext in ("tif", "png", "jpg"):
                    (out_root / f"{target}_final.{ext}").write_text("x", encoding="utf-8")

        class R: returncode = 0; stdout = ""; stderr = ""
        return R()

    def fake_run_graxpert(argv, out_path, *, runner=None, poll=0.5, settle=0.0,
                          timeout=600.0, sleep=None):
        # Fabricate the .fits GraXpert would have written (mosaic bge/denoise stages).
        out_path = Path(out_path)
        fits_path = out_path if out_path.suffix == ".fits" else Path(str(out_path) + ".fits")
        fits_path.write_text("x", encoding="utf-8")
        return fits_path

    monkeypatch.setattr(pp, "run_siril", fake_run_siril)
    monkeypatch.setattr(fin, "run_siril", fake_run_siril)
    monkeypatch.setattr(fin, "run_graxpert", fake_run_graxpert)


def test_emission_run_produces_final_deliverable(tmp_path, monkeypatch):
    _install_fakes(monkeypatch)
    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    out = tmp_path / "out"
    code = main(["dso-emission-nebula", "--in", str(subs), "--out", str(out), "--target", "M8"])
    assert code == 0
    assert (out / "M8_final.tif").exists()


def test_mosaic_run_produces_final_deliverable(tmp_path, monkeypatch):
    _install_fakes(monkeypatch)
    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    out = tmp_path / "out"
    code = main(["dso-mosaic", "--in", str(subs), "--out", str(out), "--target", "M31"])
    assert code == 0
    assert (out / "M31_final.tif").exists()


def test_spaced_out_path_rejected_with_clear_error(tmp_path, monkeypatch, capsys):
    _install_fakes(monkeypatch)
    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    out = tmp_path / "out with spaces"
    code = main(["dso-emission-nebula", "--in", str(subs), "--out", str(out), "--target", "M8"])
    assert code == 1
    assert "must not contain spaces" in capsys.readouterr().out
