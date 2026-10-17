"""Authoring controller (not shipped) for the Marvin arm rig: square and feed the stack, press the head, release.

Closed loop on the live Session state; every control the desired world pose of the right hand mount (old hand-root
frame: palm normal +x, thumb +y, fingers +z) and the finger targets are converted to right-arm joint targets by
damped-least-squares IK with a joint integral (``arm_ik``); the recorded rows replay open loop.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("MUJOCO_GL", "egl")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parents[1] / "shared"))

import mujoco  # noqa: E402
import numpy as np  # noqa: E402
from scipy.optimize import least_squares  # noqa: E402
from scipy.spatial.transform import Rotation as Rot, Slerp  # noqa: E402

import arm_ik  # noqa: E402
import arm_rig  # noqa: E402
from runtime import Session  # noqa: E402


def rot(palm, thumb, fingers):
    """Mount rotation from the world directions of the palm normal, thumb side and finger direction."""
    return np.c_[np.asarray(palm, float), np.asarray(thumb, float), np.asarray(fingers, float)]


R_RAKE = rot([-1, 0, 0], [0, 1, 0], [0, 0, -1])            # palm toward -x, fingers down
R_PRESS = (Rot.from_rotvec([0, 0, float(os.environ.get("PRESS_YAW", "0.5"))]).as_matrix()
           @ Rot.from_rotvec([0, -0.15, 0]).as_matrix() @ R_RAKE)  # fingers down, tilted 0.15 rad, turned 0.5 rad
SEEDS = [np.array(s, dtype=float) for s in (
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [-0.6, -0.9, 0.0, -1.4, 0.0, 0.0, 0.0], [-1.0, -1.2, 0.5, -1.0, 0.5, 0.0, 0.0],
    [0.0, -1.5, -0.5, -1.8, 0.0, 0.0, 0.0], [-0.3, -0.5, 0.3, -1.6, 0.3, 0.0, 0.0])]

WUJI = {"index_MCP_FE": "FFJ0", "index_MCP_AA": "FFJ1", "index_PIP": "FFJ2", "index_DIP": "FFJ3",
        "middle_MCP_FE": "MFJ0", "middle_MCP_AA": "MFJ1", "middle_PIP": "MFJ2", "middle_DIP": "MFJ3",
        "ring_MCP_FE": "RFJ0", "ring_MCP_AA": "RFJ1", "ring_PIP": "RFJ2", "ring_DIP": "RFJ3",
        "pinky_MCP_FE": "LFJ0", "pinky_MCP_AA": "LFJ1", "pinky_PIP": "LFJ2", "pinky_DIP": "LFJ3",
        "thumb_CMC_FE": None, "thumb_MCP_FE": None, "thumb_IP": None}


class ArmController:
    def __init__(self, session, log=print, ki=0.25):
        self.s = session
        self.m = session.model
        self.log = log
        self.ki = ki
        self.lay = arm_rig.layout(self.m)
        self.arm = self.lay["arm"]["right"]
        self.fing = self.lay["fingers"]["right"]
        self.ik = arm_ik.ArmIK(self.m, "right")
        self.mount = self.m.body("wrist_stage").id
        self.scratch = mujoco.MjData(self.m)
        self.row = np.array(session.data.ctrl, dtype=float)
        self.q_cmd = self.row[self.arm].copy()
        self.bias = np.zeros(7)
        d = session.data
        self.p = d.xpos[self.mount].copy()
        self.R = d.xmat[self.mount].reshape(3, 3).copy()
        self.fingers = self.row[self.fing].copy()
        self.phases = []
        self.errs = []
        self.finger_dofs = self.m.jnt_dofadr[self.m.actuator_trnid[self.fing, 0]]
        self.finger_gain = self.m.actuator_gainprm[self.fing, 0].copy()

    # ------------------------------------------------------------------ hand geometry (mount frame)
    def finger_targets(self, **joints):
        f = np.zeros(len(range(*self.fing.indices(self.m.nu))))
        names = self.s.actuator_names[self.fing]
        for k, v in joints.items():
            if self.s.hand == "sharpa":
                name = "right_" + k
            else:
                code = WUJI.get(k)
                if code is None:
                    continue
                name = "r_wuji_r_" + code
                if k.endswith("_AA"):
                    v = v * float(os.environ.get("WUJI_AA_SIGN", "0.7"))
            f[list(names).index(name)] = v
        lo, hi = self.m.actuator_ctrlrange[self.fing].T
        return np.clip(f, lo, hi)

    def tip_geoms(self, finger):
        if self.s.hand == "sharpa":
            return [self.m.geom(f"right_{finger}_fingertip_collision").id]
        part = {"index": "index_finger", "middle": "middle_finger", "ring": "ring_finger", "pinky": "pinky",
                "thumb": "thumb"}[finger]
        return [g for g in range(self.m.ngeom) if (self.m.geom(g).name or "").startswith(f"r_wuji_r_{part}_")
                and ("distal_collision" in self.m.geom(g).name or "tip_sensor_frame_collision" in self.m.geom(g).name)]

    def local_points(self, fingers, geoms):
        """Surface samples of ``geoms`` in the mount frame with the right fingers at ``fingers``."""
        d = self.scratch
        d.qpos[:] = self.s.data.qpos
        qadr = self.m.jnt_qposadr[self.m.actuator_trnid[self.fing, 0]]
        d.qpos[qadr] = fingers
        mujoco.mj_kinematics(self.m, d)
        Rm = d.xmat[self.mount].reshape(3, 3)
        pm = d.xpos[self.mount]
        pts = []
        for g in geoms:
            R = d.geom_xmat[g].reshape(3, 3)
            c = d.geom_xpos[g]
            t = self.m.geom_type[g]
            if t == mujoco.mjtGeom.mjGEOM_MESH:
                mid = self.m.geom_dataid[g]
                a, n = self.m.mesh_vertadr[mid], self.m.mesh_vertnum[mid]
                w = c + self.m.mesh_vert[a:a + n] @ R.T
            else:
                r, hl = self.m.geom_size[g][:2]
                if t == mujoco.mjtGeom.mjGEOM_SPHERE:
                    hl = 0.0
                w = []
                for zz in np.linspace(-hl, hl, 5):
                    for ang in np.linspace(0, 2 * np.pi, 16, endpoint=False):
                        w.append(c + R @ np.array([r * np.cos(ang), r * np.sin(ang), zz]))
                for ang in np.linspace(0, 2 * np.pi, 16, endpoint=False):
                    for b in np.linspace(0.15, np.pi / 2, 5):
                        for e in (-1, 1):
                            w.append(c + R @ np.array([r * np.cos(ang) * np.cos(b), r * np.sin(ang) * np.cos(b),
                                                       e * (hl + r * np.sin(b))]))
                w = np.asarray(w)
            pts.append((w - pm) @ Rm)
        return np.vstack(pts)

    @staticmethod
    def world(p, R, local):
        return p + local @ R.T

    # ------------------------------------------------------------------ execution
    def control(self, p, R, fingers, phase):
        d = self.s.data
        q_meas = d.qpos[self.ik.qadr].copy()
        q_star, ep, er = self.ik.solve(p, R, q0=self.q_cmd - self.bias, qpos=d.qpos)
        self.bias = np.clip(self.bias + self.ki * (q_star - q_meas), -0.25, 0.25)
        lo, hi = self.m.actuator_ctrlrange.T
        self.q_cmd = np.clip(q_star + self.bias, lo[self.arm], hi[self.arm])
        self.row[self.arm] = self.q_cmd
        self.row[self.fing] = fingers + d.qfrc_bias[self.finger_dofs] / self.finger_gain
        self.row = np.clip(self.row, lo, hi)
        self.s.step(self.row.copy())
        self.phases.append(phase)
        self.errs.append((float(np.linalg.norm(d.xpos[self.mount] - p)), ep, er))

    def go(self, p, R, fingers, count, phase, log=True):
        p0, R0, f0 = self.p.copy(), self.R.copy(), self.fingers.copy()
        p, R = np.asarray(p, float), np.asarray(R, float)
        fingers = f0 if fingers is None else np.asarray(fingers, float)
        slerp = Slerp([0, 1], Rot.from_matrix(np.stack([R0, R])))
        for r in np.linspace(0, 1, count + 1)[1:]:
            if self.s.done:
                break
            b = r * r * (3 - 2 * r)
            self.p = p0 + (p - p0) * b
            self.R = slerp([b]).as_matrix()[0]
            self.fingers = f0 + (fingers - f0) * b
            self.control(self.p, self.R, self.fingers, phase)
        if log:
            f = self.s.features()
            e = np.array(self.errs[-count:]) if count else np.zeros((1, 3))
            self.log(f"{self.s.steps:5d} {phase:40s} stage={f['stage']} offs={np.round(f['corner_offsets_m'], 4).tolist()} "
                     f"al={int(f['aligned'])} th={int(f['in_throat'])} head={f['head_angle_rad']:.3f} "
                     f"track={e[:, 0].max() * 1000:.1f}mm fail={f['failure']}")
        return self.s.features()

    def hold(self, count, phase):
        return self.go(self.p, self.R, self.fingers, count, phase)

    # ------------------------------------------------------------------ task phases
    def sheet_corners(self):
        c = self.s.checker
        return [c.corners(self.s.data, i) for i in range(c.n)]

    def rake(self, fingers):
        """Rake orientation (index and pinky tips at the same height and the same x): (R, index lead, pinky lead)."""
        li = self.local_points(fingers, self.tip_geoms("index"))
        lp = self.local_points(fingers, self.tip_geoms("pinky"))

        def geo(x):
            R = Rot.from_rotvec([0, 0, x[1]]).as_matrix() @ Rot.from_rotvec([x[0], 0, 0]).as_matrix() @ R_RAKE
            wi, wp = li @ R.T, lp @ R.T
            zi, zp = wi[:, 2].min(), wp[:, 2].min()
            ai = wi[wi[:, 2] < zi + 0.0012]
            ap = wp[wp[:, 2] < zp + 0.0012]
            return R, ai[np.argmin(ai[:, 0])], ap[np.argmin(ap[:, 0])], zi, zp

        def res(x):
            _, ai, ap, zi, zp = geo(x)
            return [(zp - zi) * 100, (ap[0] - ai[0]) * 100]

        fit = least_squares(res, [0.0, 0.0], diff_step=1e-3)
        R, ai, ap, zi, zp = geo(fit.x)
        self.log(f"rake roll {fit.x[0]:.4f} yaw {fit.x[1]:.4f} span {ap[1] - ai[1]:.3f} dz {zp - zi:.5f} "
                 f"dx {ap[0] - ai[0]:.5f}")
        return R, ai, ap, min(zi, zp)

    def feed_push(self, corner_target_x, label="square and feed"):
        """Index and pinky fingertips push the stack's +x edges toward -x: the upper sheets come flush, then the
        stack slides into the throat until its corner reaches the paper stop."""
        top = self.s.config["table_z"]
        corners = self.sheet_corners()
        edge_max = max(c[:, 0].max() for c in corners)
        centre = float(np.mean([c[:, 1].mean() for c in corners])) + float(os.environ.get("RAKE_DY", "0.0"))
        fingers = self.finger_targets(index_MCP_AA=-0.30, pinky_MCP_AA=0.30, middle_MCP_FE=0.5, middle_PIP=0.6,
                                      ring_MCP_FE=0.5, ring_PIP=0.6)
        R, ai, ap, zb = self.rake(fingers)
        dz = float(os.environ.get("RAKE_DZ", "0.0003" if self.s.hand == "sharpa" else "-0.0004"))
        p = np.array([edge_max + 0.010 - min(ai[0], ap[0]), centre - (ai[1] + ap[1]) / 2, top + dz - zb])
        self.go(p + [0.0, 0.0, 0.10], R, fingers, 100, f"{label}: approach above")
        self.go(p, R, fingers, 70, f"{label}: lower fingertips to desk")
        self.hold(10, f"{label}: settle on desk")
        step = p.copy()
        for k in range(600):
            if self.s.done:
                break
            cs = self.sheet_corners()
            edges = [c[:, 0].max() for c in cs]
            spread = max(edges[1:]) - edges[0]
            stop_gap = max(c[:, 0].min() for c in cs) - corner_target_x
            if spread <= 0.0003 and stop_gap <= 0.0004:
                break
            step[0] -= 0.0004
            self.go(step, R, fingers, 1, "", log=False)
            if k % 40 == 39:
                self.log(f"   k={k} spread={spread:.4f} stop_gap={stop_gap:.4f} track={self.errs[-1][0] * 1000:.2f}mm")
        self.log(f"{label}: pushed {k} increments, spread {spread:.5f}, stop gap {stop_gap:.5f}")
        over = float(os.environ.get("RAKE_OVER", "0.003"))
        if over > 0:
            step[0] -= over
            self.go(step, R, fingers, int(over / 0.0002), f"{label}: press stack against the paper stop")
        self.hold(15, f"{label}: settle")
        self.go(step + [0, 0, 0.012], R, fingers, 30, f"{label}: lift fingertips")
        self.go(step + [0.03, 0, 0.10], R, fingers, 60, f"{label}: lift away")

    def press_head(self, label="press stapler head"):
        """Straight index and middle fingers pointing down press the handle to its bottom stop, then release."""
        s = self.s
        base = s.data.xpos[s.checker.base].copy()
        fingers = self.finger_targets(index_MCP_FE=0.0, index_PIP=0.0, index_DIP=0.0, middle_MCP_FE=0.0,
                                      middle_PIP=0.0, middle_DIP=0.0, ring_MCP_FE=1.2, ring_PIP=1.4, pinky_MCP_FE=1.2,
                                      pinky_PIP=1.4, thumb_CMC_FE=0.6, thumb_MCP_FE=0.6, thumb_IP=0.6)
        R = R_PRESS
        pts = self.local_points(fingers, self.tip_geoms("index") + self.tip_geoms("middle")) @ R.T
        low = pts[np.argmin(pts[:, 2])]
        handle_top = base[2] + 0.020 + 0.0425
        press_x = base[0] + 0.030
        p = np.array([press_x - low[0], base[1] - np.mean(pts[:, 1]), handle_top + 0.012 - low[2]])
        rise = self.p.copy()
        rise[2] = max(rise[2], p[2] + 0.10)
        self.go(rise, self.R, self.fingers, 40, f"{label}: rise")
        self.go(p + [0, 0, 0.10], R, fingers, 90, f"{label}: hand over the handle")
        self.go(p, R, fingers, 50, f"{label}: fingertips above the handle")
        down = p.copy()
        hinge = s.checker.hinge
        for k in range(400):
            if s.done or s.data.qpos[hinge] >= s.head_stop - 0.004:
                break
            down[2] -= 0.0004
            self.go(down, R, fingers, 1, "", log=False)
        self.log(f"{label}: pressed {k} increments, head {s.data.qpos[hinge]:.4f} stop {s.head_stop:.4f}")
        down[2] -= 0.002
        self.go(down, R, fingers, 10, f"{label}: bottom stop")
        self.hold(15, f"{label}: hold at bottom stop")
        self.go(p, R, fingers, 40, f"{label}: release, head springs back")
        self.go(p + [0, 0, 0.10], R, fingers, 50, f"{label}: hand away")


def initial_targets(model, hand, pos, R, fingers):
    """Arm-rig reset row: right arm IK for the mount pose (best of several seeds), left arm parked."""
    ik = arm_ik.ArmIK(model, "right")
    best = None
    for seed in SEEDS:
        q, ep, er = ik.solve(pos, R, q0=seed, iters=400)
        cost = ep + 0.05 * er
        if best is None or cost < best[0]:
            best = (cost, q, ep, er)
    print("initial IK error %.2e m %.2e rad" % (best[2], best[3]), np.round(best[1], 4).tolist())
    return arm_rig.default_targets(model, arm_pose={"right": best[1]},
                                   fingers=None if fingers is None else {"right": fingers})


def make_demo(output, hand="sharpa", stop_after=None, slack_rows=200):
    s = Session(hand=hand)
    c = ArmController(s)
    c.hold(10, "settle")
    stop_face = s.data.geom_xpos[s.model.geom("paper_stop").id][0] + 0.0005
    c.feed_push(stop_face)
    if stop_after != "feed":
        c.press_head()
        c.hold(80, "released: hold")
    rows = [np.asarray(a) for a in s.actions]
    phases = list(c.phases[: len(rows)])
    success_step = s.steps if s.success else None
    last = rows[-1].copy()
    for _ in range(slack_rows):
        rows.append(last.copy())
        phases.append("hold (slack after success)")
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    s.save_trajectory(np.asarray(rows), out)
    np.save(out.with_suffix(".phases.npy"), np.asarray(phases))
    st = s.status()
    errs = np.array(c.errs)
    summary = {"success": st["success"], "success_step": success_step, "rows": len(rows), "stage": st["stage"],
               "reason": st["reason"], "state_sha": s.state_sha(), "hand": s.hand,
               "tracking_mm_mean": float(errs[:, 0].mean() * 1000), "tracking_mm_max": float(errs[:, 0].max() * 1000)}
    out.with_suffix(".live.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
    return s, c


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--hand", default="sharpa")
    p.add_argument("--stop-after")
    a = p.parse_args()
    make_demo(a.out, a.hand, a.stop_after)
