#!/usr/bin/env python3
"""Scene dynamics (docs/PROTOCOL.md §2.14): every task says whether its scene is `dynamic` or `static`, and the one table
says it first. Checks:
  - scripts/task_dynamics.toml: every entry (a benchmark's row, a family's exception) has `dynamics` in {static, dynamic}
    and a non-empty `why`; every benchmark of scripts/task_conventions.py BENCHMARKS that has tasks has a row; a
    family's exception names a benchmark that has a row, and differs from that row (an exception that says what the
    row says is noise);
  - every task's task.toml has `[metadata] dynamics`, and it is the table's value for the task (its family's exception,
    else its benchmark's row);
  - when run on every task (no arguments): every family exception matches at least one task.

    python3 ci_checks/check-dynamics.py [task dirs]      # default: every task
Fix: edit scripts/task_dynamics.toml, then `python3 scripts/task_conventions.py tasks/<task> ...` (or
`python3 scripts/task_cutoffs.py apply`, which normalizes every task and refreshes each DIGEST). Never edit the
value in a task.toml. Standard library only.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402


def table_errors(tasks: list[Path]) -> list[str]:
    errs = []
    if not tc.DYNAMICS_FILE.is_file():
        return [f"{tc.DYNAMICS_FILE.relative_to(ROOT)} is missing"]
    rows, fams = tc.dynamics_table()
    entries = [(f'benchmark "{b}"', e) for b, e in rows.items()]
    entries += [(f'family "{b}" / "{f}"', e) for b, fs in fams.items() for f, e in fs.items()]
    for where, e in entries:
        if not isinstance(e, dict) or e.get("dynamics") not in tc.DYNAMICS:
            errs.append(f"{where}: dynamics must be one of {tc.DYNAMICS}")
        elif not str(e.get("why", "")).strip():
            errs.append(f"{where}: give the reason (`why`)")
    labels = {label for _, label in tc.BENCHMARKS}
    for b in rows:
        if b not in labels:
            errs.append(f'benchmark "{b}" is not a label of scripts/task_conventions.py BENCHMARKS')
    for b, fs in fams.items():
        if b not in rows:
            errs.append(f'family exceptions for "{b}", which has no benchmark row')
            continue
        for f, e in fs.items():
            if isinstance(e, dict) and e.get("dynamics") == rows[b].get("dynamics"):
                errs.append(f'family "{b}" / "{f}" says what the benchmark row says: remove it')
    for b in sorted({tc.bench_of(t) for t in tasks} - set(rows)):
        errs.append(f'no row for benchmark "{b or "?"}" (a task directory no BENCHMARKS prefix matches has no benchmark)')
    return [f"FAIL scripts/task_dynamics.toml: {e}" for e in errs]


def task_errors(task: Path) -> list[str]:
    md = tomllib.loads((task / "task.toml").read_text()).get("metadata", {})
    want = tc.dynamics_for(task)
    have = md.get("dynamics")
    if have is None:
        return [f"FAIL {task.name}: [metadata] dynamics is missing (run scripts/task_conventions.py on it)"]
    if have not in tc.DYNAMICS:
        return [f"FAIL {task.name}: [metadata] dynamics = {have!r}, not one of {tc.DYNAMICS}"]
    if want is not None and have != want:
        return [f"FAIL {task.name}: [metadata] dynamics = {have!r}, the table says {want!r} (scripts/task_dynamics.toml; "
                "run scripts/task_conventions.py on it)"]
    return []


def main(argv: list[str]) -> int:
    every = not argv
    tasks = sorted(p.parent for p in (ROOT / "tasks").glob("*/task.toml")) if every else \
        [Path(a) for a in argv if (Path(a) / "task.toml").is_file()]
    errs = table_errors(tasks)
    for t in tasks:
        errs += task_errors(t)
    if every:
        _, fams = tc.dynamics_table()
        seen = {(tc.bench_of(t), tc.family_of(t)) for t in tasks}
        errs += [f'FAIL scripts/task_dynamics.toml: family "{b}" / "{f}" matches no task'
                 for b, fs in fams.items() for f in fs if (b, f) not in seen]
    for e in errs:
        print(e)
    if not errs:
        print(f"check-dynamics: {len(tasks)} task(s) OK")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
