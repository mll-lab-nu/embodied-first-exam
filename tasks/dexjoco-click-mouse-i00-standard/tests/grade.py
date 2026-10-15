"""Standard-mode verifier (DexJoCo): reads what the sim service (which the agent could not touch) wrote: /data/final.json
(live success, two fresh-process replays of the recorded trajectory, determinism, crash-recovery fields),
/data/trajectory.npz, /data/replay.mp4. success = live success AND replay success AND deterministic, the replays having
started in the instance's frozen state. Numeric-only reward.json.

No verdict on the agent is an infrastructure failure, never the agent's 0 (PROTOCOL §2.6, infra_error = 1):
final.json missing (the service or its collect hook never wrote one), unreadable (grader_error = 1 too), or without a
verdict (the collect hook did not finish: not `finalized`, or neither the replays' `deterministic` nor a give-up after
crashes), or the sim sidecar ran fewer than 4 OpenBLAS threads (`too_few_cpus`, with grader_error = 1: the
simulation's result depends on the thread count below 4, docs/benchmarks/dexjoco.md "Threads"; the service then starts
no episode, and replays that ran like that are no verdict). The verdict is on disk before the hook renders replay.mp4,
so a video that did not finish changes nothing.
Every reward.json carries success, deterministic, infra_error, sim_error, grader_error and missing_log."""

import json, os, shutil, traceback

DATA = os.environ.get("RCB_DATA", "/data")
LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
os.makedirs(LOG, exist_ok=True)
BASE = {"success": 0, "deterministic": 0, "infra_error": 0, "sim_error": 0, "grader_error": 0, "missing_log": 0}


def write(ok, out):
    out = {**BASE, **out}
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n")
    json.dump(out, open(f"{LOG}/reward.json", "w"))
    print(out)


def verdict(d):
    ok = bool(d.get("success")) and bool(d.get("replay_success")) and bool(d.get("deterministic"))
    ok = ok and not d.get("instance_mismatch") and not d.get("too_few_cpus")
    # a verdict = the collect hook's replays (finalized, with `deterministic`) or the service's give-up after crashes
    no_verdict = not d.get("finalized") or not (d.get("gave_up") or d.get("deterministic") is not None)
    ok = ok and not no_verdict
    num = lambda k: float(d.get(k) or 0)  # noqa: E731
    return ok, {
        "success": int(ok),
        "live_success": int(bool(d.get("success"))),
        "replay_success": int(bool(d.get("replay_success"))),
        "deterministic": int(bool(d.get("deterministic"))),
        "live_matches_replay": int(bool(d.get("live_matches_replay"))),
        "finalized": int(bool(d.get("finalized"))),
        "no_verdict": int(no_verdict),
        "task_failure": int(bool(d.get("task_failure"))),
        "n_actions": int(d.get("n_actions") or 0),
        "sim_steps": int(d.get("control_steps") or 0),
        "physics_steps": int(d.get("physics_steps") or 0),
        "steps": int(d.get("steps") or 0),
        "calls": int(d.get("calls") or 0),
        "elapsed_s": float(d.get("elapsed_s") or 0),
        "video_rendered": int(bool(d.get("video"))),
        # a replay process gave no result, or the image no longer builds the frozen start: not the agent's 0
        "grader_error": int(bool(d.get("replay_failed") or d.get("instance_mismatch") or d.get("too_few_cpus"))),
        "instance_mismatch": int(bool(d.get("instance_mismatch"))),
        # the sidecar ran fewer than 4 OpenBLAS threads (fewer than 4 CPUs visible to it): not the references' numerics
        "too_few_cpus": int(bool(d.get("too_few_cpus"))),
        "visible_cpus": int(num("visible_cpus")),
        "blas_threads": int(num("blas_threads")),
        # an infrastructure failure, not the agent's (PROTOCOL §2.6): a give-up after crashes between calls or a failed
        # resume (docs/STANDARD_MODE.md §13), the service not ending its episode for the collect hook, a replay
        # process that gave no result or ran out of the hook's time, replays that did not start in the instance's
        # frozen state, a collect hook that left no verdict
        "infra_error": int(bool(d.get("infra_error")) or no_verdict or bool(d.get("too_few_cpus"))),
        "gave_up": int(bool(d.get("gave_up"))),
        "sim_error": int(d.get("reason") == "error"),
        "sim_startups": int(d.get("sim_startups") or 0),
        "resumes": int(d.get("resumes") or 0),
        "resume_state_mismatch": int(d.get("resume_state_mismatch") or 0),
        "resume_max_joint_dev": num("resume_max_joint_dev"),
    }


def main():
    p = os.path.join(DATA, "final.json")
    if not os.path.exists(p):
        write(False, {"missing_log": 1, "infra_error": 1})
        return
    try:
        with open(p) as f:
            d = json.load(f)
        if not isinstance(d, dict):
            raise ValueError("final.json is not an object")
        ok, out = verdict(d)
    except Exception:  # noqa: BLE001 -- an unreadable final.json is not the agent's failure
        traceback.print_exc()
        write(False, {"infra_error": 1, "grader_error": 1, "corrupt_log": 1})
        return
    for f in ("replay.mp4", "trajectory.npz", "episode.jsonl"):  # evidence for humans; it never decides the verdict
        try:
            if os.path.exists(os.path.join(DATA, f)):
                shutil.copy(os.path.join(DATA, f), f"{LOG}/{f}")
        except OSError:
            traceback.print_exc()
    write(ok, out)


main()
