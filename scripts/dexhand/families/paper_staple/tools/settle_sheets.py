"""Authoring tool: settle the three loose sheets (corner propped on the stapler anvil, far edge on the desk) and
freeze their rest poses into task.json (``sheets[i].pose``). The reset then starts from this physical rest state."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation as Rot

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from scene import build  # noqa: E402

LAYOUT = [  # sheet centre (x, y) before settling; upper sheets protrude toward +x (staircase)
    (0.744, -0.0360),
    (0.748, -0.0356),
    (0.752, -0.0364),
]
PITCH = 0.0715


def main(seconds=3.0):
    path = HERE / "task.json"
    config = json.loads(path.read_text())
    t = config["sheet"]["thickness"]
    quat = Rot.from_rotvec([0, PITCH, 0]).as_quat(scalar_first=True)
    for i, (x, y) in enumerate(LAYOUT):
        z = 0.7882 + t / 2 + i * t * 1.05 + 0.0004
        config["sheets"][i] = {"center": [x, y], "yaw": 0.0, "pose": [x, y, z, *quat.tolist()]}
    model, _, _ = build(config, hand="sharpa")
    data = mujoco.MjData(model)
    qadr = model.jnt_qposadr[model.actuator_trnid[:, 0]]
    init = np.asarray(config["initial_targets"]["sharpa"])
    data.qpos[qadr] = init
    data.ctrl[:] = init
    mujoco.mj_forward(model, data)
    for _ in range(int(seconds / model.opt.timestep)):
        mujoco.mj_step(model, data)
    speeds = []
    for i in range(3):
        b = model.body(f"sheet_{i}").id
        v = np.empty(6)
        mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, b, v, 0)
        speeds.append(float(np.linalg.norm(v)))
        pos = data.xpos[b].copy()
        q = data.xquat[b].copy()
        config["sheets"][i]["pose"] = [round(float(v_), 7) for v_ in (*pos, *(q / np.linalg.norm(q)))]
    path.write_text(json.dumps(config, indent=2) + "\n")
    print(json.dumps({"speeds": speeds, "sheets": config["sheets"]}, indent=1))


if __name__ == "__main__":
    main()
