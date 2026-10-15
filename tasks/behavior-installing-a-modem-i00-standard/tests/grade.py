"""Standard-mode verifier: reads what the sim service (which the agent could not touch) wrote:
/out/final.json (live success, two fresh-process replays of the recorded trajectory, determinism, the crash-recovery
record), /data/trajectory.npz, /data/replay.mp4. success = live success AND replay success AND deterministic.
Numeric-only reward.json (docs/PROTOCOL.md §2.6, §4.8; docs/STANDARD_MODE.md §13.2).

infra_error = 1 means no verdict on the agent (2026-10-10): final.json is the trusted sidecar's own file, so when it is
missing (the service never came up, or its container was gone), unreadable, not finalized (the collect hook did not
finish: the file is still the service's own copy without the replays), or says a fresh-process replay did not run to
its result, the 0 is an infrastructure failure, not the agent's. A reward is written in every case."""
import json, os, shutil, traceback
LOG = "/logs/verifier"; os.makedirs(LOG, exist_ok=True)
def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)
DATA = next((d for d in ("/out", "/data") if os.path.exists(f"{d}/final.json")), "/out")   # the service wrote to /out: /data is the dataset
p = f"{DATA}/final.json"
if not os.path.exists(p):
    write(False, {"success": 0, "deterministic": 0, "finalized": 0, "missing_log": 1, "infra_error": 1, "grader_error": 0}); raise SystemExit
try:
    d = json.load(open(p))
    if not isinstance(d, dict): raise ValueError(f"final.json is not an object: {type(d).__name__}")
    num = lambda k: float(d.get(k) or 0.0)  # noqa: E731
    finalized = bool(d.get("finalized"))
    replay_error = bool(d.get("replay_error"))     # a replay process died, timed out or printed no result (finalize.sh)
    infra = bool(d.get("infra_error")) or bool(d.get("gpu_lost")) or replay_error or not finalized
    ok = bool(d.get("success")) and bool(d.get("replay_success")) and bool(d.get("deterministic")) and not d.get("gave_up") and not infra
    out = {"success": int(ok), "live_success": int(bool(d.get("success"))), "replay_success": int(bool(d.get("replay_success"))),
           "deterministic": int(bool(d.get("deterministic"))), "live_matches_replay": int(bool(d.get("live_matches_replay"))),
           "finalized": int(finalized), "missing_log": 0, "n_actions": int(d.get("n_actions") or 0), "sim_steps": int(d.get("control_steps") or 0),
           "physics_steps": int(d.get("physics_steps") or 0), "steps": int(d.get("steps") or 0), "elapsed_s": num("elapsed_s"),
           "video_rendered": int(bool(d.get("video"))), "gpu_lost": int(bool(d.get("gpu_lost"))), "replay_error": int(replay_error),
           "instance_ok": int(d.get("instance_ok", 1) not in (0, False)),   # 0: a replay's frozen scene did not rebuild (infra_error)
           # the episode ended by the task's failure rule: the robot fell over (reason "failure: the robot fell over")
           "task_failure": int(str(d.get("reason") or "").startswith("failure")),
           "q_score": num("q_score"),   # progress (the challenge's q_score of the replays), 2026-09-27
           # crash recovery (eai-standard/2.2): service starts, resumes, whether a resumed state differed and by how much,
           # and a give-up after too many crashes
           "sim_startups": int(d.get("sim_startups") or 0), "resumes": int(d.get("resumes") or 0),
           "resume_state_mismatch": int(bool(d.get("resume_state_mismatch"))), "resume_max_tcp_dev_m": num("resume_max_tcp_dev_m"),
           "resume_max_joint_dev": num("resume_max_joint_dev"), "gave_up": int(bool(d.get("gave_up"))),
           # an infrastructure failure, not the agent's 0: the service gave up after crashes outside calls, never ended the
           # episode, the collect hook did not finish, or the replays could not run (GPU lost to a host systemd reload, a
           # replay process that died or ran out of time)
           "infra_error": int(infra),
           "grader_error": int(bool(d.get("gpu_lost")) or replay_error)}
except Exception:  # noqa: BLE001 -- an unreadable final.json is not the agent's failure
    traceback.print_exc()
    write(False, {"success": 0, "deterministic": 0, "finalized": 0, "missing_log": 0, "infra_error": 1, "grader_error": 1}); raise SystemExit
for f in ("replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl"):
    try:
        if os.path.exists(f"{DATA}/{f}"): shutil.copy(f"{DATA}/{f}", f"{LOG}/{f}")
    except OSError:    # the evidence never decides the verdict
        traceback.print_exc()
write(ok, out)
