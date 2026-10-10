"""Verifier (privileged mode): replay /app/output/trajectory.npz from the frozen instance and write Harbor's rewards.

    python /tests/grade.py --instance /tests/instance.json --traj /app/output/trajectory.npz --repeat 2

Replays `--repeat` times in this fresh process. Pass = KinDER's goal check fires within the episode on every replay,
and every replay ends in the same state (bit-exact determinism), so a lucky non-deterministic run cannot pass.
Writes /logs/verifier/reward.txt (1/0), reward.json (numeric fields only: Harbor averages every key across the
dataset), diagnostics.json, and replay.mp4 + replay.last.png for humans.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback

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
    ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", default="/app/output/trajectory.npz")
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--no-video", action="store_true")
    a = ap.parse_args()
    if not os.path.isfile(a.traj):
        write(False, {"success": 0, "deterministic": 0, "missing_trajectory": 1, "invalid_trajectory": 0, "grader_error": 0})
        return 0
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from rcb_kinder import GL_BACKEND, Session
        s = Session(a.instance)
        try:
            acts = s.check_trajectory(s.load_trajectory(a.traj))
        except Exception as exc:  # noqa: BLE001 -- not an npz, missing keys, wrong instance, wrong shape, out of bounds
            traceback.print_exc(file=sys.stderr)
            write(False, {"success": 0, "deterministic": 0, "missing_trajectory": 0, "invalid_trajectory": 1, "grader_error": 0},
                  {"invalid": str(exc)})
            return 0
        t0 = time.perf_counter()
        outs = [s.replay(acts) for _ in range(a.repeat)]
        replay_s = time.perf_counter() - t0
        all_success = all(o["success"] for o in outs)
        deterministic = len({o["state_sha"] for o in outs}) == 1
        ok = all_success and deterministic
        out = {"success": int(ok), "all_success": int(all_success), "deterministic": int(deterministic),
               "n_actions": int(len(acts)), "sim_steps": int(outs[0]["steps"]), "missing_trajectory": 0,
               "invalid_trajectory": 0, "grader_error": 0, "video_rendered": 0}
        diagnostics = {"success_step": outs[0]["success_step"], "max_steps": s.max_steps, "state_sha": sorted({o["state_sha"] for o in outs}),
                       "gl_backend": GL_BACKEND, "replay_seconds": round(replay_s, 2)}
        write(ok, out, diagnostics)   # the verdict first: the video is for humans and may fail or run out of time
        if not a.no_video:
            try:
                s.render_video(acts, os.path.join(LOG_DIR, "replay.mp4"))
                out["video_rendered"] = 1
                write(ok, out, diagnostics)
            except Exception:  # noqa: BLE001
                traceback.print_exc(file=sys.stderr)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write(False, {"success": 0, "deterministic": 0, "missing_trajectory": 0, "invalid_trajectory": 0, "grader_error": 1})
    return 0


if __name__ == "__main__":
    sys.exit(main())
