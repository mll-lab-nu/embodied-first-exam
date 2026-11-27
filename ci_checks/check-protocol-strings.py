#!/usr/bin/env python3
"""One protocol: every standard and realtime task, service, client and document speaks `eai-standard/3.0`
(docs/protocol/standard_mode.md). A service's layer and capabilities are in its /spec (operations, timing.realtime,
kinematics, match), never in a version string. This check fails on any tracked text file (code, tasks, docs) that
names another protocol id of this family or keeps a list of accepted old ids:

  - `eai-standard/2.<n>` (any 2.x id, with or without `+match/...`);
  - `eai-standard-lockstep`, `eai-standard-realtime` (the match services' former ids);
  - `rcb-limited/` (the former name);
  - a list of accepted protocol ids: `COMPAT = [...]` / `COMPAT = (...)`, `protocol_compat`, `ACCEPTED = (...)`.

Nothing is allowlisted but this file. A benchmark's own runtime of another family (roboEngineer's `eai-policy/1.x`)
is not this family and is not flagged. Before the repository, the patterns run on built-in good and bad lines (each
pattern must flag its bad line and none may flag a good one), so a pattern that went blind fails here.
Exit 0: clean; 1: findings; 2: the check itself could not run.

    python3 ci_checks/check-protocol-strings.py [--repo DIR]
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve()
SELF = "ci_checks/check-protocol-strings.py"
OLD = "eai-standard/" + "2."            # (spelled in two pieces: this file names the patterns, it is never flagged)
PATTERNS = [
    ("a 2.x protocol id", re.compile(re.escape(OLD) + r"[0-9x_]")),
    ("a match service's former id", re.compile(r"eai-standard-(?:lockstep|realtime)\b")),
    ("the former name rcb-limited", re.compile(r"\brcb-limited/")),
    ("a list of accepted protocol ids", re.compile(r"(?m)^\s*(?:COMPAT|ACCEPTED|PROTOCOLS_ACCEPTED)\s*=\s*[\[(]|\bprotocol_compat\b")),
]
BAD = [OLD + "1", OLD + "4+match/1.0", "eai-standard-" + "lockstep/1.0", "eai-standard-" + "realtime/1.0",
       "rcb-" + "limited/2.2", "COMPAT" + ' = ["x"]', "ACCEPTED" + ' = ("a", "b")', '"protocol' + '_compat": L.X']
GOOD = ['PROTOCOL = "eai-standard/3.0"', 'protocol = "eai-policy/1.1"', 'COMPAT = "v0.1-toplevel-aliases"',
        "the eai-standard client", "eai-standard/3.0+match", "unlimited/2.2"]


def selftest() -> list[str]:
    bad = []
    for line in BAD:
        if not any(rx.search(line) for _, rx in PATTERNS):
            bad.append(f"a pattern went blind: {line!r} is not flagged")
    for line in GOOD:
        hit = [what for what, rx in PATTERNS if rx.search(line)]
        if hit:
            bad.append(f"{line!r} is flagged ({', '.join(hit)})")
    return bad


def tracked(repo: pathlib.Path) -> list[str]:
    try:
        out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, text=True, check=True).stdout
        return [f for f in out.split("\0") if f]
    except (OSError, subprocess.CalledProcessError):
        return [str(p.relative_to(repo)) for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=str(HERE.parents[1]))
    a = ap.parse_args()
    repo = pathlib.Path(a.repo).resolve()
    broken = selftest()
    if broken:
        for b in broken:
            print(f"FAIL check-protocol-strings.py: {b}")
        return 2
    files = tracked(repo)
    if not files:
        print("FAIL check-protocol-strings.py: no tracked files found")
        return 2
    findings = []
    for f in files:
        if f == SELF:
            continue
        p = repo / f
        try:
            data = p.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:8192]:
            continue                                   # a binary file
        text = data.decode("utf-8", errors="replace")
        if not any(rx.search(text) for _, rx in PATTERNS):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for what, rx in PATTERNS:
                if rx.search(line):
                    findings.append(f"{f}:{n}: {what}: {line.strip()[:120]}")
    for x in findings[:80]:
        print(f"FAIL {x}")
    if len(findings) > 80:
        print(f"  ... {len(findings) - 80} more")
    if findings:
        print(f"check-protocol-strings.py: {len(findings)} line(s) name another protocol id than eai-standard/3.0")
        return 1
    print(f"ok check-protocol-strings.py: {len(files)} tracked files name no protocol id but eai-standard/3.0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
