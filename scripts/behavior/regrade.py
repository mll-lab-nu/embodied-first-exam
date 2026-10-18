#!/usr/bin/env python3
"""Re-grade recorded BEHAVIOR-1K trials with the current grader (2026-10-14 rules: the goal held 1 s released and at rest,
the settle window, stable hashing, a simulator breakdown as a recorded failure; docs/benchmarks/behavior.md) from their
recorded trajectories, instead of re-running the agents.

    python3 scripts/behavior/regrade.py JOBS_DIR [JOBS_DIR ...] [--out regrade.jsonl] [--gpus 0,1] [--select candidates]
    python3 scripts/behavior/regrade.py --dry-run JOBS_DIR ...      # list what would be re-graded, and the old verdicts

Host side, run from the repository root (the current tasks/ are the grader): needs docker, the image the privileged
tasks' tests/Dockerfile names (ghcr.io/mll-lab-nu/eai-behavior:<tag>, private), an RTX-class GPU, and the licensed
dataset in $RCB_BEHAVIOR_DATA. For every BEHAVIOR trial under JOBS_DIR (a Harbor jobs tree: <trial>/config.json +
<trial>/verifier/reward.json) it takes the recorded trajectory (privileged: artifacts/app/output/trajectory.npz;
standard: artifacts/out/trajectory.npz, else verifier/trajectory.npz) and runs the family's privileged
tests/grade.py on it in a fresh container: two fresh-process replays, no video (`--no-video`). Reported per trial:
  old           the recorded verdict (verifier/reward.json `success`);
  new           the current verdict of the trajectory (`success`; `infra` when the replays did not run or the scene
                did not rebuild: no verdict; a replay that ended on a simulator breakdown is a 0, labelled `breakdown`);
  old_rule_here the bare BDDL goal held at some step of the replay's own rows here (0 <= `goal_first_step` <=
                `n_actions`; a step of the settle window after them does not count): the rule before
                2026-10-14. old 1, new 0 with old_rule_here 1 is the stricter rule; with old_rule_here 0 the replay
                went elsewhere on this host (`inconclusive`: re-grade it on the host class it ran on).
Standard trials: conservative. The verdict there also needed the live episode, which the service ended on the first
step the bare goal held; under the current rule it would have gone on and the agent could still have let go. The
re-grade can only say whether the recorded rows, plus the settle window, reach the current rule in both replays
(label "re-graded under 2026-10-14 rules (conservative)"). A standard trajectory over the privileged grader's
MAX_ROWS (40,000) cannot be re-graded this way (`skipped`).
--select candidates (the default) re-grades only the trials whose verdict can change: old
successes, and failures whose replays succeeded, disagreed, or (standard) whose live episode succeeded.
The container differs from the verifier's in two ways that do not touch the physics: RCB_TEXTURE_BUDGET=0.1 (so
re-grades can share a GPU; the verifier leaves Isaac's default) and a cold Kit cache.
Output: one JSON line per trial (--out, appended; trials already in it are skipped) and a table on stdout.
Standard library only."""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parents[2]
TRAJ = {"privileged": ["artifacts/app/output/trajectory.npz"],
        "standard": ["artifacts/out/trajectory.npz", "verifier/trajectory.npz"]}
MAX_ROWS = 40_000


def task_name(d: pathlib.Path) -> str | None:
    for f, get in (("result.json", lambda j: j.get("task_name")), ("config.json", lambda j: (j.get("task") or {}).get("path"))):
        try:
            v = get(json.loads((d / f).read_text()))
        except (OSError, ValueError, AttributeError):
            v = None
        if v:
            return pathlib.PurePosixPath(str(v)).name
    return None


def trials(roots: list[str]):
    for r in roots:
        for rw in sorted(pathlib.Path(r).resolve().rglob("verifier/reward.json")):   # absolute: docker -v needs it
            d = rw.parent.parent
            if any(part.startswith("_superseded") for part in d.parts):
                continue                 # an attempt voided for infrastructure (docs/protocol/running.md): never a result
            name = task_name(d) or ""
            m = re.fullmatch(r"behavior-(.+)-i(\d\d)-(privileged|standard)", name)
            if m:
                tests = ROOT / "tasks" / f"behavior-{m.group(1)}-i{m.group(2)}-privileged" / "tests"
                f = re.search(r"--family (\S+)", (tests / "test.sh").read_text()) if (tests / "test.sh").is_file() else None
                yield d, name, (f.group(1) if f else m.group(1).replace("-", "_")), m.group(3), tests


def load(p: pathlib.Path) -> dict:
    try:
        v = json.loads(p.read_text())
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def candidate(mode: str, rw: dict) -> bool:
    if mode != "privileged" and rw.get("graded_by_live"):
        return False                    # graded by the live episode (board 0151): no replay, no `deterministic` to re-grade
    if rw.get("success"):
        return True
    if mode == "privileged":
        return bool(rw.get("all_success")) or ("deterministic" in rw and not rw.get("deterministic") and "all_success" in rw)
    return bool(rw.get("live_success") or rw.get("replay_success")) or (bool(rw.get("finalized")) and not rw.get("deterministic"))


def image() -> str:
    df = ROOT / "tasks/behavior-picking-up-trash-i00-privileged/tests/Dockerfile"
    m = re.search(r"^FROM\s+(\S+)", df.read_text(), re.M)
    return m.group(1) if m else "ghcr.io/mll-lab-nu/eai-behavior:0.1.1"


