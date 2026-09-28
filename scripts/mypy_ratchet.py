#!/usr/bin/env python3
"""mypy over the whole package, held to a baseline that only shrinks.

The package does not pass the strict settings in [tool.mypy] yet; the
modules that do are gated on their own by scripts/typecheck.sh. This holds
the rest to where it stands today: `.mypy-baseline` lists every error mypy
reports, and a run fails when

* an error appears that the baseline does not list: fix it; or
* an error the baseline lists has gone: good - shrink the baseline with
  `--update` and commit it with the fix, so the error cannot come back.

Errors are compared by file, message and code, without line numbers, so an
edit above an old error does not make it new; the same error twice in one
file counts twice.

    python scripts/mypy_ratchet.py            # check, as CI does
    python scripts/mypy_ratchet.py --update   # rewrite the baseline
"""

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / ".mypy-baseline"
ERROR = re.compile(r"^(?P<path>[^:\s]+):(?P<line>\d+)(?::\d+)?: error: (?P<message>.+)$")
HEADER = (
    "# Every error `python -m mypy vechnost_bot` reports today, without line\n"
    "# numbers. scripts/mypy_ratchet.py fails on an error not listed here and\n"
    "# on one listed here that has gone; `--update` rewrites this file.\n"
)


def mypy_errors() -> list[tuple[str, str]]:
    """Each error mypy reports, as (baseline key, the line mypy printed)."""
    # `python -m mypy`, not `mypy`: see scripts/typecheck.sh.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "vechnost_bot",
            "--no-error-summary",
            "--no-pretty",
            "--no-color-output",
            "--show-error-codes",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):  # 2: mypy itself could not run
        sys.exit(f"mypy failed to run:\n{result.stdout}{result.stderr}")
    errors = []
    for line in result.stdout.splitlines():
        match = ERROR.match(line)
        if match:
            errors.append((f"{match['path']}: {match['message']}", line))
    return errors


def read_baseline() -> Counter[str]:
    if not BASELINE.exists():
        return Counter()
    return Counter(
        line
        for line in BASELINE.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--update", action="store_true", help="rewrite .mypy-baseline from what mypy reports now"
    )
    args = parser.parse_args()

    errors = mypy_errors()
    now = Counter(key for key, _ in errors)

    if args.update:
        BASELINE.write_text(
            HEADER + "".join(f"{key}\n" for key in sorted(now.elements())), encoding="utf-8"
        )
        print(f"{BASELINE.name}: {sum(now.values())} errors")
        return 0

    baseline = read_baseline()
    new = now - baseline
    gone = baseline - now

    if new:
        print(f"mypy: {sum(new.values())} error(s) the baseline does not list. Fix them:\n")
        for key, line in errors:
            if new[key]:
                print(f"  {line}")
                new[key] -= 1
        print()
    if gone:
        print(
            f"mypy: {sum(gone.values())} error(s) in {BASELINE.name} are fixed. Shrink the "
            "baseline so they stay fixed:\n\n    python scripts/mypy_ratchet.py --update\n"
        )
        for key in sorted(gone.elements()):
            print(f"  {key}")
        print()
    if new or gone:
        return 1
    print(f"mypy: {sum(now.values())} errors, all of them in {BASELINE.name}; nothing new.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
