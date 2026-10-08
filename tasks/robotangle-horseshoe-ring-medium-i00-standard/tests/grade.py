"""Standard-mode verifier (eai-standard/2.2): reads what the sim service (which the agent could not touch) wrote:
/data/final.json (live success, the fresh-process replay of the live rows done by environment/sim/finalize.sh, the
crash-recovery fields), /data/trajectory.npz, /data/replay.mp4. Adapted from robot_coding_bench's RoboWits standard
grader. success = live success AND replay success, and no infrastructure failure; TopoGym's physics runs on the GPU (the
RoboWits GPU-backend rule): the live and replayed states need not agree bit for bit, so `deterministic` is reported, not
required. A replay that produced no result is a grader error, not the agent's 0. Numeric-only reward.json. After a live
success the replay is a grading replay (tooling v16): for the GPU families, if the episode has not ended after the last
live row, it holds the final targets for up to 2 s with the replay tolerances; final.json's replay_grading has the record,
replay_hold_steps / replay_tolerance_needed summarize it. It only confirms: a live failure is final whatever the replay
shows (the collect hook then replays plainly). Task-contact penetration is evidence, not a verdict (tooling v16): a success
whose live episode or replay had a deep task contact (final.json `review` / `replay_review`, rcb_topogym.CONTACT_RULE) is
held for review: success 0 with success_pending_review 1, the events in review.json, the frames around them in
review_frames/. Forcing (final.json `forcing` / `replay_forcing`, rcb_topogym.FORCING) is evidence only: `forcing_events`,
and review.json when a review exists."""
import hashlib, json, os, shutil
from pathlib import Path
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
    d = json.loads(Path(p).read_text())
except ValueError:
    write(False, {"success": 0, "missing_log": 1, "infra_error": 1, "grader_error": 1}); raise SystemExit
gpu = True  # CUDA physics: determinism reported, not required
# infrastructure: the service gave up after crashes it caused (sim_crashed, resume_failed), the GPU was lost, the simulation
# became numerically unstable live or in the replay (simulator_instability, finalize.sh), or the episode never finished grading
infra = bool(d.get("infra_error")) or bool(d.get("gpu_lost")) or not (d.get("finalized") or d.get("gave_up"))
replayed = d.get("replay_success") is not None and os.path.isfile("/data/trajectory.npz")
mismatch = bool(d.get("instance_mismatch")) or d.get("instance_matches") is False
binding_ok = generated = False
try:
    expected = json.loads(Path("/tests/runtime_binding.json").read_text())
    wanted = hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    startup = json.loads(Path("/data/startup_binding.json").read_text())
    replay = json.loads(Path("/data/replay.verdict.json").read_text())
    # A frozen PBD state prepared on another GPU is generated from the instance's recipe on this one (instance_generated):
    # its recipe must match, and the live episode and the replay must start from the same generated state.
    generated = any(row.get("instance_generated") is True for row in (startup, replay))
    same_state = not generated or (
        all(row.get("instance_generated") is True and (row.get("initial_state") or {}).get("recipe_match") is True
            for row in (startup, replay))
        and len({((row.get("initial_state") or {}).get("manifest_sha256"), row.get("instance_sha"))
                 for row in (startup, replay)}) == 1)
    binding_ok = same_state and all((row.get("instance_exact") is True or row.get("instance_generated") is True) and
                     (row.get("runtime_binding") or {}).get("binding_id") == wanted for row in (startup, replay))
except (OSError, ValueError, TypeError):
    pass
# A real mismatch is recorded in replay.verdict.json (replay.py). A replay process that crashed (e.g. CUDA out of memory)
# writes none: that is a grader error (finalize.sh), not instance_mismatch.
verdict = os.path.isfile("/data/replay.verdict.json")
mismatch = mismatch or (verdict and not binding_ok)
grader_error = not infra and not mismatch and not d.get("gave_up") and not replayed
# the live (strict) success first: a tolerant replay success never stands in for a live failure
ok = bool(d.get("success")) and bool(d.get("replay_success")) and (bool(d.get("deterministic")) or gpu) and not infra and not grader_error and not mismatch
# a success with a deep task contact, live or in the replay, is held for review instead of credited automatically
reviews = [r if isinstance(r, dict) else None for r in (d.get("review"), d.get("replay_review"))]
forcing = [f if isinstance(f, dict) else None for f in (d.get("forcing"), d.get("replay_forcing"))]   # evidence only
pending = ok and any(reviews)
credited = ok and not pending
if any(reviews):
    try:
        with open(f"{LOG}/review.json", "w") as stream:
            json.dump({"pending": pending, "live": reviews[0], "replay": reviews[1], "forcing": {"live": forcing[0], "replay": forcing[1]},
                       "frames": d.get("review_frames") or []}, stream, indent=1)
        if pending and os.path.isdir("/data/review_frames"):
            shutil.copytree("/data/review_frames", f"{LOG}/review_frames", dirs_exist_ok=True)
    except OSError as exc:
        print(f"review evidence copy failed: {exc}")
num = lambda k, cast=int: cast(d.get(k) or 0)  # noqa: E731
write(credited, {"success": int(credited), "success_pending_review": int(pending),
           "review_events": max(int((r or {}).get("count", 0)) for r in reviews),
           "review_max_depth_mm": max(float((r or {}).get("max_depth_mm", 0.)) for r in reviews),
           "forcing_events": max(int((f or {}).get("count", 0)) for f in forcing),
           "live_success": int(bool(d.get("success"))), "replay_success": int(bool(d.get("replay_success"))),
           "runtime_binding_ok": int(binding_ok),
           "deterministic": int(bool(d.get("deterministic"))), "live_matches_replay": int(bool(d.get("live_matches_replay"))),
           "gpu_backend": int(gpu), "finalized": int(bool(d.get("finalized"))), "n_actions": num("n_actions"), "live_rows": num("live_rows"),
           "sim_steps": num("control_steps"), "physics_steps": num("physics_steps"), "steps": num("steps"), "elapsed_s": num("elapsed_s", float),
           "replay_wall_s": num("replay_wall_s", float), "video_rendered": int(bool(d.get("video"))), "gpu_lost": int(bool(d.get("gpu_lost"))),
           "replay_hold_steps": num("replay_hold_steps"), "replay_tolerance_needed": int(bool(d.get("replay_tolerance_needed"))),
           "infra_error": int(infra), "simulator_instability": int(bool(d.get("simulator_instability"))),
           "gave_up": int(bool(d.get("gave_up"))), "sim_startups": num("sim_startups"), "resumes": num("resumes"),
           "resume_state_mismatch": num("resume_state_mismatch"), "resume_max_tcp_dev_m": num("resume_max_tcp_dev_m", float),
           "resume_max_joint_dev": num("resume_max_joint_dev", float), "instance_mismatch": int(mismatch),
           "initial_state_generated": int(bool(generated)), "grader_error": int(grader_error)})

# Commit rewards before copying optional artifacts.
for f in ("replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl", "startups.jsonl", "startup_binding.json", "server.log", "replay.log", "replay.verdict.json", "final.json", "replay.frame_map.jsonl", "replay.recording_manifest.json"):
    try:
        if os.path.exists(f"/data/{f}"): shutil.copy(f"/data/{f}", f"{LOG}/{f}")
    except OSError as exc:
        print(f"artifact copy failed for {f}: {exc}")
