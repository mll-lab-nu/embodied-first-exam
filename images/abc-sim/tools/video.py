"""The episode's video (ABC Sim standard modes): ONE render pass of the recorded trajectory from the frozen instance, in
a fresh process, after the verdict is in final.json. It is for people only and decides nothing: it checks no success
and no state, and a render that fails, is stopped or runs out of time loses only the video.

    python /opt/abc-tools/video.py --instance /srv/instance.npz --traj /data/trajectory.npz --out /data/replay.mp4 \
        --result /data/video.json --deadline-s 1500

The frames are the `top`, `left` and `right` cameras side by side, 320 x 240 each, at most ~1500 of them plus the last;
the pass stops by itself `--deadline-s` seconds after it started and keeps the frames written so far (a playable file)."""
import argparse
import json
import os
import sys
import time

import numpy as np

os.environ["RCB_SESSION_LOG"] = ""
import rcb_abc as M  # noqa: E402  (first: it picks the rendering backend before mujoco loads)

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
    res = {"video": False, "frames": 0, "rows": 0, "cut_short": False, "gl": M.GL}
    try:
        A = np.asarray(np.load(a.traj, allow_pickle=False)["actions"], dtype=np.float64)
        res["rows"] = int(len(A))
        s = M.Session(instance=a.instance)
        import imageio.v2 as imageio
        cams = list(M.DEFAULT_CAMERAS)
        every = max(1, -(-len(A) // MAX_FRAMES))
        s.reset()
        w = imageio.get_writer(a.out, fps=max(1.0, 1 / (M.CONTROL_DT * every)), codec="libx264", quality=7,
                               macro_block_size=8)
        try:
            frame = lambda: np.concatenate([s.render_frame(c, SIZE) for c in cams], axis=1)  # noqa: E731
            w.append_data(frame())
            res["frames"] += 1
            for i, row in enumerate(A):
                running = s.step(row)
                if i % every == 0 or not running or i == len(A) - 1:
                    w.append_data(frame())
                    res["frames"] += 1
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
