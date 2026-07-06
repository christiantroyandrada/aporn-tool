"""Run pipeline stages with checkpoint/resume: skip done stages, verify output, stop on failure."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from aporntool.manifest import StageStatus


@dataclass
class Stage:
    id: str
    run: Callable[[], None]        # does the work (e.g. runs a SIRIL script)
    produces: Callable[[], bool]   # returns True iff this stage's output now exists + is valid


_STAGE_HINTS = {
    "calibrate": "SIRIL could not link or debayer your subs. Check that your input folder "
                 "contains valid .fit files from your telescope.",
    "register": "SIRIL could not align your frames. Common causes: too few stars (cloudy subs), "
                "very short exposures, or corrupted files. Try removing bad subs and re-running.",
    "stack": "SIRIL stacking failed. This usually means registration left too few usable frames. "
             "Try loosening the quality filter or adding more subs.",
    "mirrorx": "SIRIL could not flip the stacked image. The stack file may be missing or corrupt.",
    "spcc": "Color calibration did not produce output. Plate-solving may have failed (dense star "
            "field or faint target). The pipeline will try a fallback automatically.",
    "bge": "Background extraction failed. GraXpert may have crashed or the input FITS is invalid. "
           "Check that GraXpert works manually on the same file.",
    "denoise": "AI denoising failed. GraXpert may have run out of GPU memory. Try closing other "
               "apps, or re-run (the pipeline resumes from this stage automatically).",
    "finish": "The final stretch/export stage failed. Check the SIRIL log for the specific error.",
}


def run_pipeline(manifest, stages, *, save, from_stage=None, redo=None, force=False,
                 log=print, log_dir=None) -> bool:
    target = redo or from_stage
    if target is not None:
        if target not in manifest.order:
            valid = ", ".join(manifest.order)
            log(f"Unknown stage '{target}'. Valid stages for this run: {valid}\n"
                f"  (Check spelling -- stage names are case-sensitive.)")
            return False
        manifest.invalidate_from(target)
    by_id = {s.id: s for s in stages}
    for sid in manifest.order:
        rec = manifest.stage(sid)
        if rec.status == StageStatus.DONE.value and not force:
            continue
        stage = by_id[sid]
        manifest.mark(sid, StageStatus.RUNNING); save(manifest)
        stage.run()
        if stage.produces():
            manifest.mark(sid, StageStatus.DONE, error=""); save(manifest)
        else:
            manifest.mark(sid, StageStatus.FAILED,
                          error=f"stage '{sid}' produced no valid output")
            save(manifest)
            hint = _STAGE_HINTS.get(sid, "")
            log(f"\nFAILED at stage '{sid}': the expected output file was not created.")
            if hint:
                log(f"  Likely cause: {hint}")
            if log_dir:
                logfile = Path(log_dir) / f"{sid}.log"
                if logfile.exists():
                    log(f"  Full log: {logfile}")
                    tail = logfile.read_text(encoding="utf-8", errors="replace").strip().splitlines()
                    if tail:
                        last = tail[-min(5, len(tail)):]
                        log("  Last few lines:")
                        for line in last:
                            log(f"    {line}")
            log(f"\n  To retry: re-run the same command (it resumes from '{sid}' automatically).")
            return False
    return True
