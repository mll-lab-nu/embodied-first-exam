"""Verifier entry point: replay /app/output/trajectory.npz from the frozen instance and write Harbor rewards.

    python /tests/grade.py --family <family> --instance /tests/instance.npz --traj /app/output/trajectory.npz

Scoring happens here and nowhere else: the task image has upstream's reward functions deleted, and this
process patches the one this task needs back in (rcb_rewards.py) before it replays anything. It runs in its
own container, built from tests/Dockerfile (docs/PROTOCOL.md §4): the agent's container is gone by then, and
only /app/output/ crosses over.

Writes /logs/verifier/reward.txt (1/0), reward.json (the numeric fields of PROTOCOL.md §3 -- Harbor turns
every key into a leaderboard metric, so HumanoidBench's own numbers go to diagnostics.json instead), and a
human-viewable replay video /logs/verifier/replay.mp4 plus replay.last.png.
Replays `--repeat` times in this fresh process; success requires every replay to reach the task's
success_bar AND all final-state hashes to agree (bit-exact determinism), so a lucky non-deterministic run
cannot pass. A deliverable that breaks the contract instruction.md states -- another task's, or not a (T, nu)
array of finite values with T at most the episode limit -- scores 0 as the agent's failure, not the grader's.
"""
from __future__ import annotations
import argparse, json, os, sys, time, traceback
import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def write(ok: bool, out: dict, diagnostics: dict | None = None) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    open(os.path.join(LOG_DIR, "reward.txt"), "w").write("1\n" if ok else "0\n")
    json.dump(out, open(os.path.join(LOG_DIR, "reward.json"), "w"))
    if diagnostics:
        json.dump(diagnostics, open(os.path.join(LOG_DIR, "diagnostics.json"), "w"), indent=2)
    print(json.dumps({**out, **(diagnostics or {})}))


def load_actions(path: str, family: str, nu: int, max_steps: int) -> tuple[np.ndarray | None, str]:
    """The deliverable's actions, or None and the reward.json field that says why not."""
    try:
        d = np.load(path, allow_pickle=False)
        task, acts = str(d["task"]), np.asarray(d["actions"], dtype=np.float64)
    except Exception:  # noqa: BLE001  (not an npz, a pickle, or a key missing)
        return None, "bad_trajectory"
    if task != family:
        return None, "wrong_family"
    if acts.ndim != 2 or acts.shape[1] != nu or len(acts) > max_steps or not np.isfinite(acts).all():
        return None, "bad_trajectory"
    return acts, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True); ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz"); ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--no-video", action="store_true"); ap.add_argument("--video-every", type=int, default=5); ap.add_argument("--video-fps", type=int, default=20)
    a = ap.parse_args()
    if not os.path.isfile(a.traj):
        write(False, {"success": 0, "missing_trajectory": 1, "grader_error": 0}); return 0
    try:
        # rcb_hb first: it picks MuJoCo's GL backend, which `import mujoco` binds once per process. Then this
        # task's reward goes back before anything opens a Session, because Session decides whether it can score
        # by inspecting the class. See rcb_rewards.py.
        from rcb_hb import GL_BACKEND, Session
        from rcb_rewards import progress, restore
        restored = restore()
        s = Session(a.family, instance=a.instance)
        if not s.scored:
            write(False, {"success": 0, "grader_error": 1, "rewards_not_restored": 1}); return 0
        acts, why = load_actions(a.traj, a.family, s.nu, s.max_steps)
        if acts is None:
            write(False, {"success": 0, why: 1, "grader_error": 0}); return 0
        t_replay = time.perf_counter()
        outs = [s.replay(acts) for _ in range(a.repeat)]
        t_replay = time.perf_counter() - t_replay
        all_success = all(o["success"] for o in outs)
        deterministic = len({o["state_sha"] for o in outs}) == 1
        ok = all_success and deterministic
        out = {"success": int(ok), "all_success": int(all_success), "deterministic": int(deterministic),
               "n_actions": int(len(acts)), "final_reward": float(outs[0]["final_reward"]),
               "sim_steps": int(outs[0]["sim_steps"]), "grader_error": 0, "video_rendered": 0}
        # Not in reward.json: episode_return is on a per-task scale, and Harbor would average it across
        # the whole dataset. Keep it here, where a human debugging one task will look.
        # Harbor times the verifier as a whole; this is the split inside it. The physics half is the
        # honest cost of grading, the render half is the price of the human-viewable video -- and the
        # ratio between them is what makes the osmesa/egl difference visible.
        diagnostics = {"episode_return": [o["episode_return"] for o in outs],
                       "success_bar": s.success_bar,
                       "state_sha": sorted({o["state_sha"] for o in outs}),
                       "gl_backend": GL_BACKEND,
                       "replay_seconds": round(t_replay, 2),
                       "render_seconds": 0.0,
                       "rewards_restored": restored}
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "grader_error": 1}); return 0
    write(ok, out, diagnostics)            # the verdict first: everything below is for humans and may fail
    try:
        if prog := progress(s.low.task):   # where the last replay left a multi-stage task (cabinet, kitchen, maze, ...)
            diagnostics["progress"] = prog
        if not a.no_video:                 # /logs/verifier/replay.mp4 + replay.last.png
            s.close()
            t_render = time.perf_counter()
            sv = Session(a.family, instance=a.instance, enable_render=True)
            sv.render_video(acts, os.path.join(LOG_DIR, "replay.mp4"), every=a.video_every, fps=a.video_fps)
            diagnostics["render_seconds"] = round(time.perf_counter() - t_render, 2)
            out["video_rendered"] = 1
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
    write(ok, out, diagnostics)                # again, with the video and the progress
    return 0


if __name__ == "__main__":
    sys.exit(main())
