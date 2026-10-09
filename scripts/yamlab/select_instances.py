#!/usr/bin/env python3
"""Select YAMLab's frozen instances and record their oracles (run on a GPU host with eai-yamlab built; not part of any task).

For each task, walk YAMLab's teleoperation files in order (one object pair per file: putpot_000 = Pot/pot_000 +
Cooktop/cooktop_000, ...). YAMLab records a file's demos on a fixed placement schedule (demo j = schedule entry j:
PutPotOnCooktop 3 lateral pot positions x 3 yaws, HangMugOnTree 3 mug yaws); inside the k-th file (k = 0, 1, ...) the
demos are tried from demo k mod n on, wrapping around, so the instances spread over the schedule. A candidate is accepted when, in the eai-yamlab image,
  1. `rcb_yamlab.py make-instance` writes the instance (the demo's recorded initial state) and the oracle actions (a 30-step
     ramp from the home pose to the demo's first action, then the demo's recorded actions),
  2. `run-actions` executes them in a fresh process and succeeds (YAMLab's evaluation-threshold stages all latch),
  3. two `replay` runs, each in its own fresh process (the second also films the replay: rendering never steps physics),
     succeed and end in the same state hash as the live run.
The first accepted demo of a file is that object pair's instance; the walk stops after --per-task pairs. Every candidate's
evidence (the JSON lines of the four processes) goes to <out>/<task>/<file>_d<demo>/, and <out>/selection.json lists the
outcome. A step whose process died without its result (a crash, the GPU out of memory) is an infrastructure failure, not
a rejection: the candidate is retried (3 attempts), and if it still fails the pair is left out of this run instead of
moving on to its next demo (delete that verdict.json and rerun). Reruns skip candidates that already have a verdict.

  python3 scripts/yamlab/select_instances.py --teleop /data/yamlab/tasks_data --out /data/yamlab-select --per-task 25 --jobs 3
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS = {"put_pot_on_cooktop": ("PutPotOnCooktop", "putpot"), "hang_mug_on_tree": ("HangMugOnTree", "hangmug")}
IMAGE = "ghcr.io/mll-lab-nu/eai-yamlab:" + (HERE.parents[1] / "images" / "yamlab" / "VERSION").read_text().strip()
STEPS = """set -u
T=$1; F=$2; D=$3; O=$4; TOOL=/tool/rcb_yamlab.py; STEP_S=${STEP_S:-1500}
export RCB_SESSION_LOG=""
cd /tmp
timeout $STEP_S python $TOOL make-instance --task $T --dataset $F --demo $D --out $O/instance.json --oracle-out $O/oracle_actions.npy > $O/make.out 2> $O/make.err || exit 11
timeout $STEP_S python $TOOL run-actions --task $T --instance $O/instance.json --actions $O/oracle_actions.npy --out $O/trajectory.npz \
  --source "YAMLab teleoperation demo $(basename $F) demo_$D (30-step ramp + recorded actions)" > $O/live.out 2> $O/live.err || exit 12
