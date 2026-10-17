"""Standard-mode verifier (separate sandbox, no network): reads what the sim service, which the agent could not touch, wrote --
/out/final.json (the live result, two fresh-process replays of the recorded trajectory, the crash-recovery record) and the
evidence next to it. success = live success AND replay success AND deterministic (the two replays end in the same state).
Numeric-only reward.json (docs/PROTOCOL.md Appendix H.1, H.4; docs/STANDARD_MODE.md).

infra_error = 1 means no verdict on the agent: final.json is missing, unreadable or not finalized, a fresh-process replay
did not run to its result, or the frozen instance did not rebuild in a replay. A reward is written in every case."""
import json, os, shutil, traceback
LOG = "/logs/verifier"; os.makedirs(LOG, exist_ok=True)


def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)


DATA = next((d for d in ("/out", "/data") if os.path.exists(f"{d}/final.json")), "/out")   # where the artifacts were uploaded
p = f"{DATA}/final.json"
if not os.path.exists(p):
    write(False, {"success": 0, "deterministic": 0, "finalized": 0, "missing_log": 1, "infra_error": 1, "grader_error": 0}); raise SystemExit
try:
    d = json.load(open(p))
    if not isinstance(d, dict): raise ValueError(f"final.json is not an object: {type(d).__name__}")
    num = lambda k: float(d.get(k) or 0.0)  # noqa: E731
    finalized = bool(d.get("finalized"))
    replay_error = bool(d.get("replay_error"))
    infra = bool(d.get("infra_error")) or bool(d.get("gpu_lost")) or replay_error or not finalized
    ok = bool(d.get("success")) and bool(d.get("replay_success")) and bool(d.get("deterministic")) and not d.get("gave_up") and not infra
    out = {"success": int(ok), "live_success": int(bool(d.get("success"))), "replay_success": int(bool(d.get("replay_success"))),
           "deterministic": int(bool(d.get("deterministic"))), "live_matches_replay": int(bool(d.get("live_matches_replay"))),
           "finalized": int(finalized), "missing_log": 0, "n_actions": int(d.get("n_actions") or 0), "sim_steps": int(d.get("control_steps") or 0),
           "max_steps": int(d.get("max_steps") or 0), "steps": int(d.get("steps") or 0), "elapsed_s": num("elapsed_s"),
           # upstream's own diagnostics of the graded replay: the BDDL goal alone, and the step at which the goal held
           "symbolic_success": int(bool(d.get("replay_symbolic_success"))), "success_step": int(d.get("replay_success_step") or 0),
           "video_rendered": int(bool(d.get("video"))), "gpu_lost": int(bool(d.get("gpu_lost"))), "replay_error": int(replay_error),
           "instance_ok": int(d.get("instance_ok", 1) not in (0, False)),
           "sim_startups": int(d.get("sim_startups") or 0), "resumes": int(d.get("resumes") or 0),
           "resume_state_mismatch": int(bool(d.get("resume_state_mismatch"))), "resume_max_tcp_dev_m": num("resume_max_tcp_dev_m"),
           "resume_max_joint_dev": num("resume_max_joint_dev"), "gave_up": int(bool(d.get("gave_up"))),
           "infra_error": int(infra), "grader_error": int(bool(d.get("gpu_lost")) or replay_error)}
except Exception:  # noqa: BLE001 -- an unreadable final.json is not the agent's failure
    traceback.print_exc()
    write(False, {"success": 0, "deterministic": 0, "finalized": 0, "missing_log": 0, "infra_error": 1, "grader_error": 1}); raise SystemExit
for f in ("replay.mp4", "trajectory.npz", "episode.jsonl"):
    try:
        if os.path.exists(f"{DATA}/{f}"): shutil.copy(f"{DATA}/{f}", f"{LOG}/{f}")
    except OSError:    # the evidence never decides the verdict
        traceback.print_exc()
write(ok, out)
