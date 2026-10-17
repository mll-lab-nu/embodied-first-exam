"""Authoring controller (not shipped): open the rings, load both pages, close the rings, release.

Closed-loop scripted controller that reads the live Session state (page pose, ring pose, contacts) and records the
commanded actuator targets as open-loop rows; the recorded rows are then replayed in fresh processes.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ctl import INDEX, MIDDLE, THUMB, WRIST, Ctl  # noqa: E402
from runtime import Session  # noqa: E402
from scene import HOLE_MARGIN, OPEN_ANGLE, PAGE_HALF_T, PAGE_W, RING_RADIUS, STATIONS, WIRE_RADIUS  # noqa: E402

CURL3 = {19: 1.3, 20: 0.0, 21: 1.5, 22: 1.1, 23: 0.0, 24: 1.3, 25: 0.0, 26: 1.5, 27: 1.1}
CURL_MID = {15: 1.3, 16: 0.0, 17: 1.5, 18: 1.1}
R_I, R_T = 0.0081, 0.0094
W_CURL3 = {18: 1.3, 19: 0.0, 20: 1.6, 21: 1.0, 22: 1.3, 23: 0.0, 24: 1.6, 25: 1.0}
W_CURL_MID = {14: 1.3, 15: 0.0, 16: 1.6, 17: 1.0}
# Per-hand postures and finger groups (actuator indices); the Sharpa values are the ones that produced the oracle.
HANDMAP = {
    "sharpa": {
        "tips": {f: f"right_{f}_fingertip_collision" for f in ("thumb", "index", "middle")},
        "thumb": THUMB, "index": INDEX, "middle": MIDDLE, "r_i": R_I, "r_t": R_T,
        "point": {**CURL3, **CURL_MID, 11: 0.1, 12: 0.0, 13: 0.1, 14: 0.05, 6: 0.3, 7: 0.0, 8: 0.2, 10: 0.2},
        "pinch_seed": {**CURL3, 11: 0.2, 12: 0.0, 13: 0.2, 14: 0.1, 15: 0.2, 16: 0.0, 17: 0.2, 18: 0.1, 6: 1.2, 7: 0.0,
                       8: 0.4, 9: 0.0, 10: 0.3},
        "flat2": {**CURL3, 15: 0.1, 16: 0.0, 17: 0.1, 18: 0.05, 11: 0.1, 12: 0.0, 13: 0.1, 14: 0.05, 6: 0.3, 7: 0.0,
                  8: 0.2, 10: 0.2},
        "release_mcp": (11, 15), "release_floor": -0.17,
    },
    "wuji": {
        "tips": {"thumb": "r_wuji_r_thumb_tip_sensor_frame_collision1",
                 "index": "r_wuji_r_index_finger_tip_sensor_frame_collision1",
                 "middle": "r_wuji_r_middle_finger_tip_sensor_frame_collision1"},
        "thumb": [6, 7, 8, 9], "index": [10, 11, 12, 13], "middle": [14, 15, 16, 17], "r_i": 0.0075, "r_t": 0.0075,
        "point": {**W_CURL3, **W_CURL_MID, 10: 0.1, 11: 0.0, 12: 0.1, 13: 0.05, 6: 0.0, 7: 0.0, 8: 0.3, 9: 0.3},
        "pinch_seed": {**W_CURL3, 10: 0.2, 11: 0.0, 12: 0.2, 13: 0.1, 14: 0.2, 15: 0.0, 16: 0.2, 17: 0.1, 6: 0.5, 7: -0.5,
                       8: 0.3, 9: 0.3},
        "flat2": {**W_CURL3, 10: 0.1, 11: 0.0, 12: 0.1, 13: 0.05, 14: 0.1, 15: 0.0, 16: 0.1, 17: 0.05, 6: 0.0, 7: 0.0,
                  8: 0.3, 9: 0.3},
        "release_mcp": (10, 14), "release_floor": -1.0,
    },
}

DEFAULTS = {
    "press_frac": 0.8,
    "grip_down": 0.016,   # pinch point below the page's far (top) edge
    "pre_gap": 0.014,
    "squeeze": 0.006,
    "lift": 0.07,
    "phi0": 0.55, "phi_max": 1.05, "a_start": 3.75, "a_end": 2.4, "thread_steps": 120,
    "entry_dx": -0.012,   # hole centre offset before the tips (binder x)
    "release_open": 0.6,
    "close_y": 0.035, "close_x": -0.003, "close_stop": 0.22,
    "ki": 0.15, "imax": 0.012,
    "flatten_x": [0.11], "flatten_hi": 0.09, "flatten_lo": 0.012,
    "slide_out": 0.05,
    "desk_edge_x": 0.98, "overhang": 0.04, "drag_press": 0.0, "drag_step": 0.0008, "approach_out": 0.06, "thumb_dx": 0.006,
    "release_lift": 0.005,
}


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


class Demo(Ctl):
    def __init__(self, session, params=None, verbose=True):
        super().__init__(session, verbose)
        self.p = dict(DEFAULTS)
        self.p.update(params or {})
        self.H = HANDMAP[session.hand]
        self.tipnames = self.H["tips"]

    def with_fingers(self, q, values):
        q = np.array(q, float)
        for k, v in values.items():
            q[int(k)] = v
        return q

    # ------------------------------------------------------------------ geometry helpers
    def page_frame(self, k):
        b = self.s.data.body(f"page_{k}")
        return b.xpos.copy(), b.xmat.reshape(3, 3).copy()

    def binder_R(self):
        return self.s.data.body("binder").xmat.reshape(3, 3).copy()

    def ring_point(self, a, station=1):
        """Right open ring-half centre line at arc parameter a (a=pi: tip; a>pi: tangent extension)."""
        pl = self.s.data.body("right_ring_plate")
        y = STATIONS[station]
        if a <= np.pi:
            c = np.array([WIRE_RADIUS + RING_RADIUS * np.sin(a) - 0.008, y, RING_RADIUS * (1 - np.cos(a))])
        else:
            c = np.array([WIRE_RADIUS - 0.008 - RING_RADIUS * (a - np.pi), y, 2 * RING_RADIUS])
        return pl.xpos + pl.xmat.reshape(3, 3) @ c

    def page_R(self, phi):
        """Page frame leaning by phi from vertical towards +x (binder frame); holes at the bottom."""
        Rb = self.binder_R()
        xa = np.array([np.sin(phi), 0, np.cos(phi)])
        ya = np.array([0, 1.0, 0])
        return Rb @ np.c_[xa, ya, np.cross(xa, ya)]

    def page_in_wrist(self, k):
        wp, wR = self.wrist_pose()
        pp, pR = self.page_frame(k)
        return wR.T @ (pp - wp), wR.T @ pR

    def wrist_for_page(self, ppos, pR, rel, ctrl):
        rp, rR = rel
        wR = pR @ rR.T
        wp = ppos - wR @ rp
        return self.wrist_ctrl_for(wp, wR, ctrl)

    # ------------------------------------------------------------------ 1. open the rings (booster press)
    def open_rings(self):
        d = self.s.data
        p = self.p
        b = d.body("booster_1")
        tip = d.site("booster_tip_1").xpos.copy()
        press = b.xpos + (tip - b.xpos) * p["press_frac"]
        q0 = self.with_fingers(d.ctrl, self.H["point"])
        fdir = unit([0.3, 0, -1.0])
        R_I = self.H["r_i"]
        above = press + np.array([0, 0, R_I + 0.03])
        q1, e1 = self.ik(q0, {"index": above}, WRIST, finger_dir=fdir, w_orient=1.0)
        self.go(q1, 60, f"booster approach e={e1['index']:.4f}")
        touch = press + np.array([0, 0, R_I + 0.002])
        q2, _ = self.ik(q1, {"index": touch}, WRIST, finger_dir=fdir, w_orient=1.0)
        self.go(q2, 25, "booster touch")
        for _ in range(40):
            if self.s.status()["toggles_rad"][0] > OPEN_ANGLE - 0.03:
                break
            q2 = q2.copy()
            q2[2] -= 0.001
            self.go(q2, 2, "")
        self.report("booster pressed")
        q3 = q2.copy()
        q3[2] += 0.06
        self.go(q3, 30, "booster lift")

    # ------------------------------------------------------------------ 2. pick a page lying flat on the desk
    def slide_page(self, k):
        """Index and middle fingertips press on the printed face and drag the page +x until its far edge overhangs
        the desk edge by ``overhang`` (the desk is the only support; the page never leaves the desk)."""
        p = self.p
        pos, R = self.page_frame(k)
        xa, za = R[:, 0], R[:, 2]
        far = pos + xa * (PAGE_W - HOLE_MARGIN)
        dx = p["desk_edge_x"] + p["overhang"] - far[0]
        c = pos + xa * 0.065
        r_i = self.H["r_i"]
        down = PAGE_HALF_T + r_i - p["drag_press"]
        tg = {"index": c + np.array([0, -0.012, 0]) + za * down, "middle": c + np.array([0, 0.012, 0]) + za * down}
        q0 = self.with_fingers(self.s.data.ctrl, self.H["flat2"])
        fdir = unit([-0.35, 0, -1.0])
        var = WRIST + self.H["index"] + self.H["middle"]
        up = np.array([0, 0, 0.04])
        q1, e1 = self.ik(q0, {f: v + up for f, v in tg.items()}, var, finger_dir=fdir, w_orient=1.0)
        way = q1.copy()
        way[2] = max(self.s.data.ctrl[2], q1[2]) + 0.03
        self.go(way, 60, "")
        self.go(q1, 40, f"page{k} drag above e={max(e1.values()):.4f}")
        q2, e2 = self.ik(q1, tg, var, finger_dir=fdir, w_orient=1.0)
        # the fingertip collision capsules are tilted: put their lowest surface point ``drag_press`` into the page
        top = (pos + za * PAGE_HALF_T)[2]
        q2[2] += (top - p["drag_press"]) - self.lowest(q2, ("index", "middle"))
        q1[2] += (top + 0.03) - self.lowest(q1, ("index", "middle"))
        self.go(q1, 20, "")
        self.go(q2, 40, f"page{k} drag touch e={max(e2.values()):.4f}")
        start = self.page_frame(k)[0].copy()
        goal = p["desk_edge_x"] + p["overhang"]
        q = q2.copy()
        for j in range(int(2 * dx / p["drag_step"])):
            pp, pR = self.page_frame(k)
            if (pp + pR[:, 0] * (PAGE_W - HOLE_MARGIN))[0] >= goal:
                break
            q = q.copy()
            q[0] += p["drag_step"]
            self.step(q)
            if self.s.done:
                break
        self.hold(15, "")
        moved = self.page_frame(k)[0] - start
        if self.verbose:
            print(f"   page{k} dragged {np.round(moved * 1000, 1)} mm for a hand travel of {dx * 1000:.1f} mm", flush=True)
        q3 = q.copy()
        q3[2] += 0.04
        self.go(q3, 30, f"page{k} drag lift")
        return q3

    def lowest(self, q, fingers):
        """Lowest world z of the named fingertip collision geoms (capsule or mesh) at targets ``q``."""
        d = self.fk(q)
        z = []
        for f in fingers:
            g = self.m.geom(self.tipnames[f]).id
            R = d.geom_xmat[g].reshape(3, 3)
            if self.m.geom_type[g] == mujoco.mjtGeom.mjGEOM_CAPSULE:
                r, hl = self.m.geom_size[g][:2]
                z.append(d.geom_xpos[g][2] - r - hl * abs(R[2, 2]))
            else:
                mid = self.m.geom_dataid[g]
                a, n = self.m.mesh_vertadr[mid], self.m.mesh_vertnum[mid]
                z.append(float((d.geom_xpos[g] + self.m.mesh_vert[a:a + n] @ R.T)[:, 2].min()))
        return min(z)

    def grasp_flat(self, k):
        """Thumb under the overhanging far edge, index and middle on the printed face: pinch and lift the page."""
        p = self.p
        pos, R = self.page_frame(k)
        xa, za = R[:, 0], R[:, 2]
        far = pos + xa * (PAGE_W - HOLE_MARGIN)
        pinch = far - xa * p["grip_down"]
        back = za  # fingers on the printed (upper) face, thumb under the sheet
        gap = p["pre_gap"]
        R_I, R_T = self.H["r_i"], self.H["r_t"]
        pre = {"index": pinch + back * (PAGE_HALF_T + R_I + gap) + [0, -0.004, 0],
               "middle": pinch + back * (PAGE_HALF_T + R_I + gap) + [0, 0.014, 0] - xa * 0.004,
               "thumb": pinch - back * (PAGE_HALF_T + R_T + gap) + [0, 0.004, 0] + xa * p["thumb_dx"]}
        q0 = self.with_fingers(self.s.data.ctrl, self.H["pinch_seed"])
        fdir = unit(-xa)
        fingers = self.H["thumb"] + self.H["index"] + self.H["middle"]
        var = WRIST + fingers
        out = xa * p["approach_out"]
        q1, e1 = self.ik(q0, {f: v + out for f, v in pre.items()}, var, finger_dir=fdir, palm_dir=-back, w_orient=1.0)
        if self.verbose:
            print(f"grasp{k} pre err", {f: round(v, 4) for f, v in e1.items()}, "wrist", np.round(q1[:6], 3), flush=True)
        high = q1.copy()
        high[2] += 0.08
        cur = np.array(self.s.data.ctrl, float)
        way = high.copy()
        way[2] = max(cur[2], high[2])
        self.go(way, 80, "")
        self.go(high, 30, f"page{k} beyond the edge")
        self.go(q1, 50, f"page{k} thumb below the edge e={max(e1.values()):.4f}")
        q2, e2 = self.ik(q1, pre, var, finger_dir=fdir, palm_dir=-back, w_orient=1.0)
        self.go(q2, 50, f"page{k} pre-pinch e={max(e2.values()):.4f}")
        sq = gap + p["squeeze"]
        tgt = {"index": pre["index"] - back * sq, "middle": pre["middle"] - back * sq, "thumb": pre["thumb"] + back * sq}
        q3, e3 = self.ik(q2, tgt, fingers)
        self.go(q3, 30, f"page{k} pinch e={max(e3.values()):.4f}")
        self.hold(10)
        if self.verbose:
            d = self.s.data
            pp, pR = self.page_frame(k)
            side = {f: round(float((d.geom(self.tipnames[f]).xpos - pp) @ pR[:, 2]) * 1000, 1) for f in ("thumb", "index", "middle")}
            print(f"   pinch ik err {dict((f, round(v * 1000, 1)) for f, v in e3.items())} tip centre heights (mm) {side}", flush=True)
            qa = d.qpos[self.s.qadr]
            print("   joint err (actual-target) wrist", np.round((qa - d.ctrl)[:6], 4), "thumb/index/middle",
                  np.round((qa - d.ctrl)[fingers], 3), flush=True)
        q4 = q3.copy()
        q4[2] += 0.02
        self.go(q4, 30, "")
        q4[2] += p["lift"]
        self.go(q4, 50, f"page{k} lift")
        st = self.s.status()
        pp, pR = self.page_frame(k)
        if self.verbose:
            print(f"page{k} fingers", st["page_fingers"], "pos", np.round(pp, 4), "xaxis", np.round(pR[:, 0], 3), flush=True)
        return q4

    # ------------------------------------------------------------------ 3. thread the holes over the open ring halves
    def servo(self, k, pos, R, q):
        """One closed-loop control: wrist targets for the desired page pose, with integral position correction."""
        pp, _ = self.page_frame(k)
        self.integral = np.clip(self.integral + self.p["ki"] * (pos - pp), -self.p["imax"], self.p["imax"])
        rel = self.page_in_wrist(k)
        q = self.wrist_for_page(pos + self.integral, R, rel, q)
        self.step(q)
        return q

    def thread(self, k, q):
        p = self.p
        Rb = self.binder_R()
        bz = Rb[:, 2]
        tip = self.ring_point(np.pi)
        entry = tip + Rb[:, 0] * p["entry_dx"]
        self.integral = np.zeros(3)
        # carry high above the gap between the open halves, then lower the holes to the tip height
        rel = self.page_in_wrist(k)
        qa = self.wrist_for_page(entry + bz * 0.06, self.page_R(0.0), rel, q)
        self.go(qa, 110, f"page{k} carry")
        qb = qa
        for _ in range(30):
            qb = self.servo(k, entry + bz * 0.06, self.page_R(0.0), qb)
        for j in range(50):
            u = min(1.0, (j + 1) / 40)
            qb = self.servo(k, entry + bz * 0.06 * (1 - u), self.page_R(p["phi0"] * u), qb)
        self.report(f"page{k} lowered")
        self.debug_holes(k, "lowered")
        a_vals = np.linspace(p["a_start"], p["a_end"], p["thread_steps"])
        for j, a in enumerate(a_vals):
            if j % 15 == 0:
                self.debug_holes(k, f"a={a:.2f}")
            t = Rb.T @ (self.ring_point(min(a, np.pi) - 0.02) - self.ring_point(min(a, np.pi) + 0.02))
            phi = float(np.clip(np.arctan2(-t[2], t[0]), p["phi0"], p["phi_max"]))
            qb = self.servo(k, self.ring_point(a), self.page_R(phi), qb)
            if self.s.done:
                break
        self.report(f"page{k} threaded")
        self.debug_holes(k, "threaded")
        if self.verbose:
            dd = self.s.data
            print("   integral", np.round(self.integral * 1000, 1), flush=True)
            for c in dd.contact[:dd.ncon]:
                n1, n2 = self.m.geom(c.geom[0]).name, self.m.geom(c.geom[1]).name
                if ("right" in n1 + n2 or "wuji" in n1 + n2) and "page" in n1 + n2:
                    print("   threaded contact", n1, n2, round(c.dist, 4), flush=True)
        return qb

    def debug_holes(self, k, tag):
        if not self.verbose:
            return
        st = self.s.status()
        holes = [(h["hole"], h["open_threaded"], round(h["nearest_wire_m"], 4)) for h in st["holes"] if h["page"] == k]
        pp, pR = self.page_frame(k)
        print(f"  {tag}: page{k} holes {holes} pos {np.round(pp, 4)} xaxis {np.round(pR[:, 0], 3)}", flush=True)
        Rb = self.binder_R()
        bp = self.s.data.body("binder").xpos
        for i, y in enumerate(STATIONS):
            h = Rb.T @ (pp + pR[:, 1] * y - bp)
            t = Rb.T @ (self.ring_point(np.pi, i) - bp)
            print(f"     hole{i} (binder) {np.round(h * 1000, 1)} tip {np.round(t * 1000, 1)}", flush=True)

    # ------------------------------------------------------------------ 4. release the page onto the cover
    def release(self, k, q):
        """Lift the index and middle off the printed face, slide the thumb out from under the far edge, retreat."""
        p = self.p
        _, pR = self.page_frame(k)
        xa = pR[:, 0]
        # unload: undo the integral push of the servo before letting go
        q = np.array(q, float)
        q[:3] -= self.integral
        q[2] += p["release_lift"]
        self.go(q, 15, f"page{k} unload")
        a, b = self.H["release_mcp"]
        floor = self.H["release_floor"]
        q1 = self.with_fingers(q, {a: max(q[a] - 0.35, floor), b: max(q[b] - 0.35, floor)})
        q1[2] += 0.008
        self.go(q1, 20, f"page{k} open")
        self.hold(10, "")
        q2 = q1.copy()
        horiz = xa * np.array([1, 1, 0]) / max(np.linalg.norm(xa[:2]), 1e-6)
        q2[:3] += horiz * p["slide_out"] + np.array([0, 0, 0.004])
        for j in range(4):
            self.go(q1 + (q2 - q1) * (j + 1) / 4, 10, f"page{k} slide out {j}")
        q3 = self.with_fingers(q2, {6: max(q2[6] - 0.4, -0.17)})
        q3[2] += 0.06
        self.go(q3, 30, f"page{k} retreat")
        self.hold(40, f"page{k} settle")
        self.debug_holes(k, "settled")
        return q3

    # ------------------------------------------------------------------ 5. close the rings
    def close_rings(self):
        p = self.p
        d = self.s.data
        Rb = self.binder_R()
        bpos = d.body("binder").xpos.copy()
        plate = d.body("right_ring_plate")
        centre = bpos + Rb @ np.array([p["close_x"], p["close_y"], 0.0])
        centre[2] = plate.xpos[2] + 0.004
        q0 = self.with_fingers(d.ctrl, self.H["point"])
        fdir = unit([0.2, 0, -1.0])
        R_I = self.H["r_i"]
        above = centre + np.array([0, 0, R_I + 0.04])
        q1, e1 = self.ik(q0, {"index": above}, WRIST, finger_dir=fdir, w_orient=1.0)
        cur = np.array(d.ctrl, float)
        way = q1.copy()
        way[2] = max(cur[2], q1[2]) + 0.03
        self.go(way, 60, "")
        self.go(q1, 40, f"close approach e={e1['index']:.4f}")
        touch = centre + np.array([0, 0, R_I + 0.001])
        q2, _ = self.ik(q1, {"index": touch}, WRIST, finger_dir=fdir, w_orient=1.0)
        self.go(q2, 30, "close touch")
        for _ in range(60):
            # past the over-centre point the housing spring snaps the rings shut by itself
            if max(self.s.status()["toggles_rad"]) < p["close_stop"]:
                break
            q2 = q2.copy()
            q2[2] -= 0.001
            self.go(q2, 2, "")
        self.report("close pressed")
        q3 = q2.copy()
        q3[2] += 0.10
        self.go(q3, 40, "close lift")

    def flatten(self):
        """Press both pages down flat on the back cover so their holes slide round to the side of the closed rings."""
        p = self.p
        d = self.s.data
        Rb = self.binder_R()
        bpos = d.body("binder").xpos.copy()
        q0 = self.with_fingers(d.ctrl, self.H["flat2"])
        fdir = unit([0.2, 0, -1.0])
        for x_rel in p["flatten_x"]:
            spot = bpos + Rb @ np.array([x_rel, 0.0, 0.0])
            hi = spot + Rb[:, 2] * p["flatten_hi"]
            lo = spot + Rb[:, 2] * p["flatten_lo"]
            q1, _ = self.ik(q0, {"index": hi + [0, -0.01, 0], "middle": hi + [0, 0.01, 0]}, WRIST, finger_dir=fdir,
                            w_orient=1.0)
            cur = np.array(d.ctrl, float)
            way = q1.copy()
            way[2] = max(cur[2], q1[2]) + 0.02
            self.go(way, 40, "")
            self.go(q1, 30, f"flatten above {x_rel:.3f}")
            q2, _ = self.ik(q1, {"index": lo + [0, -0.01, 0], "middle": lo + [0, 0.01, 0]}, WRIST, finger_dir=fdir,
                            w_orient=1.0)
            self.go(q2, 60, f"flatten press {x_rel:.3f}")
            self.hold(15, "")
            q3 = q2.copy()
            q3[2] += 0.10
            self.go(q3, 40, f"flatten lift {x_rel:.3f}")
        self.hold(20, "flattened")
        if self.verbose:
            for k in range(2):
                self.debug_holes(k, "flat")

    def finish(self, n=120):
        for _ in range(n):
            self.step(self.s.data.ctrl.copy())
            if self.s.done:
                break
        self.report("final hold")


def run(hand="sharpa", params=None, verbose=True, snaps=None, cam="closeup", phases="open,page1,page0,close,flatten,finish"):
    s = Session(hand=hand)
    demo = Demo(s, params, verbose)
    if snaps:
        demo.snaps, demo.snap_cam = [], cam
    for phase in phases.split(","):
        if s.done:
            break
        if phase == "open":
            demo.open_rings()
        elif phase.startswith("page"):
            k = int(phase[4:])
            demo.slide_page(k)
            if s.done:
                break
            q = demo.grasp_flat(k)
            if s.done:
                break
            q = demo.thread(k, q)
            if s.done:
                break
            demo.release(k, q)
        elif phase == "close":
            demo.close_rings()
        elif phase == "flatten":
            demo.flatten()
        elif phase == "finish":
            demo.finish()
    return s, demo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hand", default="sharpa")
    ap.add_argument("--out", default="")
    ap.add_argument("--phases", default="open,page1,page0,close,flatten,finish")
    ap.add_argument("--snaps", default="")
    ap.add_argument("--cam", default="closeup")
    ap.add_argument("--params", default="{}")
    ap.add_argument("--slack", type=int, default=150)
    args = ap.parse_args()
    s, demo = run(args.hand, json.loads(args.params), True, args.snaps, args.cam, args.phases)
    if args.snaps and getattr(demo, "snaps", None):
        from PIL import Image, ImageDraw

        tiles = []
        for label, img in demo.snaps[-16:]:
            im = Image.fromarray(img)
            ImageDraw.Draw(im).text((5, 5), label, fill=(255, 0, 0))
            tiles.append(np.asarray(im))
        while len(tiles) % 4:
            tiles.append(np.zeros_like(tiles[0]))
        rows = [np.concatenate(tiles[i:i + 4], 1) for i in range(0, len(tiles), 4)]
        Image.fromarray(np.concatenate(rows, 0)).save(args.snaps)
    if args.out:
        rows = np.asarray(demo.rows)
        if args.slack:
            # Slack after success: hold the last targets (the episode ends at success; these rows are never executed
            # by a correct replay, they only protect the oracle against tiny numerical differences).
            rows = np.r_[rows, np.repeat(rows[-1:], args.slack, axis=0)]
        s.save_trajectory(rows, args.out)
        Path(args.out).with_suffix(".log").write_text("\n".join(demo.log) + "\n")
    st = s.status()
    print(json.dumps({k: v for k, v in st.items() if k not in ("holes", "page_pos")}, default=str)[:900])


if __name__ == "__main__":
    main()
