"""Editable nominal CPU training rollout; no deployment code, hidden draws, or private paths.

Use this as a simulator building block for parameter search or learning. It exports
only the bounded data artifact accepted by the frozen controller wrapper.
"""

import argparse
import json
from pathlib import Path

import mujoco
import numpy as np

from .go2 import Controller, JOINT_NAMES, SIDES, TORQUE_LIMIT, default_policy, inverse_leg, validate
from .go2_nominal import xml


def run(policy, assets, task="attitude", duration=6.0):
    if task not in ("attitude", "weave", "forward-jump", "yaw-jump") or not 2 <= duration <= 60:
        raise ValueError("Nominal training specification")
    model = mujoco.MjModel.from_xml_string(xml(assets))
    data = mujoco.MjData(model)
    joints = np.array([model.joint(name).id for name in JOINT_NAMES])
    qp, qv = model.jnt_qposadr[joints], model.jnt_dofadr[joints]
    motors = np.array([int(np.flatnonzero(model.actuator_trnid[:, 0] == j)[0]) for j in joints])
    data.qpos[:3] = [0, 0, 0.322]
    data.qpos[3:7] = [1, 0, 0, 0]
    data.qpos[qp] = np.concatenate([inverse_leg(np.array([0, s * 0.12, -0.30]), s) for s in SIDES])
    mujoco.mj_forward(model, data)
    controller = Controller(policy)
    history = []
    target = data.qpos[qp].copy()
    ff = np.zeros(12)
    for step in range(round(duration / 0.002)):
        t = step * 0.002
        w, x, y, z = data.qpos[3:7]
        rpy = np.array(
            [
                np.arctan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y)),
                np.arcsin(np.clip(2 * (w * y - z * x), -1, 1)),
                np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)),
            ]
        )
        cmd = np.zeros(7)
        if task == "attitude" and t >= 1:
            cmd[3:5] = [0.25 * np.sin(t - 1), 0.3 * np.sin(t - 1 + 0.8)]
        elif task == "weave" and t >= 1:
            cmd[0:2] = [0.25, 0.1 * np.cos((t - 1) * 0.8)]
        elif task == "forward-jump":
            cmd[5] = 0.85
        elif task == "yaw-jump":
            cmd[6] = np.deg2rad(135)
        obs = np.r_[data.qpos[qp], data.qvel[qv], rpy, data.qvel[3:6]]
        if step % 10 == 0:
            target, ff = controller.targets(t, task, obs, cmd)
        torque = controller.kp * (target - data.qpos[qp]) - controller.kd * data.qvel[qv] + ff
        data.ctrl[motors] = np.clip(torque, -TORQUE_LIMIT, TORQUE_LIMIT) if policy["enabled"] else 0
        if step % 25 == 0:
            history.append(
                dict(
                    t=t,
                    base_xyz=data.qpos[:3].tolist(),
                    rpy=rpy.tolist(),
                    q=data.qpos[qp].tolist(),
                    command=cmd.tolist(),
                )
            )
        mujoco.mj_step(model, data)
    return {"kind": "public-nominal-training", "task": task, "telemetry": history, "final_xyz": data.qpos[:3].tolist()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", required=True)
    parser.add_argument("--policy")
    parser.add_argument("--task", default="attitude")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    policy = json.loads(Path(args.policy).read_text()) if args.policy else default_policy()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    (out / "policy.json").write_bytes(validate(policy))
    (out / "nominal.json").write_text(json.dumps(run(policy, args.assets, args.task), allow_nan=False))
