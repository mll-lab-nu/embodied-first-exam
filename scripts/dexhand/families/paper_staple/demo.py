"""Authoring controller (closed loop on Session state, recorded as open-loop rows): align, feed, staple, release."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("MUJOCO_GL", "egl")
sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation as Rot

from rig import Rig, rot
from runtime import Session

R_XPUSH = Rot.from_rotvec([0.06, 0, 0]).as_matrix() @ rot([1, 0, 0], [0, 0, 1], [0, -1, 0])
R_YPUSH = Rot.from_rotvec([0, 0.06, 0]).as_matrix() @ rot([0, 1, 0], [0, 0, 1], [1, 0, 0])
R_RAKE = rot([1, 0, 0], [0, -1, 0], [0, 0, -1])
R_PINCH = rot([0, 0, 1], [0, 1, 0], [-1, 0, 0])
R_PRESS = rot([0, 0, -1], [0, 1, 0], [1, 0, 0])


class Controller:
    def __init__(self, session, log=print):
        self.s = session
        self.rig = Rig(session)
        self.m = session.model
        self.target = session.hold_action()
        self.phases = []
        self.log = log
        self.dofs = self.m.jnt_dofadr[self.m.actuator_trnid[:, 0]]
        self.gain = self.m.actuator_gainprm[:, 0].copy()

    # ------------------------------------------------------------------ execution
    def command(self, joint_target):
        d = self.s.data
        action = joint_target + d.qfrc_bias[self.dofs] / self.gain
        return np.clip(action, *self.m.actuator_ctrlrange.T)

    def go(self, target, count, phase, smooth=True, log=True):
        start = self.target.copy()
        target = np.asarray(target, dtype=float)
        for r in np.linspace(0, 1, count + 1)[1:]:
            if self.s.done:
                break
            b = r * r * (3 - 2 * r) if smooth else r
            self.target = start + (target - start) * b
            self.s.step(self.command(self.target))
            self.phases.append(phase)
        if not log:
            return None
        f = self.s.features()
        self.log(f"{self.s.steps:5d} {phase:28s} stage={f['stage']} offs={np.round(f['corner_offsets_m'], 4).tolist()} "
                 f"aligned={f['aligned']} throat={f['in_throat']} head={f['head_angle_rad']:.3f} fail={f['failure']}")
        if os.environ.get("DEMO_SNAP"):
            from PIL import Image
            snap = Path(os.environ["DEMO_SNAP"])
            snap.mkdir(parents=True, exist_ok=True)
            Image.fromarray(self.s.render_frame(os.environ.get("DEMO_CAM", "closeup"), 640, 360)).save(
                snap / f"{self.s.steps:05d}.png")
        return f

    def hold(self, count, phase):
        return self.go(self.target, count, phase)

    # ------------------------------------------------------------------ geometry
    def sheet_corners(self):
        return [self.s.checker.corners(self.s.data, i) for i in range(len(self.s.checker.sheet_ids))]

    def fence(self, q, axis, sign, band=0.003):
        """Leading face (max sign*coord along ``axis``) and bottom of the hand's low geoms; returns (face, bottom)."""
        ext = self.rig.extent(q)
        bottom = min(a[2] for a, b in ext.values())
        low = [(a, b) for a, b in ext.values() if a[2] <= bottom + band]
        face = max(sign * (b[axis] if sign > 0 else a[axis]) for a, b in low) * sign
        return face, bottom

    def pose(self, R, fingers=None, guess=None):
        q = self.target.copy()
        if fingers is not None:
            q[6:] = fingers
        q, cost = self.rig.orient(R, q, guess)
        if cost > 1e-4:
            raise RuntimeError(f"orientation solve failed: {cost}")
        return q

    # ------------------------------------------------------------------ phases
    def push(self, axis, R, center_offset, travel_past, label, fingers=None):
        """Fence push along +axis: the hand's low edge slides on the desk and squares the sheet edges (closed loop
        on the bottom sheet edge, which must move ``travel_past`` once all three edges are flush)."""
        top = self.s.config["table_z"]
        corners = self.sheet_corners()
        edge_min = min(c[:, axis].min() for c in corners)          # most protruding edge
        bottom_edge0 = corners[0][:, axis].min()                    # bottom sheet edge
        fingers = np.zeros(self.m.nu - 6) if fingers is None else np.asarray(fingers, dtype=float)
        other = 1 - axis
        centre = np.mean([c[:, other].mean() for c in corners])
        yaw = 0.0
        for _ in range(4):
            Rz = Rot.from_rotvec([0, 0, yaw]).as_matrix() @ R
            q = self.pose(Rz, fingers)
            q[other] += centre - q[other] + (center_offset or 0.0)
            pts = self.rig.low_points(q)
            bottom = pts[:, 2].min()
            low = pts[pts[:, 2] < bottom + 0.0012]
            # two contact zones along the fence: the extreme low points in the "other" direction
            u = low[:, other]
            a = low[u <= u.min() + 0.02]
            b = low[u >= u.max() - 0.02]
            ia, ib = np.argmax(a[:, axis]), np.argmax(b[:, axis])
            pa, pb = a[ia], b[ib]
            # yaw that makes the two leading points equal along the push axis
            delta = (pb[axis] - pa[axis]) / (pb[other] - pa[other])
            correction = np.arctan(delta) * (1 if axis == 0 else -1)
            if abs(correction) < 2e-4:
                break
            yaw += correction
        face = max(pa[axis], pb[axis])
        if center_offset is None:
            q[other] += centre - (pa[other] + pb[other]) / 2
        self.log(f"{label}: fence yaw {yaw:.4f} span {abs(pb[other] - pa[other]):.3f} lead diff {pb[axis] - pa[axis]:.5f}")
        q[axis] += (edge_min - 0.010) - face
        q[2] += top + 0.0003 - bottom
        above = q.copy()
        above[2] += 0.10
        self.go(above, 90, f"{label}: approach above")
        self.go(q, 60, f"{label}: lower fence to desk")
        step = q.copy()
        spread = None
        for k in range(400):
            if self.s.done:
                break
            edges = [c[:, axis].min() for c in self.sheet_corners()]
            spread = edges[0] - min(edges[1:])
            if spread <= travel_past:
                break
            step[axis] += 0.0004
            self.go(step, 1, f"{label}: push edges square", log=False)
        yaws = [float(np.arctan2(self.s.data.xmat[b][3], self.s.data.xmat[b][0])) for b in self.s.checker.sheet_ids]
        self.log(f"{label}: pushed {k} increments, edge spread {spread:.5f}, yaws {np.round(yaws, 4).tolist()}")
        self.hold(15, f"{label}: settle")
        back = step.copy()
        back[axis] -= 0.012
        self.go(back, 30, f"{label}: back off")
        back[2] += 0.10
        self.go(back, 60, f"{label}: lift away")


    WUJI = {"index_MCP_FE": "FFJ0", "index_MCP_AA": "FFJ1", "index_PIP": "FFJ2", "index_DIP": "FFJ3",
            "middle_MCP_FE": "MFJ0", "middle_MCP_AA": "MFJ1", "middle_PIP": "MFJ2", "middle_DIP": "MFJ3",
            "ring_MCP_FE": "RFJ0", "ring_MCP_AA": "RFJ1", "ring_PIP": "RFJ2", "ring_DIP": "RFJ3",
            "pinky_MCP_FE": "LFJ0", "pinky_MCP_AA": "LFJ1", "pinky_PIP": "LFJ2", "pinky_DIP": "LFJ3",
            "thumb_CMC_FE": None}

    def finger_targets(self, **joints):
        """Finger targets by Sharpa-style semantic names; mapped to the Wuji actuators (same flexion sense)."""
        f = np.zeros(self.m.nu - 6)
        for k, v in joints.items():
            if self.s.hand == "sharpa":
                name = "right_" + k
            else:
                code = self.WUJI.get(k)
                if code is None:
                    continue
                name = "r_wuji_r_" + code
                if k.endswith("_AA"):
                    v = v * self.wuji_aa_sign(k)
            f[self.s.actuator_names.index(name) - 6] = v
        lo, hi = self.m.actuator_ctrlrange[6:].T
        return np.clip(f, lo, hi)

    def wuji_aa_sign(self, key):
        # Wuji abduction has the same sign sense here; its wider palm needs a smaller spread for a 12-13 cm rake
        return float(os.environ.get("WUJI_AA_SIGN", "0.7"))

    def tip_geoms(self, finger):
        if self.s.hand == "sharpa":
            return [self.m.geom(f"right_{finger}_fingertip_collision").id]
        part = {"index": "index_finger", "middle": "middle_finger", "ring": "ring_finger", "pinky": "pinky",
                "thumb": "thumb"}[finger]
        return [g for g in range(self.m.ngeom) if (self.m.geom(g).name or "").startswith(f"r_wuji_r_{part}_")
                and ("distal_collision" in self.m.geom(g).name or "tip_sensor_frame_collision" in self.m.geom(g).name)]

    def rake_push(self, travel_past, label):
        """Two-point fingertip rake (index and pinky spread, pointing down) squares the sheets' -x edges."""
        top = self.s.config["table_z"]
        corners = self.sheet_corners()
        edge_min = min(c[:, 0].min() for c in corners)
        centre = np.mean([c[:, 1].mean() for c in corners])
        fingers = self.finger_targets(index_MCP_AA=-0.30, pinky_MCP_AA=0.30, middle_MCP_FE=0.5, middle_PIP=0.6,
                                      ring_MCP_FE=0.5, ring_PIP=0.6)
        gi = [self.m.geom("right_index_fingertip_collision").id]
        gp = [self.m.geom("right_pinky_fingertip_collision").id]
        roll = yaw = 0.0
        for _ in range(8):
            R = Rot.from_rotvec([0, 0, yaw]).as_matrix() @ Rot.from_rotvec([roll, 0, 0]).as_matrix() @ R_RAKE
            q = self.pose(R, fingers)
            pi, pp = self.rig.low_points(q, gi), self.rig.low_points(q, gp)
            zi, zp = pi[:, 2].min(), pp[:, 2].min()
            li, lp = pi[pi[:, 2] < zi + 0.0012], pp[pp[:, 2] < zp + 0.0012]
            ai, ap = li[np.argmax(li[:, 0])], lp[np.argmax(lp[:, 0])]
            dy = ap[1] - ai[1]
            droll = -np.arctan((zp - zi) / dy)
            dyaw = np.arctan((ap[0] - ai[0]) / dy)
            if abs(droll) < 1e-4 and abs(dyaw) < 1e-4:
                break
            roll += droll
            yaw += dyaw
        self.log(f"{label}: rake roll {roll:.4f} yaw {yaw:.4f} span {dy:.3f} dz {zp - zi:.5f} dx {ap[0] - ai[0]:.5f}")
        q[1] += centre - (ai[1] + ap[1]) / 2
        q[0] += (edge_min - 0.010) - max(ai[0], ap[0])
        q[2] += top + 0.0003 - min(zi, zp)
        above = q.copy()
        above[2] += 0.10
        self.go(above, 90, f"{label}: approach above")
        self.go(q, 60, f"{label}: lower fingertips to desk")
        step = q.copy()
        for k in range(400):
            if self.s.done:
                break
            edges = [c[:, 0].min() for c in self.sheet_corners()]
            spread = edges[0] - min(edges[1:])
            if spread <= travel_past:
                break
            step[0] += 0.0004
            self.go(step, 1, f"{label}: push edges square", log=False)
        yaws = [float(np.arctan2(self.s.data.xmat[b][3], self.s.data.xmat[b][0])) for b in self.s.checker.sheet_ids]
        self.log(f"{label}: pushed {k} increments, edge spread {spread:.5f}, yaws {np.round(yaws, 4).tolist()}")
        self.hold(15, f"{label}: settle")
        back = step.copy()
        back[2] += 0.012
        self.go(back, 30, f"{label}: lift fingertips")
        back[0] -= 0.02
        back[2] += 0.09
        self.go(back, 60, f"{label}: lift away")


    def thumb_over(self, q, rel, fingers):
        """Thumb joint targets placing the thumb pad's lowest point at ``rel`` from the index pad's highest point."""
        from scipy.optimize import least_squares

        idx = [self.s.actuator_names.index("right_thumb_" + j) for j in ("CMC_FE", "CMC_AA", "MCP_FE", "MCP_AA", "IP")]
        lo, hi = self.m.actuator_ctrlrange[idx].T
        gt = [self.m.geom("right_thumb_fingertip_collision").id]
        gi = [self.m.geom("right_index_fingertip_collision").id]
        q = q.copy()
        q[6:] = fingers

        def res(x):
            q[idx] = x
            pt, pi = self.rig.low_points(q, gt), self.rig.low_points(q, gi)
            bottom = pt[np.argmin(pt[:, 2])]
            top = pi[np.argmax(pi[:, 2])]
            return np.r_[(bottom - top - rel) * 100, (x - (lo + hi) / 2) * 0.01]

        best = None
        for start in ([0.8, 0.0, 0.3, 0.0, 0.3], [1.2, 0.2, 0.5, 0.0, 0.5], [0.4, -0.2, 0.2, 0.0, 0.2]):
            fit = least_squares(res, np.clip(start, lo + 1e-4, hi - 1e-4), bounds=(lo, hi))
            if best is None or fit.cost < best.cost:
                best = fit
        q[idx] = best.x
        return q, float(np.sqrt(2 * best.cost) / 100)


    def pinch_poses(self, y):
        """Open/closed thumb-over-index pinch at the overhang (index pad under the stack, thumb pad 18 mm further out)."""
        from scipy.optimize import least_squares

        names = self.s.actuator_names
        base = self.finger_targets(middle_MCP_FE=1.3, middle_PIP=1.5, middle_DIP=1.0, ring_MCP_FE=1.3, ring_PIP=1.5,
                                   ring_DIP=1.0, pinky_MCP_FE=1.3, pinky_PIP=1.5, pinky_DIP=1.0)
        q0 = self.pose(R_PINCH, base)
        idx = [names.index("right_thumb_" + j) for j in ("CMC_FE", "CMC_AA", "MCP_FE", "MCP_AA", "IP")]
        idx += [names.index("right_index_" + j) for j in ("MCP_FE", "PIP", "DIP")]
        lo, hi = self.m.actuator_ctrlrange[idx].T
        gt = [self.m.geom("right_thumb_fingertip_collision").id]
        gi = [self.m.geom("right_index_fingertip_collision").id]

        tip_site = self.m.site("right_thumb_fingertip").id
        dp_body = self.m.body("right_thumb_DP").id
        pp_geoms = [self.m.geom("right_thumb_PP_fit").id]

        def pts(x):
            q = q0.copy()
            q[idx] = x
            pt, pi = self.rig.low_points(q, gt), self.rig.low_points(q, gi)
            return q, pt[np.argmin(pt[:, 2])], pi[np.argmax(pi[:, 2])]

        def res(x, rel):
            q, b, t = pts(x)
            d = self.rig.d
            axis = d.site_xpos[tip_site] - d.xpos[dp_body]
            axis /= np.linalg.norm(axis)
            want = np.array([-1.0, 0.0, -0.25])
            want /= np.linalg.norm(want)
            pp = self.rig.low_points(q, pp_geoms)
            # the thumb's proximal phalanx must stay out of the stack: above it or 15+ mm beyond the pinch
            bad = (pp[:, 2] < t[2] + 0.006) & (pp[:, 0] < b[0] + 0.040)
            pen = np.minimum(0, pp[bad, 0] - (b[0] + 0.040)).sum() if bad.any() else 0.0
            return np.r_[(b - t - rel) * 100, (axis - want) * 3, pen * 50]

        out = {}
        best = None
        for start in ([1.38, -0.08, 0.14, -0.08, 0.19, 0.9, 1.17, 0.7], [1.0, 0.0, 0.0, 0.0, 1.2, 0.9, 1.1, 0.6],
                      [1.6, 0.2, 0.4, 0.0, 1.0, 0.8, 1.0, 0.6], [0.8, -0.2, -0.3, 0.0, 1.5, 0.9, 1.2, 0.7]):
            fit = least_squares(res, np.clip(start, lo + 1e-4, hi - 1e-4), bounds=(lo, hi),
                                args=(np.array([0.018, 0.0, 0.009]),))
            if best is None or fit.cost < best.cost:
                best = fit
        start = best.x
        for name, rel in (("open", [0.018, 0.0, 0.009]), ("closed", [0.018, 0.0, 0.0011])):
            fit = least_squares(res, start, bounds=(lo, hi), args=(np.array(rel),))
            q, b, t = pts(fit.x)
            self.log(f"pinch {name}: cost {fit.cost:.2e} residual {np.round(res(fit.x, np.array(rel)), 4).tolist()}")
            out[name] = (q, t - q[:3])
            start = fit.x
        return out

    def stack_state(self):
        """Corner points (4 per sheet) and the stack's -x/-y corner (sheet 0 frame)."""
        return self.sheet_corners()


    def grasp_overhang(self, label="pinch"):
        """Thumb-over-index pinch of the stack's overhanging +x strip, beyond the desk edge."""
        corners = self.sheet_corners()
        edge = min(c[:, 0].max() for c in corners)  # +x edge of the stack (innermost)
        y = float(np.mean([c[:, 1].mean() for c in corners]))
        top = self.s.config["table_z"]
        t = self.s.config["sheet"]["thickness"]
        poses = self.pinch_poses(y)
        q_open, top_open = poses["open"]
        q_closed, top_closed = poses["closed"]
        x_index = edge - 0.035
        under = q_open.copy()
        under[:3] += np.array([x_index, y, top - 0.004]) - (q_open[:3] + top_open)
        out = under.copy()
        out[0] += 0.07
        high = out.copy()
        high[2] = 1.05
        rise = self.target.copy()
        rise[2] = 1.05
        self.go(rise, 60, f"{label}: rise")
        self.go(high, 110, f"{label}: turn palm up beyond the desk edge")
        self.go(out, 110, f"{label}: descend beyond the edge")
        self.go(under, 80, f"{label}: index under, thumb over the strip")
        touch = under.copy()
        touch[2] += 0.0045
        self.go(touch, 40, f"{label}: index pad touches the stack")
        closed = q_closed.copy()
        closed[:3] += np.array([x_index, y, top + 0.0005]) - (q_closed[:3] + top_closed)
        self.go(closed, 60, f"{label}: thumb closes the pinch")
        self.hold(20, f"{label}: hold pinch")
        self.grip = closed
        return closed

    def corner_height(self, which=(-1, -1)):
        """World position of the stack's (sign x, sign y) corner of each sheet."""
        out = []
        for i, b in enumerate(self.s.checker.sheet_ids):
            R = self.s.data.xmat[b].reshape(3, 3)
            local = np.r_[np.asarray(which) * self.s.checker.half, 0]
            out.append(self.s.data.xpos[b] + R @ local)
        return np.asarray(out)


    def pinch_point(self):
        d = self.s.data
        g = self.m.geom("right_index_fingertip_collision").id
        return d.geom_xpos[g].copy()

    def rotate_about(self, q, axis_vec, angle, pivot):
        """Joint targets with the hand rotated by ``angle`` about the world axis through ``pivot``."""
        Rw = Rot.from_rotvec(np.asarray(axis_vec, dtype=float) * angle).as_matrix()
        R = Rw @ self.rig.hand_rot(q)
        q2, cost = self.rig.orient(R, q, q[3:6])
        p_old = self.rig.point(q, "body", "right_hand_C_MC")
        p_new = pivot + Rw @ (p_old - pivot)
        q2 = self.rig.place(q2, "body", "right_hand_C_MC", p_new)
        return q2

    def stack_pitch(self):
        R = self.s.data.xmat[self.s.checker.sheet_ids[0]].reshape(3, 3)
        return float(np.arcsin(np.clip(R[2, 0], -1, 1)))

    def level_and_height(self, z_far, label, iters=6, count=40):
        """Closed loop: rotate the hand about the pinch so the stack is level, then set the far corner height."""
        for k in range(iters):
            pitch = self.stack_pitch()
            far = self.corner_height((-1, -1))[0]
            q = self.rotate_about(self.target, [0, 1, 0], float(np.clip(pitch, -0.08, 0.08)), self.pinch_point())
            q[2] += z_far - far[2] - (far[0] - self.pinch_point()[0]) * np.sin(pitch) * 0
            self.go(q, count, f"{label}: level stack ({k})")
            far = self.corner_height((-1, -1))[0]
            self.log(f"   pitch {self.stack_pitch():.4f} far corner z {far[2]:.4f}")
            if abs(self.stack_pitch()) < 0.003 and abs(far[2] - z_far) < 0.0007:
                break


    def feed_push(self, corner_target_x, label="square and feed"):
        """Two-point fingertip rake pushes the stack's +x edges toward -x: squares the staircase, then slides the
        stack (corner on the anvil, far edge on the desk) into the stapler throat until the corner reaches the
        target x."""
        top = self.s.config["table_z"]
        corners = self.sheet_corners()
        edge_max = max(c[:, 0].max() for c in corners)
        centre = float(np.mean([c[:, 1].mean() for c in corners]))
        centre = centre + float(os.environ.get("RAKE_DY", "0.0"))
        fingers = self.finger_targets(index_MCP_AA=-0.30, pinky_MCP_AA=0.30, middle_MCP_FE=0.5, middle_PIP=0.6,
                                      ring_MCP_FE=0.5, ring_PIP=0.6)
        gi = self.tip_geoms("index")
        gp = self.tip_geoms("pinky")
        R0 = rot([-1, 0, 0], [0, 1, 0], [0, 0, -1])
        roll = yaw = 0.0
        for _ in range(10):
            R = Rot.from_rotvec([0, 0, yaw]).as_matrix() @ Rot.from_rotvec([roll, 0, 0]).as_matrix() @ R0
            q = self.pose(R, fingers)
            pi, pp = self.rig.low_points(q, gi), self.rig.low_points(q, gp)
            zi, zp = pi[:, 2].min(), pp[:, 2].min()
            li, lp = pi[pi[:, 2] < zi + 0.0012], pp[pp[:, 2] < zp + 0.0012]
            ai, ap = li[np.argmin(li[:, 0])], lp[np.argmin(lp[:, 0])]
            dy = ap[1] - ai[1]
            droll = -np.arctan((zp - zi) / dy)
            dyaw = np.arctan((ap[0] - ai[0]) / dy)
            if abs(droll) < 1e-4 and abs(dyaw) < 1e-4:
                break
            roll += droll
            yaw += dyaw
        self.log(f"{label}: rake roll {roll:.4f} yaw {yaw:.4f} span {dy:.3f} dz {zp - zi:.5f} dx {ap[0] - ai[0]:.5f}")
        q[1] += centre - (ai[1] + ap[1]) / 2
        q[0] += (edge_max + 0.010) - min(ai[0], ap[0])
        q[2] += top + float(os.environ.get("RAKE_DZ", "0.0003" if self.s.hand == "sharpa" else "-0.0004")) - min(zi, zp)
        above = q.copy()
        above[2] += 0.10
        self.go(above, 90, f"{label}: approach above")
        self.go(q, 60, f"{label}: lower fingertips to desk")
        step = q.copy()
        for k in range(600):
            if self.s.done:
                break
            cs = self.sheet_corners()
            edges = [c[:, 0].max() for c in cs]
            spread = max(edges[1:]) - edges[0]
            corner = cs[0][:, 0].min()
            stop_gap = max(c[:, 0].min() for c in cs) - corner_target_x
            if spread <= 0.0003 and stop_gap <= 0.0004:
                break
            step[0] -= 0.0004
            self.go(step, 1, f"{label}: push", log=False)
            if k % 40 == 39:
                yaw0 = float(np.arctan2(self.s.data.xmat[self.s.checker.sheet_ids[0]][3],
                                        self.s.data.xmat[self.s.checker.sheet_ids[0]][0]))
                self.log(f"   k={k} corner={corner:.4f} spread={spread:.4f} yaw0={yaw0:.4f} "
                         f"y0={cs[0][:, 1].min():.4f} fence_x={step[0]:.4f}")
        yaws = [float(np.arctan2(self.s.data.xmat[b][3], self.s.data.xmat[b][0])) for b in self.s.checker.sheet_ids]
        self.log(f"{label}: pushed {k} increments, edge spread {spread:.5f}, corner {corner:.4f}, yaws "
                 f"{np.round(yaws, 4).tolist()}")
        # overtravel: keep pressing the squared stack against the paper stop (finger compliance limits the force),
        # so the open-loop rows tolerate small differences in when the sheets come flush
        over = float(os.environ.get("RAKE_OVER", "0.003"))
        if over > 0:
            step[0] -= over
            self.go(step, int(over / 0.0002), f"{label}: press stack against the paper stop")
        self.hold(15, f"{label}: settle")
        back = step.copy()
        back[2] += 0.012
        self.go(back, 30, f"{label}: lift fingertips")
        back[0] += 0.03
        back[2] += 0.09
        self.go(back, 60, f"{label}: lift away")

    def press_head(self, label="press stapler head"):
        """Index and middle fingertips press the handle top down to the hinge's bottom stop, then let it spring back."""
        s = self.s
        base = s.data.xpos[s.checker.base].copy()
        fingers = self.finger_targets(index_MCP_FE=0.25, index_PIP=0.3, middle_MCP_FE=0.25, middle_PIP=0.3,
                                      ring_MCP_FE=1.2, ring_PIP=1.4, pinky_MCP_FE=1.2, pinky_PIP=1.4,
                                      thumb_CMC_FE=0.3)
        R = rot([0, 0, -1], [0, 1, 0], [1, 0, 0])  # palm down, fingers +x, thumb +y
        q = self.pose(R, fingers)
        gi = self.tip_geoms("index") + self.tip_geoms("middle")
        pts = self.rig.low_points(q, gi)
        low = pts[np.argmin(pts[:, 2])]
        # handle top at x = base + 0.035 (behind the throat), centred on the handle
        handle_top = 0.783 + 0.020 + 0.0425
        press_x = base[0] + 0.030
        q[0] += press_x - low[0]
        q[1] += base[1] - np.mean(pts[:, 1])
        q[2] += handle_top + 0.012 - low[2]
        above = q.copy()
        above[2] += 0.10
        rise = self.target.copy()
        rise[2] = max(rise[2], 1.0)
        self.go(rise, 50, f"{label}: rise")
        self.go(above, 90, f"{label}: hand over the handle")
        self.go(q, 50, f"{label}: fingertips above the handle")
        down = q.copy()
        hinge = s.checker.hinge
        for k in range(300):
            if s.done:
                break
            if s.data.qpos[hinge] >= s.head_stop - 0.004:
                break
            down[2] -= 0.0004
            self.go(down, 1, f"{label}: press", log=False)
        self.log(f"{label}: pressed {k} increments, head {s.data.qpos[hinge]:.4f} stop {s.head_stop:.4f}")
        down[2] -= 0.002
        self.go(down, 10, f"{label}: bottom stop")
        self.hold(15, f"{label}: hold at bottom stop")
        self.go(q, 40, f"{label}: release, head springs back")
        self.go(above, 50, f"{label}: hand away")


def make_demo(output, hand="sharpa", stop_after=None, slack_rows=200):
    s = Session(hand=hand)
    c = Controller(s)
    c.hold(10, "settle")
    stop_face = s.data.geom_xpos[s.model.geom("paper_stop").id][0] + 0.0005
    c.feed_push(stop_face)
    if stop_after != "feed":
        c.press_head()
        c.hold(80, "released: hold")
    rows = [np.asarray(a) for a in s.actions]
    phases = list(c.phases[: len(rows)])
    success_step = s.steps if s.success else None
    # slack: hold rows after success (never executed: the episode ends at success)
    last = c.command(c.target)
    for _ in range(slack_rows):
        rows.append(last.copy())
        phases.append("hold (slack after success)")
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    s.save_trajectory(np.asarray(rows), out)
    np.save(out.with_suffix(".phases.npy"), np.asarray(phases))
    st = s.status()
    summary = {"success": st["success"], "success_step": success_step, "rows": len(rows), "stage": st["stage"],
               "reason": st["reason"], "state_sha": s.state_sha(), "hand": s.hand}
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
