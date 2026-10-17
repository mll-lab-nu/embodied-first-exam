"""H.1 for the table-tennis twins (#282 review): the policy's user is bounded (RLIMIT_NPROC) and ended with kill(-1)
as that user; the verifier never ends without a reward. Run as root inside the twin's verifier image:

    docker run --rm --pids-limit 256 --memory 2g -v <hub>/scripts/roboolympics/fullsim/tests:/t:ro <verifier image> \
        python3 -m unittest discover -s /t

Always with --pids-limit and --memory, never on a bare host: the fork loop is real (bounded here by RLIMIT_NPROC as the worker sets it, and by the limit).

(skipped elsewhere: it needs root, the trusted simulator at /opt/trusted and the sandbox user nobody)."""

import os
import resource
import sys
import time
import unittest
from pathlib import Path

TRUSTED = Path("/opt/trusted")
sys.path.insert(0, str(TRUSTED))
NOBODY = 65534


def fork_loop_as_nobody():
    """A detached fork loop as nobody (setsid, double fork, children that fork again), as a hostile program would."""
    pid = os.fork()
    if pid == 0:
        os.setsid()
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))   # as the worker bounds the policy (NPROC), smaller here
        os.setgroups([])
        os.setgid(NOBODY)
        os.setuid(NOBODY)
        for _ in range(64):
            try:
                if os.fork() == 0:
                    while True:
                        try:
                            os.fork()
                        except OSError:
                            time.sleep(0.01)
            except OSError:
                time.sleep(0.01)
        os._exit(0)
    return pid


def pids_limited():
    """Inside a container with a pids limit (cgroup v2 pids.max, or v1); never run the fork loop without one."""
    for f in ("/sys/fs/cgroup/pids.max", "/sys/fs/cgroup/pids/pids.max"):
        try:
            return Path(f).read_text().strip() != "max"
        except OSError:
            continue
    return False


@unittest.skipUnless(os.geteuid() == 0 and (TRUSTED / "tools/tt_fullsim/formal.py").is_file() and pids_limited(),
                     "verifier image, root, a pids limit")
class EndProcesses(unittest.TestCase):
    def test_a_fork_loop_is_ended(self):
        from tools.tt_fullsim.formal import _alive_of, end_uid_processes

        os.waitpid(fork_loop_as_nobody(), 0)   # its first child exits at once; the loop lives on, detached
        time.sleep(1.0)
        self.assertTrue(_alive_of(NOBODY), "the fork loop did not start")
        self.assertTrue(end_uid_processes(NOBODY))
        self.assertEqual(_alive_of(NOBODY), [])


if __name__ == "__main__":
    unittest.main()
