#!/usr/bin/env python3
"""Standard-realtime tasks (docs/protocol/README.md §4b): each task declares its slowdown S and its reset budget, and the
declarations agree. The values are the task's own choice (PROTOCOL §0: template defaults S from the measured real-time
factor, 10 resets); this check holds no per-benchmark list. For every task whose directory ends in `-standard-realtime`:
  - slowdown: its sim service sets `RCB_SLOWDOWN` with a default (`"${RCB_SLOWDOWN:-S}"`, S > 0) in
    environment/docker-compose.yaml (a task a benchmark exports with its own service, PROTOCOL §4c, may set its own
    variable instead: `RO_SLOWDOWN`); `[metadata] slowdown` in task.toml is that S; the instruction states it, as
    `S = <S>` (or, for S = 1, says the robot runs "in real time");
  - reset budget: an `eai-standard/2.3` service declares it, `RCB_RESET_BUDGET` with a whole-number default
    (`"${RCB_RESET_BUDGET:-N}"`, or a fixed `"N"`); a §4c service may declare none (then it has no reset: N = 0);
    `[metadata] reset_budget`, where the task keeps one, is N; every "K resets" the instruction states is N; with
    N > 0 the instruction states N or points to `spec()["budget"]["reset"]`; with a declared N = 0 it says "no reset".

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

RESET_DECL = tc.RESET_DECL_RE   # RCB_RESET_BUDGET's default: overridable (`"${RCB_RESET_BUDGET:-N}"`) or fixed (`"N"`)
RESET_ANY = re.compile(r'^\s*RCB_RESET_BUDGET:', re.M)
STATED = re.compile(r"\b(\d+)\*{0,2}\s+resets?\b", re.I)            # "10 resets", "**50 resets**"
POINTER = re.compile(r"""\[["']budget["']\]\s*\[["']reset["']\]""")    # spec()["budget"]["reset"]
NO_RESET = re.compile(r"\bno resets?\b", re.I)
REAL_TIME = re.compile(r"\bin real time\b", re.I)


def check(task: Path) -> list[str]:
    errs = []
    compose = tc.read_text(task / "environment/docker-compose.yaml") or ""
    md = tomllib.loads((task / "task.toml").read_text()).get("metadata", {})
    text = tc.read_text(task / "instruction.md") or ""
    own = md.get("protocol") != "eai-standard/2.3"     # PROTOCOL §4c: a benchmark's own service and protocol
    # slowdown S
    m = tc.SLOWDOWN_RE.search(compose) or (tc.OWN_SLOWDOWN_RE.search(compose) if own else None)
    if not m:
        errs.append(f'{task.name}: its sim service needs `RCB_SLOWDOWN: "${{RCB_SLOWDOWN:-S}}"` in environment/docker-compose.yaml')
    else:
        S = float(m.group(1))
        if not S > 0:
            errs.append(f"{task.name}: RCB_SLOWDOWN's default must be > 0 (got {m.group(1)})")
        if "slowdown" not in md:
            errs.append(f"{task.name}: [metadata] slowdown is missing (run scripts/task_conventions.py on the task)")
        elif float(md["slowdown"]) != S:
            errs.append(f"{task.name}: [metadata] slowdown = {md['slowdown']}, but its service's default is {S:g}")
        if not re.search(rf"\bS = {re.escape(tc.slowdown_text(S))}\b", text) and not (S == 1 and REAL_TIME.search(text)):
            errs.append(f"{task.name}: instruction.md must state the slowdown as `S = {tc.slowdown_text(S)}`"
                        + (" (or say the robot runs `in real time`)" if S == 1 else ""))
    # reset budget N
    r = RESET_DECL.search(compose)
    if r is None and (RESET_ANY.search(compose) or not own):
        errs.append(f"{task.name}: its sim service must declare its reset budget, `RCB_RESET_BUDGET` with a whole-number "
                    f"default (\"${{RCB_RESET_BUDGET:-N}}\" or \"N\") in environment/docker-compose.yaml")
        return errs
    declared = r is not None
    n = int(r.group(1) or r.group(2)) if declared else 0
    if "reset_budget" in md and int(md["reset_budget"]) != n:
        errs.append(f"{task.name}: [metadata] reset_budget = {md['reset_budget']}, but its service's default is {n}")
    stated = {int(k) for k in STATED.findall(text)}
    if stated - {n}:
        errs.append(f"{task.name}: instruction.md states {', '.join(f'{k} resets' for k in sorted(stated - {n}))}, "
                    f"but the task's reset budget is {n}")
    if n > 0 and n not in stated and not POINTER.search(text):
        errs.append(f"{task.name}: instruction.md must state the reset budget ({n} resets) or point to "
                    f'spec()["budget"]["reset"]')
    if declared and n == 0 and not NO_RESET.search(text):
        errs.append(f"{task.name}: the reset budget is 0, so instruction.md must say there is no reset")
    return errs


def main(argv: list[str]) -> int:
    dirs = [Path(a) for a in argv] or tc.iter_tasks()
    tasks = [d for d in dirs if d.name.endswith("-standard-realtime")]
    errs = [e for t in tasks for e in check(t)]
    if errs:
        print("FAIL standard-realtime tasks (PROTOCOL §4b: the slowdown S and the reset budget declared and consistent):")
        for e in errs[:60]:
            print("  -", e)
        if len(errs) > 60:
            print(f"  ... {len(errs) - 60} more")
        return 1
    print(f"check-realtime: {len(tasks)} standard-realtime task(s) OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
