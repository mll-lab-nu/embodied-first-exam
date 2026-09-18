"""Metric aperture commands and measured pad geometry for interchangeable tools."""

from functools import lru_cache
import json
import numpy as np
from scipy.spatial.transform import Rotation
from .assets import ROBOTIQ


@lru_cache(None)
def calibration():
    data = json.loads((ROBOTIQ / "calibration.json").read_text())
    return data, sorted(data["samples"], key=lambda row: row["full_gap_m"])


def robotiq_joint_targets(half_gap):
    data, rows = calibration()
    gap = np.clip(2 * float(half_gap), 0, 0.085)
    widths = [row["full_gap_m"] for row in rows]
    return dict(
        zip(
            data["joints"],
            [
                float(np.interp(gap, widths, [row["joint_pos"][j] for row in rows]))
                for j in range(8)
            ],
        )
    )


def as_numpy(x):
    return x.detach().cpu().numpy() if hasattr(x, "detach") else np.asarray(x)


def robotiq_pad_centres(robot):
    points = []
    for name in ("left_finger", "right_finger"):
        link = robot.get_link(name)
        q = as_numpy(link.get_quat()).reshape(-1, 4)[0]
        r = Rotation.from_quat(q[[1, 2, 3, 0]])
        # Midpoint of the two real silicone contact boxes, on their inner face.
        points.append(
            as_numpy(link.get_pos()).reshape(-1, 3)[0] + r.apply([0, -0.0066, 0.01875])
        )
    return np.array(points)


def pad_vertices(robot, model):
    """World corners of the contact pads, for clearance and proximity checks."""
    if model == "robotiq_2f85":
        center, half = (
            np.array([0.0, -0.0026, 0.01875]),
            np.array([0.011, 0.004, 0.01875]),
        )
    else:
        center, half = (
            np.array([0.0, 0.0055, 0.0445]),
            np.array([0.0085, 0.004, 0.0085]),
        )
    signs = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)])
    local = center + signs * half
    vertices = []
    for name in ("left_finger", "right_finger"):
        link = robot.get_link(name)
        q = as_numpy(link.get_quat()).reshape(-1, 4)[0]
        pos = as_numpy(link.get_pos()).reshape(-1, 3)[0]
        vertices.append(pos + Rotation.from_quat(q[[1, 2, 3, 0]]).apply(local))
    return np.concatenate(vertices)
