"""The standard collect hook's video (finalize.sh): one pass over the recorded trajectory from the frozen instance, in a
fresh process, rendered into an mp4 (the default static camera and the right hand camera side by side, at most ~1500
frames). It runs after final.json holds the verdict and decides nothing: no success, no state
hash is compared or written. `--deadline-s` stops it that long after its start, keeping the frames written so far.

    python video.py --task T --instance instance.npz --traj trajectory.npz --out replay.mp4 --json video.json [--deadline-s S]
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
import rcb_dexjoco as M  # noqa: E402

M.SESSION_LOG = ""
MAX_FRAMES = 1500


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--task", required=True)
    ap.add_argument("--instance", required=True)
    ap.add_argument("--traj", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--json", required=True)
    ap.add_argument("--deadline-s", type=float, default=0.0, help="stop this long after the start (0: never)")
    a = ap.parse_args()
    t0 = time.time()
    res = {"video": False, "rows": 0}
    try:
        A = np.asarray(np.load(a.traj, allow_pickle=False)["actions"], dtype=np.float64)
        res["rows"] = int(len(A))
        s = M.Session(a.task, instance=a.instance)
        s.render_video(A, a.out, cameras=s.video_cameras(), every=max(2, -(-len(A) // MAX_FRAMES)),
                       deadline=(t0 + a.deadline_s) if a.deadline_s else None)
        s.close()
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
