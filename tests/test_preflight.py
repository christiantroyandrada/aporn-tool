from aporntool.preflight import (
    check_binary, check_graxpert_models, run_preflight, CheckResult,
)


def test_check_binary_ok_and_missing():
    assert check_binary("siril", "/usr/bin/siril").ok is True
    missing = check_binary("siril", None)
    assert missing.ok is False and missing.remediation   # has actionable text


def test_graxpert_models_missing(tmp_path):
    # Empty model root → both bge + denoise reported missing, with remediation.
    r = check_graxpert_models(tmp_path)
    assert r.ok is False
    assert "bge" in r.detail and "denoise" in r.detail
    assert "Model Manager" in r.remediation or "download" in r.remediation.lower()


def test_graxpert_models_present(tmp_path):
    for kind in ("bge", "denoise"):
        d = tmp_path / f"{kind}-ai-models" / "1.0.0"
        d.mkdir(parents=True)
        (d / "model.onnx").write_bytes(b"x")
    assert check_graxpert_models(tmp_path).ok is True


def test_run_preflight_emission_needs_only_siril(tmp_path):
    results = run_preflight("dso-emission-nebula",
                            tool_paths={"siril": "/usr/bin/siril"},
                            graxpert_model_root=tmp_path)
    names = {r.name for r in results}
    assert names == {"siril"}                # emission does NOT need GraXpert/StarNet


def test_run_preflight_mosaic_flags_missing_graxpert_model(tmp_path):
    results = run_preflight("dso-mosaic",
                            tool_paths={"siril": "/s", "graxpert": "/g", "starnet2": "/n"},
                            graxpert_model_root=tmp_path)   # empty → model check fails
    assert any(r.name == "graxpert-models" and not r.ok for r in results)
