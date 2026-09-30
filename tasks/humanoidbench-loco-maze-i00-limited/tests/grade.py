"""Limited-mode verifier: reads what the sim service (which the agent could not touch) wrote:
/data/final.json (live success, fresh replay of the recorded trajectory, determinism), /data/trajectory.npz,
/data/replay.mp4. success = live success AND replay success AND deterministic. Numeric-only reward.json:
sim_steps is the graded episode's length (the steps replayed, as in full mode), steps every step of the trial."""
import json, os, shutil, traceback
LOG = "/logs/verifier"; os.makedirs(LOG, exist_ok=True)
def write(ok, out):
    open(f"{LOG}/reward.txt", "w").write("1\n" if ok else "0\n"); json.dump(out, open(f"{LOG}/reward.json", "w")); print(out)
p = "/data/final.json"
if not os.path.exists(p):
    write(False, {"success": 0, "missing_log": 1, "grader_error": 0}); raise SystemExit
try:
    d = json.load(open(p))
    ok = bool(d.get("success")) and bool(d.get("replay_success")) and bool(d.get("deterministic"))
    out = {"success": int(ok), "missing_log": 0, "live_success": int(bool(d.get("success"))), "replay_success": int(bool(d.get("replay_success"))),
           "deterministic": int(bool(d.get("deterministic"))), "finalized": int(bool(d.get("finalized"))),
           "n_actions": int(d.get("n_actions") or 0), "sim_steps": int(d.get("n_actions") or 0),
           "steps": int(d.get("steps") or 0), "resets": int(d.get("resets") or 0),
           "elapsed_s": float(d.get("elapsed_s") or 0), "video_rendered": int(bool(d.get("video"))), "grader_error": 0}
except Exception:  # noqa: BLE001 -- an unreadable final.json is the grader's failure, not the agent's
    traceback.print_exc(); write(False, {"success": 0, "missing_log": 0, "grader_error": 1}); raise SystemExit
for f in ("replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl"):   # evidence for humans: never the verdict
    try:
        if os.path.exists(f"/data/{f}"): shutil.copy(f"/data/{f}", f"{LOG}/{f}")
    except OSError:
        traceback.print_exc()
write(ok, out)
