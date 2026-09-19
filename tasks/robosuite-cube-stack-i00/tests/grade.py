"""Verifier entry point: replay /app/output/trajectory.npz from the frozen instance and write Harbor rewards.

    python /tests/grade.py --family cube_stack --instance /tests/instance.npz --traj /app/output/trajectory.npz

Writes /logs/verifier/reward.txt (1/0), reward.json (numeric fields only — Harbor rejects strings), and a
human-viewable replay video /logs/verifier/replay.mp4 (scene + wrist camera) plus replay.last.png.
Replays `--repeat` times in this fresh process; success requires every replay to complete the task AND
all final-state hashes to agree (bit-exact determinism), so a lucky non-deterministic run cannot pass.
"""
from __future__ import annotations
import argparse, json, os, sys, traceback
import numpy as np

LOG_DIR = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")


def write(ok: bool, out: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    open(os.path.join(LOG_DIR, "reward.txt"), "w").write("1\n" if ok else "0\n")
    json.dump(out, open(os.path.join(LOG_DIR, "reward.json"), "w"))
    print(json.dumps(out))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True); ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz"); ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--no-video", action="store_true"); ap.add_argument("--video-every", type=int, default=5); ap.add_argument("--video-fps", type=int, default=20)
    a = ap.parse_args()
    if not os.path.isfile(a.traj):
        write(False, {"success": 0, "missing_trajectory": 1, "grader_error": 0}); return 0
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from rcb_traj import Session
        s = Session(a.family, instance=a.instance)
        d = np.load(a.traj, allow_pickle=False)
        if str(d["task"]) != a.family:
            write(False, {"success": 0, "wrong_family": 1, "grader_error": 0}); return 0
        acts = d["actions"]
        outs = [s.replay(acts) for _ in range(a.repeat)]
        all_success = all(o["success"] for o in outs)
        deterministic = len({o["state_sha"] for o in outs}) == 1
        ok = all_success and deterministic
        out = {"success": int(ok), "all_success": int(all_success), "deterministic": int(deterministic),
               "n_actions": int(len(acts)), "final_reward": float(outs[0]["reward"]),
               "sim_steps": int(outs[0]["sim_steps"]), "grader_error": 0, "video_rendered": 0}
        # Human-viewable replay video (never affects the verdict): /logs/verifier/replay.mp4 + replay.last.png
        if not a.no_video:
            try:
                s.close()
                sv = Session(a.family, instance=a.instance, enable_render=True)
                sv.render_video(acts, os.path.join(LOG_DIR, "replay.mp4"), every=a.video_every, fps=a.video_fps, wrist=True)
                out["video_rendered"] = 1
            except Exception:  # noqa: BLE001
                traceback.print_exc(file=sys.stderr)
        write(ok, out)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "grader_error": 1})
    return 0


if __name__ == "__main__":
    sys.exit(main())
