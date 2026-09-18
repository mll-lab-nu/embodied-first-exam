"""Regenerate the unloaded aperture-to-joint map; no hardware calibration.

.venv-gs121-nyx/bin/python scripts/calibrate_robotiq_model.py
"""

import json
from pathlib import Path

import mujoco
import numpy as np


def main():
    folder = Path(__file__).resolve().parents[1] / "assets/robots/robotiq_2f85"
    model = mujoco.MjModel.from_xml_path(str(folder / "2f85.xml"))
    model.opt.gravity[:] = 0
    data = mujoco.MjData(model)
    samples = []
    for command in np.linspace(0, 255, 65):
        data.ctrl[:] = command
        for _ in range(1000):
            mujoco.mj_step(model, data)
        right = data.geom("right_pad1").xpos
        left = data.geom("left_pad1").xpos
        samples.append(
            dict(
                full_gap_m=float(abs(right[0] - left[0]) - 0.008),
                joint_pos=data.qpos.tolist(),
                pad_center_z=float((right[2] + left[2]) / 2 - 0.009375),
            )
        )
    result = dict(
        source="Unloaded MuJoCo model equilibrium; not measured hardware calibration",
        gravity=[0, 0, 0],
        joints=[model.joint(i).name for i in range(model.njnt)],
        samples=samples,
    )
    (folder / "calibration.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
