"""Standard-mode verifier of the IKEA MuJoCo tasks (scripts/ikea_mujoco/standard/grade.py, copied unchanged), in the
separate verifier sandbox, without network. Reads what the sim service (which the agent could not touch) wrote:
/data/final.json (the live result, finalized by environment/sim/finalize.sh) and /data/trajectory.npz (every control row
the live episode executed, float64). Replays the trajectory itself, exactly as the privileged grader does
(replay_grade.py = scripts/ikea_mujoco/shared/grade.py unchanged: two fresh processes, per row data.ctrl[:] = row and
S.step(4) with the scene's mechanism, success.py on the final state, the scene checked file by file against
runtime_binding.json and its initial-state hash).

success = live success AND both replays succeed AND the replays end in the same state AND that state is the live final
state (live_sha: MuJoCo on the CPU is bit-deterministic) AND no infrastructure failure. A replay that produced no result
is a grader error, not the agent's 0. reward.txt = success (1/0); reward.json = numbers only.
Failure classes (PROTOCOL H.5: infra_error / grader_error give a free retry): a simulator error the agent's rows caused
(final.json sim_error: the scene's code or MuJoCo raised in a call) is the agent's 0 (sim_error 1); a failed live
episode (no live success) is the agent's 0 without replays (nothing a replay finds could make it a success); a scene,
image or runtime that differs from the binding, a live success whose trajectory was not dumped, and a render-process
failure are infra_error; a live success whose deterministic replays end elsewhere than the live state is grader_error
(the service's fault)."""
import json, os, shutil, subprocess, sys

LOG = "/logs/verifier"; os.makedirs(LOG, exist_ok=True)
TASK = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))


def write(ok, out):
    for name, value in (("reward.json", out), ("reward.txt", int(ok))):
        tmp = f"{LOG}/.{name}.tmp"
        with open(tmp, "w") as f:
            json.dump(value, f); f.write("\n")
        os.replace(tmp, f"{LOG}/{name}")
    print(json.dumps(out), flush=True)


def copy_evidence():
    for f in ("live.mp4", *(f"live.{i}.mp4" for i in range(2, 8)), "live.last.png", "final.json", "episode.json", "startup_binding.json",
              "startups.jsonl", "server.log", "episode.jsonl"):
        try:
            if os.path.exists(f"/data/{f}"):
                shutil.copy(f"/data/{f}", f"{LOG}/{f}")
        except OSError as exc:
            print(f"artifact copy failed for {f}: {exc}")


p = "/data/final.json"
if not os.path.exists(p):
    write(False, {"success": 0, "missing_log": 1, "infra_error": 1, "grader_error": 0}); copy_evidence(); raise SystemExit
try:
    d = json.load(open(p))
except ValueError:
    write(False, {"success": 0, "missing_log": 1, "infra_error": 1, "grader_error": 1}); copy_evidence(); raise SystemExit
sim_error = bool(d.get("sim_error")) and not d.get("infra_error")
# a done episode with rows but no trajectory file (the dump failed: disk, ...): the service's fault
dump_lost = bool(d.get("dump_error")) or (int(d.get("live_rows") or 0) > 0 and not os.path.isfile("/data/trajectory.npz"))
mismatch = bool(d.get("instance_mismatch"))
infra = bool(d.get("infra_error")) or not d.get("finalized") or mismatch or (dump_lost and bool(d.get("success")) and not sim_error)
num = lambda k, cast=int: cast(d.get(k) or 0)  # noqa: E731
base = {"live_success": int(bool(d.get("success"))), "finalized": int(bool(d.get("finalized"))), "live_rows": num("live_rows"),
        "sim_steps": num("physics_steps"), "control_steps": num("control_steps"), "sim_time_s": num("sim_time_s", float),
        "elapsed_s": num("elapsed_s", float), "service_time_s": num("service_time_s", float),
        "calls": num("calls"), "gave_up": int(bool(d.get("gave_up"))), "sim_startups": num("sim_startups"), "resumes": num("resumes"),
        "resume_state_mismatch": num("resume_state_mismatch"), "video_rendered": int(os.path.isfile("/data/live.mp4"))}
rep, replays = {}, []
traj = "/data/trajectory.npz"
if not infra and not sim_error and d.get("success") and os.path.isfile(traj):
    rg = "/tmp/replay_grade"; os.makedirs(rg, exist_ok=True)
    env = dict(os.environ, RCB_VERIFIER_LOG_DIR=rg)
    subprocess.run([sys.executable, os.path.join(HERE, "replay_grade.py"), "--task", TASK, "--binding", os.path.join(HERE, "runtime_binding.json"),
                    "--traj", traj, "--repeat", "2"], env=env, stderr=open(f"{LOG}/replay_grade.log", "w"))
    for extra in ("instance_error.json", "submission_error.json", "replay_0.log", "replay_1.log"):   # why a replay failed
        if os.path.isfile(f"{rg}/{extra}"):
            shutil.copy(f"{rg}/{extra}", f"{LOG}/{extra}")
    try:
        rep = json.load(open(f"{rg}/reward.json"))
        replays = json.load(open(f"{rg}/verdict.json")).get("evidence", {}).get("replays", [])
        shutil.copy(f"{rg}/verdict.json", f"{LOG}/replay_verdict.json")
    except (OSError, ValueError):
        rep = {"grader_error": 1}
replay_ok = bool(rep.get("success"))
replay_sha = replays[0].get("state_sha") if replays else None
live_match = bool(replay_sha) and replay_sha == d.get("live_sha")
rows_match = bool(replays) and int(replays[0].get("rows", -1)) == int(d.get("live_rows") or 0)
if rep.get("infra_error"):      # the verifier image's scene / runtime is not the bound one (replay_grade.py)
    infra = True
# a live success whose deterministic replays end elsewhere than the live state (or after another row count): the agent
# cannot change the journal or live_sha, so this is the service's or the host's fault, not the agent's 0
service_mismatch = bool(d.get("success")) and ((bool(replays) and bool(rep.get("deterministic")) and not (live_match and rows_match))
                                              or bool(rep.get("replay_crash")))   # a live success whose replays crash
grader_error = (bool(rep.get("grader_error")) or service_mismatch) and not infra
ok = bool(d.get("success")) and replay_ok and live_match and rows_match and not infra and not mismatch and not grader_error
write(ok, {"success": int(ok), **base, "replay_success": int(replay_ok), "replays": len(replays),
           "deterministic": int(bool(rep.get("deterministic")) and live_match), "live_matches_replay": int(live_match),
           "rows_match": int(rows_match), "instance_ok": int(bool(rep.get("instance_ok", not mismatch))),
           "instance_exact": int(bool(rep.get("instance_exact", not mismatch))), "instance_mismatch": int(mismatch or rep.get("instance_mismatch", 0) == 1),
           "bad_trajectory": int(bool(rep.get("bad_trajectory"))), "sim_breakdown": int(bool(rep.get("sim_breakdown"))),
           "replay_crash": int(bool(rep.get("replay_crash"))), "replay_wall_s": float(rep.get("replay_wall_s") or 0.0),
           "sim_error": int(sim_error), "dump_lost": int(dump_lost), "live_replay_mismatch": int(service_mismatch), "replays_skipped": int(not replays and not rep),
           "infra_error": int(infra), "grader_error": int(grader_error)})
copy_evidence()
