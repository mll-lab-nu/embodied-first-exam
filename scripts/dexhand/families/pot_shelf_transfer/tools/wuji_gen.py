"""wuji_gen.py: closed-loop scripted Wuji Hand 2.2 controller for pot_shelf_transfer; writes the trajectory deliverable.

Structure follows the accepted Sharpa authoring controller (scripts/scene_expansion/tasks/pot_transfer/run.py,
trial-14 options --approach --strong --level, height 0.135, grip_y 0.202): IK on the wrist wrapper body of each
arm, arm targets plus the model's own gravity/Coriolis bias divided by the servo stiffness, the same phase schedule.
Changes for the Wuji Hand 2.2: a grip-point offset in the wrapper frame, a Wuji finger posture (20 targets per hand),
optional extra phases/timings. The controller only reads Session state (allowed in privileged mode) and writes rows
through Session.step, so the recorded rows replay bit for bit in a fresh Session.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from runtime import Session

DT = 0.002
START = np.array([0.52, -0.05, 0.75])
TARGET = np.array([0.46, 0.31, 0.79])
# Sharpa power-grip calibration (scripts/everyday_dexterity/powergrip.json), wrapper frame of the right hand.
TOOL_P = np.array([0.03323298479231314, -0.0021769027068166973, 0.07117869474456741])
TOOL_Q = np.array([0.7086256240317594, -0.6630007317696909, -0.1763726612314715, -0.16484064731910886])  # wxyz
SIDES = ("l", "r")

DEFAULT = dict(
    hand="wuji",
    spin=float(np.pi / 2),
    height=0.135,
    grip_y=0.202,
    grip_offset=[0.0, 0.0, 0.0],      # extra grip-point offset in the right wrapper frame (mirrored for the left)
    rot_offset=[0.0, 0.0, 0.0],       # extra rotation (rotvec, right wrapper frame; mirrored for the left)
    # Wuji per-hand finger posture: TH0..3, FF0..3, MF0..3, RF0..3, LF0..3 (applied as close * posture)
    posture=[0.8, -0.5, 0.8, 0.8] + [1.4, 0.0, 1.4, 1.2] * 4,
    approach_close=0.4,
    approach_retreat=0.06,
    mid_retreat=0.03,
    lift_dz=0.08,
    carry_dz=0.04,
    times=dict(settle=0.6, approach=1.2, close=1.5, dwell=0.6, lift=1.5, level=2.0, hold=1.0, carry=3.0,
               lower=1.5, settle2=0.8, open=1.2, withdraw=1.5, dwell2=1.3),
    open_retreat=0.06,
    withdraw_retreat=0.09,
    open_dx=-0.6,     # x motion per unit retreat during release (run.py: p[0] -= 0.6 * ret)
    open_dz=0.1,
    lower_target_dz=0.0,
    target_shift=[0.0, 0.0],
    level=True,
    ik_every=10,
    ik_iters=45,
)


def tool_rot():
    return Rotation.from_quat(np.roll(TOOL_Q, -1)).as_matrix()


class Controller:
    def __init__(self, params: dict, session: Session | None = None):
        self.p = {**DEFAULT, **params}
        self.p["times"] = {**DEFAULT["times"], **params.get("times", {})}
        self.s = session or Session("pot_shelf_transfer", hand=self.p["hand"])
        s = self.s
        m = s.model
        self.m = m
        self.scratch = mujoco.MjData(m)
        self.arm_act = np.arange(14)
        self.arm_jnt = m.actuator_trnid[:14, 0]
        self.arm_qadr = m.jnt_qposadr[self.arm_jnt]
        self.arm_dof = m.jnt_dofadr[self.arm_jnt]
        self.hand_body = {x: m.body(f"{x}_hand_palm").id for x in SIDES}
        self.nf = (s.action_dim - 14) // 2
        self.lo, self.hi = s.actuator_ranges.T

    # ------------------------------------------------------------------ kinematics
    def palm_pose(self, side, foot, grip_extra=None):
        p = TOOL_P.copy() + np.asarray(self.p["grip_offset"])
        r = tool_rot()
        r = Rotation.from_rotvec(self.p["rot_offset"]).as_matrix() @ r
        if side == "l":
            S = np.diag([1.0, -1.0, 1.0])
            p = S @ p
            r = S @ r @ S
        spin = self.p["spin"] if side == "r" else -self.p["spin"]
        axis = Rotation.from_euler("z", spin).as_matrix()
        palm = axis @ r.T
        grip = np.array(foot) + [0, (1 if side == "l" else -1) * self.p["grip_y"], self.p["height"]]
        return grip - palm @ p, palm

    def ik(self, side, pos, rot, initial, iterations):
        m, d = self.m, self.scratch
        d.qpos[:] = self.s.data.qpos
        idx = slice(0, 7) if side == "l" else slice(7, 14)
        qa, do, jid = self.arm_qadr[idx], self.arm_dof[idx], self.arm_jnt[idx]
        d.qpos[qa] = initial
        bounds = m.jnt_range[jid]
        jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        body = self.hand_body[side]
        error = np.zeros(6)
        for _ in range(iterations):
            mujoco.mj_kinematics(m, d)
            mujoco.mj_comPos(m, d)
            error = np.r_[pos - d.xpos[body],
                          0.20 * Rotation.from_matrix(rot @ d.xmat[body].reshape(3, 3).T).as_rotvec()]
            if np.linalg.norm(error) < 1e-5:
                break
            mujoco.mj_jacBody(m, d, jp, jr, body)
            J = np.vstack([jp[:, do], 0.20 * jr[:, do]])
            change = J.T @ np.linalg.solve(J @ J.T + 0.00005 * np.eye(6), error)
            d.qpos[qa] = np.clip(d.qpos[qa] + np.clip(change, -0.12, 0.12), bounds[:, 0] + 0.015, bounds[:, 1] - 0.015)
        return d.qpos[qa].copy(), float(np.linalg.norm(error))

    def row(self, arm_target, fingers):
        d = self.s.data
        out = np.zeros(self.s.action_dim)
        out[:14] = np.clip(arm_target + d.qfrc_bias[self.arm_dof] / 700, self.lo[:14], self.hi[:14])
        out[14:14 + self.nf] = fingers["l"]
        out[14 + self.nf:] = fingers["r"]
        return np.clip(out, self.lo, self.hi)

    # ------------------------------------------------------------------ episode
    def plan(self):
        p, t = self.p, self.p["times"]
        seg = []
        tgt = TARGET + np.r_[p["target_shift"], 0.0]

        def add(name, key, foot, finger, retreat):
            if t[key] > 0:
                seg.append(dict(phase=name, n=round(t[key] / DT), foot=np.array(foot, float), finger=finger,
                                retreat=retreat))

        add("settle", "settle", START, 0, p["approach_retreat"])
        add("approach", "approach", START, p["approach_close"], p["mid_retreat"])
        add("close", "close", START, 1, 0.0)
        add("dwell", "dwell", START, 1, 0.0)
        add("lift", "lift", START + [0, 0, p["lift_dz"]], 1, 0.0)
        if p["level"]:
            add("level", "level", START + [0, 0, p["lift_dz"]], 1, 0.0)
        add("hold", "hold", START + [0, 0, p["lift_dz"]], 1, 0.0)
        add("carry", "carry", tgt + [0, 0, p["carry_dz"]], 1, 0.0)
        add("lower", "lower", tgt + [0, 0, p["lower_target_dz"]], 1, 0.0)
        add("settle2", "settle2", tgt + [0, 0, p["lower_target_dz"]], 1, 0.0)
        add("open", "open", tgt + [0, 0, p["lower_target_dz"]], 0, p["open_retreat"])
        add("withdraw", "withdraw", tgt + [0, 0, p["lower_target_dz"]], 0, p["withdraw_retreat"])
        add("dwell2", "dwell2", tgt + [0, 0, p["lower_target_dz"]], 0, p["withdraw_retreat"])
        return seg

    def run(self, stop_phase: str | None = None, verbose=False, snap_at: str | None = None):
        s, m = self.s, self.m
        d = s.data
        s.reset()
        posture = np.asarray(self.p["posture"], float)
        q0 = d.qpos[self.arm_qadr].copy()
        arm_target = q0.copy()
        prev, prevf, prevr = START.copy(), 0.0, self.p["approach_retreat"]
        grip_frames = None
        held_position = planned = level_rot = None
        log = []
        release = ("open", "withdraw", "dwell2")
        self.snapshots = {}
        for cmd in self.plan():
            name, n = cmd["phase"], cmd["n"]
            if name == stop_phase:
                break
            if snap_at == name:
                self.snapshots[name] = (s.snapshot(), arm_target.copy(), prev.copy(), prevf, prevr)
            if name == "level" or (name == "hold" and grip_frames is None and not self.p["level"]):
                held_position = d.xpos[s.pot_body].copy()
                planned = held_position.copy()
                level_rot = d.xmat[s.pot_body].reshape(3, 3).copy()
                grip_frames = {x: (level_rot.T @ (d.xpos[self.hand_body[x]] - held_position),
                                   level_rot.T @ d.xmat[self.hand_body[x]].reshape(3, 3)) for x in SIDES}
            seg_start = planned.copy() if planned is not None else None
            for j in range(n):
                tt = (j + 1) / n
                blend = tt * tt * (3 - 2 * tt)
                foot = prev + blend * (cmd["foot"] - prev)
                close = prevf + blend * (cmd["finger"] - prevf)
                ret = prevr + blend * (cmd["retreat"] - prevr)
                if j % self.p["ik_every"] == 0:
                    for x in SIDES:
                        if grip_frames is None:
                            pos, rot = self.palm_pose(x, foot)
                        else:
                            if name == "level":
                                dpos = held_position
                                drot = level_rot @ Rotation.from_rotvec(
                                    blend * Rotation.from_matrix(level_rot.T).as_rotvec()).as_matrix()
                            elif name == "hold":
                                dpos, drot = held_position, np.eye(3) if self.p["level"] else level_rot
                            else:
                                dpos = seg_start + blend * (cmd["foot"] - seg_start)
                                drot = np.eye(3) if self.p["level"] else level_rot
                            rp, rr = grip_frames[x]
                            pos = dpos + drot @ rp
                            rot = drot @ rr
                        pos = pos.copy()
                        if name in release:
                            pos[1] += (1 if x == "l" else -1) * ret
                            pos[0] += self.p["open_dx"] * ret
                            pos[2] += self.p["open_dz"] * ret
                        else:
                            pos[1] += (1 if x == "l" else -1) * ret
                        idx = slice(0, 7) if x == "l" else slice(7, 14)
                        arm_target[idx], err = self.ik(x, pos, rot, arm_target[idx], self.p["ik_iters"])
                fingers = {x: close * posture for x in SIDES}
                st = s.step(self.row(arm_target, fingers))
                if st["done"]:
                    break
            prev, prevf, prevr = cmd["foot"], cmd["finger"], cmd["retreat"]
            if grip_frames is not None and name not in ("level", "hold"):
                planned = cmd["foot"].copy()
            f = s.features()
            entry = dict(phase=name, steps=st["steps"], reason=st["reason"], lift_s=st["lift_s"], hold_s=st["hold_s"],
                         pot=np.round(f["pot_position_m"], 4).tolist(), tilt=round(f["pot_tilt_rad"], 4),
                         load=f["hand_up_load_n"], contacts=f["hand_contacts"], support=f["support"],
                         unmet=f["terminal_unmet"], peak=f["peak"])
            log.append(entry)
            if verbose:
                print(json.dumps(entry), flush=True)
            if st["done"]:
                break
        return s.status(), log


def main():
    """Author the Wuji episode with the default parameters above and save /app/output/trajectory.npz (or argv[1])."""
    out = sys.argv[1] if len(sys.argv) > 1 else "/app/output/trajectory.npz"
    c = Controller({"hand": "wuji"})
    status, log = c.run(verbose=True)
    print(json.dumps(status))
    if not status["success"]:
        raise SystemExit("episode did not succeed")
    c.s.save_trajectory(None, out)
    print("saved", out, len(c.s.actions), "rows")


if __name__ == "__main__":
    main()
