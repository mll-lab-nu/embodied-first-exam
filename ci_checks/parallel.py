#!/usr/bin/env python3
"""Run shell commands concurrently, print each one's output in one piece, fail if any failed.

    parallel.py [-j N] [--expect N] [--advisory] < commands   # one command per line (run with bash -c), from the repo root
    parallel.py --nproc                # the default N

--expect N (the required CI job `invariants`, ci_checks/run_invariants.sh): exit 1 unless exactly N commands were given
and all N ran to completion with exit 0 -- an incomplete run fails, never passes.
--advisory (the CI job `advisories`): a command that exits non-zero is a warning, not a failure (exit 3 is the
convention for "warnings only"; an advisory check that exits 1 is reported the same way); its `FAIL` lines are printed
as `WARN`, as GitHub annotations (`::warning ::`, when GITHUB_ACTIONS is set) and appended to the file
$RCB_ADVISORIES_OUT if set (ci_checks/pr_overview.py --advisories puts them in the pull request's overview). Exit 3
when there was any warning, else 0.

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
    try:
        p = subprocess.run(["bash", "-c", cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    except OSError as e:   # e.g. E2BIG, a command line longer than one argument may be: this command fails, not the pool
        return cmd, 126, f"could not start: {e}\n", time.monotonic() - t0
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
    expect, advisory = None, False
    i = 0
    while i < len(argv):
        if argv[i] == "-j":
            jobs, i = int(argv[i + 1]), i + 2
        elif argv[i] == "--expect":
            expect, i = int(argv[i + 1]), i + 2
        elif argv[i] == "--advisory":
            advisory, i = True, i + 1
        else:
            raise SystemExit(f"usage: parallel.py [-j N] [--expect N] [--advisory] < commands; got {argv[i]!r}")
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
    done: list[str] = []
    warn_lines: list[str] = []
    lock = threading.Lock()
    if expect is not None and len(cmds) != expect:
        print(f"FAIL parallel.py: {len(cmds)} command(s) given, {expect} expected (an incomplete or padded run never passes)")
        return 1

    def report(cmd: str, rc: int, out: str, dt: float) -> None:
        with lock:
            done.append(cmd)
            if advisory and rc != 0:
                out = "".join(("WARN" + ln[4:]) if ln.startswith("FAIL") else ln for ln in out.splitlines(keepends=True))
                lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
                found = [ln for ln in lines if ln.startswith(("WARN", "-"))] or lines[-5:] or [f"exit {rc}"]
                short_cmd = cmd if len(cmd) <= 100 else cmd[:97] + "..."
                warn_lines.extend(f"{short_cmd}: {ln}" for ln in found)
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
    if expect is not None and len(done) != expect:
        print(f"FAIL parallel.py: {len(done)} of {expect} command(s) completed")
        return 1
    if advisory:
        if warn_lines:
            if os.environ.get("GITHUB_ACTIONS"):
                for ln in warn_lines[:200]:
                    msg = ln.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
                    print(f"::warning title=advisory::{msg}")
            if os.environ.get("RCB_ADVISORIES_OUT"):
                with open(os.environ["RCB_ADVISORIES_OUT"], "a") as f:
                    f.write("".join(ln + "\n" for ln in warn_lines))
            print(f"WARN {len(failed)} of {len(cmds)} advisory command(s) reported {len(warn_lines)} finding(s) (not blocking)")
            return 3
        print(f"ok all {len(cmds)} advisory command(s)")
        return 0
    if failed:
        print(f"FAIL {len(failed)} of {len(cmds)} command(s):")
        for c in failed:
            print(f"  - {c if len(c) <= 200 else c[:197] + '...'}")
        return 1
    print(f"ok all {len(cmds)} command(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
