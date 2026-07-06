from pathlib import Path
from aporntool.tools.graxpert import bge_cmd, denoise_cmd, fix_double_ext, run_graxpert


def test_bge_cmd_shape():
    c = bge_cmd("GraXpert.exe", "in.fit", "out", gpu=True, smoothing=0.0)
    assert c[0] == "GraXpert.exe"
    j = " ".join(c)
    assert "-cli" in c and "background-extraction" in j
    assert "-correction" in c and "Subtraction" in c
    assert "-gpu" in c and "true" in c


def test_denoise_cmd_has_strength():
    c = denoise_cmd("GraXpert.exe", "in.fit", "out", strength=0.8)
    assert "denoising" in " ".join(c) and "0.8" in " ".join(c)


def test_fix_double_ext_renames(tmp_path):
    # GraXpert writes out.fits.fits; we want out.fits.
    dd = tmp_path / "out.fits.fits"; dd.write_text("x", encoding="utf-8")
    final = fix_double_ext(tmp_path / "out")
    assert final == tmp_path / "out.fits"
    assert final.exists() and not dd.exists()


def test_fix_double_ext_noop_when_single(tmp_path):
    (tmp_path / "out.fits").write_text("x", encoding="utf-8")
    final = fix_double_ext(tmp_path / "out")
    assert final == tmp_path / "out.fits"


def test_run_graxpert_runs_then_fixes_extension(tmp_path):
    def fake_runner(cmd, **kw):
        # emulate GraXpert writing the double-extension file
        (tmp_path / "out.fits.fits").write_text("data", encoding="utf-8")
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    final = run_graxpert(["GraXpert.exe", "-cli"], tmp_path / "out", runner=fake_runner)
    assert final == tmp_path / "out.fits" and final.exists()


def test_fix_double_ext_append_semantics_for_nonfits_suffix(tmp_path):
    # out_path carries a .fit suffix → GraXpert wrote X.fit.fits (append). Must return the REAL file.
    real = tmp_path / "X.fit.fits"; real.write_text("d", encoding="utf-8")
    got = fix_double_ext(tmp_path / "X.fit")
    assert got.exists() and got == real          # not a phantom X.fits


def test_run_graxpert_size_poll_waits_then_returns(tmp_path):
    (tmp_path / "out.fits.fits").write_text("data", encoding="utf-8")   # already-stable double
    slept = []
    def fake_runner(cmd, **kw):
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    final = run_graxpert(["G", "-cli"], tmp_path / "out", runner=fake_runner,
                         settle=1.0, poll=0.5, sleep=lambda s: slept.append(s))
    assert final == tmp_path / "out.fits" and final.exists()
    assert slept                                  # the poll actually ran
