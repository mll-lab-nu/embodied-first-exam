"""Standard-mode verifier (MyoSuite): reads what the sim service (which the agent could not touch) wrote: /data/final.json
(live success, two fresh-process replays of the recorded trajectory, determinism, crash-recovery fields),
/data/trajectory.npz, /data/replay.mp4; with a reset budget, the record is the last episode's. success = live success AND
replay success AND deterministic, the replays having started in the instance's recorded state. Numeric-only
reward.json.

infra_error = 1 (no verdict on the agent, PROTOCOL §2.6) also when there is no final.json, when it cannot be read, and
when it was never finalized (the collect hook ran out of time or died before its replays' verdict was written): none of
them is the agent's 0. Every branch writes success, deterministic, infra_error and grader_error."""

import json, os, shutil, traceback

DATA = os.environ.get("RCB_DATA", "/data")  # the sim sidecar's artifacts (the variables are for the tests)
LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
os.makedirs(LOG, exist_ok=True)


def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n")
    json.dump(out, open(f"{LOG}/reward.json", "w"))
    print(out)


p = f"{DATA}/final.json"
if not os.path.exists(p):  # the service never wrote one (it never came up): infrastructure, not the agent's 0
    write(False, {"success": 0, "deterministic": 0, "missing_log": 1, "finalized": 0, "grader_error": 0, "infra_error": 1})
    raise SystemExit
try:
    with open(p) as fh:
        d = json.load(fh)
    if not isinstance(d, dict):
        raise ValueError("final.json is not a JSON object")
except Exception:  # noqa: BLE001 -- cut short or corrupt: no verdict to read
    traceback.print_exc()
    write(False, {"success": 0, "deterministic": 0, "missing_log": 0, "finalized": 0, "grader_error": 1, "infra_error": 1})
    raise SystemExit
for f in ("replay.mp4", "trajectory.npz", "episode.jsonl"):
    try:
        if os.path.exists(f"{DATA}/{f}"):
            shutil.copy(f"{DATA}/{f}", f"{LOG}/{f}")
    except OSError:  # evidence for humans: it never decides the verdict
        traceback.print_exc()
unfinished = not d.get("finalized")  # the live summary only: the replays' verdict never reached final.json
infra = bool(d.get("infra_error")) or unfinished
ok = bool(d.get("success")) and bool(d.get("replay_success")) and bool(d.get("deterministic"))
ok = ok and not d.get("instance_mismatch") and not infra
num = lambda k: float(d.get(k) or 0)  # noqa: E731
reason = str(d.get("reason") or "")
write(
    ok,
    {
        "success": int(ok),
        "live_success": int(bool(d.get("success"))),
        "replay_success": int(bool(d.get("replay_success"))),
        "deterministic": int(bool(d.get("deterministic"))),
        "live_matches_replay": int(bool(d.get("live_matches_replay"))),
        "finalized": int(not unfinished),
        "missing_log": 0,
        "n_actions": int(d.get("n_actions") or 0),
        "sim_steps": int(d.get("control_steps") or 0),
        "physics_steps": int(d.get("physics_steps") or 0),
        "steps": int(d.get("steps") or 0),
        "calls": int(d.get("calls") or 0),
        # the reset budget (PROTOCOL §4.5; MyoSuite standard: 10): only the last episode is graded; results under
        # different budgets are reported separately
        "episodes": int(d.get("episodes") or 1),
        "resets": int(d.get("resets") or 0),
        "reset_budget": int(d.get("reset_budget") or 0),
        "sim_steps_total": int(d.get("control_steps_total") or d.get("control_steps") or 0),
        "elapsed_s": float(d.get("elapsed_s") or 0),
        "video_rendered": int(bool(d.get("video"))),
        "task_failure": int(reason.startswith("failure")),
        "timeout": int(reason == "timeout"),
        # a replay process gave no result, or the image no longer builds the frozen start: not the agent's 0
        "grader_error": int(bool(d.get("replay_failed") or d.get("instance_mismatch"))),
        "instance_mismatch": int(bool(d.get("instance_mismatch"))),
        # an infrastructure failure, not the agent's (PROTOCOL §2.6): a give-up after crashes between calls or a failed
        # resume (docs/STANDARD_MODE.md §13), the service not ending its episode for the collect hook, a replay
        # process that gave no result, replays that did not start in the instance's recorded state, a final.json the
        # collect hook never finalized
        "infra_error": int(infra),
        "gave_up": int(bool(d.get("gave_up"))),
        "sim_error": int(reason == "error"),
        "sim_startups": int(d.get("sim_startups") or 0),
        "resumes": int(d.get("resumes") or 0),
        "resume_state_mismatch": int(d.get("resume_state_mismatch") or 0),
        "resume_max_joint_dev": num("resume_max_joint_dev"),
    },
)
