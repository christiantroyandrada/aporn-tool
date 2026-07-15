from pathlib import Path
import numpy as np
from astropy.io import fits
from aporntool.cli import main


def _write_fake_fits(path):
    # Auto-crop (the default) reads real FITS data from the golden anchor at stage run time, so
    # fakes standing in for SIRIL's anchor save must write valid FITS, not a bare "x" text file.
    arr = np.full((3, 10, 10), 0.5, np.float32)
    fits.writeto(str(path), arr, overwrite=True)


def _install_fake_siril(monkeypatch, tmp_home, calls):
    # Pretend all tools are found, and make run_siril a no-op that fabricates each stage's output
    # so the pipeline advances to the golden anchor without real SIRIL. `calls` records the stage
    # name (script filename) of every invocation so tests can assert whether a stage was re-run.
    monkeypatch.setattr("aporntool.cli.discover_tool", lambda name, **kw: "/usr/bin/" + name)

    import aporntool.stages.preprocess as pp
    import aporntool.stages.finish as fin

    def fake_run_siril(script_path, *, workdir, siril_exe, runner=None, log_path=None):
        # Read which stage this is from the script filename and touch its expected output.
        name = Path(script_path).stem
        calls.append(name)
        proc = Path(workdir) / "01_process"
        proc.mkdir(parents=True, exist_ok=True)
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
        _write_fake_fits(linear / f"{target}_Linear.fit")
        if name == "finish":
            # The finish stage (emission/cluster) writes deliverables at the --out root (one
            # level above _work/<target>); SIRIL's `save` produces .fit, which the stage then
            # renames to .fits (FR-27's deliverable name).
            out_root = Path(workdir).parent.parent
            (out_root / f"{target}_final.fit").write_text("x", encoding="utf-8")
            for ext in ("tif", "png", "jpg"):
                (out_root / f"{target}_final.{ext}").write_text("x", encoding="utf-8")
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()

    def fake_run_composite_finish(clean_fits, out_stem, *, mode, starnet_exe, runner=None,
                                  scratch_dir=None, params=None, star_strength=None, jpeg_quality=95):
        # Emission/mosaic finish is now the composite dual-layer — fabricate its four deliverables.
        for ext in ("fits", "tif", "png", "jpg"):
            p = Path(f"{out_stem}.{ext}"); p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x", encoding="utf-8")
        return Path(f"{out_stem}.tif")

    monkeypatch.setattr(pp, "run_siril", fake_run_siril)
    monkeypatch.setattr(fin, "run_siril", fake_run_siril)
    monkeypatch.setattr(fin, "run_composite_finish", fake_run_composite_finish)


def test_emission_run_reaches_golden_anchor(capsys, tmp_path, monkeypatch):
    _install_fake_siril(monkeypatch, tmp_path, [])
    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    out = tmp_path / "out"
    code = main(["dso-emission-nebula", "--in", str(subs), "--out", str(out), "--target", "M8"])
    assert code == 0
    assert (out / "_work" / "M8" / "02_linear" / "M8_Linear.fit").exists()
    # Finish stages now run too (Task 3), so the pipeline reaches deliverables, not just the anchor.
    assert "deliverables" in capsys.readouterr().out.lower()


def test_rerun_is_idempotent_and_resumes(capsys, tmp_path, monkeypatch):
    calls = []
    _install_fake_siril(monkeypatch, tmp_path, calls)
    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    out = tmp_path / "out"
    args = ["dso-emission-nebula", "--in", str(subs), "--out", str(out), "--target", "M8"]
    assert main(args) == 0
    assert len(calls) >= 4                 # run 1 executed the preprocess stages
    calls.clear()
    assert main(args) == 0                 # run 2: all stages already done
    assert calls == []                     # resume → NO stage re-run (this is the regression guard)
