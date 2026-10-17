"""Standard-mode verifier (eai-standard/2.2): reads what the sim service (which the agent could not touch) wrote:
/data/final.json (the live episode's verdict, crash recovery), /data/trajectory.npz, /data/replay.mp4. success = the
live episode's success: the settle window that ended the episode passed on the service's simulator (final.json
"graded_by": "live"; nothing is replayed: docs/PROTOCOL.md H.4; owner, 2026-10-17, board 0151), and no infrastructure
failure (infra_error = 1: no record, no live verdict, a give-up the service caused, a frozen instance the host could
not rebuild, a service that could not record the end of an episode that ended normally). Numeric-only reward.json.
Source: scripts/robowits/shared/grade_standard.py. RCB_DATA / RCB_VERIFIER_LOG_DIR: test hooks (never set in tasks)."""
import json, os, shutil
DATA = os.environ.get("RCB_DATA", "/data"); LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier"); os.makedirs(LOG, exist_ok=True)
FAIL = {"success": 0, "live_success": 0, "graded_by_live": 0, "replays": 0, "finalized": 0, "sim_error": 0}
def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)
p = f"{DATA}/final.json"
if not os.path.exists(p):
    write(False, {**FAIL, "missing_log": 1, "infra_error": 1, "grader_error": 0}); raise SystemExit   # the service never started
try:
    d = json.load(open(p))
    if not isinstance(d, dict): raise ValueError("final.json is not an object")
except (OSError, ValueError):
    write(False, {**FAIL, "missing_log": 1, "infra_error": 1, "grader_error": 1}); raise SystemExit
for f in ("replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl", "startups.jsonl", "server.log"):
    try:   # evidence for people: a copy that fails never decides the verdict
        if os.path.exists(f"{DATA}/{f}"): shutil.copy(f"{DATA}/{f}", f"{LOG}/{f}")
    except OSError as exc:
        print(f"[grade] {f} not copied: {exc!r}")
gpu = os.environ.get("RCB_ROBOWITS_BACKEND", "cpu") == "gpu"
reason = str(d.get("reason") or "")
sim_error = reason == "error"                          # the live episode ended with a simulator error (PROTOCOL §4.6): the agent's 0
instance_mismatch = reason.startswith("instance_mismatch")   # the host could not rebuild the frozen instance (server.py)
live_verdict = d.get("graded_by") == "live"            # the service wrote the live episode's verdict
# The service could not record the end of the episode (final.json grade_error). After an episode that ended normally that
# is not the agent's failure. After a simulator error it stays the agent's 0 (sim_error), so an agent cannot void a
# failed episode by breaking the simulator.
grade_error = bool(d.get("grade_error")) and not sim_error
# infrastructure: the service gave up after crashes it caused (sim_crashed, resume_failed; not sim_crashed_on_call) or
# because it could not rebuild the frozen instance (instance_mismatch), never wrote the live verdict, or could not record it
infra = (bool(d.get("infra_error")) or not (live_verdict or d.get("gave_up")) or not d.get("finalized") or grade_error)
live = bool(d.get("success"))                          # the verdict: final.json `success` decides (live_success beside it)
ok = live and live_verdict and not infra
num = lambda k, cast=int: cast(d.get(k) or 0)  # noqa: E731
write(ok, {"success": int(ok), "live_success": int(bool(d.get("live_success", d.get("success")))), "graded_by_live": int(live_verdict), "replays": 0,
           "gpu_backend": int(gpu), "finalized": int(bool(d.get("finalized"))), "missing_log": 0,
           "n_actions": num("n_actions"), "sim_steps": num("control_steps"), "physics_steps": num("physics_steps"), "steps": num("steps"),
           "elapsed_s": num("elapsed_s", float), "video_rendered": int(bool(d.get("video"))), "infra_error": int(infra),
           "sim_error": int(sim_error), "instance_mismatch": int(instance_mismatch), "instance_exact": int(bool(d.get("instance_exact"))),
           "settle_passed": int(bool((d.get("settle") or {}).get("success"))), "final_window": num("final_window"),
           "gave_up": int(bool(d.get("gave_up"))), "sim_startups": num("sim_startups"), "resumes": num("resumes"),
           "resume_state_mismatch": num("resume_state_mismatch"), "resume_max_tcp_dev_m": num("resume_max_tcp_dev_m", float),
           "resume_max_joint_dev": num("resume_max_joint_dev", float), "grader_error": int(grade_error)})
