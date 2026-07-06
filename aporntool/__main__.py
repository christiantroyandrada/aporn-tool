"""Lets `python -m aporntool ...` work the same as the installed `aporntool` command."""
import sys

from aporntool.cli import main

if __name__ == "__main__":
    # Forward the process exit code from main() so shells/scripts see success/failure correctly.
    sys.exit(main())
