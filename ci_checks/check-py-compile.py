#!/usr/bin/env python3
"""Every tracked Python file compiles (an advisory check; ci_checks/run_all.sh, and the CI job `unit-tests`, where it fails
the job).

A SyntaxError in a file nobody imports in a test (a benchmark's service, a grader, a task's tooling) otherwise surfaces
only in a trial. For each file of `git ls-files '*.py'` this compiles the source with compile() (no import, no module
code run, no .pyc written) under the running Python (CI: 3.12). EXCLUDE lists the tracked files that deliberately do not
compile under it (none today). Standard library only.
Usage: check-py-compile.py [paths...]   (default: every tracked .py file; the given files or directories otherwise)
"""
from __future__ import annotations

import subprocess
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE: tuple[str, ...] = ()   # repository-relative paths (or directory prefixes ending in /) that are not Python 3 sources


def tracked(paths: list[str]) -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--", *(paths or ["*.py"])],
                         capture_output=True, check=True).stdout.decode()
    return sorted(f for f in out.split("\0") if f.endswith(".py"))


def main(argv: list[str]) -> int:
    paths = [str(Path(a).resolve().relative_to(ROOT)) if Path(a).exists() else a for a in argv]
    files = [f for f in tracked(paths) if not any(f == e or (e.endswith("/") and f.startswith(e)) for e in EXCLUDE)]
    if not files:
        print("FAIL check-py-compile: no tracked .py file" + (f" under {' '.join(argv)}" if argv else ""))
        return 1
    bad = 0
    for f in files:
        p = ROOT / f
        if not p.is_file():          # deleted in the working tree, not yet in the index
            continue
        try:
            with warnings.catch_warnings():    # a SyntaxWarning (an invalid escape) is not a failure here
                warnings.simplefilter("ignore")
                compile(p.read_bytes(), f, "exec", dont_inherit=True)
        except (SyntaxError, ValueError) as e:
            bad += 1
            where = f"{f}:{e.lineno}" if isinstance(e, SyntaxError) and e.lineno else f
            print(f"FAIL {where}: {type(e).__name__}: {e.msg if isinstance(e, SyntaxError) else e}")
    if bad:
        print(f"check-py-compile: {bad} of {len(files)} tracked .py file(s) do not compile (Python {sys.version.split()[0]})")
        return 1
    print(f"ok check-py-compile: {len(files)} tracked .py file(s) compile (Python {sys.version.split()[0]})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
