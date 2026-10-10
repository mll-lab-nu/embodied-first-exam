"""Standard-mode verifier (MuJoCo Playground quadrupeds): reads what the sim service (which the agent could not touch) wrote:
/data/final.json (live success, two fresh-process replays of the recorded trajectory, determinism, crash-recovery
fields), /data/trajectory.npz, /data/replay.mp4. success = live success AND replay success AND deterministic, the
replays having started in the instance's t = 0 state. Numeric-only reward.json.
infra_error = 1: there is no verdict on the agent (final.json missing or unreadable; not finalized: the collect hook
never ran or was cut short before it wrote the verdict; the service gave up after crashes between calls; a replay
process gave no result): such a trial is not the agent's 0."""

import json, os, shutil, traceback

LOG = "/logs/verifier"
os.makedirs(LOG, exist_ok=True)


def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n")
    json.dump(out, open(f"{LOG}/reward.json", "w"))
    print(out)


p = "/data/final.json"
if not os.path.exists(p):  # the service never wrote anything (it never started): infrastructure, not the agent
    write(False, {"success": 0, "deterministic": 0, "missing_log": 1, "sim_error": 0, "grader_error": 0, "infra_error": 1})
    raise SystemExit
try:
    d = json.load(open(p))
    if not isinstance(d, dict):
        raise ValueError("final.json is not a JSON object")
except Exception:  # noqa: BLE001 -- cut short or garbled: not the agent's 0
    traceback.print_exc()
    write(False, {"success": 0, "deterministic": 0, "missing_log": 0, "bad_log": 1, "sim_error": 0, "grader_error": 1, "infra_error": 1})
    raise SystemExit
for f in ("replay.mp4", "trajectory.npz", "episode.jsonl"):
    try:
        if os.path.exists(f"/data/{f}"):
            shutil.copy(f"/data/{f}", f"{LOG}/{f}")
    except OSError:
        traceback.print_exc()
# not finalized: the service's own final.json (live outcome only), never completed by the collect hook's replays
unfinished = not d.get("finalized")
infra = bool(d.get("infra_error")) or unfinished
ok = bool(d.get("success")) and bool(d.get("replay_success")) and bool(d.get("deterministic"))
ok = ok and not d.get("instance_mismatch") and not infra
num = lambda k: float(d.get(k) or 0)  # noqa: E731
write(
    ok,
    {
        "success": int(ok),
        "live_success": int(bool(d.get("success"))),
        "replay_success": int(bool(d.get("replay_success"))),
        "deterministic": int(bool(d.get("deterministic"))),
        "live_matches_replay": int(bool(d.get("live_matches_replay"))),
        "finalized": int(bool(d.get("finalized"))),
        "n_actions": int(d.get("n_actions") or 0),
        "sim_steps": int(d.get("control_steps") or 0),
        "physics_steps": int(d.get("physics_steps") or 0),
        "steps": int(d.get("steps") or 0),
        "elapsed_s": float(d.get("elapsed_s") or 0),
        "video_rendered": int(bool(d.get("video"))),
        "fell": int(d.get("fell_at") is not None),
        "worst_lin_err": float(d["worst_lin_err"]) if d.get("worst_lin_err") is not None else -1.0,
        "worst_yaw_err": float(d["worst_yaw_err"]) if d.get("worst_yaw_err") is not None else -1.0,
        "end_tilt_deg": float(d["tilt_deg"]) if d.get("tilt_deg") is not None else -1.0,
        "end_imu_height": float(d["imu_height"]) if d.get("imu_height") is not None else -1.0,
        "end_pose_angle_deg": float(d["pose_angle_deg"]) if d.get("pose_angle_deg") is not None else -1.0,
        # a replay process gave no result, or the image no longer builds the frozen start: not the agent's 0
        "grader_error": int(bool(d.get("replay_failed") or d.get("instance_mismatch"))),
        "instance_mismatch": int(bool(d.get("instance_mismatch"))),
        # an infrastructure failure, not the agent's (PROTOCOL §2.6): a give-up after crashes between calls or a failed
        # resume (docs/STANDARD_MODE.md §13), the service not ending its episode for the collect hook, a replay
        # process that gave no result, replays that did not start in the instance's t = 0 state, a final.json the collect
        # hook never finalized
        "infra_error": int(infra),
        "no_verdict": int(unfinished),
        "missing_log": 0,
        "gave_up": int(bool(d.get("gave_up"))),
        "sim_error": int(d.get("reason") == "error"),
        "sim_startups": int(d.get("sim_startups") or 0),
        "resumes": int(d.get("resumes") or 0),
        "resume_state_mismatch": int(d.get("resume_state_mismatch") or 0),
        "resume_max_joint_dev": num("resume_max_joint_dev"),
    },
)
