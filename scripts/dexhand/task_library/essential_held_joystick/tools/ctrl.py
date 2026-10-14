"""Wuji Hand 2.2 closed-loop authoring controller for essential_held_joystick (authoring only).

Only the 26 actuator targets of the selected hand go to the simulator (wrist targets locked). The thumb pad is placed
on the joystick's flat cap (kinematic IK in a separate MjData) and dragged tangentially by an integral controller on
the measured gimbal angles; the other fingers keep their neutral targets (the controller rests on the hand).
"""
from __future__ import annotations

import argparse, json, math, sys, time
from pathlib import Path

import mujoco
import numpy as np
from scipy.optimize import least_squares

from rcb_dexhand import Session

TH = slice(6, 10)  # thumb actuator columns in the 26-wide Wuji row


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


class ThumbIK:
    def __init__(self, s, nominal):
        self.s, self.m = s, s.model
        self.d = mujoco.MjData(self.m)
        self.qa = s._act_qpos[TH]
        self.jid = s._act_jids[TH]
        self.lo, self.hi = self.m.actuator_ctrlrange[TH].T
        self.tip = self.m.geom("right_thumb_fingertip_collision").id
        self.knob = self.m.geom("task_joystick_knob").id
        self.body = self.m.geom_bodyid[self.tip]
        self.kp = self.m.actuator_gainprm[TH, 0]
        # pad point: closest point of the thumb tip to the knob in the nominal configuration, in the tip body frame
        self.d.qpos[:] = s.data.qpos
        self.d.qpos[self.qa] = nominal
        mujoco.mj_kinematics(self.m, self.d)
        ft = np.zeros(6)
        mujoco.mj_geomDistance(self.m, self.d, self.tip, self.knob, 0.05, ft)
        R = self.d.xmat[self.body].reshape(3, 3)
        self.pad_local = R.T @ (ft[:3] - self.d.xpos[self.body])
        self.q = np.array(nominal, float)

    def pad(self, d=None):
        d = d or self.d
        return d.xpos[self.body] + d.xmat[self.body].reshape(3, 3) @ self.pad_local

    def solve(self, target, q0=None):
        q0 = self.q if q0 is None else q0
        self.d.qpos[:] = self.s.data.qpos

        def res(q):
            self.d.qpos[self.qa] = q
            mujoco.mj_kinematics(self.m, self.d)
            return np.r_[1000 * (self.pad() - target), 0.3 * (q - q0)]

        r = least_squares(res, np.clip(q0, self.lo + 1e-6, self.hi - 1e-6), bounds=(self.lo, self.hi), max_nfev=50,
                          xtol=1e-8, ftol=1e-8)
        self.q = r.x
        return r.x, float(np.linalg.norm(res(r.x)[:3]) / 1000)

    def gravity_ff(self, q):
        """Feedforward so the weak position servos reach q against gravity (bias forces at q)."""
        self.d.qpos[:] = self.s.data.qpos
        self.d.qpos[self.qa] = q
        self.d.qvel[:] = 0
        mujoco.mj_forward(self.m, self.d)
        dofs = self.m.jnt_dofadr[self.jid]
        return self.d.qfrc_bias[dofs] / self.kp


def knob_geometry(s, top_world):
    """Return the cap-top point in the stick frame (angles 0) for a measured world top point."""
    d = s.data
    p = d.body("task_joystick_stick").xpos
    R = d.body("task_joystick_stick").xmat.reshape(3, 3)
    return R.T @ (top_world - p)


def cap_point(s, top_local, ax, ay):
    d = s.data
    piv = d.body("task_joystick_gimbal").xpos
    Ro = d.body("object").xmat.reshape(3, 3)
    Rl = rot_y(ax) @ rot_x(-ay)
    return piv + Ro @ Rl @ top_local, Ro @ Rl[:, 2], Ro