timeout $STEP_S python $TOOL replay --task $T --instance $O/instance.json --traj $O/trajectory.npz --strict > $O/replay1.out 2> $O/replay1.err || exit 13
timeout $STEP_S python $TOOL replay --task $T --instance $O/instance.json --traj $O/trajectory.npz --strict --video $O/replay.mp4 > $O/replay2.out 2> $O/replay2.err || exit 14
"""


def last_json(p: Path) -> dict:
    try:
        lines = [l for l in p.read_text().splitlines() if l.startswith("{")]
        return json.loads(lines[-1]) if lines else {}
    except OSError:
        return {}


def verdict(d: Path) -> dict:
    mk, live, r1, r2 = (last_json(d / f) for f in ("make.out", "live.out", "replay1.out", "replay2.out"))
    o1, o2 = ((r.get("replays") or [{}])[0] for r in (r1, r2))
    shas = [live.get("state_sha"), o1.get("state_sha"), o2.get("state_sha")]
    ok = bool(live.get("success")) and bool(o1.get("success")) and bool(o2.get("success")) and None not in shas and len(set(shas)) == 1 \
        and bool(r1.get("instance_exact")) and bool(r2.get("instance_exact"))
    return {"accepted": ok, "instance_sha": mk.get("state_sha"), "assets": mk.get("assets"), "n_actions": live.get("n_actions"),
            "live": {k: live.get(k) for k in ("success", "stages", "sim_steps", "state_sha")}, "replay_shas": shas[1:],
            "replay_success": [o1.get("success"), o2.get("success")], "instance_exact": [r1.get("instance_exact"), r2.get("instance_exact")]}


GPU_LOCK = threading.Lock()


def wait_for_gpu(min_free_mb: int = 8000, settle_s: int = 150) -> None:
    """Isaac's RTX renderer hangs or fails when the GPU runs out of memory while it initialises (2-4 GB per starting process
    on a shared GPU): start a candidate only with enough free GPU memory, one start at a time, and let it settle."""
    lock_path = os.environ.get("YAMLAB_GPU_LOCK")       # optional: a lock file other jobs on this GPU take too (flock)
    with GPU_LOCK, open(lock_path or os.devnull, "a") as lf:
        if lock_path:
            import fcntl
            fcntl.flock(lf, fcntl.LOCK_EX)
        while True:
            out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout
            if int(out.split()[0]) >= min_free_mb:
                break
            time.sleep(30)
        time.sleep(settle_s)


def infra_failure(d: Path, rc: int) -> bool:
    """A step's process died without its result (a crash, a GPU out of memory, a timeout): an infrastructure failure, not a
    rejection of the candidate. A rejection is a run that finished and failed (no success, or the hashes differ)."""
    if rc == 0:
        return False
    step = {11: "make.out", 12: "live.out", 13: "replay1.out", 14: "replay2.out"}.get(rc)
    return step is None or not last_json(d / step)


def run_candidate(task: str, teleop: Path, f: Path, demo: int, out: Path, cache: str, tries: int = 3) -> dict:
    d = out / task / f"{f.stem}_d{demo}"
    if (d / "verdict.json").exists():
        return json.loads((d / "verdict.json").read_text())
    rel = f.relative_to(teleop)
    name = f"yamlab-select-{task}-{f.stem}-d{demo}"
    cmd = ["docker", "run", "--rm", "--name", name, "--gpus", "all", "--shm-size", "8g", "--memory", "32g",
           "-v", f"{HERE / 'shared'}:/tool:ro", "-v", f"{teleop}:/teleop:ro", "-v", f"{d}:/o", "-v", f"{cache}:/cache",
           IMAGE, "bash", "/o/steps.sh", task, f"/teleop/{rel}", str(demo), "/o"]
    infra = []
    for attempt in range(tries):
        if d.exists():
            for old in d.iterdir():            # a fresh start: nothing of a failed attempt stays
                old.unlink()
        d.mkdir(parents=True, exist_ok=True)
        (d / "steps.sh").write_text(STEPS)
        wait_for_gpu()
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        try:
            rc = subprocess.run(cmd, capture_output=True, text=True, timeout=7200).returncode
        except subprocess.TimeoutExpired:
            rc = -9
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)   # never leave a container behind
        if not infra_failure(d, rc):
            break
        infra.append({"attempt": attempt, "rc": rc})
        print(json.dumps({"task": task, "file": f.name, "demo": demo, "infra_failure": rc, "attempt": attempt}), flush=True)
    v = {"task": task, "file": f.name, "demo": demo, "rc": rc, "infra_failures": infra, **verdict(d)}
    if infra_failure(d, rc):
        v["infra"] = True                      # not a rejection: the walk stops at this candidate (see pair())
    (d / "verdict.json").write_text(json.dumps(v, indent=1))
    return v


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--teleop", required=True, help="YAMLab dataset tasks_data/ with <Task>/teleop/*.hdf5")
    ap.add_argument("--out", required=True); ap.add_argument("--per-task", type=int, default=25); ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--tasks", default=",".join(TASKS)); ap.add_argument("--max-demos", type=int, default=9)
    ap.add_argument("--cache", default="rcb_yamlab_dev_cache", help="docker volume for Isaac's Kit cache (selection only)")
    a = ap.parse_args()
    teleop, out = Path(a.teleop).resolve(), Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    sel_path = out / "selection.json"
    lock = threading.Lock()
    selection = json.loads(sel_path.read_text()) if sel_path.exists() else {}
    for task in a.tasks.split(","):
        data, prefix = TASKS[task]
        files = sorted((teleop / data / "teleop").glob(f"{prefix}_*.hdf5"))
        chosen: dict[str, dict] = {}
        tried: list[dict] = []
        # one worker per object pair: a pair's demos are tried in order until one passes
        def pair(f: Path) -> tuple[str, dict | None, list]:
            import h5py
            with h5py.File(f, "r") as h:
                n = len([k for k in h["data"].keys() if k.startswith("demo_")])
            log = []
            # YAMLab records a file's demos on a fixed placement schedule (PutPotOnCooktop: 3 lateral positions x 3 yaws,
            # HangMugOnTree: 3 yaws, demo j = schedule entry j). The k-th file starts at demo k mod n and wraps around, so
            # the instances spread evenly over the schedule instead of all taking its first placement.
            k = files.index(f)
            for demo in [(k + j) % n for j in range(n)][: a.max_demos]:
                v = run_candidate(task, teleop, f, demo, out, a.cache); log.append(v)
                print(json.dumps({k: v.get(k) for k in ("task", "file", "demo", "rc", "accepted", "n_actions", "replay_shas", "infra")}), flush=True)
                if v.get("accepted"):
                    return f.name, v, log
                if v.get("infra"):             # never skip a demo for an infrastructure failure: the pair waits for a rerun
                    return f.name, None, log
            return f.name, None, log
        with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
            pending = list(files); futs = {}
            while pending or futs:
                while pending and len(futs) < a.jobs and len(chosen) + len(futs) < a.per_task:
                    f = pending.pop(0); futs[ex.submit(pair, f)] = f
                if not futs:
                    break
                done, _ = cf.wait(futs, return_when=cf.FIRST_COMPLETED)
                for fu in done:
                    futs.pop(fu)
                    name, v, log = fu.result(); tried += log
                    if v is not None:
                        chosen[name] = v
        with lock:
            selection[task] = {"chosen": dict(sorted(chosen.items())[: a.per_task]), "tried": tried,
                               "rule": "files in order; inside the k-th file, demos from k mod n on (wrapping); the first accepted demo is the pair's instance"}
            sel_path.write_text(json.dumps(selection, indent=1))
        print(json.dumps({"task": task, "chosen": len(chosen), "tried": len(tried)}), flush=True)


if __name__ == "__main__":
    sys.exit(main())
