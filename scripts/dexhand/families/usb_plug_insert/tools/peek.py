#!/usr/bin/env python3
"""Authoring only: render a few frames of a trajectory (wide view) to a PNG contact sheet.

  peek.py <config.json> <rows.npz> <out.png> [control ...]
"""
import json, os, sys
from pathlib import Path
os.environ.setdefault("MUJOCO_GL", "egl")
FAMILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FAMILY))
os.chdir(FAMILY)
import numpy as np
import mujoco
import imageio.v2 as imageio
from runtime import Session

cfg = json.loads(Path(sys.argv[1]).read_text())
rows = np.load(sys.argv[2])["actions"]
picks = sorted(int(x) for x in sys.argv[4:]) or [0, 200, 300, 400, 500, 600, 700, 800]
s = Session(config=cfg, hand="sharpa")
r = mujoco.Renderer(s.model, 360, 480)
cam = mujoco.MjvCamera()
cam.type = mujoco.mjtCamera.mjCAMERA_FREE
cam.lookat[:] = (0.8, -0.2, 0.8); cam.distance = 1.6; cam.azimuth = -20; cam.elevation = -15
cam2 = mujoco.MjvCamera(); cam2.type = mujoco.mjtCamera.mjCAMERA_FREE
cam2.lookat[:] = (0.66, -0.13, 0.70); cam2.distance = 0.30; cam2.azimuth = -60; cam2.elevation = -10
tiles = []
for i, row in enumerate(rows):
    if s.steps in picks:
        row_imgs = []
        for c in (cam, cam2):
            r.update_scene(s.data, c); row_imgs.append(r.render().copy())
        tiles.append(np.concatenate(row_imgs, axis=1))
    s.step(row)
    if s.done:
        break
for c in (cam, cam2):
    pass
row_imgs = []
for c in (cam, cam2):
    r.update_scene(s.data, c); row_imgs.append(r.render().copy())
tiles.append(np.concatenate(row_imgs, axis=1))
print("end", s.steps, s.status()["reason"], s.failure_detail)
imageio.imwrite(sys.argv[3], np.concatenate(tiles, axis=0))
