"""The skill sandbox against a fork loop (skilleval/sandbox.py): RLIMIT_NPROC bounds it, close() ends the skill's
session (os.killpg; the skill is started with setsid) and every process below the evaluator that runs as the sandbox
user. Runs ONLY inside a container whose pids cgroup is limited (pids.max <= 512, e.g. docker run --pids-limit 256
--memory 2g): never on a host, where a fork loop that escaped its limits would take the machine down. Skipped
otherwise.

    docker run --rm --network none --pids-limit 256 --memory 2g -v $PWD:/src:ro -w /src python:3.12-slim \
        python3 -B skilleval/tests/test_sandbox_isolation.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from skilleval.sandbox import NOBODY, SkillProcess  # noqa: E402

FORK_LOOP = """import os, time
def _loop():
    while True:
        try:
            if os.fork() == 0:
                os.setsid()
        except OSError:
            time.sleep(0.01)
if os.fork() == 0:          # a detached fork loop that outlives the skill's own process unless the sandbox ends it
    os.setsid()
    _loop()
def act(x=None):
    return x
"""


def pids_limited() -> bool:
    for f in ("/sys/fs/cgroup/pids.max", "/sys/fs/cgroup/pids/pids.max"):
        try:
            v = Path(f).read_text().strip()
        except OSError:
            continue
        return v.isdigit() and int(v) <= 512
    return False


def live(uid: int) -> int:
    n = 0
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                st = Path(f"/proc/{d}/stat").read_text()
                if os.stat(f"/proc/{d}").st_uid == uid and st.rsplit(")", 1)[1].split()[0] not in ("Z", "X") \
                        and int(d) != os.getpid():
                    n += 1
            except (OSError, IndexError):
                continue
    return n


def test_close_ends_a_fork_loop():
    uid = NOBODY if os.geteuid() == 0 else os.getuid()
    with tempfile.TemporaryDirectory() as tmp:
        os.chmod(tmp, 0o755)
        Path(tmp, "skill.py").write_text(FORK_LOOP)
        os.chmod(Path(tmp, "skill.py"), 0o644)
        s = SkillProcess(tmp, "skill", limits={"processes": 64}, sweep_uid=None if os.geteuid() == 0 else uid)
        time.sleep(2.0)                                  # let the loop fill its limit
        assert live(uid) <= 64 + 8, live(uid)            # RLIMIT_NPROC held it (as nobody: 64 processes)
        s.close()
        assert live(uid) == 0, f"{live(uid)} processes of uid {uid} survived close()"


def main():
    if not pids_limited():
        print("skip: run only inside a pids-limited container (pids.max <= 512; see the docstring)")
        return 0
    test_close_ends_a_fork_loop()
    print("ok   test_close_ends_a_fork_loop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
