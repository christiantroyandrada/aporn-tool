from aporntool.manifest import (
    Manifest, StageStatus, input_fingerprint, load_manifest, save_manifest,
)


def _demo():
    m = Manifest(mode="dso-galaxy", target="M31",
                 order=["stage", "register", "stack", "spcc", "crop", "finish"])
    return m


def test_next_pending_is_first_not_done():
    m = _demo()
    m.mark("stage", StageStatus.DONE)
    m.mark("register", StageStatus.DONE)
    assert m.next_pending() == "stack"


def test_failed_stage_is_next():
    m = _demo()
    m.mark("stage", StageStatus.DONE)
    m.mark("register", StageStatus.FAILED)
    assert m.next_pending() == "register"


def test_invalidate_from_resets_downstream_only():
    m = _demo()
    for s in ["stage", "register", "stack", "spcc"]:
        m.mark(s, StageStatus.DONE)
    m.invalidate_from("stack")               # e.g. feather changed
    assert m.stage("register").status == StageStatus.DONE.value   # upstream untouched
    assert m.stage("stack").status == StageStatus.PENDING.value   # this + downstream reset
    assert m.stage("spcc").status == StageStatus.PENDING.value


def test_fingerprint_changes_when_a_sub_is_added(tmp_path):
    a = tmp_path / "a.fit"; a.write_bytes(b"12345")
    fp1 = input_fingerprint([a])
    b = tmp_path / "b.fit"; b.write_bytes(b"67890")
    fp2 = input_fingerprint([a, b])
    assert fp1 != fp2


def test_manifest_roundtrip(tmp_path):
    m = _demo()
    m.input_fingerprint = "abc123"
    m.mark("stage", StageStatus.DONE, outputs=["x.fit"])
    p = tmp_path / "aporntool.json"
    save_manifest(m, p)
    loaded = load_manifest(p)
    assert loaded.mode == "dso-galaxy"
    assert loaded.input_fingerprint == "abc123"
    assert loaded.stage("stage").status == StageStatus.DONE.value
    assert loaded.stage("stage").outputs == ["x.fit"]