STAGES = [(-0.3, 0.0), (0.0, 0.3), (0.3, 0.0), (0.0, -0.3), (0.0, 0.0)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs/r1")
    ap.add_argument("--press", type=float, default=0.0015)
    ap.add_argument("--ki", type=float, default=0.02)
    ap.add_argument("--kp", type=float, default=1.0)
    ap.add_argument("--ff", type=float, default=1.0)
    ap.add_argument("--approach", type=int, default=60)
    ap.add_argument("--max", type=int, default=1500)
    ap.add_argument("--nominal", default="0.39,-0.1,1.09,1.33")
    ap.add_argument("--rate", type=float, default=0.006)
    ap.add_argument("--umax", type=float, default=0.15)
    ap.add_argument("--kin", type=float, default=0.1)
    ap.add_argument("--vmax", type=float, default=0.006)
    ap.add_argument("--curl", default="", help="col=value,... finger targets ramped in during the approach")
    ap.add_argument("--target", type=float, default=0.3)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    s = Session("essential_held_joystick", hand="wuji")
    base = s.hold_action().copy()
    curl = {}
    for item in filter(None, a.curl.split(",")):
        k_, v_ = item.split("=")
        curl[s.actuator_names.index("r_wuji_r_" + k_)] = float(v_)
    nominal = np.array([float(v) for v in a.nominal.split(",")])
    ik = ThumbIK(s, nominal)
    # measured knob top at reset (from the nominal pad contact)
    d2 = mujoco.MjData(s.model); d2.qpos[:] = s.data.qpos; d2.qpos[ik.qa] = nominal; mujoco.mj_kinematics(s.model, d2)
    ft = np.zeros(6); mujoco.mj_geomDistance(s.model, d2, ik.tip, ik.knob, 0.05, ft)
    top_local = knob_geometry(s, ft[3:])
    print("top_local", top_local)
    actions, log = [], []
    u = np.zeros(2)  # integral tangential offset (object-frame x, y), metres
    q_prev = np.zeros(4)
    cmd = np.zeros(2)
    v = np.zeros(3)
    for t in range(a.max):
        f = s.features()
        st = s.status()
        if st["done"]:
            break
        k = min(st["stage_index"], 4)
        tx, ty = (np.array(STAGES[k]) * a.target / 0.3)
        jx, jy = f["joystick_x"], f["joystick_y"]
        top, axis, Ro = cap_point(s, top_local, 0.0, 0.0)
        if t < a.approach:
            # approach above the cap, then descend
            alpha = min(1.0, (t + 1) / (0.6 * a.approach))
            lift = 0.012 * (1 - min(1.0, max(0.0, (t - 0.6 * a.approach) / (0.4 * a.approach))))
            q, err = ik.solve(top + axis * (lift - a.press * min(1, t / a.approach)))
            q = alpha * q + (1 - alpha) * q_prev if t == 0 else q
            q_cmd = q
            if t < 0.6 * a.approach:
                q_cmd = alpha * q
        else:
            goal = np.array([tx, ty])
            cmd = cmd + np.clip(goal - cmd, -a.rate, a.rate)
            e = np.array([cmd[0] - jx, cmd[1] - jy])
            # outer loop: angle integral shifts the commanded cap angle (slip / spring compensation)
            u += a.ki * e
            u = np.clip(u, -a.umax, a.umax)
            eff = cmd + a.kp * e + u
            top_d, axis_d, Ro = cap_point(s, top_local, eff[0], eff[1])
            # inner loop: servo the measured pad tangentially onto the desired cap point
            pad = ik.pad(s.data)
            err_w = top_d - pad
            err_o = Ro.T @ err_w
            v += a.kin * np.array([err_o[0], err_o[1], 0.0])
            v = np.clip(v, -a.vmax, a.vmax)
            q, err = ik.solve(top_d + Ro @ v - axis_d * a.press)
            q_cmd = q
        row = base.copy()
        for c_, v_ in curl.items():
            row[c_] = base[c_] + min(1.0, (t + 1) / max(1, a.approach)) * (v_ - base[c_])
        row[TH] = np.clip(q_cmd + a.ff * ik.gravity_ff(q_cmd), ik.lo, ik.hi)
        st = s.step(row)
        actions.append(row)
        f = s.features()
        kn = 0.0
        for ci in range(s.data.ncon):
            c = s.data.contact[ci]
            if {int(c.geom1), int(c.geom2)} & {ik.knob, s.model.geom("task_joystick_stem").id}:
                fc = np.zeros(6); mujoco.mj_contactForce(s.model, s.data, ci, fc); kn += fc[0]
        log.append(dict(kn=kn, t=t, stage=st["stage_index"], jx=f["joystick_x"], jy=f["joystick_y"], base=f["base_contacts"],
                        mech=f["mechanism_contacts"], drift=f["body_drift"], rot=f["body_rotation"], u=u.tolist(), v=v.tolist(),
                        reason=st["reason"], failure=st["failure"]))
        if t % 20 == 0 or st["done"]:
            print(t, "stage", st["stage_index"], "hold", st["stage_hold"], "kn %.3f jx %.3f jy %.3f base %d mech %d drift %.4f rot %.3f u %s v %s ik %.4f" % (kn,
                f["joystick_x"], f["joystick_y"], f["base_contacts"], f["mechanism_contacts"], f["body_drift"], f["body_rotation"], np.round(u, 3), np.round(v*1000, 2), err), st["failure"] or "", flush=True)
    st = s.status()
    print("final", st)
    np.save(out / "actions.npy", np.array(actions))
    s.save_trajectory(np.array(actions), out / "trajectory.npz")
    (out / "log.json").write_text(json.dumps(dict(status=st, args=vars(a), log=log), default=float))


if __name__ == "__main__":
    main()
