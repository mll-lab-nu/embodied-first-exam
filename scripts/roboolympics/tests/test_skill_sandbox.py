#!/usr/bin/env python3
"""RoboOlympics' exported skill tasks (PROTOCOL §4c): the verifier's sandbox ends every process a skill starts before
anything is graded (board 0111; the #180 review's finding: a detached child of the skill outlived the evaluation and
could rewrite the report). Standard library only; runs as any user (as root the skill runs as `nobody`, as in the
verifier).

    python3 scripts/roboolympics/tests/test_skill_sandbox.py

1. The two skill tasks carry the same skilleval sandbox, evaluator, probe, host and grader (one fix, both tasks).
2. A skill that double-forks a detached sleeper (`setsid`): after close() the sleeper is gone.
3. Without the sweep (a non-root caller that asks for none), the same sleeper survives close(): the check above is real.
4. RLIMIT_NPROC is set for the skill when it runs as `nobody`."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TASKS = ["roboolympics-tabletennis-hitskill-i00-standard", "roboolympics-badminton-actskill-i00-standard"]
SHARED = ["tests/sim/skilleval/sandbox.py", "tests/sim/skilleval/evaluate.py", "tests/sim/skilleval/probe/probe.py",
          "tests/sim/skilleval/host.py", "tests/engineer_grade.py"]

SKILL = '''
import os, resource, time
PIDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "sleeper.pid")
if os.fork() == 0:                    # detach: a new session, then a grandchild that sleeps
    os.setsid()
    if os.fork() == 0:
        with open(PIDS, "w") as f:
            f.write(str(os.getpid()))
        time.sleep(120)
    os._exit(0)

def hit(*args, **kwargs):
    return {"nproc": resource.getrlimit(resource.RLIMIT_NPROC)[0], "uid": os.getuid()}
'''


def alive(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


def load_sandbox():
    path = ROOT / "tasks" / TASKS[0] / "tests/sim/skilleval/sandbox.py"
    spec = importlib.util.spec_from_file_location("rcb_skill_sandbox", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_skill(sb, sweep: bool) -> tuple[int, dict]:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "skill"
        (d / "out").mkdir(parents=True)
        (d / "hit.py").write_text(SKILL)
        os.chmod(td, 0o755)
        os.chmod(d, 0o755)
        os.chmod(d / "hit.py", 0o644)
        os.chmod(d / "out", 0o777)                    # the skill (nobody, when run as root) writes its sleeper's pid
        kw = {} if os.geteuid() == 0 or not sweep else {"sweep_uid": os.getuid()}
        s = sb.SkillProcess(d, "hit", timeouts={"hit": 10}, **kw)
        assert s.alive, f"the skill did not load: {s.errors}"
        ret = s.call("hit")
        pidfile = d / "out" / "sleeper.pid"
        for _ in range(200):
            if pidfile.is_file() and pidfile.read_text():
                break
            time.sleep(0.01)
        pid = int(pidfile.read_text())
        assert alive(pid), "the sleeper did not start"
        s.close()
        return pid, ret


def main() -> int:
    for f in SHARED:
        a, b = (ROOT / "tasks" / t / f for t in TASKS)
        assert a.read_bytes() == b.read_bytes(), f"{f} differs between {TASKS[0]} and {TASKS[1]}"
    sb = load_sandbox()
    pid, ret = run_skill(sb, sweep=True)
    time.sleep(0.05)
    assert not alive(pid), f"a detached process of the skill (pid {pid}) outlived close()"
    if os.geteuid() == 0:
        assert ret["uid"] == sb.NOBODY, ret
        assert ret["nproc"] == sb.LIMITS["processes"], f"RLIMIT_NPROC not set for the skill: {ret}"
        print("ok: as root (the skill as nobody): a detached process of the skill is ended by close(); RLIMIT_NPROC set")
        return 0
    pid2, _ = run_skill(sb, sweep=False)              # control: the session alone does not hold a detached process
    try:
        assert alive(pid2), "control: the detached sleeper should survive a close() without the sweep"
    finally:
        sb.end_sandbox_processes(os.getuid())
    assert not alive(pid2)
    print("ok: a detached process of the skill is ended by close() (and survives without the sweep: the control)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
