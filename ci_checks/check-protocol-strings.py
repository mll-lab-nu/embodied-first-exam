#!/usr/bin/env python3
"""One protocol: every standard and realtime task, service, client and document speaks `eai-standard/3.0`
(docs/protocol/eai-standard.md). A service's layer and capabilities are in its /spec (operations, timing.realtime,
kinematics, match), never in a version string. This check fails on any tracked text file (code, tasks, docs) that
names another protocol id of this family or keeps a list of accepted old ids:

  - `eai-standard/2.<n>` (any 2.x id, with or without `+match/...`);
  - `eai-standard-lockstep`, `eai-standard-realtime` (the match services' former ids);
  - `rcb-limited/` (the former name);
  - a list of accepted protocol ids: `COMPAT = [...]` / `COMPAT = (...)`, `protocol_compat`, `ACCEPTED = (...)`;
  - a layer called by a former version number (`the 2.2 layer`, `a 2.4 service`, `2.1's keys`, `2.2/2.4`,
    `protocol 2.2`) or a note on what changed at 3.0 (`before 3.0`, `from 3.0`): a layer has a name (sidecar, shared,
    realtime, operations) and the rules are the current ones.

Nothing is allowlisted but this file and the files of a vendored upstream snapshot whose bytes match its pinned
manifest (SNAPSHOTS: Embodied Safety Exam's source in images/ese/context/ese-src/, checked file by file against
ese-src.sha256 in the image build, so an edit there would break the published image's recipe; a file that does not
match is checked like any other). A benchmark's own runtime of another family (roboEngineer's `eai-policy/1.x`)
is not this family and is not flagged. Before the repository, the patterns run on built-in good and bad lines (each
pattern must flag its bad line and none may flag a good one), so a pattern that went blind fails here.
Exit 0: clean; 1: findings; 2: the check itself could not run.

    python3 ci_checks/check-protocol-strings.py [--repo DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve()
SELF = "ci_checks/check-protocol-strings.py"
SNAPSHOTS = {"images/ese/context/ese-src/": "images/ese/context/ese-src.sha256"}   # prefix -> its sha256 manifest
OLD = "eai-standard/" + "2."            # (spelled in two pieces: this file names the patterns, it is never flagged)
PATTERNS = [
    ("a 2.x protocol id", re.compile(re.escape(OLD) + r"[0-9x_]")),
    ("a match service's former id", re.compile(r"eai-standard-(?:lockstep|realtime)\b")),
    ("the former name rcb-limited", re.compile(r"\brcb-limited/")),
    ("a list of accepted protocol ids", re.compile(r"(?m)^\s*(?:COMPAT|ACCEPTED|PROTOCOLS_ACCEPTED)\s*=\s*[\[(]|\bprotocol_compat\b")),
    ("a layer called by a former version number", re.compile(
        r"\b2\.[1-4x](?:/2\.[0-4])*(?:'s)? (?:layer|layers|adapter|adapters|handler|additions?|extras|client|clients|service|"
        r"services|server|servers|sidecar|recorder|stride|benchmarks?|tasks?|tooling|inputs|proprio|requests?|behaviou?r|"
        r"keys|rule|columns)\b|\(2\.x: |\bprotocol v?2\.[0-4]\b|\b2\.[0-4] ?\u2013 ?2\.[0-4]\b(?! ?(?:m|cm|mm|s|kg|N|GB|GiB|%)\b)|"
        r"\b2\.[0-4]/2\.[0-4]\b|"
        r"\b2\.x (?:task|client|service)|\b(?:the|a|every) 2\.0 (?:client|service|columns)\b")),
    ("a note on what changed at 3.0", re.compile(r"\bbefore v?3\.0\b|\b[Ff]rom v?3\.0\b")),
]
BAD = [OLD + "1", OLD + "4+match/1.0", "eai-standard-" + "lockstep/1.0", "eai-standard-" + "realtime/1.0",
       "rcb-" + "limited/2.2", "COMPAT" + ' = ["x"]', "ACCEPTED" + ' = ("a", "b")', '"protocol' + '_compat": L.X',
       "the shared 2." + "2 layer", "a 2." + "4 service", "2." + "1's keys", "(2." + "2/2.4 answer them)", "protocol 2." + "2",
       "(2." + "x: 200)", "every 2." + "x service", "the 2." + "0 client's default", "before " + "3.0 a success ended it",
       "From " + "3.0: last_s", "From " + "v3.0 every episode"]
GOOD = ['PROTOCOL = "eai-standard/3.0"', 'protocol = "eai-policy/1.1"', 'COMPAT = "v0.1-toplevel-aliases"',
        "the eai-standard client", "eai-standard/3.0+match", "unlimited/2.2", "the BiGym 2.0 adapter", "Wuji Hand 2.2",
        "memory 2.2 GiB", "2.2-2.6 cores", "PROTOCOL \u00a72.1", "Isaac Lab 2.3 / Isaac Sim 5.1", "FIVB 11.2.2:", "3.0 m", "(2.0\u2013" + "2.1 m)"]


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


def pinned(repo: pathlib.Path) -> dict[str, str]:
    """Each vendored snapshot file's pinned sha256, by its path in the repository (SNAPSHOTS)."""
    out = {}
    for prefix, manifest in SNAPSHOTS.items():
        try:
            lines = (repo / manifest).read_text().splitlines()
        except OSError:
            continue
        for line in lines:
            h, _, name = line.partition("  ")
            if h and name:
                out[prefix + name.removeprefix("./")] = h
    return out


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
    snap = pinned(repo)
    for f in files:
        if f == SELF:
            continue
        p = repo / f
        try:
            data = p.read_bytes()
        except OSError:
            continue
        if f in snap and hashlib.sha256(data).hexdigest() == snap[f]:
            continue                                   # upstream's bytes, as the image build checks them
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
        print(f"check-protocol-strings.py: {len(findings)} line(s) name another protocol id than eai-standard/3.0, "
              "a layer by a former version number or what changed at 3.0")
        return 1
    print(f"ok check-protocol-strings.py: {len(files)} tracked files name no protocol id but eai-standard/3.0 and no "
          "layer by a former version number")
    return 0


if __name__ == "__main__":
    sys.exit(main())
