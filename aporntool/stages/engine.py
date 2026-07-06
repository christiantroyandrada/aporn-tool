"""Run pipeline stages with checkpoint/resume: skip done stages, verify output, stop on failure."""
from dataclasses import dataclass
from typing import Callable

from aporntool.manifest import StageStatus


@dataclass
class Stage:
    id: str
    run: Callable[[], None]        # does the work (e.g. runs a SIRIL script)
    produces: Callable[[], bool]   # returns True iff this stage's output now exists + is valid


def run_pipeline(manifest, stages, *, save, from_stage=None, redo=None, force=False, log=print) -> bool:
    # Decide where to (re)start. --force reruns all; --redo/--from reset from a named stage
    # downstream (invalidation, FR-24e); otherwise resume at the first not-done stage.
    if redo or from_stage:
        manifest.invalidate_from(redo or from_stage)
    by_id = {s.id: s for s in stages}
    for sid in manifest.order:
        rec = manifest.stage(sid)
        if rec.status == StageStatus.DONE.value and not force:
            continue                                  # already done → skip (resume)
        stage = by_id[sid]
        manifest.mark(sid, StageStatus.RUNNING); save(manifest)
        stage.run()
        if stage.produces():
            manifest.mark(sid, StageStatus.DONE, error=""); save(manifest)
        else:
            manifest.mark(sid, StageStatus.FAILED,
                          error=f"stage '{sid}' produced no valid output")
            save(manifest)
            log(f"FAILED at stage '{sid}': no valid output. Fix, then re-run to continue.")
            return False
    return True
