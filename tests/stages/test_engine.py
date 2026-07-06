from aporntool.manifest import Manifest, StageStatus
from aporntool.stages.engine import Stage, run_pipeline


def _mk(order):
    m = Manifest(mode="dso-emission-nebula", target="M8", order=order)
    return m


def _saver():
    saves = []
    return saves, (lambda m, *a, **k: saves.append(m.next_pending()))


def test_runs_all_and_marks_done():
    ran = []
    m = _mk(["a", "b"])
    stages = [Stage("a", lambda: ran.append("a"), lambda: True),
              Stage("b", lambda: ran.append("b"), lambda: True)]
    _, save = _saver()
    ok = run_pipeline(m, stages, save=save)
    assert ok is True and ran == ["a", "b"]
    assert m.stage("a").status == StageStatus.DONE.value
    assert m.stage("b").status == StageStatus.DONE.value


def test_skips_already_done_stages():
    ran = []
    m = _mk(["a", "b"])
    m.mark("a", StageStatus.DONE)               # a already done (resume)
    stages = [Stage("a", lambda: ran.append("a"), lambda: True),
              Stage("b", lambda: ran.append("b"), lambda: True)]
    _, save = _saver()
    run_pipeline(m, stages, save=save)
    assert ran == ["b"]                         # a was skipped


def test_stops_and_marks_failed_when_output_missing():
    ran = []
    m = _mk(["a", "b"])
    stages = [Stage("a", lambda: ran.append("a"), lambda: False),   # produces nothing
              Stage("b", lambda: ran.append("b"), lambda: True)]
    _, save = _saver()
    ok = run_pipeline(m, stages, save=save)
    assert ok is False
    assert m.stage("a").status == StageStatus.FAILED.value
    assert ran == ["a"]                         # b never runs after a fails


def test_redo_reruns_a_done_stage_and_downstream():
    ran = []
    m = _mk(["a", "b", "c"])
    for s in ("a", "b", "c"):
        m.mark(s, StageStatus.DONE)
    stages = [Stage(s, (lambda s=s: ran.append(s)), lambda: True) for s in ("a", "b", "c")]
    _, save = _saver()
    run_pipeline(m, stages, save=save, redo="b")
    assert ran == ["b", "c"]                    # b + downstream re-run; a untouched


def test_force_reruns_everything():
    ran = []
    m = _mk(["a", "b"])
    m.mark("a", StageStatus.DONE); m.mark("b", StageStatus.DONE)
    stages = [Stage("a", lambda: ran.append("a"), lambda: True),
              Stage("b", lambda: ran.append("b"), lambda: True)]
    _, save = _saver()
    run_pipeline(m, stages, save=save, force=True)
    assert ran == ["a", "b"]


def test_unknown_from_stage_fails_loud_without_running():
    ran = []
    m = _mk(["a", "b"])
    stages = [Stage("a", lambda: ran.append("a"), lambda: True),
              Stage("b", lambda: ran.append("b"), lambda: True)]
    _, save = _saver()
    msgs = []
    ok = run_pipeline(m, stages, save=save, from_stage="nosuch", log=msgs.append)
    assert ok is False
    assert ran == []                                  # nothing ran
    assert any("Unknown stage 'nosuch'" in msg for msg in msgs)
