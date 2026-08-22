"""Run the suite and hold the calculation core to full branch coverage.

    .venv/Scripts/python.exe tools/verify_core.py

The core is the part that must not be wrong: the number formatting, the stack,
and both engines. The Qt layer around it is checked by the test suite too, but
is not held to this bar - it is mostly property plumbing, and the parts that
matter there are covered by `tests/test_backend_keys.py`.

Exits non-zero if any test fails or if the core drops below 100% of statements
and branches, so it is usable as a gate.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CORE = [
    "*/numeric.py",
    "*/stack.py",
    "*/rpn_engine.py",
    "*/alg_engine.py",
    "*/keymap.py",
]


def run(*arguments: str) -> int:
    return subprocess.run([sys.executable, "-m", *arguments], cwd=ROOT).returncode


def main() -> int:
    try:
        import coverage  # noqa: F401
    except ImportError:
        print('coverage is missing. Run: pip install -e ".[dev]"', file=sys.stderr)
        return 1

    print("running the suite under branch coverage\n")
    if run("coverage", "run", "--branch", "--source=src/rpncalc", "-m", "pytest", "-q"):
        print("\ntests failed", file=sys.stderr)
        return 1

    print("\ncalculation core:")
    core = run(
        "coverage", "report", "--show-missing",
        f"--include={','.join(CORE)}", "--fail-under=100",
    )

    print("\neverything else (reported, not gated):")
    run("coverage", "report", "--show-missing", f"--omit={','.join(CORE)}")

    if core:
        print(
            "\nthe calculation core is below full branch coverage",
            file=sys.stderr,
        )
        return 1

    print("\ncore at 100% of statements and branches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
