"""Authoring only (wave-3 realism experiment): the turner starts resting on the counter at the source's rest pose and
the right Marvin arm picks it up (palm-down grasp of the handle), then serves with the turner-pose servo (demo_arm).

    python tools/pickup_arm.py make-reset --hand sharpa [--write]
    python tools/pickup_arm.py author --out solution/trajectory.npz [--params '{...}']
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
for _parent in HERE.parents:
    if (_parent / "shared/arm_ik.py").is_file():
        sys.path.append(str(_parent / "shared"))
        break

import mujoco  # noqa: E402

import arm_ik  # noqa: E402
import arm_rig  # noqa: E402
import demo  # noqa: E402
import demo_arm  # noqa: E402
from runtime import Session  # noqa: E402

REST = [0.76, -0.30, 0.878, 0.9895, 0.1443, 0.0, 0.0]  # T16 source: turner at rest on the counter (pos, quat wxyz)
GRIP_IN_HAND = np.array([0.0421, 0.0, 0.0669])
GRASP = [1.8683, 0.0354, 1.2223, 0.349, 1.5388, 0.6632, 0, 1.1508, 0.7582, 0.6632, 0, 1.1508, 0.7582,
         0.6632, 0, 1.1508, 0.7582, 0.1, 0.6632, 0, 1.1508, 0.7582]


def frame(palm, index):
    g = np.asarray(index, float)
    g = g / np.linalg.norm(g)
    b = np.asarray(palm, float)
    b = b - (b @ g) * g
    b = b / np.linalg.norm(b)
    return np.c_[b, g, np.cross(b, g)]


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * x * (10 + x * (-15 + 6 * x))


def make_reset(hand, write, settle=1.5):
    s = Session(hand=hand)
    m, d = s.model, s.data
    lay = arm_rig.layout(m)
    qa = m.joint("turner_free").qposadr[0]
    d.qpos[qa:qa + 7] = REST
    d.qpos[qa + 3:qa + 7] /= np.linalg.norm(d.qpos[qa + 3:qa + 7])
    for j in range(3):
        d.qpos[m.joint(f"turner_bend_{j}").qposadr[0]] = 0.0
    fr = lay["fingers"]["right"]
    lo, hi = m.actuator_ctrlrange.T
    row = s.initial_targets.copy()
    row[fr] = np.clip(0.0, lo[fr], hi[fr])
    for i in range(fr.start, fr.stop):
        d.qpos[m.jnt_qposadr[m.actuator_trnid[i, 0]]] = row[i]
    d.qvel[:] = 0
    mujoco.mj_forward(m, d)
    ik = arm_ik.ArmIK(m, "right", body="wrist_stage")
    mount = m.body("wrist_stage").id
    pos, R = d.xpos[mount].copy(), d.xmat[mount].reshape(3, 3).copy()
    sl = lay["arm"]["right"]
    bias = np.zeros(7)
    for _ in range(int(settle / s.control_dt)):
        q_meas = d.qpos[ik.qadr].copy()
        q_star, _, _ = ik.solve(pos, R, q0=row[sl] - bias, qpos=d.qpos)
        bias = np.clip(bias + 0.25 * (q_star - q_meas), -0.25, 0.25)
        row[sl] = np.clip(q_star + bias, lo[sl], hi[sl])
        row = row.astype(np.float32).astype(np.float64)
        d.ctrl[:] = row
        for _ in range(s.substeps):
            mujoco.mj_step(m, d)
    d.qvel[:] = 0
    mujoco.mj_forward(m, d)
    t = m.body("turner").id
    print("turner", d.xpos[t].round(4).tolist(), "hand-root err %.4f" % np.linalg.norm(d.xpos[mount] - pos))
    if write:
        cfg = json.loads((HERE / "task.json").read_text())
        cfg["initial_qpos"][hand] = [float(v) for v in d.qpos]
        cfg["initial_targets"][hand] = [float(v) for v in row]
        (HERE / "task.json").write_text(json.dumps(cfg, indent=1) + "\n")
        print("wrote", hand)


class PickupController(demo_arm.ArmController):
    left_target = None

    def command(self, target, phase):
        if self.left_target is not None:  # the left arm holds its pose (closed-loop IK + joint integral)
            d = self.s.data
            if not hasattr(self, "ikL"):
                self.ikL = arm_ik.ArmIK(self.s.model, "left")
                self.biasL = np.zeros(7)
                self.prevL = self.row[self.lay["arm"]["left"]].copy()
            pos, R, fingers = self.left_target
            sl = self.lay["arm"]["left"]
            q_meas = d.qpos[self.ikL.qadr].copy()
            q_star, _, _ = self.ikL.solve(pos, R, q0=self.prevL - self.biasL, qpos=d.qpos)
            self.biasL = np.clip(self.biasL + self.ki * (q_star - q_meas), -0.25, 0.25)
            self.row[sl] = np.clip(q_star + self.biasL, self.lo[sl], self.hi[sl])
            self.prevL = self.row[sl].copy()
            if fingers is not None:
                self.row[self.lay["fingers"]["left"]] = fingers
        super().command(target, phase)

    def pose(self, pos, R, fingers, phase):
        if fingers is not None:
            self.row[self.lay["fingers"]["right"]] = fingers
        self.command((pos, R), phase)

    def interp(self, p0, R0, p1, R1, f0, f1, n, phase):
        q0, q1 = np.zeros(4), np.zeros(4)
        mujoco.mju_mat2Quat(q0, R0.ravel())
        mujoco.mju_mat2Quat(q1, R1.ravel())
        if q0 @ q1 < 0:
            q1 = -q1
        for k in range(n):
            if self.s.done:
                return
            a = smooth((k + 1) / n)
            q = (1 - a) * q0 + a * q1
            q /= np.linalg.norm(q)
            M = np.zeros(9)
            mujoco.mju_quat2Mat(M, q)
            self.pose(p0 + a * (p1 - p0), M.reshape(3, 3), f0 + a * (f1 - f0), phase)

    def hold_pan(self, P):
        """Left hand: palm-down power grasp of the pan handle (it points toward the robot), kept for the episode."""
        d, m = self.s.data, self.s.model
        pts = []
        for g in range(m.ngeom):
            if m.geom(g).name.startswith("pan_handle_") and m.geom_type[g] == 7:
                mid = m.geom_dataid[g]
                V = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]]
                pts.append(V @ d.geom_xmat[g].reshape(3, 3).T + d.geom_xpos[g])
        pts = np.vstack(pts)
        centre = d.xpos[m.body("pan").id]
        end = pts[np.argmax(np.linalg.norm(pts[:, :2] - centre[:2], axis=1))]
        ax = end - centre
        ax[2] = 0
        ax /= np.linalg.norm(ax)
        # handle centre line (with its slope) from a line fit; grip at pan_t of its length from the pan
        mean = pts.mean(0)
        a = np.linalg.svd(pts - mean, full_matrices=False)[2][0]
        a = a if a @ ax > 0 else -a
        u = (pts - mean) @ a
        hp = mean + a * (u.min() + P["pan_t"] * (u.max() - u.min()))
        down = np.array([0, 0, -1.0])
        down -= (down @ a) * a
        down /= np.linalg.norm(down)
        side = np.cross(a, down)
        best = None
        ikL = arm_ik.ArmIK(m, "left")
        for roll in P["pan_rolls"]:
            for sg in (1, -1):
                r = math.radians(roll)
                R = frame(math.cos(r) * down + math.sin(r) * side, sg * a)
                grip = hp + P["pan_b"] * R[:, 0] + P["pan_n"] * R[:, 2]
                root = grip - R @ GRIP_IN_HAND
                q, ep, er = ikL.solve(root, R, q0=self.row[self.lay["arm"]["left"]], iters=300)
                for seed in ([0.6, -0.9, 0.0, -1.4, 0.0, 0.0, 0.0], [0.488, -0.159, 0.351, -2.176, 2.193, 0.6, -0.977]):
                    q2, ep2, er2 = ikL.solve(root, R, q0=np.array(seed), iters=300)
                    if ep2 + 0.05 * er2 < ep + 0.05 * er:
                        ep, er = ep2, er2
                if best is None or ep + 0.05 * er < best[0]:
                    best = (ep + 0.05 * er, R, root, roll, sg)
        _, R, root, roll, sg = best
        self.pan_grasp = (roll, sg)
        fl = self.lay["fingers"]["left"]
        lo, hi = m.actuator_ctrlrange[fl].T
        f_open = np.clip(np.zeros(22), lo, hi)
        grasp = np.clip(np.asarray(GRASP, float), lo, hi)
        mountL = m.body(arm_rig._mount_names(m)[0]).id
        p0, R0 = d.xpos[mountL].copy(), d.xmat[mountL].reshape(3, 3).copy()
        above = root - R[:, 0] * P["above"]
        right_hold = (d.xpos[self.stage_body].copy(), d.xmat[self.stage_body].reshape(3, 3).copy())
        f0 = self.row[fl].copy()

        def move(pa, Ra, pb, Rb, fa, fb, n, phase):
            q0, q1 = np.zeros(4), np.zeros(4)
            mujoco.mju_mat2Quat(q0, Ra.ravel())
            mujoco.mju_mat2Quat(q1, Rb.ravel())
            if q0 @ q1 < 0:
                q1 = -q1
            for k in range(n):
                if self.s.done:
                    return
                al = smooth((k + 1) / n)
                q = (1 - al) * q0 + al * q1
                q /= np.linalg.norm(q)
                M = np.zeros(9)
                mujoco.mju_quat2Mat(M, q)
                self.left_target = (pa + al * (pb - pa), M.reshape(3, 3), fa + al * (fb - fa))
                self.command(right_hold, phase)

        move(p0, R0, above, R, f0, f_open, 100, "left: reach the pan handle")
        move(above, R, root, R, f_open, f_open, 60, "left: hand over the pan handle")
        move(root, R, root, R, f_open, grasp, 60, "left: hold the pan")
        self.left_target = (root, R, grasp)

    def pickup(self, P):
        d, m = self.s.data, self.s.model
        t = self.turner
        Rt = d.xmat[t].reshape(3, 3)
        a = Rt[:, 1]
        hp = d.xpos[t] + Rt @ np.array([0, P["grip_y"], 0])
        down = np.array([0, 0, -1.0])
        down -= (down @ a) * a
        down /= np.linalg.norm(down)
        side = np.cross(a, down)
        r = math.radians(P["roll_deg"])
        R = frame(math.cos(r) * down + math.sin(r) * side, a)
        grip = hp + P["grip_b"] * R[:, 0] + P["grip_n"] * R[:, 2]
        root = grip - R @ GRIP_IN_HAND
        fr = self.lay["fingers"]["right"]
        lo, hi = m.actuator_ctrlrange[fr].T
        f_open = np.clip(np.zeros(22), lo, hi)
        grasp = np.clip(np.asarray(P.get("grasp", GRASP), float), lo, hi)
        tight = grasp.copy()
        sq = P["squeeze"]
        for k in range(4):
            base = 5 + 4 * k + (1 if k == 3 else 0)
            tight[base] += sq[0]
            tight[base + 2] += sq[1]
            tight[base + 3] += sq[2]
        tight = np.clip(tight, lo, hi)
        mount = m.body("wrist_stage").id
        p0, R0 = d.xpos[mount].copy(), d.xmat[mount].reshape(3, 3).copy()
        above = root - R[:, 0] * P["above"]
        f0 = self.row[fr].copy()
        self.interp(p0, R0, above, R, f0, f_open, 100, "reach the turner")
        self.interp(above, R, root, R, f_open, f_open, 60, "hand over the handle")
        self.interp(root, R, root, R, f_open, grasp, 60, "grasp the handle")
        self.interp(root, R, root, R, grasp, tight, 20, "squeeze")
        self.interp(root, R, root + [0, 0, P["lift"]], R, tight, tight, 60, "pick the turner up")
        self.fingers = tight


DEFAULTS = {"grip_y": 0.03, "roll_deg": 0.0, "grip_b": 0.0, "grip_n": -0.035, "above": 0.07, "lift": 0.10,
            "squeeze": [0.6, 0.5, 0.4], "hand": "sharpa", "pan_hold": False, "pan_t": 0.5, "pan_b": 0.0,
            "pan_n": -0.035, "pan_rolls": [-60, -30, 0, 30, 60]}


def controller_class(params):
    """demo.Controller replacement: picks the turner up in its constructor, then serves (demo.run's steps)."""
    P = {**DEFAULTS, **params}

    class C(PickupController):
        def __init__(self, session, prm=None):
            super().__init__(session, prm)
            if P["pan_hold"]:
                self.hold_pan(P)
            self.pickup(P)

    return C, {k: v for k, v in params.items() if k not in DEFAULTS} | {"hand": P["hand"]}


def author(params, out, phases_out=None):
    demo.Controller, dp = controller_class(params)
    status, c = demo.run(dp, out, verbose=True, phases_out=phases_out)
    print(json.dumps({k: status[k] for k in ("success", "reason", "stage", "steps", "failure_detail")}, default=str))
    print("max IK pos err", round(c.max_err, 4), "rows", len(c.rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make-reset", "author"])
    ap.add_argument("--hand", default="sharpa")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--params", default="{}")
    ap.add_argument("--phases")
    a = ap.parse_args()
    if a.cmd == "make-reset":
        make_reset(a.hand, a.write)
    else:
        author(json.loads(a.params), a.out, a.phases)


if __name__ == "__main__":
    main()
