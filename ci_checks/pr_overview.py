#!/usr/bin/env python3
"""A pull request's overview: what it changes, for the sticky comment and the labels (the job `advisories` of .github/workflows/static-checks.yml).

As Terminal-Bench's task-pr-overview: the changed tasks with their mode, oracle, cutoff and minimum compute, a table of
the cutoffs it changes (old -> new; PROTOCOL §2: the task author's decision, stated in the pull request), the cutoffs per benchmark and mode after it
(several numbers in one benchmark and mode are marked: a pull request says why), twins whose cutoffs differ, and the
scope its static checks run on (ci_checks/ci_scope.py), and the advisory checks' findings ("Advisories (not blocking)",
from the file the CI job `advisories` writes: --advisories FILE). Labels:
  new-task       a task directory is added           task-fix   an existing task directory changes (or is removed)
  shared         a path outside the benchmarks' own   cutoff-change   an existing task's `[agent] timeout_sec` changes

    python3 ci_checks/pr_overview.py --diff-from REV [--labels FILE] [--advisories FILE]   # markdown on stdout; labels
                                                                      # one per line in FILE
Standard library only.
"""
from __future__ import annotations

import subprocess
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "ci_checks"))
import task_conventions as tc  # noqa: E402
import ci_scope  # noqa: E402

MARKER = "<!-- rcb-pr-overview -->"


def old_toml(rev: str, name: str) -> dict | None:
    """The task's task.toml at `rev`: tasks/<folder>/<task>/, or the flat tasks/<task>/ of a revision before the
    benchmark folders."""
    for rel in (tc.task_relpath(name), f"tasks/{name}"):
        try:
            return tomllib.loads(ci_scope.git("show", f"{rev}:{rel}/task.toml"))
        except (subprocess.CalledProcessError, tomllib.TOMLDecodeError):
            continue
    return None


def cutoff(d: dict | None):
    v = (d or {}).get("agent", {}).get("timeout_sec")
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and float(v) == int(v) else v


