"""Run GraXpert background-extraction + AI denoise; handle its .fits.fits output quirk."""
import subprocess
import time
from pathlib import Path


def bge_cmd(exe, in_path, out_path, *, gpu=True, smoothing=0.0, correction="Subtraction") -> list:
    # Background extraction; Subtraction is the proven default (Division is the alternative).
    return [str(exe), "-cli", "-cmd", "background-extraction",
            "-gpu", "true" if gpu else "false",
            "-smoothing", str(smoothing), "-correction", str(correction),
            "-output", str(out_path), str(in_path)]


def denoise_cmd(exe, in_path, out_path, *, gpu=True, strength=0.8) -> list:
    # AI denoise on the LINEAR image; 0.8 is the sweet spot (1.0 over-sharpens).
    return [str(exe), "-cli", "-cmd", "denoising",
            "-gpu", "true" if gpu else "false",
            "-strength", str(strength), "-output", str(out_path), str(in_path)]


def fix_double_ext(out_path) -> Path:
    # GraXpert APPENDS ".fits" to -output (it does NOT replace an existing suffix): extension-less
    # "X" -> "X.fits"; "X.fits" -> "X.fits.fits". Return the real single-.fits file, renaming the
    # double down if present. Robust to whatever suffix out_path carries.
    out_path = Path(out_path)
    base = out_path if out_path.suffix == ".fits" else Path(str(out_path) + ".fits")
    double = Path(str(base) + ".fits")
    if double.exists():
        if base.exists():
            base.unlink()          # clear a stale single so rename can't fail on Windows
        double.rename(base)
    return base


def run_graxpert(argv, out_path, *, runner=subprocess.run, poll=0.5, settle=0.0,
                 timeout=600.0, proc_timeout=1200.0, sleep=time.sleep) -> Path:
    # proc_timeout caps the GraXpert subprocess itself: without it a GraXpert that hangs (e.g. it
    # runs out of memory on a very large DSLR image and stalls instead of exiting) would block the
    # whole pipeline forever. On timeout the child is killed and the stage fails cleanly (its
    # produces() check finds no output), so the run stops with a clear message instead of hanging.
    try:
        proc = runner(argv, capture_output=True, text=True, timeout=proc_timeout)
    except subprocess.TimeoutExpired:
        print(f"  WARNING: GraXpert did not finish within {int(proc_timeout)}s and was terminated. "
              f"This usually means the image is too large (memory) — try a smaller or downscaled "
              f"input. Failing this stage cleanly; re-run to resume.")
        return fix_double_ext(out_path)
    if proc.returncode != 0:
        _report_graxpert_error(proc)
    if settle > 0:
        _await_stable_output(out_path, poll=poll, settle=settle, timeout=timeout, sleep=sleep)
    return fix_double_ext(out_path)


def _report_graxpert_error(proc) -> None:
    # Surface a non-zero GraXpert exit with an actionable hint (GPU-memory is the common one).
    stderr = (proc.stderr or "").strip()
    print(f"  WARNING: GraXpert exited with code {proc.returncode}.")
    if "CUDA" in stderr or "out of memory" in stderr.lower():
        print("  This looks like a GPU memory issue. Try closing other apps or re-running.")
    elif stderr:
        print(f"  Last error line: {stderr.splitlines()[-1]}")


def _await_stable_output(out_path, *, poll, settle, timeout, sleep) -> None:
    # Wait until GraXpert's output file has stopped growing for `settle` seconds (it writes then
    # post-processes), bounded by `timeout`. GraXpert may write the double-.fits name (see
    # fix_double_ext), so watch whichever of the two exists.
    base = out_path if str(out_path).endswith(".fits") else Path(str(out_path) + ".fits")
    double = Path(str(base) + ".fits")
    waited = 0.0
    last = -1
    stable = 0.0
    while waited < timeout:
        target = double if double.exists() else Path(base)
        size = target.stat().st_size if target.exists() else -1
        if size >= 0 and size == last:
            stable += poll
            if stable >= settle:
                break
        else:
            stable = 0.0
            last = size
        sleep(poll)
        waited += poll
