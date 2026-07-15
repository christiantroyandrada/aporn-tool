import pytest
from aporntool.catalog import resolve_target, TARGETS


def test_known_target_case_and_space_insensitive():
    t = resolve_target("m 31")
    assert t.ra == 11.25 and t.dec == 41.4 and t.mode == "galaxy"


def test_cluster_present():
    assert resolve_target("M13").mode == "star-cluster"


def test_unknown_without_coords_raises():
    with pytest.raises(KeyError):
        resolve_target("NGC9999")


def test_unknown_with_coords_builds_target():
    t = resolve_target("NGC9999", coords="12.5,-3.25")
    assert t.ra == 12.5 and t.dec == -3.25 and t.mode == "unknown"


def test_bad_coords_raise_valueerror():
    with pytest.raises(ValueError):
        resolve_target("X", coords="12.5")        # missing DEC
    with pytest.raises(ValueError):
        resolve_target("X", coords="a,b")          # non-numeric
