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


def test_graxpert_model_root_flat_default_on_linux(monkeypatch):
    # Fresh machine (no models on disk): macOS/Linux put the model dirs directly under the
    # app-data dir — NOT in a second nested GraXpert/ (that layout is Windows-only).
    monkeypatch.setattr(loc.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_DATA_HOME", "/x")
    assert loc.graxpert_model_root() == Path("/x/GraXpert")


def test_graxpert_model_root_nested_default_on_windows(monkeypatch):
    # Fresh machine on Windows: models nest under %LOCALAPPDATA%\\GraXpert\\GraXpert\\.
    monkeypatch.setattr(loc.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", "C:\\AD")
    assert loc.graxpert_model_root() == Path("C:\\AD") / "GraXpert" / "GraXpert"


def test_graxpert_model_root_detects_flat_layout(tmp_path, monkeypatch):
    # Models actually present directly under the app-data dir (macOS/Linux) → use that dir.
    monkeypatch.setattr(loc.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    (tmp_path / "GraXpert" / "bge-ai-models").mkdir(parents=True)
    assert loc.graxpert_model_root() == tmp_path / "GraXpert"


def test_graxpert_model_root_detects_nested_layout(tmp_path, monkeypatch):
    # Models present in the nested GraXpert/ (Windows layout) → detect it even off-Windows.
    monkeypatch.setattr(loc.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    (tmp_path / "GraXpert" / "GraXpert" / "denoise-ai-models").mkdir(parents=True)
    assert loc.graxpert_model_root() == tmp_path / "GraXpert" / "GraXpert"


def test_siril_config_dir_macos_prefers_org_siril_when_present(tmp_path, monkeypatch):
    # SIRIL 1.4.x macOS app uses <AppSupport>/org.siril.Siril/siril/; pick it when it has a config.
    monkeypatch.setattr(loc.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(loc.Path, "home", classmethod(lambda cls: tmp_path))
    d = tmp_path / "Library" / "Application Support" / "org.siril.Siril" / "siril"
    d.mkdir(parents=True)
    (d / "config.1.4.ini").write_text("", encoding="utf-8")
    assert loc.siril_config_dir() == d


def test_siril_config_dir_macos_falls_back_to_legacy_when_that_has_config(tmp_path, monkeypatch):
    monkeypatch.setattr(loc.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(loc.Path, "home", classmethod(lambda cls: tmp_path))
    legacy = tmp_path / "Library" / "Application Support" / "siril"
    legacy.mkdir(parents=True)
    (legacy / "config.1.2.ini").write_text("", encoding="utf-8")
    assert loc.siril_config_dir() == legacy


def test_siril_config_dir_macos_default_is_org_siril_when_none_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(loc.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(loc.Path, "home", classmethod(lambda cls: tmp_path))
    exp = tmp_path / "Library" / "Application Support" / "org.siril.Siril" / "siril"
    assert loc.siril_config_dir() == exp


def test_siril_starnet_exe_reads_config(tmp_path, monkeypatch):
    d = tmp_path / "siril"; d.mkdir()
    (d / "config.1.4.ini").write_text("foo=bar\nstarnet_exe=/usr/local/bin/starnet2\nbaz=1\n",
                                      encoding="utf-8")
    monkeypatch.setattr(loc, "siril_config_dir", lambda: d)
    assert loc.siril_starnet_exe() == "/usr/local/bin/starnet2"


def test_siril_starnet_exe_empty_when_unset(tmp_path, monkeypatch):
    d = tmp_path / "siril"; d.mkdir()
    (d / "config.1.4.ini").write_text("starnet_exe=\n", encoding="utf-8")
    monkeypatch.setattr(loc, "siril_config_dir", lambda: d)
    assert loc.siril_starnet_exe() == ""
