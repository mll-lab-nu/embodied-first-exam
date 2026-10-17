"""Authoring only: settle the pre-held turner grasp and freeze it as the reset state in task.json.

The turner is placed across the open palm and kept still (authoring-time state hold) only while the fingers close
on it; then it is released and the whole scene integrates freely under gravity: grasp settling, a conditioning
motion of the wrist stage (so the handle seats in the fist) and a final rest at the start pose. The resulting
qpos (hand, turner, pancake, pan, plate) and the finger targets become ``initial_qpos[hand]`` /
``initial_targets[hand]``; the runtime reset only writes this frozen state (zero velocity) before the episode.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from scene import build  # noqa: E402

# Start pose of the wrist stage (world metres, serial XYZ radians): palm down above the turner's rest spot.
START = {"sharpa": [0.40, -0.32, 1.06, np.pi, 0.0, 0.0], "wuji": [0.40, -0.32, 1.06, np.pi, 0.0, 0.0]}
# Turner handle pose in the wrist-stage frame while the fingers close (x along the fingers, z palm normal).
HANDLE = {"sharpa": [0.125, 0.0, 0.028, np.pi, 0.0, 0.0], "wuji": [0.115, 0.0, 0.012, np.pi, 0.0, 0.0]}
FINGERS = {
    # thumb CMC_FE, CMC_AA, MCP_FE, MCP_AA, IP; index/middle/ring MCP_FE, MCP_AA, PIP, DIP; pinky CMC, MCP_FE...
    "sharpa": [1.6, 0, 0.9, 0, 1.2] + [1.3, 0, 1.3, 1.0] * 3 + [0.2] + [1.3, 0, 1.3, 1.0],
    # THJ0..3, then FF/MF/RF/LF J0 (MCP flex), J1 (abduction), J2 (PIP), J3 (DIP)
    "wuji": [0.3, -1.4, 1.3, 1.3] + [1.57, 0, 2.0, 1.5] * 4,
}


def settle(config, hand, start=None, handle=None, fingers=None, conditioning=True):
    start = np.asarray(START[hand] if start is None else start, float)
    handle = np.asarray(HANDLE[hand] if handle is None else handle, float)
    fingers = np.asarray(FINGERS[hand] if fingers is None else fingers, float)
    model, _ = build(config, hand=hand)
    data = mujoco.MjData(model)
    qadr = model.jnt_qposadr[model.actuator_trnid[:, 0]]
    target = np.zeros(model.nu)
    target[:6] = start
    data.qpos[qadr[:6]] = start
    data.ctrl[:] = target
    mujoco.mj_forward(model, data)
    stage = model.body("wrist_stage").id
    rotation = data.xmat[stage].reshape(3, 3) @ Rotation.from_euler("XYZ", handle[3:]).as_matrix()
    position = data.xpos[stage] + data.xmat[stage].reshape(3, 3) @ handle[:3]
    xyzw = Rotation.from_matrix(rotation).as_quat()
    pose = np.r_[position, xyzw[3], xyzw[:3]]
    qa = model.joint("turner_free").qposadr[0]
    va = model.joint("turner_free").dofadr[0]
    data.qpos[qa:qa + 7] = pose
    mujoco.mj_forward(model, data)
    substeps = round(config["control_dt"] / config["physics_dt"])
    for k in range(20):  # fingers close on the held handle (0.4 s)
        target[6:] = fingers * min(1.0, (k + 1) / 15)
        data.ctrl[:] = target
        for _ in range(substeps):
            mujoco.mj_step(model, data)
            data.qpos[qa:qa + 7] = pose
            data.qvel[va:va + 6] = 0.0

    def run(controls, goal=None):
        start_ctrl = data.ctrl[:6].copy()
        for k in range(controls):
            if goal is not None:
                s = (k + 1) / controls
                data.ctrl[:6] = start_ctrl + (np.asarray(goal) - start_ctrl) * (s * s * (3 - 2 * s))
            for _ in range(substeps):
                mujoco.mj_step(model, data)

    run(75)  # release: the handle seats in the fist under gravity
    if conditioning:
        base = start.copy()
        for offset in ([0, 0, -0.08, 0, 0, 0], [0.12, 0.06, -0.08, 0.15, 0, 0], [0.12, 0.06, -0.04, -0.15, 0, 0],
                       [0, 0, 0, 0, 0, 0]):
            run(60, base + np.asarray(offset))
    run(100)  # rest at the start pose
    return model, data, target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hand", default="sharpa", choices=["sharpa", "wuji"])
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--png")
    args = parser.parse_args()
    path = HERE / "task.json"
    config = json.loads(path.read_text())
    model, data, target = settle(config, args.hand)
    turner = model.body("turner").id
    stage = model.body("wrist_stage").id
    rel = data.xmat[stage].reshape(3, 3).T @ (data.xpos[turner] - data.xpos[stage])
    print("turner in wrist frame", rel.round(4).tolist(), "max |qvel|", float(np.abs(data.qvel).max()))
    print("ncon", data.ncon, "turner z", float(data.xpos[turner][2]))
    if args.png:
        from PIL import Image

        renderer = mujoco.Renderer(model, 720, 1280)
        frames = []
        for cam in ("overview", "side"):
            renderer.update_scene(data, cam)
            frames.append(renderer.render().copy())
        Image.fromarray(np.vstack(frames)).save(args.png)
    if args.write:
        config["initial_qpos"][args.hand] = [float(v) for v in data.qpos]
        config["initial_targets"][args.hand] = [float(v) for v in target]
        path.write_text(json.dumps(config, indent=1) + "\n")
        print("wrote", path)


if __name__ == "__main__":
    main()
