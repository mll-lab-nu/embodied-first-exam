"""Persistent program process. JSON views in, legal command proposals out.

This is an API/process boundary, NOT a security boundary against hostile same-uid code.
"""

import contextlib
import importlib.util
import json
import resource
import sys
from pathlib import Path

NPROC = 256  # processes + threads of uid nobody (RLIMIT_NPROC counts the whole host's, so not tighter); end_uid_processes ends them

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
_cpu = int(sys.argv[2]) if len(sys.argv) > 2 else 1800  # the formal match cutoff
resource.setrlimit(resource.RLIMIT_CPU, (_cpu, _cpu))
resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2, 16 * 1024**2))
# H.1: a bounded number of processes and threads (the program runs as nobody, alone under that uid in the verifier)
resource.setrlimit(resource.RLIMIT_NPROC, (NPROC, NPROC))
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
