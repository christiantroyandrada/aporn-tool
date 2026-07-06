"""Run GraXpert background-extraction + AI denoise; handle its .fits.fits output quirk."""
import subprocess
import time
from pathlib import Path


def bge_cmd(exe, in_path, out_path, *, gpu=True, smoothing=0.0) -> list:
    # Background extraction, Subtraction mode (the proven setting).
    return [str(exe), "-cli", "-cmd", "background-extraction",
            "-gpu", "true" if gpu else "false",
            "-smoothing", str(smoothing), "-correction", "Subtraction",
            "-output", str(out_path), str(in_path)]


def denoise_cmd(exe, in_path, out_path, *, gpu=True, strength=0.8) -> list:
    # AI denoise on the LINEAR image; 0.8 is the sweet spot (1.0 over-sharpens).
    return [str(exe), "-cli", "-cmd", "denoising",
            "-gpu", "true" if gpu else "false",
            "-strength", str(strength), "-output", str(out_path), str(in_path)]


def fix_double_ext(out_path) -> Path:
    # GraXpert appends .fits to -output, so `out` becomes `out.fits.fits`. Normalise to `out.fits`.
    out_path = Path(out_path)
    single = out_path.with_suffix(".fits") if out_path.suffix != ".fits" else out_path
    double = Path(str(single) + ".fits")
    if double.exists():
        if single.exists():
            single.unlink()
        double.rename(single)
    return single


def run_graxpert(argv, out_path, *, runner=subprocess.run, settle=0.0) -> Path:
    # Run GraXpert, wait for the write to settle (CLI can return early), then fix the extension.
    runner(argv, capture_output=True, text=True)
    if settle:
        time.sleep(settle)   # give the file system a moment; real callers pass a few seconds
    return fix_double_ext(out_path)
