#!/usr/bin/env python3
"""Clamp the CPU caps of task copies to the host's CPU count (PROTOCOL §2.10: a runner MUST clamp every CPU cap to the
host's count in the copy of the task it runs; the task's files keep their values).

    python3 scripts/clamp_cpus.py [--cpus N] <task dir> ...           # rewrite the copies in place
    python3 scripts/clamp_cpus.py [--cpus N] --needs <task dir> ...   # write nothing; exit 0 if a cap is above N, else 1

Docker refuses a container whose `cpus` exceeds the machine's ("range of CPUs is from 0.01 to 8.00"): a task whose cap is
12 or 16 does not start on an 8-CPU host, and the trial would end in environment setup. What is clamped: every `cpus = <n>`
line of task.toml (`[environment]`: Harbor passes it to docker as main's cap; `[verifier.environment]`: the separate
verifier sandbox's) and every `cpus: <n>` line of the compose files under environment/ (the sidecars). Memory and pids
caps are never clamped. N defaults to the CPUs this process may use (`nproc`); the pool runner clamps its host copies
the same way (batch_eval_live prep_host.py CLAMP_CPUS). Never run it on tasks/ itself (scripts/run_agent_batch.sh runs
it on a job's own copy). Standard library only."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

TOML = re.compile(r"^(cpus[ \t]*=[ \t]*)(\d+(?:\.\d+)?)", re.M)
COMPOSE = re.compile(r"^([ \t]*cpus:[ \t]*)(\d+(?:\.\d+)?)", re.M)
COMPOSE_FILES = ("docker-compose.yaml", "docker-compose.yml", "gpu.docker-compose.yaml", "gpu.docker-compose.yml")


def host_cpus() -> int:
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:                       # not Linux
        return os.cpu_count() or 1


def files(task: Path) -> list[tuple[Path, re.Pattern]]:
    out = [(task / "task.toml", TOML)]
    out += [(task / "environment" / f, COMPOSE) for f in COMPOSE_FILES]
    return [(p, rx) for p, rx in out if p.is_file()]


def fmt(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else f"{n:g}"


def clamp(task: Path, n: float, write: bool) -> list[str]:
    """-> one line per cap above n ("<file>: <old> -> <n>"); with write, the file is rewritten with those caps clamped."""
    changed = []
    for p, rx in files(task):
        s = p.read_text()

        def sub(m: re.Match) -> str:
            if float(m.group(2)) <= n:
                return m.group(0)
            changed.append(f"{p}: cpus {m.group(2)} -> {fmt(n)}")
            return m.group(1) + fmt(n)

        new = rx.sub(sub, s)
        if write and new != s:
            p.write_text(new)
    return changed


def main(argv: list[str]) -> int:
    needs = "--needs" in argv
    args = [a for a in argv if a != "--needs"]
    n: float = host_cpus()
    if "--cpus" in args:
        i = args.index("--cpus")
        try:
            n = float(args[i + 1])
        except (IndexError, ValueError):
            sys.exit("--cpus needs a number")
        del args[i:i + 2]
        if n <= 0:
            sys.exit("--cpus must be positive")
    if not args:
        sys.exit(__doc__)
    repo_tasks = (Path(__file__).resolve().parents[1] / "tasks").resolve()
    found = []
    for a in args:
        t = Path(a)
        if not (t / "task.toml").is_file():
            sys.exit(f"{a}: not a task directory (no task.toml)")
        if not needs and t.resolve().parent == repo_tasks:
            sys.exit(f"{a}: a task of the repository itself; clamp a copy (PROTOCOL §2.10: the task's files keep their values)")
        found += clamp(t, n, write=not needs)
    for line in found:
        print(line)
    if needs:
        return 0 if found else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
