from pathlib import Path
import aporntool.locations as loc


def test_windows_data_dir(monkeypatch):
    monkeypatch.setattr(loc.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\me\\AppData\\Local")
    assert loc.user_data_dir("GraXpert") == Path("C:\\Users\\me\\AppData\\Local") / "GraXpert"


def test_macos_data_dir(monkeypatch):
    monkeypatch.setattr(loc.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(loc.Path, "home", classmethod(lambda cls: Path("/Users/me")))
    assert loc.user_data_dir("GraXpert") == Path("/Users/me/Library/Application Support/GraXpert")


def test_linux_data_dir_uses_xdg(monkeypatch):
    monkeypatch.setattr(loc.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_DATA_HOME", "/home/me/.local/share")
    assert loc.user_data_dir("GraXpert") == Path("/home/me/.local/share/GraXpert")


def test_graxpert_model_root_nests_graxpert(monkeypatch):
    monkeypatch.setattr(loc.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_DATA_HOME", "/x")
    # GraXpert nests models under <data>/GraXpert/GraXpert/.
    assert loc.graxpert_model_root() == Path("/x/GraXpert/GraXpert")
