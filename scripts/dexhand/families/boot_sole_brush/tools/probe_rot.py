import json, sys, itertools
from pathlib import Path
import numpy as np, mujoco
HERE = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(HERE))
from scene import build
cfg = json.loads((HERE / "task.json").read_text())
m, _ = build(cfg); d = mujoco.MjData(m)
qadr = m.jnt_qposadr[m.actuator_trnid[:, 0]]
def frame(rot):
    q = np.zeros(m.nu); q[3:6] = rot; d.qpos[:] = 0; d.qpos[qadr] = q; mujoco.mj_forward(m, d)
    palm = d.site_xpos[m.site("wrist_site").id].copy()
    mid = d.site_xpos[m.site("right_middle_fingertip").id] - palm
    th = d.site_xpos[m.site("right_thumb_fingertip").id] - palm
    t0 = d.site_xpos[m.site("right_index_fingertip").id].copy()
    q[11] = 1.0; d.qpos[qadr] = q; mujoco.mj_forward(m, d)
    flex = d.site_xpos[m.site("right_index_fingertip").id] - t0
    return mid / np.linalg.norm(mid), th, flex / np.linalg.norm(flex)
best = []
for rot in itertools.product(np.linspace(-np.pi, np.pi, 9), repeat=3):
    f, th, n = frame(rot)
    score = np.dot(f, [0, 1, 0]) + np.dot(n, [0, 0, -1])
    best.append((score, tuple(np.round(rot, 3)), f.round(2), n.round(2), th.round(3)))
best.sort(key=lambda x: -x[0])
for b in best[:6]: print(b)
