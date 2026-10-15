"""Authoring preview: replay a trajectory (every control) and write a 1280x720 mp4 plus selected PNG frames.

CPU rendering: MUJOCO_GL=egl __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json (Mesa llvmpipe).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from replay import load_trajectory, overlay  # noqa: E402
from runtime import Session  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--traj", required=True)
p.add_argument("--out", required=True)
p.add_argument("--camera", default="overview")
p.add_argument("--fps", type=int, default=25)
p.add_argument("--frames", default="", help="comma separated control indices to save as PNG")
p.add_argument("--label", default="actuator replay")
p.add_argument("--start", type=int, default=0, help="first control rendered (earlier controls are simulated only)")
a = p.parse_args()
import imageio.v2 as imageio
from PIL import Image

actions, hand, _ = load_trajectory(a.traj)
s = Session(hand=hand)
s.model.vis.quality.offsamples = 4
stride = max(1, round(1 / (s.control_dt * a.fps)))
want = {int(x) for x in a.frames.split(",") if x}
out = Path(a.out)
out.parent.mkdir(parents=True, exist_ok=True)
label = s.hand_info["model"]
w = imageio.get_writer(out, fps=a.fps, codec="libx264", quality=8, macro_block_size=16)
def frame():
    return overlay(s.render_frame(a.camera, width=1280, height=720, shadows=True), s.features(), a.label, label)
saved = []
for row in actions[: a.start]:
    s.step(row)
w.append_data(frame())
for i, row in enumerate(actions[a.start:], start=a.start):
    s.step(row)
    if (i + 1) % stride == 0 or s.done:
        img = frame()
        w.append_data(img)
        if any(abs(i + 1 - k) < stride for k in want if k not in [x[0] for x in saved]):
            k = min(want, key=lambda k: abs(i + 1 - k))
            path = out.with_name(out.stem + f"_{i + 1:05d}.png")
            Image.fromarray(img).save(path)
            saved.append((k, str(path)))
    if s.done:
        break
last = frame()
for _ in range(a.fps):
    w.append_data(last)
Image.fromarray(last).save(out.with_name(out.stem + "_final.png"))
w.close()
st = s.status()
print(json.dumps({"video": str(out), "frames": [x[1] for x in saved], "success": st["success"], "reason": st["reason"],
                  "steps": st["steps"], "stage": st["stage"]}))
