"""Agent-accessible training rollout, containing only nominal MuJoCo dynamics."""

import argparse
import json
import numpy as np
import mujoco
from .model import CT, DT, GRAVITY, HORIZON, MASS, MOTOR_TAU, sample_task, xml
from .policy import Controller, DEFAULT


def rollout(policy=DEFAULT, seed=0):
    rng = np.random.default_rng(seed)
    initial, pad = sample_task(rng)
    m = mujoco.MjModel.from_xml_string(xml(pad))
    d = mujoco.MjData(m)
    d.qpos[:3] = initial
    d.qpos[3:7] = [1, 0, 0, 0]
    motors = np.full(4, MASS * GRAVITY / 4)
    controller = Controller(policy)
    rows = []
    for k in range(round(HORIZON / DT)):
        d.ctrl[:] = motors
        mujoco.mj_forward(m, d)
        obs = {
            "t": k * DT,
            "pad_position": pad.tolist(),
            "position": (d.qpos[:3] + rng.normal(0, 0.002, 3)).tolist(),
            "velocity": (d.qvel[:3] + rng.normal(0, 0.008, 3)).tolist(),
            "quaternion": d.qpos[3:7].tolist(),
            "omega": d.qvel[3:].tolist(),
            "rotor_rpm": np.sqrt(motors / CT).tolist(),
        }
        command = controller.act(obs)
        for _ in range(5):
            motors += (1 - np.exp(-m.opt.timestep / MOTOR_TAU)) * (command - motors)
            d.ctrl[:] = motors
            mujoco.mj_step(m, d)
        rows.append(
            {
                "t": float(d.time),
                "position": d.qpos[:3].tolist(),
                "velocity": d.qvel[:3].tolist(),
                "pad_position": pad.tolist(),
            }
        )
    return rows


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    a = p.parse_args()
    with open(a.out, "w") as f:
        json.dump(rollout(), f)
