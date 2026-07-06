from aporntool.stages.preprocess import (
    convert_cmds, calibrate_cmds, register_cmds, stack_cmds, mirrorx_cmds,
    is_single_panel, spcc_in_preprocess,
)


def test_calibrate_debayers_no_darks():
    assert calibrate_cmds() == ["calibrate light -debayer"]


def test_mosaic_register_uses_wcs_and_framing_max():
    cmds = register_cmds("dso-mosaic")
    joined = " ".join(cmds)
    assert "seqplatesolve pp_light" in joined      # WCS assembly path
    assert "-framing=max" in joined


def test_single_panel_register_uses_2pass():
    cmds = register_cmds("dso-emission-nebula")
    joined = " ".join(cmds)
    assert "register pp_light -2pass" in joined
    assert "-framing=max" not in joined


def test_star_cluster_adds_wfwhm_cull():
    joined = " ".join(register_cmds("dso-star-cluster"))
    assert "-filter-round=2.5k" in joined and "-filter-wfwhm=2.5k" in joined


def test_mosaic_stack_has_feather_100():
    joined = " ".join(stack_cmds("dso-mosaic"))
    assert "-feather=100" in joined and "-out=result" in joined


def test_single_panel_stack_has_no_feather():
    joined = " ".join(stack_cmds("dso-emission-nebula"))
    assert "-feather" not in joined


def test_mirrorx_only_single_panel():
    assert is_single_panel("dso-emission-nebula") is True
    assert is_single_panel("dso-mosaic") is False
    assert mirrorx_cmds() == ["mirrorx_single result"]


def test_spcc_in_preprocess_flags():
    assert spcc_in_preprocess("dso-mosaic") is True
    assert spcc_in_preprocess("dso-reflection-nebula") is True
    assert spcc_in_preprocess("dso-emission-nebula") is False   # emission SPCCs in finish
    assert spcc_in_preprocess("dso-star-cluster") is False
