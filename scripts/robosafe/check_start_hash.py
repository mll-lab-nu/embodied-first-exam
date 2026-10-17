#!/usr/bin/env python3
"""Every task starts from the state RoboSafeBench admitted: the start hash of the episode a task's service serves equals
the frozen instance's `state_sha` (instance.json, written by make_instances.py from RoboSafeBench's own start of the key),
and equals the hash of RoboSafeBench's own start of the same key (family, member, seed, robot, interface) in the same
image. A mismatch is a blocker: the admission evidence would not cover what the agent gets.

    python3 scripts/robosafe/check_start_hash.py --records <jobs dir> [...]    # fast: the trials already run (standard
                                         # library): each verdict.json's two replays started from the frozen start
    scripts/robosafe/check_start_hash.py --image <tag> [task dirs]          # live: in the image, per task, the service
                                         # built from the task's own environment/sim/ (no physics step) and RoboSafeBench's
                                         # start of the key, against instance.json (default: every rsb-* task; podman)
    python scripts/robosafe/check_start_hash.py --inside <task dir> ...     # what --image runs in the container

Exit 1 on any mismatch, with the task and the three hashes.
"""
from __future__ import annotations

import concurrent.futures as cf
import glob
import json
import os
import pathlib
import subprocess
import sys
import tempfile

_HERE = pathlib.Path(__file__).resolve()
ROOT = _HERE.parents[2] if len(_HERE.parents) > 2 else pathlib.Path("/")   # in the container: /chk/

PROBE = r"""
import json, os, sys, tempfile
sim = sys.argv[1]
sys.path.insert(0, sim)
os.environ["RCB_DATA"] = tempfile.mkdtemp()
import rcb_rsb
inst = json.load(open(os.path.join(sim, "instance.json")))
out = {"instance": inst["state_sha"]}
try:
    import server
    out["service"] = server.RoboSafe(os.path.join(sim, "instance.json")).s.ep.state_hash()
except RuntimeError as e:                      # the service refuses a start that differs from the frozen one
    out["service"] = "refused: " + str(e)[:120]
_, _, ep = rcb_rsb.start(dict(inst["key"]))
out["robosafebench"] = ep.state_hash()
print(json.dumps(out))
"""


def records(dirs: list[str]) -> int:
    n, bad = 0, []
    for d in dirs:
        for f in sorted(glob.glob(os.path.join(d, "**", "verifier", "verdict.json"), recursive=True)):
            t = pathlib.Path(f).parents[1].name.split("__")[0]
            rp = json.loads(pathlib.Path(f).read_text()).get("replays") or {}
            ss, fz = rp.get("start_sha") or [], rp.get("frozen_start_sha")
            inst = ROOT / "tasks" / t / "environment/sim/instance.json"
            want = json.loads(inst.read_text())["state_sha"] if inst.exists() else fz
            n += 1
            if not (len(ss) == 2 and ss[0] == ss[1] == fz == want):
                bad.append(f"{f}: replays started {ss}, frozen {fz}, instance.json {want}")
    for b in bad:
        print("MISMATCH", b)
    print(f"start hashes of {n} trial(s): {n - len(bad)} from the frozen start, {len(bad)} not")
    return 1 if bad else 0


def inside(tasks: list[str]) -> int:
    def one(t):
        sim = os.path.join(t, "environment", "sim")
        r = subprocess.run([sys.executable, "-c", PROBE, sim], capture_output=True, text=True)
        try:
            return t, json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            return t, {"error": (r.stderr or r.stdout)[-300:]}
    bad = 0
    with cf.ThreadPoolExecutor(int(os.environ.get("JOBS", "6"))) as ex:
        for t, h in ex.map(one, tasks):
            ok = "error" not in h and h["instance"] == h["service"] == h["robosafebench"]
            bad += not ok
            print(("ok       " if ok else "MISMATCH ") + os.path.basename(t.rstrip("/")) + " " + json.dumps(h), flush=True)
    print(f"start hashes of {len(tasks)} task(s), live: {len(tasks) - bad} equal (instance.json = service = RoboSafeBench), {bad} not")
    return 1 if bad else 0


def image(tag: str, tasks: list[str]) -> int:
    tasks = [str(pathlib.Path(t).resolve()) for t in tasks] or sorted(str(p) for p in (ROOT / "tasks").glob("rsb-*-standard"))   # the realtime tasks: check_double_build_rt.py
    tdir = str(ROOT / "tasks")
    inner = ["/tasks/" + os.path.basename(t) for t in tasks]
    cmd = ["podman", "run", "--rm", "-e", f"JOBS={os.environ.get('JOBS', '6')}", "-v", f"{tdir}:/tasks:ro",
           "-v", f"{pathlib.Path(__file__).resolve()}:/chk/check_start_hash.py:ro", "-w", "/tmp", tag,
           "python", "/chk/check_start_hash.py", "--inside", *inner]
    return subprocess.run(cmd).returncode


def main() -> int:
    a = sys.argv[1:]
    if a and a[0] == "--records":
        return records(a[1:])
    if a and a[0] == "--inside":
        return inside(a[1:])
    if len(a) >= 2 and a[0] == "--image":
        return image(a[1], a[2:])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
