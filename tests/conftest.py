import pytest


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path, monkeypatch):
    # A mode run now auto-writes aporntool.config.json into CWD (out-of-the-box behaviour). Run every
    # test from its own tmp dir so that write never lands in the repo. Tests use absolute tmp_path
    # paths for --in/--out, so the chdir is side-effect-free for them.
    monkeypatch.chdir(tmp_path)
