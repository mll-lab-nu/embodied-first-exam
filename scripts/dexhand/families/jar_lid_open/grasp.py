"""Authoring helper: fingertip grasp synthesis around the lid skirt (kinematic least squares, no physics)."""

from __future__ import annotations

import math

import mujoco
import numpy as np
from scipy.optimize import least_squares

from scene import LID_RADIUS

FINGERS = ("thumb", "index", "middle", "ring")
# Finger actuator columns of a row (after the six wrist targets) and the fingertip contact geom per hand.
LAYOUT = {
    "sharpa": {
        "act": {"thumb": range(6, 11), "index": range(11, 15), "middle": range(15, 19), "ring": range(19, 23),
                "pinky": range(23, 28)},
        "tip": {f: f"right_{f}_fingertip_collision" for f in FINGERS},
    },
    "wuji": {
        "act": {"thumb": range(6, 10), "index": range(10, 14), "middle": range(14, 18), "ring": range(18, 22),
                "pinky": range(22, 26)},
        "tip": {"thumb": "r_wuji_r_thumb_tip_sensor_frame_collision1",
                "index": "r_wuji_r_index_finger_tip_sensor_frame_collision1",
                "middle": "r_wuji_r_middle_finger_tip_sensor_frame_collision1",
                "ring": "r_wuji_r_ring_finger_tip_sensor_frame_collision1"},
    },
}


def pad_radius(model, gid):
    """Contact offset of a fingertip geom: capsule radius, else the smaller half extent of its bounding box."""
    if model.geom_type[gid] == mujoco.mjtGeom.mjGEOM_CAPSULE:
        return float(model.geom_size[gid, 0])
    return float(min(model.geom_aabb[gid, 3:5]))


def grasp_pose(session, centre, angles, height, radius_offset, seed, yaw=0.0, weights=None, collide=True,
               fix_wrist=False):
    """Joint targets placing fingertip pads on a circle around ``centre``.

    ``angles``: finger -> contact angle (rad, world frame, before ``yaw``); pads at radius LID_RADIUS + pad radius +
    ``radius_offset`` and at z = centre z + ``height``. The wrist keeps rx = ry = 0 and rz = ``yaw``.
    """
    m = session.model
    d = mujoco.MjData(m)
    layout = LAYOUT[session.hand]
    q = np.asarray(seed, dtype=float).copy()
    q[3:5] = 0.0
    q[5] = yaw
    fingers = np.concatenate([np.asarray(layout["act"][f]) for f in FINGERS])
    variable = fingers if fix_wrist else np.r_[0:3, fingers]
    nwrist = 0 if fix_wrist else 3
    lo, hi = m.actuator_ctrlrange[variable].T.copy()
    tips = {f: m.geom(layout["tip"][f]).id for f in FINGERS}
    pad = {f: pad_radius(m, g) for f, g in tips.items()}
    lid_geoms = [m.geom(n).id for n in ("lid_top", "jar_body_collision", "jar_shoulder")]
    lid_geoms += [m.geom(f"lid_skirt_{i}").id for i in range(0, 24, 3)]
    hand_geoms = [g for g in range(m.ngeom) if session.checker.owner[g] == 3 and m.geom_contype[g]
                  and g not in tips.values()]
    targets = {}
    for f, a in angles.items():
        r = LID_RADIUS + pad[f] + radius_offset
        targets[f] = np.array([centre[0] + r * math.cos(a + yaw), centre[1] + r * math.sin(a + yaw),
                               centre[2] + height])
    weights = weights or {}
    seed_values = np.asarray(seed, dtype=float)[variable[nwrist:]]

    def residual(values):
        q[variable] = values
        d.qpos[:] = session.data.qpos
        d.qpos[session.qadr] = q
        mujoco.mj_kinematics(m, d)
        mujoco.mj_comPos(m, d)
        err = []
        for f in FINGERS:
            err.extend((d.geom_xpos[tips[f]] - targets[f]) * 100 * weights.get(f, 1.0))
        for g in hand_geoms if collide else ():
            for o in lid_geoms:
                dist = mujoco.mj_geomDistance(m, d, g, o, 0.01, None)
                err.append(min(0.0, dist - 0.003) * 300)
        err.extend((values[nwrist:] - seed_values) * 0.01)
        return np.asarray(err)

    x0 = np.clip(q[variable], lo + 1e-6, hi - 1e-6)
    fit = least_squares(residual, x0, bounds=(lo, hi), max_nfev=200)
    residual(fit.x)
    tip_err = {f: float(np.linalg.norm(d.geom_xpos[tips[f]] - targets[f])) for f in FINGERS}
    return q.copy(), fit.cost, tip_err
