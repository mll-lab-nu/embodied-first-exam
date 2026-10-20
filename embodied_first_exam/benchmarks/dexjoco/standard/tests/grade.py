"""Standard-mode verifier (DexJoCo): reads what the sim service (which the agent could not touch) wrote: /data/final.json
(the live episode's verdict, crash-recovery fields), /data/trajectory.npz, /data/replay.mp4. success = the live episode
ended in success under DexJoCo's own check (graded_by = "live": owner, 2026-10-17; nothing is replayed to
grade it), the episode having started in the instance's frozen state. Numeric-only reward.json.

No verdict on the agent is an infrastructure failure, never the agent's 0 (PROTOCOL §2.6, infra_error = 1):
final.json missing (the service or its collect hook never wrote one), unreadable (grader_error = 1 too), or without a
verdict (the collect hook did not finish: not `finalized`, or neither the live verdict (`graded_by`) nor a give-up), a
give-up after crashes that were not all inside the agent's calls (`sim_crashed`, `resume_failed`), the service not
ending its episode for the collect hook, a scene that did not start in the frozen instance (`instance_mismatch`, with
grader_error = 1), or the sim sidecar ran fewer than 4 OpenBLAS threads (`too_few_cpus`, with grader_error = 1: the
simulation's result depends on the thread count below 4, docs/benchmarks/dexjoco.md "Threads"; the service then starts
no episode). Crashes all inside the agent's calls (`sim_crashed_on_call`), a simulator error raised by the agent's
actions (`reason = "error"`, sim_error = 1), a timeout or a task failure are the agent's result. The verdict is on disk
before the hook renders replay.mp4, so a video that did not finish changes nothing.
Every reward.json carries success, live_success, graded_by_live, replays, infra_error, sim_error, grader_error,
finalized and missing_log."""

import json, os, shutil, traceback

DATA = os.environ.get("RCB_DATA", "/data")
LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
os.makedirs(LOG, exist_ok=True)
BASE = {"success": 0, "live_success": 0, "graded_by_live": 1, "replays": 0, "infra_error": 0, "sim_error": 0,
        "grader_error": 0, "finalized": 0, "missing_log": 0}


def write(ok, out):
    out = {**BASE, **out}
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n")
    json.dump(out, open(f"{LOG}/reward.json", "w"))
    print(out)


def verdict(d):
    # a verdict = the live episode's, written by the collect hook (finalized, graded_by = "live"), or the service's
    # give-up (after crashes, or at the start)
    no_verdict = not d.get("finalized") or not (d.get("gave_up") or d.get("graded_by") == "live")
    ok = bool(d.get("success")) and d.get("graded_by") == "live" and not no_verdict
    ok = ok and not d.get("instance_mismatch") and not d.get("too_few_cpus") and not d.get("infra_error")
    ok = ok and d.get("reason") != "error"     # an episode a simulator error ended is never a success
    num = lambda k: float(d.get(k) or 0)  # noqa: E731
    return ok, {
        "success": int(ok),
        "live_success": int(bool(d.get("live_success", d.get("success")))),
        "graded_by_live": 1,
        "replays": 0,
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
        # the image no longer builds the frozen start, or too few CPUs: no verdict on the agent, not the agent's 0
        "grader_error": int(bool(d.get("instance_mismatch") or d.get("too_few_cpus"))),
        "instance_mismatch": int(bool(d.get("instance_mismatch"))),
        # the sidecar ran fewer than 4 OpenBLAS threads (fewer than 4 CPUs visible to it): not the references' numerics
        "too_few_cpus": int(bool(d.get("too_few_cpus"))),
        "visible_cpus": int(num("visible_cpus")),
        "blas_threads": int(num("blas_threads")),
        # an infrastructure failure, not the agent's (PROTOCOL §2.6): a give-up after crashes between calls or a failed
        # resume (docs/protocol/standard_mode.md §13), the service not ending its episode for the collect hook, a scene that did
        # not start in the instance's frozen state, too few CPUs, a collect hook that left no verdict
        "infra_error": int(bool(d.get("infra_error")) or no_verdict or bool(d.get("too_few_cpus"))
                           or bool(d.get("instance_mismatch"))),
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
