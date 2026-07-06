import pytest
from aporntool.rigs import RigProfile, PROFILES, resolve_profile, detect_profile


def test_seestar_s30_specs():
    p = resolve_profile("seestar-s30")
    assert (p.focal_mm, p.pixel_um, p.sensor) == (150.0, 2.9, "IMX662")
    assert p.mirrorx is True and p.internal_calibration is True


def test_case_insensitive_lookup():
    assert resolve_profile("Seestar-S50").focal_mm == 250.0


def test_all_smart_scopes_present():
    for k in ("seestar-s30", "seestar-s30pro", "seestar-s50", "dwarf3", "dwarf-mini",
              "vespera-ii", "vespera-pro", "stellina", "evscope2", "odyssey"):
        assert k in PROFILES and PROFILES[k].internal_calibration is True


def test_dslr_needs_calibration_and_has_no_fixed_optics():
    p = resolve_profile("dslr")
    assert p.internal_calibration is False and p.focal_mm is None


def test_unknown_profile_lists_valid_keys():
    with pytest.raises(KeyError) as e:
        resolve_profile("nikon-p1000")
    assert "seestar-s30" in str(e.value)


def test_detect_from_instrume_header():
    assert detect_profile({"INSTRUME": "Seestar S30"}).key == "seestar-s30"
    assert detect_profile({"TELESCOP": "DWARF3"}).key == "dwarf3"
    assert detect_profile({"INSTRUME": "Vaonis Vespera"}).key == "vespera-ii"
    assert detect_profile({"INSTRUME": "Canon EOS 6D"}) is None
