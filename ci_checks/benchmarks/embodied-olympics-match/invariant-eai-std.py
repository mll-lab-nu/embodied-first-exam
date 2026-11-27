#!/usr/bin/env python3
"""INVARIANT hook (PROTOCOL §1: copies of shared sources are byte-identical; docs/protocol/standard_mode.md Part 5),
this benchmark's own: ci_checks/run_invariants.sh runs every ci_checks/benchmarks/*/invariant-* hook with the task
directories in scope.

A match on the match extension (apply_eai_std.py TASKS there) serves it from environment/sim/eai_std/, a byte copy of
embodied_first_exam/benchmarks/embodied-olympics-match/eai_std/ (its rcb1.py = embodied_first_exam/standard/rcb1.py), and
its sim sidecar runs `python3 -m eai_std.serve` with EAI_STD_CLOCK set (realtime for a `-realtime` task, lockstep or
turn for a `-standard` one); any other match carries no copy. Equivalently: `apply_eai_std.py --check` there changes nothing. `--selftest` runs the hook's own cases.
Standard library only.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "embodied_first_exam/benchmarks/embodied-olympics-match/eai_std"
PREFIX = "embodied-olympics-match-"
_spec = importlib.util.spec_from_file_location("apply_eai_std", SRC.parent / "apply_eai_std.py")
_apply = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_apply)
ON_EXTENSION = frozenset(_apply.TASKS)        # the matches on the match extension


def clocks(task: Path) -> tuple[str, ...]:
    return ("realtime",) if task.name.endswith("-realtime") else ("lockstep", "turn")


def problems(task: Path, src: Path = SRC, on: frozenset = ON_EXTENSION) -> list[str]:
    copy = task / "environment/sim/eai_std"
    if task.name not in on:
        return ["environment/sim/eai_std/ in a task that is not on the match extension"] if copy.exists() else []
    out = []
    want = {f.name: f.read_bytes() for f in sorted(src.glob("*.py"))}
    have = {f.name: f.read_bytes() for f in sorted(copy.glob("*.py"))} if copy.is_dir() else {}
    for name in sorted(set(want) | set(have)):
        if name not in have:
            out.append(f"environment/sim/eai_std/{name} missing")
        elif name not in want:
            out.append(f"environment/sim/eai_std/{name} is not in the source")
        elif have[name] != want[name]:
            out.append(f"environment/sim/eai_std/{name} differs from {src.relative_to(ROOT) if src.is_relative_to(ROOT) else src}/{name}")
    std_rcb1 = ROOT / "embodied_first_exam/standard/rcb1.py"
    if "rcb1.py" in want and std_rcb1.is_file() and want["rcb1.py"] != std_rcb1.read_bytes():
        out.append("the source's rcb1.py differs from embodied_first_exam/standard/rcb1.py")
    compose = task / "environment/docker-compose.yaml"
    text = compose.read_text() if compose.is_file() else ""
    sim = re.search(r"(?ms)^  sim:\n(.*?)(?=^  \S|\Z)", text)
    blk = sim.group(1) if sim else ""
    if not re.search(r"^    command: python3 -m eai_std\.serve\s*$", blk, re.M):
        out.append("the sim sidecar does not run `python3 -m eai_std.serve`")
    clock = re.search(r'^\s+EAI_STD_CLOCK:\s*"?(\w+)"?\s*$', blk, re.M)
    if not clock or clock.group(1) not in clocks(task):
        out.append(f"EAI_STD_CLOCK {clock.group(1) if clock else None!r} (one of {list(clocks(task))})")
    return out


def selftest() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src"
        src.mkdir()
        (src / "a.py").write_text("x = 1\n")
        t = Path(d) / (PREFIX + "x-realtime")
        on = frozenset({t.name})
        (t / "environment/sim/eai_std").mkdir(parents=True)
        (t / "task.toml").write_text('[metadata]\nprotocol = "eai-standard/3.0"\n')
        (t / "environment/sim/eai_std/a.py").write_text("x = 1\n")
        (t / "environment/docker-compose.yaml").write_text(
            'services:\n  sim:\n    command: python3 -m eai_std.serve\n    environment:\n      EAI_STD_CLOCK: "realtime"\n')
        cases = [(problems(t, src, on), 0)]
        (t / "environment/sim/eai_std/a.py").write_text("x = 2\n")
        cases.append((problems(t, src, on), 1))
        (t / "environment/sim/eai_std/a.py").write_text("x = 1\n")
        (t / "environment/docker-compose.yaml").write_text(
            'services:\n  sim:\n    command: python3 -m core.lockstep\n    environment:\n      EAI_STD_CLOCK: "lockstep"\n')
        cases.append((problems(t, src, on), 2))
        cases.append((problems(t, src, frozenset()), 1))
    bad = [(i, got, n) for i, (got, n) in enumerate(cases) if len(got) != n]
    for i, got, n in bad:
        print(f"FAIL selftest case {i}: {got} (want {n} problem(s))")
    if not bad:
        print(f"ok embodied-olympics-match eai_std selftest: {len(cases)} cases")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--selftest"]:
        return selftest()
    errs, n = [], 0
    for a in argv:
        t = Path(a.rstrip("/"))
        if not t.name.startswith(PREFIX) or not (t / "task.toml").is_file() or t.name.endswith("-privileged"):
            continue
        n += 1
        errs += [f"{t.name}: {p}" for p in problems(t)]
    for e in errs:
        print("FAIL", e)
    if not errs:
        print(f"ok embodied-olympics-match eai_std: {n} task(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
