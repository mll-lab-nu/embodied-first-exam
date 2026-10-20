"""The episode's video (MyoSuite standard mode): ONE render pass of the recorded trajectory from the frozen instance, in a
fresh process, after the verdict is in final.json (finalize.sh). It is for people only and decides nothing: it checks no
success and no state, and a render that fails, is stopped or runs out of time loses only the video.

    python /srv/video.py --instance /srv/instance.npz --traj /data/trajectory.npz --out /data/replay.mp4 \
        --result /data/video.json --deadline-s 1500

The frames are what Session.render_video draws (the hand close-ups `hand_top` + `hand_side_inter` side by side where
the scene has them, else its default camera; 320 x 240, 25 fps), at most ~1500 of them plus the last; the pass stops
by itself `--deadline-s` seconds after it started and keeps the frames written so far (a playable file)."""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["RCB_SESSION_LOG"] = ""
import rcb_myosuite as M  # noqa: E402  (first: it picks the rendering backend before mujoco loads)

M.SESSION_LOG = ""
MAX_FRAMES = 1500
SIZE = (240, 320)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--result", required=True, help="write {video, frames, rows, cut_short} here")
    ap.add_argument("--deadline-s", type=float, default=0.0, help="stop this long after the start (0: never)")
    a = ap.parse_args()
    t0 = time.time()
    res = {"video": False, "frames": 0, "rows": 0, "cut_short": False}
    try:
        A = np.asarray(np.load(a.traj, allow_pickle=False)["actions"], dtype=np.float64)
        res["rows"] = int(len(A))
        task = str(np.load(a.instance, allow_pickle=False)["task"])
        s = M.Session(task, instance=a.instance)
        import imageio.v2 as imageio
        cams = [c for c in ("hand_top", "hand_side_inter") if c in s.cameras()] or [s.default_camera()]
        every = max(1, -(-len(A) // MAX_FRAMES))
        s.reset()
        w = imageio.get_writer(a.out, fps=25, codec="libx264", quality=7, macro_block_size=8)
        try:
            frame = lambda: np.concatenate([s.render_frame(c, SIZE) for c in cams], axis=1)  # noqa: E731
            w.append_data(frame()); res["frames"] += 1
            for i, row in enumerate(A):
                running = s.step(row)
                if i % every == 0 or not running or i == len(A) - 1:
                    w.append_data(frame()); res["frames"] += 1
                if not running:
                    break
                if a.deadline_s and time.time() - t0 > a.deadline_s:
                    res["cut_short"] = True
                    break
        finally:
            w.close()
        res["video"] = os.path.isfile(a.out)
    except Exception as exc:  # noqa: BLE001 -- the video never changes the verdict
        import traceback
        traceback.print_exc()
        res["error"] = repr(exc)[:300]
    res["elapsed_s"] = round(time.time() - t0, 1)
    with open(a.result, "w") as f:
        json.dump(res, f)
    print(json.dumps(res), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
