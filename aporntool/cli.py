"""Command-line entry point. Parses args and dispatches to a subcommand."""
import argparse

import aporntool


def build_parser() -> argparse.ArgumentParser:
    # Top-level parser; subcommands (config/status/<mode>) are added in later tasks.
    parser = argparse.ArgumentParser(prog="aporntool", description="Astropornography tool")
    # action="version" prints "aporntool <version>" and raises SystemExit(0) automatically.
    parser.add_argument(
        "--version", action="version", version=f"aporntool {aporntool.__version__}"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    # Returns a process exit code (0 = success) so tests can assert on it.
    parser = build_parser()
    parser.parse_args(argv)
    return 0
