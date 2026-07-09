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


# --- guards: a missing / corrupt / partial / hand-edited config must never crash; defaults apply ---
import json as _json
from aporntool.config import Config, load_config, save_config


def test_absent_config_uses_defaults(tmp_path):
    c = load_config(tmp_path / "nope.json")
    assert c.pipeline.mosaic_finish.ght_d == 0.8 and c.seestar_focal_mm == 150.0


def test_corrupt_config_falls_back_without_crashing(tmp_path, capsys):
    p = tmp_path / "bad.json"; p.write_text("{ not valid json ]", encoding="utf-8")
    c = load_config(p)
    assert c.pipeline.stack.sigma_low == 3.0
    assert "using built-in defaults" in capsys.readouterr().out


def test_partial_override_keeps_sibling_defaults(tmp_path):
    p = tmp_path / "part.json"
    _json.dump({"pipeline": {"mosaic_finish": {"ght_d": 1.1}}, "seestar_focal_mm": 250}, open(p, "w"))
    c = load_config(p)
    assert c.pipeline.mosaic_finish.ght_d == 1.1
    assert c.pipeline.mosaic_finish.ght_b == 3.0
    assert c.pipeline.stack.sigma_low == 3.0
    assert c.seestar_focal_mm == 250


def test_unknown_keys_and_wrong_types_ignored(tmp_path):
    p = tmp_path / "weird.json"
    _json.dump({"pipeline": {"bogus_group": {"x": 1}, "graxpert": "not-a-dict",
                             "crop": {"bg_frac": "high", "margin_frac": 0.05}},
                "unknown_top": 5}, open(p, "w"))
    c = load_config(p)
    assert c.pipeline.crop.bg_frac == 0.25
    assert c.pipeline.crop.margin_frac == 0.05
    assert c.pipeline.graxpert.denoise_strength == 0.8


def test_save_writes_full_editable_template(tmp_path):
    p = tmp_path / "rt.json"; save_config(Config.default(), p)
    data = _json.load(open(p))
    assert "reflection_finish" in data["pipeline"] and "stack" in data["pipeline"]
    assert load_config(p).pipeline.spcc.sensor == "Sony IMX662"
