"""Standard-mode verifier (eai-standard/2.2): reads what the sim service (which the agent could not touch) wrote:
/data/final.json (live success, the fresh-process replay of the live rows done by environment/sim/finalize.sh, the
crash-recovery fields), /data/trajectory.npz, /data/replay.mp4. Adapted from robot_coding_bench's RoboWits standard
grader. success = live success AND replay success, and no infrastructure failure; TopoGym's physics runs on the GPU (the
RoboWits GPU-backend rule): the live and replayed states need not agree bit for bit, so `deterministic` is reported, not
required. A replay that produced no result is a grader error, not the agent's 0. Numeric-only reward.json."""
import json, os, shutil
LOG = "/logs/verifier"; os.makedirs(LOG, exist_ok=True)
def write(ok, out):
    for name, value in (("reward.json", out), ("reward.txt", int(ok))):
        temporary = f"{LOG}/.{name}.{os.getpid()}.tmp"
        with open(temporary, "w") as stream:
            json.dump(value, stream); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, f"{LOG}/{name}")
    print(out)
p = "/data/final.json"
if not os.path.exists(p):
    write(False, {"success": 0, "missing_log": 1, "infra_error": 1, "grader_error": 0}); raise SystemExit   # the service never started
try:
    d = json.load(open(p))
except ValueError:
    write(False, {"success": 0, "missing_log": 1, "infra_error": 1, "grader_error": 1}); raise SystemExit
gpu = True  # CUDA physics: determinism reported, not required
# infrastructure: the service gave up after crashes it caused (sim_crashed, resume_failed), the GPU was lost, or the episode
# never finished grading
infra = bool(d.get("infra_error")) or bool(d.get("gpu_lost")) or not (d.get("finalized") or d.get("gave_up"))
replayed = d.get("replay_success") is not None and os.path.isfile("/data/trajectory.npz")
mismatch = bool(d.get("instance_mismatch")) or d.get("instance_matches") is False
grader_error = not infra and not mismatch and not d.get("gave_up") and not replayed
ok = bool(d.get("success")) and bool(d.get("replay_success")) and (bool(d.get("deterministic")) or gpu) and not infra and not grader_error and not mismatch
num = lambda k, cast=int: cast(d.get(k) or 0)  # noqa: E731
write(ok, {"success": int(ok), "live_success": int(bool(d.get("success"))), "replay_success": int(bool(d.get("replay_success"))),
           "deterministic": int(bool(d.get("deterministic"))), "live_matches_replay": int(bool(d.get("live_matches_replay"))),
           "gpu_backend": int(gpu), "finalized": int(bool(d.get("finalized"))), "n_actions": num("n_actions"), "live_rows": num("live_rows"),
           "sim_steps": num("control_steps"), "physics_steps": num("physics_steps"), "steps": num("steps"), "elapsed_s": num("elapsed_s", float),
           "replay_wall_s": num("replay_wall_s", float), "video_rendered": int(bool(d.get("video"))), "gpu_lost": int(bool(d.get("gpu_lost"))),
           "infra_error": int(infra), "gave_up": int(bool(d.get("gave_up"))), "sim_startups": num("sim_startups"), "resumes": num("resumes"),
           "resume_state_mismatch": num("resume_state_mismatch"), "resume_max_tcp_dev_m": num("resume_max_tcp_dev_m", float),
           "resume_max_joint_dev": num("resume_max_joint_dev", float), "instance_mismatch": int(mismatch), "grader_error": int(grader_error)})

# Commit rewards before copying optional artifacts.
for f in ("replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl", "startups.jsonl", "server.log", "replay.log", "replay.verdict.json", "final.json", "replay.frame_map.jsonl", "replay.recording_manifest.json"):
    try:
        if os.path.exists(f"/data/{f}"): shutil.copy(f"/data/{f}", f"{LOG}/{f}")
    except OSError as exc:
        print(f"artifact copy failed for {f}: {exc}")
