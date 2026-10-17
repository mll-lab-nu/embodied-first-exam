#!/usr/bin/env python3
"""Re-grade recorded RoboARC privileged trials under the 2026-10-14 grading rule (docs/benchmarks/roboarc.md, Grading
replays) instead of re-running them: success needs both grading replays to succeed AND one of them to reach the goal with
the instance's own thresholds within the trajectory's rows (R-hold, 2026-10-05 to 2026-10-14, required only the first).

    python3 scripts/roboarc/regrade.py JOBS_DIR [JOBS_DIR ...] [--out regrade_roboarc.jsonl]
    python3 scripts/roboarc/regrade.py JOBS_DIR ... --replay [--parallel N] [--memory 24g]

Finds every trial dir under JOBS_DIR: a Harbor trial (<trial>/verifier/reward.json, the task from result.json or
config.json) or a trial downloaded from the evaluation dashboard (<trial>/files/verifier/reward.json, the task in the dir
name). Per trial:
  recorded     the recorded verdict (reward.json `success`);
  old_verdict  the verdict of the rule before 2026-10-14;
  new_verdict  the verdict of the current rule.
From the record (the default): the grader before this change recorded `strict_goal_reached` next to its verdict, so
new_verdict = the recorded success AND strict_goal_reached, exactly (the replays are deterministic on the host class they ran
on, and the rule only adds that condition). A trial already graded under the current rule (`strict_replay_required` 1) keeps
its verdict.
With --replay (needs docker, a GPU and the image of images/roboarc/VERSION): the recorded trajectory
(artifacts/app/output/trajectory.npz) is also replayed by the current task's own tests/grade.py in the task's verifier image
(built from a stamped copy of tasks/<task>/tests/ and checked to hold its files, scripts/stamp_mtimes.py and
scripts/check_image_files.py; the verifier's two replays, no video): new_verdict = that run's
`success`, old_verdict = its replays all succeeded with no review event (what the earlier grade.py credited). Only recorded
successes (and trials without a record) are replayed: the rule only adds a condition, so a recorded failure stays a failure.
A recorded success the replay does not reproduce under the old rule is marked `inconclusive`: re-grade it on the host class
it ran on.

Scope: only the 94 tasks of the RoboARC 0.1.0 release (RELEASED below) are re-graded. A trial of any other task (a RoboARC
task added after 0.1.0, a Genesis robotangle-* task) is listed with `skipped` and the reason, and so is a standard trial
(the standard twins are graded by the live episode since 2026-10-17: docs/benchmarks/roboarc.md, Standard grading). Output: one JSON line per trial (--out) and a table on stdout."""
from __future__ import annotations
import argparse, json, os, pathlib, re, shutil, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_image_files, stamp_mtimes  # noqa: E402  (issue #258: a stamped build context, the image checked)
# The RoboARC 0.1.0 release (main at 2026-10-14): family -> number of tasks, roboarc-<family>-01..NN-i01-{privileged,standard}.
RELEASED_FAMILIES = {"blanket-flatten": 6, "blanket-fold": 5, "buzz-wire-3d": 10, "cast-coil": 8, "cast-keyhole": 6,
                     "fiber-bundling": 10, "hedgehog-in-cage": 8, "horseshoe-ring": 5, "interlocked-claws": 12,
                     "knot-untying": 5, "lock-picking": 5, "orbits": 1, "rope-threading": 8, "slotted-post-ring": 5}
RELEASED = sorted(f"roboarc-{f}-{n:02d}-i01" for f, k in RELEASED_FAMILIES.items() for n in range(1, k + 1))
assert len(RELEASED) == 94
NAME_RE = re.compile(r"(roboarc-[a-z0-9-]+?-\d\d-i\d\d)-(privileged|standard)")


