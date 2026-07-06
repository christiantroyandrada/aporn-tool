from aporntool.config import Config, load_config, save_config


def test_defaults_are_seestar():
    c = Config.default()
    assert c.seestar_focal_mm == 150.0 and c.seestar_pixel_um == 2.9
    assert c.tool_paths == {}


def test_missing_file_returns_defaults(tmp_path):
    c = load_config(tmp_path / "nope.json")
    assert c.seestar_focal_mm == 150.0


def test_roundtrip_and_override(tmp_path):
    p = tmp_path / "aporntool.config.json"
    c = Config.default()
    c.tool_paths["siril"] = "/opt/siril"
    c.seestar_focal_mm = 250.0
    save_config(c, p)
    loaded = load_config(p)
    assert loaded.tool_paths["siril"] == "/opt/siril"
    assert loaded.seestar_focal_mm == 250.0
    # Unspecified fields keep their defaults.
    assert loaded.seestar_pixel_um == 2.9
