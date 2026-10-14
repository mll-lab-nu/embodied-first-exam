#!/usr/bin/env python3
"""Standard-realtime tasks (docs/PROTOCOL.md §4b): every one states its slowdown S and allows resets. Checks, for every
task whose directory ends in `-standard-realtime`:
  - its sim service sets `RCB_SLOWDOWN` with a default (`"${RCB_SLOWDOWN:-S}"`, S > 0) in environment/docker-compose.yaml;
  - `[metadata] slowdown` in task.toml is that S (written by scripts/task_conventions.py `normalize`);
  - its service sets `RCB_RESET_BUDGET` with a default of at least 1 (owner, 2026-10-14: every standard-realtime task
    allows resets, 10 by default), unless its benchmark is in RESET_EXCEPTIONS (PROTOCOL §4b, per-benchmark exceptions);
  - its instruction states S, as `S = <S>` (the generator's text; the README's "Real time" row and task.toml say it too),
    unless its benchmark is in TEXT_GRANDFATHERED (the twins that existed before the rule; their S is in /spec.timing).

    python3 ci_checks/check-realtime.py [task dirs]      # default: every task
Standard library only.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402

# PROTOCOL §4b: benchmarks whose standard-realtime tasks default to no reset (owner decisions)
RESET_EXCEPTIONS = {
    "BiGym 2.0": "its realtime twins stay as they are (owner, 2026-10-14, D2); budget.reset = 0 since 2026-10-08",
    "RoboOlympics": "a match is one episode (owner, 2026-10-08)",
    "RoboSafeBench": ("a safety episode is one attempt: a harm done cannot be reset away, and its standard tasks have no reset "
                      "either (board 0114, 2026-10-14; pending the owner's confirmation)"),
}
# Realtime twins made before 2026-10-14 (owner D2: kept as they are): their instructions need not quote S
TEXT_GRANDFATHERED = {"HumanoidBench", "BiGym 2.0", "RoboOlympics"}


def check(task: Path) -> list[str]:
    errs = []
    compose = tc.read_text(task / "environment/docker-compose.yaml") or ""
    m = tc.SLOWDOWN_RE.search(compose)
    if not m:
        return [f'{task.name}: its sim service needs `RCB_SLOWDOWN: "${{RCB_SLOWDOWN:-S}}"` in environment/docker-compose.yaml']
    S = float(m.group(1))
    if not S > 0:
        errs.append(f"{task.name}: RCB_SLOWDOWN's default must be > 0 (got {m.group(1)})")
    md = tomllib.loads((task / "task.toml").read_text()).get("metadata", {})
    if "slowdown" not in md:
        errs.append(f"{task.name}: [metadata] slowdown is missing (run scripts/task_conventions.py on the task)")
    elif float(md["slowdown"]) != S:
        errs.append(f"{task.name}: [metadata] slowdown = {md['slowdown']}, but its service's RCB_SLOWDOWN default is {S:g}")
    bench = tc.bench_of(task)
    r = tc.RESET_RE.search(compose)
    if bench not in RESET_EXCEPTIONS and (r is None or int(r.group(1)) < 1):
        errs.append(f"{task.name}: a standard-realtime task allows resets (RCB_RESET_BUDGET default >= 1; 10 by default, "
                    f"owner 2026-10-14), got {'none' if r is None else r.group(1)}")
    if bench not in TEXT_GRANDFATHERED:
        text = tc.read_text(task / "instruction.md") or ""
        if not re.search(rf"\bS = {re.escape(tc.slowdown_text(S))}\b", text):
            errs.append(f"{task.name}: instruction.md must state the slowdown as `S = {tc.slowdown_text(S)}`")
    return errs


def main(argv: list[str]) -> int:
    dirs = [Path(a) for a in argv] or sorted(p for p in (ROOT / "tasks").iterdir() if (p / "task.toml").is_file())
    tasks = [d for d in dirs if d.name.endswith("-standard-realtime")]
    errs = [e for t in tasks for e in check(t)]
    if errs:
        print("FAIL standard-realtime tasks (PROTOCOL §4b: the slowdown S stated, resets allowed):")
        for e in errs[:60]:
            print("  -", e)
        if len(errs) > 60:
            print(f"  ... {len(errs) - 60} more")
        return 1
    print(f"check-realtime: {len(tasks)} standard-realtime task(s) OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