def task_of(d: pathlib.Path) -> str | None:
    """The full task name of a trial dir: Harbor's result.json / config.json, else the dir name (a dashboard download names
    the task, or `<mode>-<base>__...` for the earlier runner), else Harbor's trial name (the task cut to 32 characters, then
    __<id>) matched against the released names."""
    for f, get in (("result.json", lambda j: j.get("task_name")), ("config.json", lambda j: (j.get("task") or {}).get("path"))):
        try:
            v = get(json.loads((d / f).read_text()))
        except (OSError, ValueError, AttributeError):
            v = None
        if v:
            return pathlib.PurePosixPath(str(v)).name
    m = NAME_RE.search(d.name)
    if m:
        return m.group(0)
    m = re.search(r"(privileged|standard)-(roboarc-[a-z0-9-]+?-\d\d-i\d\d)__", d.name)
    if m:
        return f"{m.group(2)}-{m.group(1)}"
    cut = d.name.split("__")[0]
    hits = [f"{b}-{mode}" for b in RELEASED for mode in ("privileged", "standard") if f"{b}-{mode}".startswith(cut)]
    return hits[0] if len(hits) == 1 else (cut if cut.startswith(("roboarc-", "robotangle-")) else None)


def record_of(d: pathlib.Path) -> dict:
    """The recorded reward: verifier/reward.json (Harbor), files/verifier/reward.json or trial.json's `reward` (a
    dashboard download)."""
    for f in (d / "verifier/reward.json", d / "files/verifier/reward.json"):
        try:
            return json.loads(f.read_text())
        except (OSError, ValueError):
            pass
    try:
        return json.loads((d / "trial.json").read_text()).get("reward") or {}
    except (OSError, ValueError, AttributeError):
        return {}


def find_trials(roots: list[str]) -> list[dict]:
    """Trial dirs under the roots: a Harbor trial (result.json, config.json or verifier/) or a dashboard download
    (trial.json, files/verifier/)."""
    seen, out = set(), []
    for r in roots:
        for f in sorted(pathlib.Path(r).rglob("*")):
            if f.name not in ("result.json", "trial.json", "verifier") or (f.name == "verifier" and not f.is_dir()):
                continue
            d = f.parent.parent if f.parent.name == "files" else f.parent
            if d in seen or not ((d / "trial.json").is_file() or any((d / x).is_dir() for x in ("verifier", "agent", "files"))):
                continue                                       # a Harbor job dir (its trials are below it)
            task = task_of(d)
            if not task or not task.startswith(("roboarc-", "robotangle-")):
                continue
            seen.add(d)
            traj = d / "artifacts/app/output/trajectory.npz"
            out.append({"trial": str(d), "task": task, "reward": record_of(d), "traj": str(traj) if traj.is_file() else None})
    return out


def scope(t: dict) -> str | None:
    """Why a trial is not re-graded, or None."""
    m = NAME_RE.fullmatch(t["task"])
    if not m or m.group(1) not in RELEASED:
        return "not in the RoboARC 0.1.0 release (main's released set): not part of this re-grade"
    if m.group(2) == "standard":
        return "standard twin: its grading did not change"
    return None


def from_record(t: dict) -> dict:
    rec = t["reward"]
    out = {"recorded": rec.get("success")}
    if rec.get("success") is None:
        return {**out, "error": "no recorded verdict (no reward with `success`)"}
    if not rec["success"]:   # the rule only adds a condition: a failure stays a failure
        return {**out, "old_verdict": False, "new_verdict": False, "basis": "record (a failure stays a failure)"}
    if int(rec.get("strict_replay_required", 0) or 0) == 1:
        return {**out, "old_verdict": None, "new_verdict": bool(rec["success"]), "basis": "record (already graded under the current rule)"}
    if "strict_goal_reached" not in rec:
        return {**out, "error": "the record has no strict_goal_reached: use --replay"}
    return {**out, "old_verdict": bool(rec["success"]), "new_verdict": bool(rec["success"]) and bool(rec["strict_goal_reached"]),
            "strict_goal_reached": int(rec["strict_goal_reached"]), "replay_hold_steps": rec.get("replay_hold_steps"),
            "basis": "record"}


