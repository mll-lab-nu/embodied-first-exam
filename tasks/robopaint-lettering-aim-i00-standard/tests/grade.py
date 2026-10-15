"""Standard-mode verifier (RoboPaint brush tasks): reads what the sim service (which the agent could not touch) wrote:
/data/final.json (the recorded episode replayed twice in fresh processes by the collect hook, the replayed main sheet scored against
the exemplar, determinism), plus the replay video and sheet pictures. success = both replays meet the task's rule AND they agree
exactly. Numeric-only reward.json; every metric of the replayed sheet is reported (final_reward = the replay's final_reward), with
the crash-recovery evidence (sim_startups, resumes, resume_state_mismatch, ...; docs/STANDARD_MODE.md §13.2) and infra_error
(the service gave up after crashes that were not the agent's, or never dumped its episode).

No verdict on the agent is an infrastructure failure, never the agent's 0 (PROTOCOL §2.6, infra_error = 1): final.json missing (the
service or its collect hook never wrote one), unreadable (grader_error = 1 too), without a verdict (the collect hook did not finish:
not `finalized`, or neither the replays' `deterministic` nor a give-up after crashes), or from replays that could not run (gpu_lost,
or a replay process without a result). Every reward.json carries success, final_reward, deterministic, infra_error, sim_error,
grader_error and missing_log."""
import json, os, shutil, traceback
LOG = "/logs/verifier"; os.makedirs(LOG, exist_ok=True)
RECOVERY = ("sim_startups", "resumes", "resume_state_mismatch", "resume_max_tcp_dev_m", "resume_max_joint_dev")


BASE = {"success": 0, "final_reward": 0.0, "deterministic": 0, "infra_error": 0, "sim_error": 0, "grader_error": 0, "missing_log": 0}


def write(ok, out):
    out = {**BASE, **out}
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)


def verdict(d):
    m = d.get("metrics") or {}
    # a verdict = the collect hook's replays (finalized, with `deterministic`) or the service's give-up after crashes
    no_verdict = not d.get("finalized") or not (d.get("gave_up") or d.get("deterministic") is not None)
    # the replays could not run or gave no result although there was an episode to replay: not the agent's 0
    replay_lost = bool(d.get("gpu_lost")) or (bool(d.get("replay_error")) and int(d.get("n_actions") or 0) > 0)
    ok = bool(d.get("replay_success")) and bool(d.get("deterministic")) and not no_verdict
    return ok, {**{k: float(v) for k, v in m.items() if isinstance(v, (int, float)) and not isinstance(v, bool)},
                "success": int(ok), "replay_success": int(bool(d.get("replay_success"))), "deterministic": int(bool(d.get("deterministic"))),
                "live_matches_replay": int(bool(d.get("live_matches_replay"))), "instance_exact": int(bool(d.get("instance_exact"))),
                "finalized": int(bool(d.get("finalized"))), "no_verdict": int(no_verdict), "final_reward": float(m.get("final_reward") or 0.0),
                "n_actions": int(d.get("n_actions") or 0), "sim_steps": int(d.get("control_steps") or 0), "physics_steps": int(d.get("physics_steps") or 0),
                "steps": int(d.get("steps") or 0), "calls": int(d.get("calls") or 0), "elapsed_s": float(d.get("elapsed_s") or 0),
                "video_rendered": int(bool(d.get("video"))), "gpu_lost": int(bool(d.get("gpu_lost"))),
                **{k: float(d.get(k) or 0) for k in RECOVERY}, "gave_up": int(bool(d.get("gave_up"))),
                "sim_error": int(d.get("reason") == "error"), "missing_log": 0,
                "infra_error": int(bool(d.get("infra_error")) or no_verdict or replay_lost),
                "grader_error": int(replay_lost)}


def main():
    p = "/data/final.json"
    if not os.path.exists(p):  # the service or its collect hook never wrote one: infrastructure, the agent cannot touch /data
        write(False, {"missing_log": 1, "infra_error": 1}); return
    try:
        with open(p) as f:
            d = json.load(f)
        if not isinstance(d, dict):
            raise ValueError("final.json is not an object")
        ok, out = verdict(d)
    except Exception:  # noqa: BLE001 -- an unreadable final.json is not the agent's failure
        traceback.print_exc()
        write(False, {"infra_error": 1, "grader_error": 1, "corrupt_log": 1}); return
    for f in ("replay.mp4", "replay.last.png", "canvas.png", "canvas_practice.png", "canvas_live.png", "canvas_live_practice.png", "trajectory.npz", "episode.jsonl"):
        try:  # evidence for humans; it never decides the verdict
            if os.path.exists(f"/data/{f}"): shutil.copy(f"/data/{f}", f"{LOG}/{f}")
        except OSError:
            traceback.print_exc()
    write(ok, out)


main()
