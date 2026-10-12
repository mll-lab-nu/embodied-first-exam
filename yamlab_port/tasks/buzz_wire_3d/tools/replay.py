"""Open-loop replay of a saved BuzzWire3D action sequence from the same reset.

Physics only (vast):
  BUZZ_NO_CAMERAS=1 PYTHONPATH=$RUN/yamlab python replay.py --headless --tier very_easy --actions oracle_actions.npy --out DIR
With frames (host with working RTX, e.g. ws/ws3 Isaac 5.1 container; do NOT set BUZZ_NO_CAMERAS):
  PYTHONPATH=<yamlab copy with the task installed> python replay.py --headless --enable_cameras --tier very_easy \
      --actions oracle_actions.npy --out DIR --frame_every 2
Frames (top + both wrist cameras, PNG) go to DIR/frames/; make a video e.g. with
  ffmpeg -framerate 15 -pattern_type glob -i 'DIR/frames/top_camera_*.png' top.mp4
"""
import argparse
import json
import os
import sys

from isaaclab.app import AppLauncher

ap = argparse.ArgumentParser()
ap.add_argument("--tier", default="very_easy")
ap.add_argument("--actions", required=True)
ap.add_argument("--out", default="replay")
ap.add_argument("--name", default="replay")
ap.add_argument("--frame_every", type=int, default=3)
AppLauncher.add_app_launcher_args(ap)
args = ap.parse_args()
args.headless = True
app = AppLauncher(args).app

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bw_runner import Runner, make_env

cams = bool(getattr(args, "enable_cameras", False)) and os.environ.get("BUZZ_NO_CAMERAS", "0") != "1"
env = make_env(args.tier, cameras=cams)
env.reset()
R = Runner(env, args.out, frames_dir=os.path.join(args.out, "frames") if cams else None, frame_every=args.frame_every)
acts = np.load(args.actions)
R.phase = "replay"
for a in acts:
    R.action = a.astype(np.float32).copy()
    R.step()
    if R.done:
        break
m = R.save(args.name, extra=dict(mode="replay", tier=args.tier, source_actions=os.path.abspath(args.actions), cameras=cams))
print("RESULT", json.dumps({k: m[k] for k in ("success", "termination", "steps", "touched", "min_metal_wire_gap_mm",
                                               "traversal_complete", "state_sha256")}))
env.close()
app.close()
