from pathlib import Path
from aporntool.paths import sanitize_dropped_path, to_input_dir


def test_strips_double_quotes_and_trailing_space():
    # Windows wraps spaced paths in quotes; a drop often leaves a trailing space.
    assert sanitize_dropped_path('"C:\\Astro\\M 31 subs" ') == Path("C:\\Astro\\M 31 subs")


def test_strips_single_quotes():
    assert sanitize_dropped_path("'/home/me/subs'") == Path("/home/me/subs")


def test_strips_trailing_separator():
    assert sanitize_dropped_path("/home/me/subs/") == Path("/home/me/subs")


def test_expands_env_var(monkeypatch):
    monkeypatch.setenv("MYDIR", "/data/lights")
    assert sanitize_dropped_path("$MYDIR") == Path("/data/lights")


def test_decodes_linux_file_uri():
    # GNOME/Konsole hand over percent-encoded file:// URIs on drop.
    assert sanitize_dropped_path("file:///home/me/M%2031") == Path("/home/me/M 31")


def test_decodes_windows_file_uri():
    assert sanitize_dropped_path("file:///C:/Astro/M%2031") == Path("C:/Astro/M 31")


def test_to_input_dir_maps_file_to_parent(tmp_path):
    # Dragging one .fit instead of the folder → use its parent.
    f = tmp_path / "Light_0001.fit"
    f.write_bytes(b"x")
    assert to_input_dir(f) == tmp_path


def test_to_input_dir_keeps_folder(tmp_path):
    assert to_input_dir(tmp_path) == tmp_path
