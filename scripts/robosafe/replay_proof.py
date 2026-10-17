#!/usr/bin/env python3
"""Before the tasks are pointed at another eai-robosafe image: every task's reference, as its solution sends it (the
rows of solution/oracle.json and oracle.npz), replayed in the new image from the task's own frozen instance, ends in the
state hash recorded when it was frozen (scripts/robosafe/oracles/<slug>-<NN>.json `result.state_sha`) and is judged
the same. A task whose hash or verdict differs is re-swept under the new image.

    scripts/robosafe/replay_proof.py --image <tag> [task dirs]     # podman, the repository mounted read-only
    python scripts/robosafe/replay_proof.py --inside <task dir> ...  # what --image runs in the container
Exit 1 on any difference, listing the tasks.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import pathlib
import subprocess
import sys

_HERE = pathlib.Path(__file__).resolve()
ROOT = _HERE.parents[2] if len(_HERE.parents) > 2 else pathlib.Path("/")

PROBE = r"""
import json, os, sys
task, rcb = sys.argv[1], sys.argv[2]
sys.path[:0] = [os.path.join(task, "environment", "sim"), os.path.join(rcb, "scripts", "robosafebench")]
import numpy as np
import make_instances as mi
inst = json.load(open(os.path.join(task, "environment", "sim", "instance.json")))
plan = json.load(open(os.path.join(task, "solution", "oracle.json")))["plan"]
npz = os.path.join(task, "solution", "oracle.npz")
arrays = dict(np.load(npz)) if os.path.exists(npz) else {}
res = mi.run_rows(inst, mi.expand(plan, arrays))
print(json.dumps({"state_sha": res["state_sha"], "outcome": res["outcome"], "pass": res["pass"]}))
"""


def inside(tasks: list[str]) -> int:
    rcb = os.environ.get("RCB", "/rcb")

    def one(t):
        name = os.path.basename(t.rstrip("/"))
        base = name[len("rsb-"):].rsplit("-standard", 1)[0]
        want = json.load(open(os.path.join(rcb, "scripts", "robosafebench", "oracles", f"{base}.json")))["result"]
        r = subprocess.run([sys.executable, "-c", PROBE, t, rcb], capture_output=True, text=True)
        try:
            got = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            return name, False, {"error": (r.stderr or r.stdout)[-300:]}
        ok = got["state_sha"] == want["state_sha"] and got["outcome"] == want["outcome"] and got["pass"] == want["pass"]
        return name, ok, {"recorded": want["state_sha"][:16], "replayed": got["state_sha"][:16], "outcome": got["outcome"]}

    bad = []
    with cf.ThreadPoolExecutor(int(os.environ.get("JOBS", "6"))) as ex:
        for name, ok, info in ex.map(one, tasks):
            print(("same     " if ok else "DIFFERS  ") + name + " " + json.dumps(info), flush=True)
            if not ok:
                bad.append(name)
    print(f"replay proof: {len(tasks) - len(bad)} of {len(tasks)} references end in their recorded state and verdict"
          + (f"; re-sweep: {' '.join(bad)}" if bad else ""))
    return 1 if bad else 0


def image(tag: str, tasks: list[str]) -> int:
    tasks = [pathlib.Path(t).resolve() for t in tasks] or sorted((ROOT / "tasks").glob("rsb-*-standard"))
    inner = [f"/rcb/tasks/{t.name}" for t in tasks]
    cmd = ["podman", "run", "--rm", "-e", f"JOBS={os.environ.get('JOBS', '6')}", "-e", "RCB=/rcb", "-e",
           "PYTHONDONTWRITEBYTECODE=1", "-v", f"{ROOT}:/rcb:ro", "-w", "/tmp", tag,
           "python", "/rcb/scripts/robosafe/replay_proof.py", "--inside", *inner]
    return subprocess.run(cmd).returncode


def main() -> int:
    a = sys.argv[1:]
    if a and a[0] == "--inside":
        return inside(a[1:])
    if len(a) >= 2 and a[0] == "--image":
        return image(a[1], a[2:])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
