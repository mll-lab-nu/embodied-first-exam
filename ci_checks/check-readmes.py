#!/usr/bin/env python3
"""ADVISORY (docs/protocol/README.md §1): the per-task READMEs and the benchmark READMEs (scripts/task_conventions.py
render_readme, tasks/<benchmark>/readme.toml).

    python3 ci_checks/check-readmes.py [task dir ...]     # default: every task

- each task's README.md describes that task alone: no other task directory's name or base name appears in it (its own
  base may), and none of the retired words (README_FORBIDDEN: Twin, Difficulty, Baselines, eai-standard/2.x);
- tasks/<benchmark>/readme.toml loads with its schema, and every [families] / [tasks] entry names a family or a task
  the benchmark has (a stale entry is a finding: the README of a renamed task would lose its text silently);
- tasks/<benchmark>/README.md has the sections of BENCH_README_SECTIONS, in that order (Others optional).
The per-task README's own sections and key table: ci_checks/check-task-layout.py; that it is the rendered one:
scripts/task_conventions.py --check. Standard library only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402

TOKEN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\-]*")


def names_index() -> tuple[set[str], set[str]]:
    tasks = tc.iter_tasks()
    return {t.name for t in tasks}, {tc.base_of(t) for t in tasks}


def other_names(task: Path, text: str, names: set[str], bases: set[str]) -> list[str]:
    own, own_base = task.name, tc.base_of(task)
    hits = set()
    for tok in TOKEN.findall(text):
        tok = tok.rstrip(".-")
        if tok in (own, own_base):
            continue
        if tok in names or tok in bases:
            hits.add(tok)
    return sorted(hits)


def task_errors(task: Path, names: set[str], bases: set[str]) -> list[str]:
    s = tc.read_text(task / "README.md") or ""
    errs = [f"names another task: `{n}` (each task's README describes that task alone)"
            for n in other_names(task, s, names, bases)]
    errs += [f"retired wording {m!r}: not in a task README" for m in sorted(set(tc.README_FORBIDDEN.findall(s)))]
    return errs


def bench_errors(bench: str) -> list[str]:
    errs = []
    try:
        data = tc.readme_data(bench)
    except tc.ReadmeError as e:
        return [str(e)]
    tasks = [t for t in tc.iter_tasks() if tc.bench_dir(t) == bench]
    fams = {str(tc.metadata_of(t).get("family", "")) for t in tasks}
    known = {t.name for t in tasks} | {tc.base_of(t) for t in tasks}
    errs += [f"{tc.README_DATA}: [families.{f!r}] is no family of the benchmark's tasks"
             for f in sorted(set(data.get("families") or {}) - fams)]
    errs += [f"{tc.README_DATA}: [tasks.{n!r}] is no task (directory or base) of the benchmark"
             for n in sorted(set(data.get("tasks") or {}) - known)]
    s = tc.read_text(tc.TASKS_DIR / bench / "README.md") or ""
    heads = re.findall(r"(?m)^## (.+?)\s*$", s)
    want = [h for h in tc.BENCH_README_SECTIONS if h != "Others" or h in heads]
    if heads != want:
        errs.append("README.md sections must be " + ", ".join("## " + h for h in tc.BENCH_README_SECTIONS)
                    + " in this order (Others optional); found " + (", ".join("## " + h for h in heads) or "none"))
    return errs


def main(argv: list[str]) -> int:
    tasks = [Path(a).resolve() for a in argv] or tc.iter_tasks()
    tasks = [t for t in tasks if (t / "task.toml").is_file()]
    names, bases = names_index()
    rc = 0
    for t in tasks:
        for e in task_errors(t, names, bases):
            print(f"FAIL {t}: README.md: {e}")
            rc = 1
    benches = sorted({tc.bench_dir(t) for t in tasks} if argv else {folder for _, _, folder in tc.BENCHMARK_TABLE})
    for b in benches:
        for e in bench_errors(b):
            print(f"FAIL tasks/{b}: {e}")
            rc = 1
    if rc == 0:
        print(f"check-readmes: {len(tasks)} task READMEs of {len(benches)} benchmark(s): no other task named, no "
              "retired wording, readme.toml and benchmark README in shape")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
