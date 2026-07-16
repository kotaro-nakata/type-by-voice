#!/usr/bin/env python3
"""Build a clean VoiceTerm onedir bundle for the current operating system."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print(
            "PyInstaller is missing. Install build dependencies with: "
            f"{sys.executable} -m pip install -r requirements-build.txt",
            file=sys.stderr,
        )
        return 2

    for directory in (ROOT / "build", ROOT / "dist"):
        if directory.exists():
            shutil.rmtree(directory)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        str(ROOT / "VoiceTerm.spec"),
    ]
    print(f"[build] {' '.join(command)}")
    subprocess.run(command, cwd=ROOT, check=True)

    expected = ROOT / "dist" / (
        "VoiceTerm.app" if sys.platform == "darwin" else "VoiceTerm"
    )
    if not expected.exists():
        print(f"[error] Expected bundle was not created: {expected}", file=sys.stderr)
        return 1
    print(f"[ok] Bundle created: {expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
