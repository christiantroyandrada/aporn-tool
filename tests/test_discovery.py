from pathlib import Path
from aporntool.discovery import discover_tool


def test_config_path_wins_when_it_exists():
    got = discover_tool("siril", config_path="/opt/siril",
                        which=lambda n: "/usr/bin/siril", exists=lambda p: True)
    assert got == Path("/opt/siril")


def test_falls_back_to_path():
    got = discover_tool("siril", which=lambda n: "/usr/bin/siril", exists=lambda p: False)
    assert got == Path("/usr/bin/siril")


def test_falls_back_to_known_candidate():
    got = discover_tool("siril", candidates=["/A", "/B"],
                        which=lambda n: None, exists=lambda p: p == "/B")
    assert got == Path("/B")


def test_returns_none_when_nowhere():
    assert discover_tool("nope", which=lambda n: None, exists=lambda p: False) is None
