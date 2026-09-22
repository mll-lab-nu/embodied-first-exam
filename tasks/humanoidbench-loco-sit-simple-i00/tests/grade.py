"""Verifier entry point: replay /app/output/trajectory.npz from the frozen instance and write Harbor rewards.

    python /tests/grade.py --family <family> --instance /tests/instance.npz --traj /app/output/trajectory.npz

Scoring happens here and nowhere else: the task image has upstream's reward functions deleted, and this
process patches the one this task needs back in (rcb_rewards.py) before it replays anything. Harbor only
copies tests/ into the container once the agent has finished, so the formula is never readable by it.

Writes /logs/verifier/reward.txt (1/0), reward.json (the numeric fields of PROTOCOL.md §3 -- Harbor turns
every key into a leaderboard metric, so HumanoidBench's own numbers go to diagnostics.json instead), and a
human-viewable replay video /logs/verifier/replay.mp4 plus replay.last.png.
Replays `--repeat` times in this fresh process; success requires every replay to reach the task's
success_bar AND all final-state hashes to agree (bit-exact determinism), so a lucky non-deterministic run
cannot pass.
"""
from __future__ import annotations
import argparse, json, os, sys, time, traceback
import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")


def write(ok: bool, out: dict, diagnostics: dict | None = None) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    open(os.path.join(LOG_DIR, "reward.txt"), "w").write("1\n" if ok else "0\n")
    json.dump(out, open(os.path.join(LOG_DIR, "reward.json"), "w"))
    if diagnostics:
        json.dump(diagnostics, open(os.path.join(LOG_DIR, "diagnostics.json"), "w"), indent=2)
    print(json.dumps({**out, **(diagnostics or {})}))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True); ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz"); ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--no-video", action="store_true"); ap.add_argument("--video-every", type=int, default=5); ap.add_argument("--video-fps", type=int, default=20)
    a = ap.parse_args()
    if not os.path.isfile(a.traj):
        write(False, {"success": 0, "missing_trajectory": 1, "grader_error": 0}); return 0
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        # The image has no reward function -- put this task's back before anything opens a Session,
        # because Session decides whether it can score by inspecting the class. See rcb_rewards.py.
        from rcb_rewards import restore
        restored = restore()
        from rcb_hb import GL_BACKEND, Session
        s = Session(a.family, instance=a.instance)
        if not s.scored:
            write(False, {"success": 0, "grader_error": 1, "rewards_not_restored": 1}); return 0
        d = np.load(a.traj, allow_pickle=False)
        if str(d["task"]) != a.family:
            write(False, {"success": 0, "wrong_family": 1, "grader_error": 0}); return 0
        acts = d["actions"]
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
                       "sim_steps_total": outs[-1]["sim_steps_total"],
                       "resets": outs[-1]["resets"],
                       "replay_seconds": round(t_replay, 2),
                       "render_seconds": 0.0,
                       "rewards_restored": restored}
        # Human-viewable replay video (never affects the verdict): /logs/verifier/replay.mp4 + replay.last.png
        if not a.no_video:
            try:
                s.close()
                t_render = time.perf_counter()
                sv = Session(a.family, instance=a.instance, enable_render=True)
                sv.render_video(acts, os.path.join(LOG_DIR, "replay.mp4"), every=a.video_every, fps=a.video_fps)
                diagnostics["render_seconds"] = round(time.perf_counter() - t_render, 2)
                out["video_rendered"] = 1
            except Exception:  # noqa: BLE001
                traceback.print_exc(file=sys.stderr)
        write(ok, out, diagnostics)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "grader_error": 1})
    return 0


if __name__ == "__main__":
    sys.exit(main())