def regrade(tests: pathlib.Path, fam: str, traj: pathlib.Path, gpu: str, img: str, data: str) -> dict:
    if not (tests / "grade.py").is_file():
        return {"error": f"no grader at {tests} (a task no longer in this checkout)"}
    with tempfile.TemporaryDirectory(prefix="rcb_behavior_regrade_") as tmp:
        os.chmod(tmp, 0o777)
        name = f"rcb-behavior-regrade-{os.getpid()}-{threading.get_ident()}"
        cmd = ["docker", "run", "--rm", "--name", name, "--gpus", f"device={gpu}", "--shm-size", "8g",
               "-e", "PYTHONHASHSEED=0", "-e", "OMP_NUM_THREADS=8", "-e", "MKL_NUM_THREADS=8", "-e", "RCB_TEXTURE_BUDGET=0.1",
               "-e", "RCB_VERIFIER_LOG_DIR=/o", "-v", f"{data}:/data:ro", "-v", f"{tests}:/tests:ro",
               "-v", f"{traj.parent}:/traj:ro", "-v", f"{tmp}:/o", img,
               "python", "/tests/grade.py", "--family", fam, "--instance", "/tests/instance.json",
               "--traj", f"/traj/{traj.name}", "--repeat", "2", "--no-video"]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=2 * 28000 + 1800)
        except subprocess.TimeoutExpired:   # the CLI is gone, the container is not: free the GPU
            subprocess.run(["docker", "kill", name], capture_output=True, timeout=120)
            return {"error": "re-grade timed out"}
        new = load(pathlib.Path(tmp) / "reward.json")
        if not new:
            new = {"error": f"no reward.json (docker exit {p.returncode}): {p.stderr[-400:]}"}
        return new


def verdict(mode: str, old: dict, new: dict) -> dict:
    o = int(bool(old.get("success")))
    if new.get("error") or new.get("infra_error") or new.get("grader_error"):
        n = "infra"
    else:
        n = int(bool(new.get("success")))
    # the old rule held on the agent's own rows (not only in the settle window after them)
    here = 0 <= int(new.get("goal_first_step", -1)) <= int(new.get("n_actions") or 0)
    label = "unchanged" if n == o else ("infra (no verdict)" if n == "infra" else "now passes" if n == 1 else
                                        "breakdown" if new.get("sim_breakdown") else
                                        "stricter rule" if here else "inconclusive (replay went elsewhere here)")
    if mode == "standard":
        label += "; re-graded under 2026-10-14 rules (conservative)"
    return {"old": o, "new": n, "old_rule_here": int(here), "label": label}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("jobs", nargs="+")
    ap.add_argument("--out", default="behavior_regrade.jsonl")
    ap.add_argument("--gpus", default="0", help="GPU indices, one re-grade at a time on each (e.g. 0,1)")
    ap.add_argument("--select", choices=("candidates", "all"), default="candidates")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    data = os.path.abspath(os.environ["RCB_BEHAVIOR_DATA"]) if os.environ.get("RCB_BEHAVIOR_DATA") else ""
    if not a.dry_run and not data:
        sys.exit("set RCB_BEHAVIOR_DATA to the licensed BEHAVIOR dataset (docs/benchmarks/behavior.md)")
    done = set()
    if os.path.exists(a.out):
        for line in open(a.out):
            try:
                done.add(json.loads(line)["trial"])
            except (ValueError, KeyError):
                pass
    work, skipped = [], []
    for d, task, fam, mode, tests in trials(a.jobs):
        if str(d) in done:
            continue
        old = load(d / "verifier" / "reward.json")
        if a.select == "candidates" and not candidate(mode, old):
            continue
        traj = next((d / t for t in TRAJ[mode] if (d / t).is_file()), None)
        n_rows = int(old.get("n_actions") or 0)
        if traj is None or (mode == "standard" and n_rows > MAX_ROWS):
            skipped.append((d, task, "no trajectory" if traj is None else f"{n_rows} rows > {MAX_ROWS}"))
            continue
        work.append((d, task, fam, mode, traj, old, tests))
    print(f"{len(work)} trial(s) to re-grade, {len(skipped)} skipped, {len(done)} already in {a.out}", flush=True)
    for d, task, why in skipped:
        print(f"  skipped {task} {d.name}: {why}")
    if a.dry_run:
        for d, task, fam, mode, traj, old, tests in work:
            print(f"  {task} {d.name} old={int(bool(old.get('success')))} rows={old.get('n_actions')}")
        return 0
    img, gpus, lock = image(), [g.strip() for g in a.gpus.split(",") if g.strip()], threading.Lock()
    free = list(gpus)

    def one(item):
        d, task, fam, mode, traj, old, tests = item
        with lock:
            gpu = free.pop()
        try:
            new = regrade(tests, fam, traj, gpu, img, data)
        except Exception as exc:  # noqa: BLE001
            new = {"error": repr(exc)[:400]}
        finally:
            with lock:
                free.append(gpu)
        rec = {"trial": str(d), "task": task, "mode": mode, **verdict(mode, old, new),
               "new_reward": {k: v for k, v in new.items() if not isinstance(v, (dict, list))}}
        with lock:
            with open(a.out, "a") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"{rec['task']:<62} {mode:<10} old={rec['old']} new={rec['new']} {rec['label']}", flush=True)
        return rec

    with cf.ThreadPoolExecutor(max_workers=len(gpus)) as ex:
        recs = list(ex.map(one, work))
    flips = [r for r in recs if r["old"] != r["new"]]
    print(f"\n{len(recs)} re-graded; {len(flips)} changed:")
    for r in flips:
        print(f"  {r['task']} {r['mode']}: {r['old']} -> {r['new']} ({r['label']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
