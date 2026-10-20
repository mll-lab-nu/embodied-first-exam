"""The standard collect hook's video (finalize.sh): one pass over the recorded trajectory from the frozen instance, in a
fresh process, rendered into an mp4 (rcb_quadruped.Session.render_video: the robot's first two cameras side by side,
at most ~150 frames) and its last frame. It runs after final.json holds the verdict and decides nothing: no success, no
state hash is compared or written.

    python video.py --instance instance.json --traj trajectory.npz --out replay.mp4 --json video.json
"""
import argparse
import json
import os
import sys
import time
import traceback

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["RCB_SESSION_LOG"] = ""
os.environ["RCB_AGENT_TRACE_DIR"] = ""
import rcb_quadruped as Q  # noqa: E402  (first: it picks the rendering backend before mujoco loads)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--json", required=True)
    a = ap.parse_args()
    t0 = time.time()
    res = {"video": False, "rows": 0}
    try:
        A = np.asarray(np.load(a.traj, allow_pickle=False)["actions"], dtype=np.float64)
        res["rows"] = int(len(A))
        Q.Session(a.instance, check_hash=False).render_video(A, a.out)
        res["video"] = os.path.isfile(a.out)
    except Exception as exc:  # noqa: BLE001 -- a video that failed is only a missing video
        traceback.print_exc()
        res["error"] = repr(exc)[:300]
    res["video_s"] = round(time.time() - t0, 1)
    with open(a.json, "w") as f:
        json.dump(res, f)
    print(json.dumps(res), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
