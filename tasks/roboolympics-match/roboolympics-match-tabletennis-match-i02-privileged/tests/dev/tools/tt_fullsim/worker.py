"""Persistent program process. JSON views in, legal command proposals out.

This is an API/process boundary, NOT a security boundary against hostile same-uid code.
"""

import contextlib
import importlib.util
import json
import os
import resource
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
NPROC = 256  # processes and threads of uid 65534 (the kernel counts the user's, not this container's): generous
sys.path.insert(0, str(root))
resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
resource.setrlimit(resource.RLIMIT_CPU, (7200, 7200))  # = the formal match's wall bound (the twin's cutoff)
# H.1 (#282 review): a bounded number of processes for the policy's user; the verifier then ends them all with kill(-1)
if os.geteuid() == 65534:  # the formal run (for another user the count includes all of that user's own processes)
    resource.setrlimit(resource.RLIMIT_NPROC, (NPROC, NPROC))
resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2, 16 * 1024**2))
wire = sys.stdout


def send(obj):
    wire.write(json.dumps(obj, allow_nan=False) + "\n")
    wire.flush()


with contextlib.redirect_stdout(sys.stderr):
    spec = importlib.util.spec_from_file_location("submitted_program", sys.argv[1])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    sys.path.insert(0, str(Path(sys.argv[1]).resolve().parent))
    spec.loader.exec_module(mod)
    initial = json.loads(sys.stdin.readline())
    policy = mod.make_policy(initial)
send({"ready": True})
for line in sys.stdin:
    with contextlib.redirect_stdout(sys.stderr):
        command = policy.act(json.loads(line))
    send({"command": command})
