"""Standard-mode verifier (MyoSuite): reads what the sim service (which the agent could not touch) wrote: /data/final.json,
/data/trajectory.npz, /data/replay.mp4; with a reset budget, the record is the last episode's. The verdict is the live
episode's (docs/protocol/README.md H.4; owner, 2026-10-17, board 0151): success = the episode the service ran ended in success
under the task's rule (its hold / track windows included), as the service judged it after the agent's container was
stopped ("graded_by": "live"); nothing is replayed. Numeric-only reward.json.

infra_error = 1 (no verdict on the agent, PROTOCOL §2.6): no final.json, one that cannot be read, one without a verdict
(the collect hook never finalized it: it ran out of time or died; or neither the live verdict nor a give-up is in it),
a give-up the service booked as infrastructure (crashes not all inside the agent's calls, a failed resume, the service
not ending its episode for the collect hook), and a scene that did not start at the frozen instance's recorded state
(instance_mismatch, checked when the episode began; grader_error = 1 too). Not infrastructure: a crash inside the
agent's calls (sim_crashed_on_call), a simulator error from the agent's actions (reason "error"), a timeout, a failure.
The video is rendered after the verdict and never decides anything. Every branch writes success, live_success,
graded_by_live, replays, infra_error and grader_error."""

import json, os, shutil, traceback

DATA = os.environ.get("RCB_DATA", "/data")  # the sim sidecar's artifacts (the variables are for the tests)
LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
os.makedirs(LOG, exist_ok=True)
BASE = {"success": 0, "live_success": 0, "graded_by_live": 1, "replays": 0, "finalized": 0, "missing_log": 0,
        "infra_error": 0, "sim_error": 0, "grader_error": 0}


def write(ok, out):
    out = {**BASE, **out}
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n")
    json.dump(out, open(f"{LOG}/reward.json", "w"))
    print(out)


p = f"{DATA}/final.json"
if not os.path.exists(p):  # the service never wrote one (it never came up): infrastructure, not the agent's 0
    write(False, {"missing_log": 1, "infra_error": 1})
    raise SystemExit
try:
    with open(p) as fh:
        d = json.load(fh)
    if not isinstance(d, dict):
        raise ValueError("final.json is not a JSON object")
except Exception:  # noqa: BLE001 -- cut short or corrupt: no verdict to read
    traceback.print_exc()
    write(False, {"grader_error": 1, "infra_error": 1, "corrupt_log": 1})
    raise SystemExit
for f in ("replay.mp4", "trajectory.npz", "episode.jsonl"):
    try:
        if os.path.exists(f"{DATA}/{f}"):
            shutil.copy(f"{DATA}/{f}", f"{LOG}/{f}")
    except OSError:  # evidence for humans: it never decides the verdict
        traceback.print_exc()
reason = str(d.get("reason") or "")
live = d.get("graded_by") == "live"
# a verdict = the collect hook's record of the live episode (finalized, graded_by live) or the service's give-up
no_verdict = not d.get("finalized") or not (live or d.get("gave_up"))
mismatch = bool(d.get("instance_mismatch")) or reason.startswith("instance_mismatch")
infra = bool(d.get("infra_error")) or no_verdict or mismatch
ok = live and bool(d.get("success")) and bool(d.get("live_success", d.get("success"))) and not infra
num = lambda k: float(d.get(k) or 0)  # noqa: E731
write(
    ok,
    {
        "success": int(ok),
        "live_success": int(bool(d.get("live_success", d.get("success")))),
        "graded_by_live": 1,
        "replays": 0,
        "finalized": int(bool(d.get("finalized"))),
        "no_verdict": int(no_verdict),
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
        # the image no longer builds the frozen start (checked when the episode began): not the agent's 0
        "grader_error": int(mismatch),
        "instance_mismatch": int(mismatch),
        # an infrastructure failure, not the agent's (PROTOCOL §2.6): a give-up after crashes between calls or a failed
        # resume (docs/protocol/standard_mode.md §13), the service not ending its episode for the collect hook, a scene that did
        # not start at the instance's recorded state, a final.json without a verdict
        "infra_error": int(infra),
        "gave_up": int(bool(d.get("gave_up"))),
        "sim_error": int(reason == "error"),
        "sim_crashed_on_call": int(reason == "sim_crashed_on_call"),
        "sim_startups": int(d.get("sim_startups") or 0),
        "resumes": int(d.get("resumes") or 0),
        "resume_state_mismatch": int(d.get("resume_state_mismatch") or 0),
        "resume_max_joint_dev": num("resume_max_joint_dev"),
    },
)
