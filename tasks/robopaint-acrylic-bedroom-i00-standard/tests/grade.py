"""Standard-mode verifier (RoboPaint brush tasks): reads what the sim service (which the agent could not touch) wrote:
/data/final.json (the live episode's verdict: the service scored its live main sheet against the exemplar with the graders'
rcb_brush_strict.py, the picture rule and the process rules, after the agent's container was stopped; "graded_by": "live",
nothing replayed: docs/PROTOCOL.md H.4; owner, 2026-10-17, board 0151), plus the video and sheet pictures. success = the live
sheet meets the task's rule. Numeric-only reward.json; every metric of the live sheet is reported (final_reward = its
final_reward), with the crash-recovery evidence (sim_startups, resumes, resume_state_mismatch, ...; docs/STANDARD_MODE.md §13.2)
and infra_error.

No verdict on the agent is an infrastructure failure, never the agent's 0 (PROTOCOL §2.6, infra_error = 1): final.json missing (the
service or its collect hook never wrote one), unreadable (grader_error = 1 too), without a verdict (not `finalized`, or neither the
live verdict nor a give-up after crashes), the service's give-up after crashes that were not all inside the agent's calls or
because the frozen instance does not rebuild (final.json infra_error), or a live sheet the service could not score after an
episode that ended normally (grade_error, grader_error = 1). Every reward.json carries success, live_success, graded_by_live,
replays, final_reward, infra_error, sim_error, grader_error and missing_log. RCB_DATA / RCB_VERIFIER_LOG_DIR: test hooks."""
import json, os, shutil, traceback
DATA = os.environ.get("RCB_DATA", "/data"); LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier"); os.makedirs(LOG, exist_ok=True)
RECOVERY = ("sim_startups", "resumes", "resume_state_mismatch", "resume_max_tcp_dev_m", "resume_max_joint_dev")


BASE = {"success": 0, "live_success": 0, "graded_by_live": 0, "replays": 0, "final_reward": 0.0, "infra_error": 0, "sim_error": 0,
        "grader_error": 0, "missing_log": 0}


def write(ok, out):
    out = {**BASE, **out}
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)


def verdict(d):
    m = d.get("metrics") or {}
    live_verdict = d.get("graded_by") == "live"
    # a verdict = the service's record of the live episode (finalized, graded_by live) or its give-up after crashes
    no_verdict = not d.get("finalized") or not (live_verdict or d.get("gave_up"))
    sim_error = d.get("reason") == "error"
    # the service could not score the live sheet after an episode that ended normally: not the agent's 0
    grade_error = bool(d.get("grade_error")) and not sim_error
    live = bool(d.get("success"))   # the verdict: final.json `success` decides (live_success is reported beside it)
    infra = bool(d.get("infra_error")) or no_verdict or grade_error
    ok = live and live_verdict and not infra
    return ok, {**{k: float(v) for k, v in m.items() if isinstance(v, (int, float)) and not isinstance(v, bool)},
                "success": int(ok), "live_success": int(bool(d.get("live_success", d.get("success")))), "graded_by_live": int(live_verdict), "replays": 0,
                "instance_exact": int(bool(d.get("instance_exact"))),
                "finalized": int(bool(d.get("finalized"))), "no_verdict": int(no_verdict), "final_reward": float(m.get("final_reward") or 0.0),
                "n_actions": int(d.get("n_actions") or 0), "sim_steps": int(d.get("control_steps") or 0), "physics_steps": int(d.get("physics_steps") or 0),
                "steps": int(d.get("steps") or 0), "calls": int(d.get("calls") or 0), "elapsed_s": float(d.get("elapsed_s") or 0),
                "video_rendered": int(bool(d.get("video"))),
                **{k: float(d.get(k) or 0) for k in RECOVERY}, "gave_up": int(bool(d.get("gave_up"))),
                "instance_mismatch": int(str(d.get("reason") or "").startswith("instance_mismatch")),
                "sim_error": int(sim_error), "missing_log": 0, "infra_error": int(infra), "grader_error": int(grade_error)}


def main():
    p = f"{DATA}/final.json"
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
    for f in ("replay.mp4", "replay.last.png", "canvas_live.png", "canvas_live_practice.png", "trajectory.npz", "episode.jsonl"):
        try:  # evidence for humans; it never decides the verdict
            if os.path.exists(f"{DATA}/{f}"): shutil.copy(f"{DATA}/{f}", f"{LOG}/{f}")
        except OSError:
            traceback.print_exc()
    write(ok, out)


main()
