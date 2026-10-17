"""Verifier (privileged mode): replay /app/output/trajectory.npz open-loop from the scene's initial state and write the
Harbor rewards.

    python /tests/grade.py --task lack --binding /tests/runtime_binding.json --traj /app/output/trajectory.npz

The scene (/opt/ikea/scenes/<task>, from the image) must match the runtime binding file by file (`instance_exact`) and
build to the bound initial state (`instance_ok`). `--repeat` (2) replays run in fresh processes at the same time
(rcb_ikea.py replay: per row `data.ctrl[:] = row; S.step(4)`, then rcb_ikea's final_check(): success.py, released, at
rest and no breakdown at the end of the rows and again after the SETTLE_S hold of the last row). Pass iff every replay
succeeds and all end in the same state hashes, before and after the hold (`deterministic`; MuJoCo on the CPU is
bit-deterministic).
Writes /logs/verifier/reward.txt (1/0), reward.json (numbers only) and verdict.json (the replays' reports).
Replay video (PROTOCOL §4, board 0136; evidence only, never the verdict): a third process, render_video.py, replays the
same rows at the same time and writes /logs/verifier/replay.mp4 (+ replay.last.png, replay.json); the verdict is written
first, then `video_rendered` is set once the video exists, waiting for it at most as long again as the verdict replays
took plus 600 s and never past the verifier's limit (--budget-s); a video that fails or is late changes nothing else. No
video for a missing or invalid trajectory.
Failure classes (PROTOCOL H.5: grader_error / infra_error give a free retry, so only what is not the deliverable's doing
lands there): a replay killed by a signal (`replay_crash`) or one in which the scene's code or MuJoCo raised
(`replay_exception`, rcb_ikea.py replay) is a breakdown, the agent's 0; a scene that differs from the binding or builds
to another initial state (`instance_mismatch`) is infra_error; anything else that goes wrong in here is grader_error.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
T_START = time.time()
BUDGET_S = 0.0     # the task's [verifier] timeout_sec (--budget-s from tests/test.sh); 0: unknown


def atomic_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def write(ok: bool, out: dict, evidence=None) -> None:
    atomic_json(os.path.join(LOG_DIR, "verdict.json"), {"reward": out, "success": bool(ok), "evidence": evidence or {}})
    atomic_json(os.path.join(LOG_DIR, "reward.json"), out)
    atomic_json(os.path.join(LOG_DIR, "reward.txt"), int(ok))
    print(json.dumps(out), flush=True)


def wait_video(render, video: str, out: dict, outs: list, ok: bool = False) -> None:
    """The verdict is written; the video only adds evidence. It replays the same rows as the verdict replays did (at the
    same time, in its own process), so it gets as long again as they took, plus 600 s; a render that takes longer, fails
    or crashes leaves `video_rendered` 0 and the verdict unchanged, never an error."""
    if render is None:
        return
    wait = max(600.0, float(out.get("replay_wall_s") or 0.0)) + 600.0
    if BUDGET_S:                # stop well inside the verifier's time limit: a timed-out verifier loses the verdict
        wait = min(wait, BUDGET_S - (time.time() - T_START) - 180.0)
    try:
        if wait <= 0:
            raise subprocess.TimeoutExpired("render_video.py", 0)
        render.wait(timeout=wait)
    except subprocess.TimeoutExpired:
        render.kill(); render.wait()
        return
    except Exception:  # noqa: BLE001
        return
    if render.returncode == 0 and os.path.isfile(video) and os.path.getsize(video) > 0:
        out["video_rendered"] = 1
        write(ok, out, evidence={"replays": outs})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--binding", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz")
    ap.add_argument("--scene-dir", default=None)
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--max-rows", type=int, default=None, help="the task's row cap (its instruction states it)")
    ap.add_argument("--budget-s", type=float, default=0.0, help="the task's [verifier] timeout_sec (bounds the video wait)")
    a = ap.parse_args()
    global BUDGET_S
    BUDGET_S = a.budget_s
    os.makedirs(LOG_DIR, exist_ok=True)
    if os.path.islink(a.traj) or not os.path.isfile(a.traj):   # a regular file of the agent's own (H.1), never a link
        write(False, {"success": 0, "missing_trajectory": 1, "grader_error": 0})
        return 0
    try:
        import rcb_ikea as R
        b = json.load(open(a.binding))
        scene_dir = a.scene_dir or os.path.join(R.SCENES_ROOT, a.task)
        files = R.scene_files(scene_dir)
        exact = files == b["scene_files"]
        if not exact:
            diff = sorted(k for k in set(files) | set(b["scene_files"]) if files.get(k) != b["scene_files"].get(k))
            atomic_json(os.path.join(LOG_DIR, "instance_error.json"), {"differing_files": diff[:50]})
            # the image's scene is not the one the task was validated on: the host's / image's fault, not the agent's 0
            write(False, {"success": 0, "instance_mismatch": 1, "instance_exact": 0, "grader_error": 0, "infra_error": 1})
            return 0
        try:
            rows = len(R.load_trajectory(a.traj, int(b["nu"]), float(b["timestep"])))
            if a.max_rows is not None and rows > a.max_rows:
                raise R.InvalidTrajectory(f"{rows} rows, over the task's cap of {a.max_rows} (the verifier's replays must fit its time limit)")
        except R.InvalidTrajectory as exc:
            atomic_json(os.path.join(LOG_DIR, "submission_error.json"), {"error": str(exc)})
            write(False, {"success": 0, "bad_trajectory": 1, "grader_error": 0})
            return 0
        if a.repeat < 2:
            raise ValueError("grading requires at least two replays")
        t0 = time.time()
        outs, procs = [], []
        env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
        for k in range(a.repeat):
            path = f"/tmp/replay_{k}.json"
            log = open(os.path.join(LOG_DIR, f"replay_{k}.log"), "w")
            cmd = [sys.executable, os.path.join(HERE, "rcb_ikea.py"), "replay", "--task", a.task, "--traj", a.traj,
                   "--scene-dir", scene_dir, "--out", path]
            procs.append((subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log, env=env), path))
        video = os.path.join(LOG_DIR, "replay.mp4")
        render = None
        if os.path.isfile(os.path.join(HERE, "render_video.py")):
            render = subprocess.Popen([sys.executable, os.path.join(HERE, "render_video.py"), "--task", a.task, "--traj", a.traj,
                                       "--scene-dir", scene_dir, "--out", video], stdout=subprocess.DEVNULL,
                                      stderr=open(os.path.join(LOG_DIR, "render.log"), "w"), env=env)
        codes = [p.wait() for p, _ in procs]
        crashed = [c for c in codes if c < 0]
        if crashed:
            # a replay killed by a signal is a simulator crash (e.g. SIGSEGV inside MuJoCo) on the deliverable: a
            # breakdown, never a success and never the grader's fault. If only some replays crashed, the replays also
            # disagree (deterministic 0).
            out = {"success": 0, "sim_breakdown": 1, "replay_crash": 1, "replay_signal": -crashed[0],
                   "replays_crashed": len(crashed), "replays": len(codes),
                   "deterministic": int(len(crashed) == len(codes)), "replay_wall_s": round(time.time() - t0, 1),
                   "video_rendered": 0, "grader_error": 0, "infra_error": 0}
            write(False, out)
            wait_video(render, video, out, [])
            return 0
        for c, (p, path) in zip(codes, procs):
            if c != 0:
                raise RuntimeError(f"replay process exited with {c}")
            outs.append(json.load(open(path)))
        instance_ok = all(o["initial_state_sha"] == b["initial_state_sha256"] for o in outs)
        if not instance_ok:
            # the pinned scene files built to another initial state on this host: the host's fault (H.5), not the agent's 0
            out = {"success": 0, "instance_ok": 0, "instance_exact": 1, "instance_mismatch": 1, "replays": len(outs),
                   "video_rendered": 0, "grader_error": 0, "infra_error": 1}
            write(False, out, evidence={"replays": outs})
            return 0
        raised = [o for o in outs if o.get("replay_exception")]
        if raised:
            # the scene's code or MuJoCo raised on the state the rows drove it into (rcb_ikea.py replay): a breakdown
            # caused by the deliverable, the agent's 0, never a grader error (PROTOCOL H.5: no free retry).
            same = len(raised) == len(outs) and len({(o["replay_exception"], o.get("rows")) for o in outs}) == 1
            out = {"success": 0, "sim_breakdown": 1, "replay_exception": 1, "replays_raised": len(raised),
                   "replays": len(outs), "deterministic": int(same), "replay_wall_s": round(time.time() - t0, 1),
                   "video_rendered": 0, "grader_error": 0, "infra_error": 0}
            write(False, out, evidence={"replays": outs})
            wait_video(render, video, out, outs)
            return 0
        all_success = all(o.get("success") for o in outs)
        deterministic = len({(o.get("state_sha"), o.get("settled_sha")) for o in outs}) == 1
        ok = instance_ok and all_success and deterministic
        last, settled = outs[-1], outs[-1].get("settled") or {}
        term = last.get("terminal") or {}
        out = {"success": int(ok), "all_success": int(all_success), "deterministic": int(deterministic),
               "goal_at_end": int(bool(last.get("goal"))), "released_at_end": int(bool(last.get("released"))),
               "at_rest_at_end": int(bool(last.get("at_rest"))), "goal_after_settle": int(bool(settled.get("goal"))),
               "released_after_settle": int(bool(settled.get("released"))),
               "at_rest_after_settle": int(bool(settled.get("at_rest"))),
               "sim_breakdown": int(bool(last.get("breakdown") or settled.get("breakdown"))),
               "max_part_depth_mm": float((settled.get("terminal") or term).get("max_part_depth_mm") or 0.0),
               "settle_s": float(last.get("settle_s") or 0.0),
               "instance_ok": int(instance_ok), "instance_exact": 1, "runtime_binding_ok": 1,
               "n_actions": int(outs[-1].get("rows", 0)), "sim_steps": int(outs[-1].get("sim_steps", 0)),
               "sim_time_s": float(outs[-1].get("sim_time_s", 0.0)), "replays": len(outs),
               "replay_wall_s": round(time.time() - t0, 1), "video_rendered": 0, "grader_error": 0, "infra_error": 0}
        write(ok, out, evidence={"replays": outs})
        wait_video(render, video, out, outs, ok)
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "grader_error": 1})
    return 0


if __name__ == "__main__":
    sys.exit(main())
