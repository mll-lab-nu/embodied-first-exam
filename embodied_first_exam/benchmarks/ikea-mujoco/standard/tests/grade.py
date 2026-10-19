"""Standard-mode verifier of the IKEA MuJoCo tasks (scripts/ikea_mujoco/standard/grade.py, copied unchanged), in the
separate verifier sandbox, without network. Reads what the sim service (which the agent could not touch) wrote:
/data/final.json (the live episode's result, finalized by environment/sim/finalize.sh) and checks that
/data/trajectory.npz (every control row the live episode executed, float64: the deliverable) was dumped. It replays
nothing (owner, 2026-10-17, board 0150/0151: the standard modes are graded by the live episode).

success = the live episode's success AND no infrastructure failure. The live success is the grader's rule on the live
simulator (server.py: rcb_ikea.Session.status(), then final_check() with the last executed row held 1.0 s more, the
privileged grader's terminal rules), so it already includes the settle window. reward.txt = success (1/0); reward.json
= numbers only.
Failure classes (PROTOCOL H.5: infra_error / grader_error give a free retry): a simulator error the agent's rows caused
(final.json sim_error: the scene's code or MuJoCo raised in a call) is the agent's 0 (sim_error 1), and so are a
breakdown, a timeout, an episode without actions and a crash give-up whose crashes were all inside the agent's calls
(`sim_crashed_on_call`); no / unreadable / unfinalized final.json, a scene, image or runtime that differs from the
binding at the episode's start (`instance_mismatch`, server.py), a give-up after crashes between calls (`sim_crashed`,
`resume_failed`, `call_watchdog`: final.json infra_error), a service-side error and a live success whose trajectory was
not dumped are infra_error. The live video (/data/live.mp4) is evidence only: its absence never changes the verdict."""
import json, os, shutil, sys

LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier"); os.makedirs(LOG, exist_ok=True)
DATA = os.environ.get("RCB_VERIFIER_DATA") or os.environ.get("RCB_DATA") or "/data"   # tests only: the sandbox sets neither
TASK = sys.argv[1] if len(sys.argv) > 1 else ""


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
            if os.path.exists(f"{DATA}/{f}"):
                shutil.copy(f"{DATA}/{f}", f"{LOG}/{f}")
        except OSError as exc:
            print(f"artifact copy failed for {f}: {exc}")


def grade() -> None:
    p = f"{DATA}/final.json"
    if not os.path.exists(p):
        write(False, {"success": 0, "live_success": 0, "graded_by_live": 1, "replays": 0, "finalized": 0, "missing_log": 1,
                      "infra_error": 1, "sim_error": 0, "grader_error": 0})
        return
    try:
        d = json.load(open(p))
        assert isinstance(d, dict)
    except (ValueError, AssertionError):
        write(False, {"success": 0, "live_success": 0, "graded_by_live": 1, "replays": 0, "finalized": 0, "missing_log": 1,
                      "infra_error": 1, "sim_error": 0, "grader_error": 1})
        return
    def num(k, cast=int):
        """A finite number from final.json, else 0 (reward.json takes numbers only; a bad value never fails the grader)."""
        try:
            v = float(d.get(k) or 0)
        except (TypeError, ValueError):
            return cast(0)
        return cast(v) if v == v and abs(v) != float("inf") else cast(0)
    sim_error = bool(d.get("sim_error")) and not d.get("infra_error")
    # `success` decides (a live rule recorded beside the live success, e.g. a failed settle, can only take it away)
    live = bool(d.get("success")) and bool(d.get("live_success", True)) and not d.get("gave_up")
    # a done episode with rows but no trajectory file (the dump failed: disk, ...): the service's fault
    dump_lost = bool(d.get("dump_error")) or (num("live_rows") > 0 and not os.path.isfile(f"{DATA}/trajectory.npz"))
    mismatch = bool(d.get("instance_mismatch"))
    infra = bool(d.get("infra_error")) or not d.get("finalized") or mismatch or (dump_lost and live and not sim_error)
    ok = live and not infra and not sim_error
    videos = [f for f in ("live.mp4", *(f"live.{i}.mp4" for i in range(2, 8))) if os.path.isfile(f"{DATA}/{f}")]
    write(ok, {"success": int(ok), "live_success": int(live), "graded_by_live": 1, "replays": 0,
               "finalized": int(bool(d.get("finalized"))), "missing_log": 0, "live_rows": num("live_rows"),
               "sim_steps": num("physics_steps"), "control_steps": num("control_steps"), "sim_time_s": num("sim_time_s", float),
               "elapsed_s": num("elapsed_s", float), "service_time_s": num("service_time_s", float),
               "calls": num("calls"), "settle_failed": num("settle_failed"), "gave_up": int(bool(d.get("gave_up"))),
               "sim_startups": num("sim_startups"), "resumes": num("resumes"), "resume_state_mismatch": num("resume_state_mismatch"),
               "instance_mismatch": int(mismatch), "video_rendered": int(bool(videos)), "video_segments": len(videos),
               "sim_error": int(sim_error), "dump_lost": int(dump_lost), "infra_error": int(infra), "grader_error": 0})


if __name__ == "__main__":
    try:
        grade()
    finally:
        copy_evidence()
