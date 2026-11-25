"""Run every check in one go: ruff (lint), mypy (types), privacy and the tests.

    uv run python scripts/check.py

GitHub runs the same on macOS and Windows on every push to main
(.github/workflows/build.yml).  Exit code 0 only when everything passed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CHECKS = [
    ("lint", [sys.executable, "-m", "ruff", "check", "."]),
    ("types", [sys.executable, "-m", "mypy"]),
    ("privacy", [sys.executable, str(ROOT / "scripts" / "privacy_check.py")]),
    ("tests", [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]),
]


def main() -> int:
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    results = {}
    for title, cmd in CHECKS:
        print(f"\n== {title}: {' '.join(Path(c).name if os.sep in c else c for c in cmd)}", flush=True)
        results[title] = subprocess.run(cmd, cwd=ROOT, env=env).returncode == 0
        print(f"== {title}: {'ok' if results[title] else 'FAILED'}", flush=True)
    print("\nSummary: " + ", ".join(f"{k} {'ok' if v else 'FAILED'}" for k, v in results.items()))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
