#!/usr/bin/env python3
"""Run shell commands concurrently, print each one's output in one piece, fail if any failed.

    parallel.py [-j N] < commands      # one command per line (run with bash -c), from the repo root
    parallel.py --nproc                # the default N

A line `@lane:<name> <command>` puts the command in a lane: the commands of one lane run one after another (in their
order, started before the commands outside lanes), each lane taking one of the N slots. For tests that cannot share
the host with each other, e.g. the service tests that pick a free port and start a server on it (two of them running
at once can pick the same port and talk to each other's server).

-j: at most N at a time (default: $RCB_CI_JOBS, else the CPUs this process may use: its CPU affinity, capped by the
cgroup's CPU quota -- a runner container started with `--cpus 4` sees all of the host's CPUs but gets four). Each command's stdout + stderr is captured and
printed when it ends, under a `== <command> (<s> s, exit <rc>)` header, so concurrent output never interleaves (a
command that succeeds silently prints nothing). The exit code is 1 when any command exited non-zero, and the failed commands are listed at the end.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor


def run(cmd: str) -> tuple[str, int, str, float]:
    t0 = time.monotonic()
    p = subprocess.run(["bash", "-c", cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    return cmd, p.returncode, p.stdout, time.monotonic() - t0


def cpus() -> int:
    if os.environ.get("RCB_CI_JOBS", "").isdigit() and int(os.environ["RCB_CI_JOBS"]) > 0:
        return int(os.environ["RCB_CI_JOBS"])
    n = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
    try:   # cgroup v2: "<quota> <period>" or "max <period>"
        quota, period = open("/sys/fs/cgroup/cpu.max").read().split()[:2]
        if quota != "max":
            n = min(n, max(1, -(-int(quota) // int(period))))
    except (OSError, ValueError):
        try:   # cgroup v1
            quota = int(open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read())
            period = int(open("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read())
            if quota > 0:
                n = min(n, max(1, -(-quota // period)))
        except (OSError, ValueError):
            pass
    return max(1, n)


def main(argv: list[str]) -> int:
    if argv == ["--nproc"]:
        print(cpus())
        return 0
    jobs = cpus()
    i = 0
    while i < len(argv):
        if argv[i] == "-j":
            jobs, i = int(argv[i + 1]), i + 2
        else:
            raise SystemExit(f"usage: parallel.py [-j N] < commands; got {argv[i]!r}")
    lines = [c for c in (line.strip() for line in sys.stdin) if c and not c.startswith("#")]
    lanes: dict[str, list[str]] = {}
    units: list[list[str]] = []
    for c in lines:
        if c.startswith("@lane:"):
            name, _, cmd = c[len("@lane:"):].partition(" ")
            lanes.setdefault(name, []).append(cmd.strip())
        else:
            units.append([c])
    units = list(lanes.values()) + units
    cmds = [c for u in units for c in u]
    failed: list[str] = []
    lock = threading.Lock()

    def report(cmd: str, rc: int, out: str, dt: float) -> None:
        with lock:
            if rc != 0:
                failed.append(cmd)
            if rc == 0 and not out.strip():   # silent success (e.g. task_conventions.py --check): no header
                return
            short = cmd if len(cmd) <= 160 else cmd[:157] + "..."
            sys.stdout.write(f"== {short} ({dt:.0f} s, exit {rc})\n{out}")
            if out and not out.endswith("\n"):
                sys.stdout.write("\n")
            sys.stdout.flush()

    def run_unit(unit: list[str]) -> None:
        for c in unit:
            report(*run(c))

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        for fut in [pool.submit(run_unit, u) for u in units]:
            fut.result()
    if failed:
        print(f"FAIL {len(failed)} of {len(cmds)} command(s):")
        for c in failed:
            print(f"  - {c if len(c) <= 200 else c[:197] + '...'}")
        return 1
    print(f"ok all {len(cmds)} command(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