def family_of(tests: pathlib.Path) -> str:
    m = re.search(r"--family\s+(\S+)", (tests / "test.sh").read_text())
    if not m:
        raise ValueError(f"{tests}/test.sh names no --family")
    return m.group(1)


def replay(t: dict, work: pathlib.Path, memory: str) -> dict:
    """The current task's tests/grade.py on the recorded trajectory, in the task's verifier image."""
    tests = ROOT / "tasks" / t["task"] / "tests"
    if not tests.is_dir():
        return {"replay_error": f"no task dir {tests.parent.name} in this checkout"}
    if not t["traj"]:
        return {"replay_error": "no recorded trajectory (artifacts/app/output/trajectory.npz) in the trial dir"}
    tag = f"rcb-regrade-{t['task']}:local"
    # built from a stamped copy and checked after (issue #258: BuildKit can put another task's equal-size tests/ file, a
    # runtime_binding.json, into this image when the checkout's mtimes are equal; scripts/stamp_mtimes.py)
    ctx = work / "context" / "tests"
    shutil.rmtree(ctx, ignore_errors=True)
    shutil.copytree(tests, ctx, symlinks=True)
    if stamp_mtimes.stamp_tree(str(ctx), full=True)["err"]:
        return {"replay_error": f"could not stamp the build context {ctx}"}
    b = subprocess.run(["docker", "build", "-q", "-t", tag, str(ctx)], capture_output=True, text=True)
    if b.returncode:
        return {"replay_error": f"docker build failed: {(b.stderr or b.stdout)[-300:]}"}
    try:
        chk = check_image_files.check(tag, str(ctx))
    except (OSError, RuntimeError, ValueError) as e:
        return {"replay_error": f"could not check the verifier image's files: {e}"}
    if chk["mismatch"]:
        return {"replay_error": "the verifier image holds other files than the task's tests/: "
                                + ", ".join(m["file"] for m in chk["mismatch"])}
    out = work / "verifier"; out.mkdir(parents=True, exist_ok=True)
    cmd = ["docker", "run", "--rm", "--gpus", "all", "-e", "NVIDIA_DRIVER_CAPABILITIES=all", "--memory", memory,
           "-e", "RCB_VERIFIER_LOG_DIR=/o", "-v", f"{out}:/o", "-v", f"{pathlib.Path(t['traj']).resolve()}:/app/output/trajectory.npz:ro",
           tag, "bash", "-c", f"python /tests/grade.py --family {family_of(tests)} --instance /tests/instance.json "
           "--traj /app/output/trajectory.npz --repeat 2 --no-video; rc=$?; chmod -R a+rX /o; exit $rc"]   # as test.sh: readable
    with open(work / "grade.log", "w") as log:
        p = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
    try:
        r = json.loads((out / "reward.json").read_text())
    except (OSError, ValueError):
        return {"replay_error": f"grade.py gave no reward.json (rc={p.returncode}; log {work / 'grade.log'})"}
    if r.get("grader_error") or r.get("infra_error") or r.get("bad_trajectory") or r.get("missing_trajectory"):
        keys = [k for k in ("grader_error", "infra_error", "bad_trajectory", "missing_trajectory") if r.get(k)]
        return {"replay_error": "replay: " + ", ".join(keys), "replay_reward": r}
    old = bool(r.get("all_success")) and bool(r.get("instance_ok")) and not r.get("simulator_instability") \
        and not int(r.get("review_events", 0) or 0)
    return {"replay_old_verdict": old, "replay_new_verdict": bool(r.get("success")),
            "replay_strict_goal_reached": int(r.get("strict_goal_reached", 0)), "replay_hold_steps": r.get("replay_hold_steps"),
            "replay_success_in_hold_only": int(r.get("success_in_hold_only", 0)), "replay_deterministic": int(r.get("deterministic", 0))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jobs", nargs="+", help="Harbor jobs trees or downloaded trial folders")
    ap.add_argument("--out", default="regrade_roboarc.jsonl")
    ap.add_argument("--replay", action="store_true", help="also replay the recorded trajectories (docker, GPU)")
    ap.add_argument("--parallel", type=int, default=1, help="--replay: trials replayed at once (each a verifier container)")
    ap.add_argument("--memory", default="24g", help="--replay: memory limit of each verifier container")
    ap.add_argument("--work", default="", help="--replay: keep the work dirs (grade logs, verdicts) here instead of a temporary dir")
    a = ap.parse_args()
    trials = find_trials(a.jobs)
    results = []
    todo = []
    for t in trials:
        r = {"trial": t["trial"], "task": t["task"]}
        why = scope(t)
        if why:
            results.append({**r, "skipped": why}); continue
        r.update(from_record(t))
        results.append(r)
        if r.get("recorded") is None or r["recorded"]:      # a recorded failure stays a failure: nothing to replay
            todo.append((t, r))
    if a.replay and todo:
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory(prefix="roboarc_regrade_") as tmp, ThreadPoolExecutor(max(1, a.parallel)) as ex:
            td = pathlib.Path(a.work).resolve() if a.work else pathlib.Path(tmp)

            def one(k_tr):
                k, (t, r) = k_tr
                print(f"[regrade] replaying {t['task']} ({pathlib.Path(t['trial']).name})", file=sys.stderr, flush=True)
                r.update(replay(t, td / f"{k:04d}", a.memory))
            list(ex.map(one, enumerate(todo)))
        for t, r in todo:
            if "replay_new_verdict" in r:
                rec = r.get("recorded")
                if rec is not None and int(t["reward"].get("strict_replay_required", 0) or 0) == 0:
                    r["reproduced"] = bool(r["replay_old_verdict"]) == bool(rec)
                    r["inconclusive"] = bool(rec) and not r["replay_old_verdict"]
                r["old_verdict"] = r["replay_old_verdict"] if r.get("old_verdict") is None else r["old_verdict"]
                if r.get("new_verdict") is not None and r["new_verdict"] != r["replay_new_verdict"]:
                    r["record_vs_replay"] = "the record and the replay disagree on the new verdict"
                if r.get("inconclusive"):
                    # board 0130 review M1: a replay that does not reproduce the recorded success under the old rule says
                    # nothing about the new one; keep the record's exact verdict (None when there is none)
                    r["basis"] = "record (replay inconclusive on this host)"
                else:
                    r["new_verdict"] = r["replay_new_verdict"]
                    r["basis"] = "replay"
    for r in results:
        if "skipped" not in r and "error" not in r and r.get("new_verdict") is not None:
            r["label"] = "re-graded under 2026-10-14 rules"
    with open(a.out, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    v = lambda x: "-" if x is None else ("PASS" if x else "fail")  # noqa: E731
    for r in results:
        note = r.get("skipped") or r.get("error") or r.get("replay_error") or \
            ("INCONCLUSIVE: recorded success not reproduced on this host" if r.get("inconclusive") else r.get("basis", ""))
        print(f"{r['task'][:44]:44s} rec={v(r.get('recorded')):4s} old={v(r.get('old_verdict')):4s} "
              f"new={v(r.get('new_verdict')):4s} {pathlib.Path(r['trial']).name[-24:]:24s} {note[:90]}")
    n = [r for r in results if "new_verdict" in r and r.get("old_verdict") is not None]
    print(f"[regrade] {len(results)} trial(s): {len(n)} re-graded, {sum(1 for r in n if r['old_verdict'] and not r['new_verdict'])} "
          f"success(es) withdrawn, {sum(1 for r in results if 'skipped' in r)} skipped; {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
