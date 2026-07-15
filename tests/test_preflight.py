from aporntool.preflight import (
    check_binary, check_graxpert_models, check_siril_starnet, run_preflight, CheckResult,
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


def test_run_preflight_emission_needs_siril_and_starnet(tmp_path):
    # Emission now runs the composite dual-layer finish (StarNet2 CLI directly, like reflection),
    # so it needs siril + starnet2 — but still NOT GraXpert (it uses SIRIL subsky/denoise).
    results = run_preflight("dso-emission-nebula",
                            tool_paths={"siril": "/usr/bin/siril", "starnet2": "/usr/bin/starnet2"},
                            graxpert_model_root=tmp_path)
    names = {r.name for r in results}
    assert names == {"siril", "starnet2"}


def test_run_preflight_mosaic_flags_missing_graxpert_model(tmp_path):
    results = run_preflight("dso-galaxy",
                            tool_paths={"siril": "/s", "graxpert": "/g", "starnet2": "/n"},
                            graxpert_model_root=tmp_path)   # empty → model check fails
    assert any(r.name == "graxpert-models" and not r.ok for r in results)


def test_check_siril_starnet_ok_when_configured(tmp_path):
    exe = tmp_path / "starnet2"; exe.write_bytes(b"x")
    assert check_siril_starnet(str(exe)).ok is True


def test_check_siril_starnet_fails_when_unset_or_missing(tmp_path):
    unset = check_siril_starnet("")
    assert unset.ok is False and unset.remediation
    missing = check_siril_starnet(str(tmp_path / "nope"))
    assert missing.ok is False and "missing" in missing.detail.lower()


def test_galaxy_preflight_needs_starnet2_binary_not_siril_internal(tmp_path):
    # Galaxy now runs the composite finish (StarNet2 CLI directly), so it needs the starnet2 BINARY
    # like reflection — but NOT StarNet configured inside SIRIL (that requirement is gone for all modes).
    for kind in ("bge", "denoise"):
        (tmp_path / f"{kind}-ai-models" / "1").mkdir(parents=True)
        (tmp_path / f"{kind}-ai-models" / "1" / "m.onnx").write_bytes(b"x")
    results = run_preflight("dso-galaxy",
                            tool_paths={"siril": "/s", "graxpert": "/g", "starnet2": "/usr/bin/starnet2"},
                            graxpert_model_root=tmp_path, siril_starnet_exe="")
    names = {r.name for r in results}
    assert "starnet2" in names                                   # needs the StarNet2 binary
    assert not any(r.name == "siril-starnet" for r in results)   # no SIRIL-internal requirement


def test_emission_preflight_has_no_siril_starnet_check(tmp_path):
    # Emission/cluster keep all stars → no SIRIL starnet requirement even if we pass the arg.
    results = run_preflight("dso-emission-nebula",
                            tool_paths={"siril": "/s"}, siril_starnet_exe="")
    assert not any(r.name == "siril-starnet" for r in results)
