"""End-to-end cmd_mode: preprocess + finish stages combined into one pipeline (Task 3)."""
from pathlib import Path
import numpy as np
from astropy.io import fits
from aporntool.cli import main


def _write_fake_fits(path):
    # Auto-crop (the default) reads real FITS data from the golden anchor at stage run time, so
    # fakes standing in for SIRIL's anchor save must write valid FITS, not a bare "x" text file.
    # Full-frame signal (no border) means auto-crop resolves to None (nothing to trim/emit).
    arr = np.full((3, 10, 10), 0.5, np.float32)
    fits.writeto(str(path), arr, overwrite=True)


def _install_fakes(monkeypatch, tmp_path):
    # Pretend every tool is discoverable, and fake both run_siril (preprocess + finish) and
    # run_graxpert so a full mode run reaches real deliverables without launching real tools.
    monkeypatch.setattr("aporntool.cli.discover_tool", lambda name, **kw: "/usr/bin/" + name)

    # Preflight checks that GraXpert's AI models exist on disk (mosaic/reflection need them).
    # Point that check at a temp models dir with fake .onnx files so the test is hermetic,
    # instead of depending on whether this machine happens to have GraXpert models installed.
    models = tmp_path / "gxmodels"
    for kind in ("bge", "denoise"):
        d = models / f"{kind}-ai-models" / "v1"
        d.mkdir(parents=True, exist_ok=True)
        (d / "model.onnx").write_bytes(b"x")
    monkeypatch.setattr("aporntool.cli.graxpert_model_root", lambda: models)

    # Mosaic preflight also checks StarNet is configured inside SIRIL (starnet_exe); point it
    # at a real temp file so the test doesn't depend on this machine's SIRIL config.
    starnet = tmp_path / "starnet2"
    starnet.write_bytes(b"x")
    monkeypatch.setattr("aporntool.cli.siril_starnet_exe", lambda: str(starnet))

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
        _write_fake_fits(linear / f"{target}_Linear.fit")
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
    _install_fakes(monkeypatch, tmp_path)
    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    out = tmp_path / "out"
    code = main(["dso-emission-nebula", "--in", str(subs), "--out", str(out), "--target", "M8"])
    assert code == 0
    assert (out / "M8_final.tif").exists()


def test_mosaic_run_produces_final_deliverable(tmp_path, monkeypatch):
    _install_fakes(monkeypatch, tmp_path)
    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    out = tmp_path / "out"
    code = main(["dso-mosaic", "--in", str(subs), "--out", str(out), "--target", "M31"])
    assert code == 0
    assert (out / "M31_final.tif").exists()


def test_spaced_out_path_rejected_with_clear_error(tmp_path, monkeypatch, capsys):
    _install_fakes(monkeypatch, tmp_path)
    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    out = tmp_path / "out with spaces"
    code = main(["dso-emission-nebula", "--in", str(subs), "--out", str(out), "--target", "M8"])
    assert code == 1
    assert "must not contain spaces" in capsys.readouterr().out


def test_crop_and_no_crop_are_mutually_exclusive(tmp_path, capsys):
    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    out = tmp_path / "out"
    code = main(["dso-mosaic", "--in", str(subs), "--out", str(out),
                 "--target", "M31", "--crop", "0 0 10 10", "--no-crop"])
    assert code == 1
    assert "mutually exclusive" in capsys.readouterr().out


def test_clean_flag_parses_and_defaults_false():
    from aporntool.cli import build_parser
    p = build_parser()
    a = p.parse_args(["dso-mosaic", "--in", "x", "--out", "y", "--target", "M31", "--clean"])
    assert a.clean is True
    b = p.parse_args(["dso-mosaic", "--in", "x", "--out", "y", "--target", "M31"])
    assert b.clean is False


def test_clean_flag_removes_work_keeps_anchor(tmp_path, monkeypatch):
    # On success, --clean deletes the bulky working files but keeps the golden anchor + manifest.
    _install_fakes(monkeypatch, tmp_path)
    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    out = tmp_path / "out"
    code = main(["dso-mosaic", "--in", str(subs), "--out", str(out),
                 "--target", "M31", "--clean"])
    assert code == 0
    work = out / "_work" / "M31"
    assert (out / "M31_final.tif").exists()                       # deliverables kept at root
    assert (work / "02_linear" / "M31_Linear.fit").exists()       # golden anchor kept
    assert (work / "aporntool.json").exists()                     # manifest kept (resume survives)
    assert not (work / "01_process").exists()                     # bulky dirs gone
    assert not (work / "03_graxpert").exists()
    assert not (work / "05_finish").exists()
    assert not (work / "00_lights").exists()
    assert not (work / "02_linear" / "M31_cropped.fit").exists()  # disposable cropped anchor gone


def test_without_clean_flag_all_work_is_retained(tmp_path, monkeypatch):
    # Default (no --clean): every working file is retained.
    _install_fakes(monkeypatch, tmp_path)
    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    out = tmp_path / "out"
    code = main(["dso-mosaic", "--in", str(subs), "--out", str(out), "--target", "M31"])
    assert code == 0
    work = out / "_work" / "M31"
    assert (work / "01_process").exists()                         # retained by default
    assert (work / "02_linear" / "M31_Linear.fit").exists()


def test_clean_does_not_fire_on_failure(tmp_path, monkeypatch):
    # If the pipeline fails, --clean must NOT delete working files (resume must still work).
    _install_fakes(monkeypatch, tmp_path)
    import aporntool.stages.finish as fin

    def boom(*a, **k):
        raise RuntimeError("StarNet exploded")
    monkeypatch.setattr(fin, "run_graxpert", boom)   # make the mosaic bge stage fail

    subs = tmp_path / "subs"; subs.mkdir()
    (subs / "Light_0001.fit").write_bytes(b"x")
    out = tmp_path / "out"
    code = main(["dso-mosaic", "--in", str(subs), "--out", str(out),
                 "--target", "M31", "--clean"])
    assert code == 1
    work = out / "_work" / "M31"
    # anchor from the successful preprocess must still be there for resume
    assert (work / "02_linear" / "M31_Linear.fit").exists()
    assert (work / "00_lights").exists()             # NOT cleaned — run did not succeed