def main(argv: list[str]) -> int:
    rev = argv[argv.index("--diff-from") + 1] if "--diff-from" in argv else "origin/main"
    labels_file = Path(argv[argv.index("--labels") + 1]) if "--labels" in argv else None
    adv_file = Path(argv[argv.index("--advisories") + 1]) if "--advisories" in argv else None
    paths = sorted({p for p in ci_scope.git("diff", "--name-only", "--no-renames", rev, "HEAD").splitlines() if p})
    names = sorted({n for p in paths if (n := ci_scope.task_name_of(p))})
    added, changed, removed = [], [], []
    for n in names:
        now, before = (tc.task_dir(n) / "task.toml").is_file(), old_toml(rev, n) is not None
        (added if now and not before else changed if now else removed if before else []).append(n)
    sc = ci_scope.scope(paths)
    labels = set()
    if added:
        labels.add("new-task")
    if changed or removed:
        labels.add("task-fix")
    if sc["scope"] == "full":
        labels.add("shared")
    out = [MARKER, "## Pull request overview", "",
           f"{len(paths)} changed path(s); {len(added)} task(s) added, {len(changed)} changed, {len(removed)} removed. "
           f"Static checks: scope **{sc['scope']}** ({sc['reason']})"
           + (f"; benchmarks: {', '.join(sc['benches'])}" if sc["benches"] else "") + "."]
    # cutoffs changed in existing tasks
    moves = []
    for n in changed:
        a, b = cutoff(old_toml(rev, n)), tc.cutoff_for(tc.task_dir(n))
        if a != b:
            moves.append((n, a, b))
    if moves:
        labels.add("cutoff-change")
        groups = defaultdict(list)
        for n, a, b in moves:
            t = tc.task_dir(n)
            groups[(tc.bench_of(t), tc.mode_of(t), a, b)].append(n)
        out += ["", "### Cutoff changes (PROTOCOL §2: the task author's decision; say old -> new and why above)", "",
                "| Benchmark | Mode | Old | New | Tasks |", "|---|---|---|---|---|"]
        out += [f"| {bench} | {mode} | {a} s | {b} s | {len(ns)} (`{ns[0]}`{', ...' if len(ns) > 1 else ''}) |"
                for (bench, mode, a, b), ns in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1]))]
    # the tasks it adds or changes
    shown = added + changed
    if shown:
        out += ["", "### Tasks", "", "| Task | Status | Mode | Oracle | Cutoff | Minimum compute (CPU / GB / GPU GB, class) |",
                "|---|---|---|---|---|---|"]
        for n in shown[:60]:
            t = tc.task_dir(n)
            d = tomllib.loads((t / "task.toml").read_text())
            md = d.get("metadata", {})
            r = md.get("resources") or {}
            res = (f"{r.get('min_cpus', '?')} / {r.get('min_memory_gb', '?')} / {r.get('min_gpu_memory_gb', '?')}, "
                   f"{r.get('gpu_class', '?')}") if r else "—"
            out.append(f"| `{n}` | {'added' if n in added else 'changed'} | {tc.mode_of(t)} | {md.get('oracle', '—')} | "
                       f"{cutoff(d)} s | {res} |")
        if len(shown) > 60:
            out.append(f"| ... {len(shown) - 60} more | | | | | |")
    if removed:
        out += ["", "Removed: " + ", ".join(f"`{n}`" for n in removed[:40]) + (" ..." if len(removed) > 40 else "")]
    # cutoffs per benchmark and mode, after the change, for the benchmarks it touches
    benches = sorted({tc.bench_of(Path(n)) for n in shown})
    if benches:
        every = [p for p in tc.iter_tasks() if tc.bench_of(p) in benches]
        vals = defaultdict(set)
        for t in every:
            vals[(tc.bench_of(t), tc.mode_of(t))].add(tc.cutoff_for(t))
        out += ["", "### Cutoffs of the benchmarks it touches (after it)", "", "| Benchmark | Mode | Cutoff |", "|---|---|---|"]
        for (bench, mode), v in sorted(vals.items()):
            vs = sorted(v, key=lambda x: (x is None, x or 0))
            out.append(f"| {bench} | {mode} | {' / '.join(f'{x} s' for x in vs)}"
                       + (" **(several numbers: the pull request says why, PROTOCOL §2)**" if len(vs) > 1 else "") + " |")
        pairs = sorted({p for t in every for p in tc.cutoff_pairs(t) if tc.cutoff_for(p[0]) != tc.cutoff_for(p[1])})
        twins = [f"`{b.name}` {tc.cutoff_for(b)} s, `{a.name}` {tc.cutoff_for(a)} s" for a, b in pairs]
        if twins:
            out += ["", "**Twins with different cutoffs** (the required job `invariants` fails; PROTOCOL Appendix H.7): " + "; ".join(twins[:10])]
    if adv_file is not None:
        lines = [ln for ln in (adv_file.read_text(errors="replace").splitlines() if adv_file.is_file() else []) if ln.strip()]
        out += ["", "### Advisories (not blocking)", ""]
        if not lines:
            out.append("None: every advisory check passed (the required job `invariants` decides the merge).")
        else:
            out.append(f"{len(lines)} finding(s) of the advisory checks (PROTOCOL §1-§7 are recommendations; only Appendix H "
                       "blocks). Fix them or say in the pull request why the task departs:")
            out += ["", "```"] + [ln[:300] for ln in lines[:60]] + (["... %d more" % (len(lines) - 60)] if len(lines) > 60 else []) + ["```"]
    out += ["", "Maintainers: comment `/validate` to run the oracle (where `oracle = \"full\"`) and `nop` on the changed tasks."]
    print("\n".join(out))
    if labels_file:
        labels_file.write_text("".join(f"{x}\n" for x in sorted(labels)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
