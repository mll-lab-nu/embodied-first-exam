"""Authoring controller (Sharpa Wave): closed-loop scripted battery swap, recorded as open-loop actuator rows.

The controller reads simulator state only to plan its next motor targets (inverse kinematics of fingertip
positions with collision margins); the recorded rows are plain actuator targets that replay without it.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from runtime import Session

FINGERS = ("thumb", "index", "middle", "ring", "pinky")
# Sharpa actuator index ranges (wrist 0..5).
ACT = {"thumb": list(range(6, 11)), "index": list(range(11, 15)), "middle": list(range(15, 19)),
       "ring": list(range(19, 23)), "pinky": list(range(23, 28))}
CURLED = {"middle": [1.3, 0.0, 1.5, 0.9], "ring": [1.3, 0.0, 1.5, 0.9], "pinky": [0.1, 1.3, 0.0, 1.5, 0.9]}


def hand_rotation(fingers_dir, palm_dir):
    """Wave hand frame: fingers +Z, palm normal +X, thumb +Y."""
    z = np.asarray(fingers_dir, float)
    z /= np.linalg.norm(z)
    x = np.asarray(palm_dir, float)
    x -= z * (x @ z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return np.column_stack([x, y, z])


class Controller:
    tip_axis_sign = 1.0  # +1: the fingertip geom's z axis points out of the fingertip (Sharpa capsules)

    def __init__(self, session: Session, log=print):
        self.s = session
        self.m = session.model
        self.d = session.data
        self.log = log
        m = self.m
        self.scratch = mujoco.MjData(m)
        self.gains = m.actuator_gainprm[:, 0].copy()
        self.lo, self.hi = m.actuator_ctrlrange.T.copy()
        self.target = session.hold_action().copy()
        self.phases = []
        self.tip = self.find_tips()
        self.hand_body = m.body("right_hand_C_MC").id
        own = session.checker.geom_owner
        self.hand_geoms = [g for g in range(m.ngeom) if own[g] == "hand" and m.geom_contype[g]]
        self.obstacle = {}
        for g in range(m.ngeom):
            if own[g] in ("remote", "tray", "old_cell", "new_cell") and (m.geom_contype[g] or m.geom_conaffinity[g]):
                self.obstacle.setdefault(own[g], []).append(g)
        self.obstacle["table"] = [m.geom("table").id]
        # wrist mount: the hand root frame relative to the wrist body frame
        self.mount = np.empty(9)
        mujoco.mju_quat2Mat(self.mount, m.body_quat[self.hand_body])
        self.mount = self.mount.reshape(3, 3)

    def find_tips(self):
        return {f: self.m.geom(f"right_{f}_fingertip_collision").id for f in FINGERS}

    # ------------------------------------------------------------------------------------------ kinematics
    def fk(self, q):
        d = self.scratch
        d.qpos[:] = self.d.qpos
        d.qpos[self.s.qadr] = q
        mujoco.mj_kinematics(self.m, d)
        mujoco.mj_comPos(self.m, d)
        return d

    def wrist_euler_for(self, R_hand):
        R_wrist = R_hand @ self.mount.T
        return Rotation.from_matrix(R_wrist).as_euler("XYZ")

    def solve(self, tips, seed, variable, R_hand=None, rot_weight=0.5, avoid=(), avoid_margin=0.002, allow=(),
              reg=0.01, max_nfev=200, lo_override=None, pad=False, tip_axis=None, axis_weight=2.0):
        """Least-squares IK: ``tips`` = {finger: world point for the fingertip capsule centre}."""
        m = self.m
        q = np.asarray(seed, float).copy()
        variable = np.asarray(variable)
        lo, hi = self.lo[variable].copy(), self.hi[variable].copy()
        if lo_override:
            for k, v in lo_override.items():
                lo[list(variable).index(k)] = v
        initial = q[variable].copy()
        obstacles = [g for name in avoid for g in self.obstacle[name]]
        checked = [g for g in self.hand_geoms if not any(m.geom(g).name.startswith(f"right_{f}_fingertip") for f in allow)]

        def residual(values):
            q[variable] = values
            d = self.fk(q)
            errors = []
            for finger, point in tips.items():
                errors.extend((self.tip_point(d, finger, pad) - point) * 100)
            for finger, axis in (tip_axis or {}).items():
                g = self.tip[finger]
                errors.extend((self.tip_axis_sign * d.geom_xmat[g].reshape(3, 3)[:, 2] - axis) * axis_weight)
            if R_hand is not None:
                R = d.xmat[self.hand_body].reshape(3, 3)
                errors.extend((R - R_hand).ravel() * rot_weight)
            for gid in checked:
                for ob in obstacles:
                    dist = mujoco.mj_geomDistance(m, d, gid, ob, 0.02, None)
                    errors.append(min(0.0, dist - avoid_margin) * 300)
            errors.extend((values - initial) * reg)
            return np.asarray(errors)

        x0 = np.clip(initial, lo + 1e-6, hi - 1e-6)
        fit = least_squares(residual, x0, bounds=(lo + 1e-9, hi - 1e-9), max_nfev=max_nfev)
        q[variable] = fit.x
        d = self.fk(q)
        err = {f: float(np.linalg.norm(self.tip_point(d, f, pad) - p)) for f, p in tips.items()}
        return q, err, fit.cost

    def tip_point(self, d, finger, pad):
        """Capsule centre, or (pad=True) the centre of its distal hemisphere (the fingertip pad)."""
        g = self.tip[finger]
        if not pad:
            return d.geom_xpos[g]
        return d.geom_xpos[g] + self.m.geom_size[g, 1] * d.geom_xmat[g].reshape(3, 3)[:, 2]

    # ------------------------------------------------------------------------------------------ execution
    default_boost = 2.0
    release_slice = slice(6, 15)  # thumb + index actuators (Sharpa)

    def execute(self, target, count, phase, boost=None):
        boost = self.default_boost if boost is None else boost
        s = self.s
        start = self.target.copy()
        target = np.asarray(target, float)
        for ratio in np.linspace(0, 1, count + 1)[1:]:
            if s.done:
                break
            blend = ratio * ratio * (3 - 2 * ratio)
            self.target = start + (target - start) * blend
            action = self.target + self.d.qfrc_bias[s.dofs] / self.gains
            action[6:] += boost * (self.target[6:] - self.d.qpos[s.qadr[6:]])
            # stay 1e-5 inside the native bounds so float32-rounded rows stay valid
            action = np.clip(action, self.lo + 1e-5, self.hi - 1e-5)
            s.step(action)
            self.phases.append(phase)
        f = s.features()
        self.log(f"[{s.steps:5d}] {phase:32s} stage={f['stage']} cover={f['cover_slide_m']:.4f} "
                 f"hand={f['hand_contacts']} fail={f['failure']} remote_disp={f['remote_displacement_m']:.4f}")
        return f

    def hold(self, count, phase, boost=None):
        return self.execute(self.target.copy(), count, phase, boost)

    def body_pos(self, name):
        return self.d.xpos[self.m.body(name).id].copy()

    def body_axis(self, name, k=2):
        return self.d.xmat[self.m.body(name).id].reshape(3, 3)[:, k].copy()


# ---------------------------------------------------------------------------------------------- task phases
R_DOWN_X = hand_rotation((1, 0, 0), (0, 0, -1))  # palm down, fingers along +x, thumb toward +y
TIP_R = 0.008


def base_seed(c, R):
    seed = c.target.copy()
    seed[3:6] = c.wrist_euler_for(R)
    seed[ACT["thumb"]] = [0.3, 0.0, 0.3, 0.0, 0.5]
    seed[ACT["index"]] = [1.2, 0.0, 1.0, 0.6]
    for f, v in CURLED.items():
        seed[ACT[f]] = v
    return seed


def phase_open_cover(c):
    s = c.s
    R = R_DOWN_X
    seed = base_seed(c, R)
    remote = c.body_pos("remote")
    ridge = remote + np.array([-0.025 + s.config["cover_ridge_local_x"], 0, 0.014 + 0.0035])
    cover_top = remote[2] + 0.016
    pre = np.array([ridge[0] + 0.0015 + TIP_R + 0.003, remote[1], cover_top + TIP_R + 0.012])
    q_pre, err, _ = c.solve({"index": pre}, seed, list(range(6)) + ACT["index"], R_hand=R, avoid=("remote",),
                            allow=("index",))
    down = pre.copy()
    down[0] = ridge[0] + 0.0015 + TIP_R + 0.0005
    down[2] = cover_top + TIP_R - 0.0015
    q_down, err, _ = c.solve({"index": down}, q_pre, list(range(6)) + ACT["index"], R_hand=R, allow=("index",))
    above = q_pre.copy()
    above[2] += 0.10
    c.execute(above, 60, "approach above the door")
    c.execute(q_pre, 50, "finger behind the door ridge")
    c.execute(q_down, 40, "press on the door")
    push = q_down.copy()
    push[0] -= 0.080
    c.execute(push, 150, "slide the door open")
    c.hold(15, "door open")
    lift = push.copy()
    lift[2] += 0.06
    c.execute(lift, 40, "lift off the door")
    return lift


def pinch_targets(center, across, clearance, dz, pad=False):
    """Thumb on the +across side, index on the -across side of a cell centre."""
    across = np.asarray(across, float)
    up = np.array([0, 0, dz])
    if pad:
        return {"thumb": center + (0.007 + 0.00943 + clearance) * across + up,
                "index": center - (0.007 + 0.00806 + clearance) * across + up}
    off = (0.007 + TIP_R + clearance) * across
    return {"thumb": center + off + up, "index": center - off + up}


def pad_pinch(c, name, yaw, dz, open_clear, squeeze, tilt, avoid, seed):
    """Thumb/index pad pinch across a lying cell: open and closed postures (IK, collision margins)."""
    var = list(range(6)) + ACT["thumb"] + ACT["index"]
    cell = c.body_pos(name)
    R = yaw_rotation(yaw)
    across = R[:, 1]
    down = np.array([0, 0, -1.0])
    # fingertip capsules nearly vertical, tilted slightly toward the cell: pads meet it just above its equator
    axes = {"thumb": down * np.cos(tilt) - across * np.sin(tilt), "index": down * np.cos(tilt) + across * np.sin(tilt)}
    seed = seed.copy()
    seed[3:6] = c.wrist_euler_for(R)
    q_open, e1, _ = c.solve(pinch_targets(cell, across, open_clear, dz, pad=True), seed, var, R_hand=R,
                            rot_weight=0.1, avoid=tuple(avoid) + (name,), avoid_margin=0.0008, pad=True, tip_axis=axes)
    q_close, e2, _ = c.solve(pinch_targets(cell, across, squeeze, dz, pad=True), q_open, var, R_hand=R,
                             rot_weight=0.1, avoid=tuple(avoid), avoid_margin=0.0003, allow=("thumb", "index"),
                             pad=True, tip_axis=axes)
    c.log(f"{name} pinch ik open={e1} close={e2}")
    return q_open, q_close


def phase_old_to_tray(c, start, release_clearance=0.004):
    s = c.s
    remote_yaw = float(np.arctan2(c.d.xmat[c.m.body("remote").id][3], c.d.xmat[c.m.body("remote").id][0]))
    q_open, q_close = pad_pinch(c, "old_cell", remote_yaw, 0.0025, 0.004, -0.004, 0.12, ("remote",), start)
    above = q_open.copy()
    above[2] += 0.06
    c.execute(above, 50, "over the old cell")
    c.execute(q_open, 60, "fingers beside the old cell")
    c.execute(q_close, 40, "pinch the old cell")
    c.hold(30, "stabilize the pinch")
    up = q_close.copy()
    up[2] += 0.07
    c.execute(up, 60, "lift the old cell")
    tray = c.body_pos("tray")
    floor_top = tray[2] + 0.003
    carry = up.copy()
    carry[:2] += tray[:2] - c.body_pos("old_cell")[:2]
    c.execute(carry, 110, "carry to the tray")
    c.hold(20, "settle over the tray")
    carry[:2] += tray[:2] - c.body_pos("old_cell")[:2]
    carry[2] += (floor_top + 0.007 + release_clearance) - c.body_pos("old_cell")[2]
    c.execute(carry, 70, "lower into the tray")
    c.hold(20, "settle in the tray")
    release = carry.copy()
    release[6:15] = q_open[6:15]
    c.execute(release, 40, "open the pinch")
    c.hold(30, "let the old cell rest")
    away = release.copy()
    away[2] += 0.08
    c.execute(away, 50, "withdraw from the tray")
    return away


def yaw_rotation(yaw):
    return hand_rotation((np.cos(yaw), np.sin(yaw), 0), (0, 0, -1))


def rotate_about(c, q, center, delta):
    """Wrist targets that turn the whole hand by ``delta`` (rad) about a vertical axis through ``center``."""
    q = q.copy()
    Rz = Rotation.from_euler("z", delta).as_matrix()
    q[:3] = center + Rz @ (q[:3] - center)
    Rw = Rotation.from_euler("XYZ", q[3:6]).as_matrix()
    e = Rotation.from_matrix(Rz @ Rw).as_euler("XYZ")
    q[3:6] = q[3:6] + np.angle(np.exp(1j * (e - q[3:6])))
    return q


def cell_yaw(c, name):
    axis = c.body_axis(name)
    return float(np.arctan2(axis[1], axis[0]))


def phase_new_pick(c, start, dz=0.003, squeeze=-0.003, tilt=0.3):
    yaw = cell_yaw(c, "new_cell")
    q_open, q_close = pad_pinch(c, "new_cell", yaw, dz, 0.006, squeeze, tilt, ("table",), start)
    above = q_open.copy()
    above[2] += 0.07
    c.execute(above, 90, "over the new cell")
    c.execute(q_open, 60, "fingers beside the new cell")
    c.execute(q_close, 40, "pinch the new cell")
    c.hold(30, "stabilize the pinch")
    up = q_close.copy()
    up[2] += 0.07
    c.execute(up, 60, "lift the new cell")
    return up, q_open


def phase_new_seat(c, up, q_open, yaw_steps=120, carry_steps=(60, 25, 25), lower=((0.012, 50), (0.0, 50))):
    s = c.s
    remote = c.body_pos("remote")
    Rr = c.d.xmat[c.m.body("remote").id].reshape(3, 3)
    slot = remote + Rr @ np.asarray(s.config["slot_center_local"])
    # rotate the wrist yaw so the cell's + end points along the remote's +x
    yaw_err = np.arctan2(Rr[1, 0], Rr[0, 0]) - cell_yaw(c, "new_cell")
    carry = rotate_about(c, up, c.body_pos("new_cell"), yaw_err)
    c.execute(carry, yaw_steps, "turn the cell: + end to the gold contact")
    for steps in carry_steps:
        cell = c.body_pos("new_cell")
        carry[:2] += slot[:2] - cell[:2]
        c.execute(carry, steps, "carry over the slot")
        yaw_err = np.arctan2(Rr[1, 0], Rr[0, 0]) - cell_yaw(c, "new_cell")
        carry = rotate_about(c, carry, c.body_pos("new_cell"), yaw_err)
    for offset, steps in lower:
        cell = c.body_pos("new_cell")
        carry[2] += (slot[2] + offset) - cell[2]
        c.execute(carry, steps, "lower into the slot")
    c.hold(20, "settle in the slot")
    release = carry.copy()
    release[c.release_slice] = q_open[c.release_slice]
    c.execute(release, 40, "release the new cell")
    c.hold(30, "let the new cell seat")
    away = release.copy()
    away[2] += 0.07
    c.execute(away, 50, "withdraw from the slot")
    return away


def phase_close_cover(c, start, overshoot=0.004):
    s = c.s
    R = R_DOWN_X
    seed = base_seed(c, R)
    seed[:3] = start[:3]
    remote = c.body_pos("remote")
    opened = float(c.d.qpos[s.checker.cover_qadr])
    ridge = remote + np.array([-0.025 - opened + s.config["cover_ridge_local_x"], 0, 0.014 + 0.0035])
    cover_top = remote[2] + 0.016
    pre = np.array([ridge[0] - 0.0015 - TIP_R - 0.004, remote[1], cover_top + TIP_R + 0.012])
    q_pre, _, _ = c.solve({"index": pre}, seed, list(range(6)) + ACT["index"], R_hand=R, avoid=("remote",),
                          allow=("index",))
    down = pre.copy()
    down[0] = ridge[0] - 0.0015 - TIP_R - 0.0005
    down[2] = cover_top + TIP_R - 0.0015
    q_down, _, _ = c.solve({"index": down}, q_pre, list(range(6)) + ACT["index"], R_hand=R, allow=("index",))
    above = q_pre.copy()
    above[2] += 0.08
    c.execute(above, 80, "move behind the open door")
    c.execute(q_pre, 50, "finger behind the door ridge")
    c.execute(q_down, 40, "press on the door")
    push = q_down.copy()
    push[0] += opened + overshoot
    c.execute(push, 150, "slide the door shut")
    c.hold(15, "door closed")
    lift = push.copy()
    lift[2] += 0.05
    c.execute(lift, 40, "lift off the door")
    away = lift.copy()
    away[0] -= 0.10
    away[2] += 0.06
    c.execute(away, 60, "hand clear of the remote")
    return away


def make_demo(output, slack_rows=150, log=print, seat_kw=None, tray_kw=None):
    """Run the scripted controller from the frozen reset and save the executed rows plus hold rows."""
    s = Session()
    c = Controller(s, log=log)
    t0 = time.time()
    c.hold(25, "settle")
    q = phase_open_cover(c)
    q = phase_old_to_tray(c, q, **(tray_kw or {}))
    up, q_open = phase_new_pick(c, q)
    q = phase_new_seat(c, up, q_open, **(seat_kw or {}))
    q = phase_close_cover(c, q)
    c.hold(120, "released hold")
    status = s.status()
    actions = np.asarray(s.actions)
    success_step = s.steps if s.success else None
    # Slack: the episode ends at success; extra hold rows keep the hand still if a replay succeeds later.
    rows = np.concatenate([actions, np.repeat(actions[-1:], slack_rows, axis=0)]) if len(actions) else actions
    phases = np.asarray(c.phases + ["hold (slack)"] * slack_rows)[: len(rows)]
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    s.save_trajectory(rows, out)
    np.savez_compressed(out.with_suffix(".phases.npz"), phases=phases)
    summary = {
        "success": bool(s.success), "success_step": success_step, "rows": int(len(rows)),
        "executed_rows": int(len(actions)), "reason": status["reason"], "stage_steps": status.get("stage_steps"),
        "final_sha": s.state_sha(), "seconds": round(time.time() - t0, 1),
    }
    out.with_suffix(".live.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    log(json.dumps(summary, default=str))
    s.close()
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--slack-rows", type=int, default=150)
    args = parser.parse_args()
    make_demo(args.out, args.slack_rows)
