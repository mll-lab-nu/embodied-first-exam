"""Authoring-only closed-loop scripted controller (reads Session state, records open-loop rows).

Grasp: both hands hang fingers-down outside the two ends of the long tray axis; the index..pinky fingertips are
curled inward and pushed through the open handle slot under the handle bar (a hook grip), then the wrist stages lift
the tray 100 mm, carry it around the bottle (detour to y = -0.17) and across the counter gap, set it down on the
receiving counter, pull the fingertips back out of the slots and rise. The tray is levelled during the carry by
rotating both wrists about y (roll) and by differential wrist heights (pitch).

Usage: python tools/controller.py --hand sharpa --out solution/trajectory.npz [--slack 120]
       python tools/controller.py --hand wuji --out solution/wuji/trajectory.npz
Per-hand parameters: tools/oracle_params.json (Wuji: adducted outer fingers, equalised fingertip heights, deeper hook,
fingers half-opened before the fingertips are withdrawn).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from runtime import Session  # noqa: E402

FINGERS = ("index", "middle", "ring", "pinky")


def smooth(a):
    a = np.clip(a, 0.0, 1.0)
    return a * a * a * (10 + a * (-15 + 6 * a))


class Driver:
    def __init__(self, hand="sharpa", params=None):
        self.s = Session(hand=hand)
        self.p = {"mcp": 0.1, "pip": 0.9, "dip": 0.6, "insert": 0.022, "slot_z": 0.894, "clear": 0.005,
                  "lift": 0.10, "level_gain": 0.5, "carry_level": False, "unload": 0.004, **(params or {})}
        self.idx = {n: i for i, n in enumerate(self.s.actuator_names)}
        self.ctrl = self.s.hold_action()
        self.rows = []
        self.log = []

    # --------------------------------------------------------------- primitives
    def a(self, name):
        return self.idx[name]

    def set(self, values):
        for k, v in values.items():
            self.ctrl[self.idx[k]] = v

    def step(self, n=1, level=False):
        for _ in range(n):
            if level:
                self.level()
            lo, hi = self.s.model.actuator_ctrlrange.T
            self.ctrl = np.clip(self.ctrl, lo, hi)
            self.rows.append(self.ctrl.copy())
            st = self.s.step(self.ctrl)
            self.step_track(st)
            if st["done"]:
                return st
        return self.s.status()

    def move(self, target, n, level=False):
        """Smooth (quintic) move of the named targets; increments, so levelling corrections persist."""
        start = {k: self.ctrl[self.idx[k]] for k in target}
        st = None
        prev = 0.0
        for i in range(1, n + 1):
            w = smooth(i / n)
            for k, v in target.items():
                self.ctrl[self.idx[k]] += (v - start[k]) * (w - prev)
            prev = w
            st = self.step(1, level)
            if st["done"]:
                break
        return st

    def finger_joints(self, side):
        """(mcp, pip, dip) actuator names of index, middle, ring, little finger for the selected hand."""
        if self.s.hand == "sharpa":
            return [(f"{side}_hand_{f}_MCP_FE", f"{side}_hand_{f}_PIP", f"{side}_hand_{f}_DIP") for f in FINGERS]
        return [tuple(f"{side}_wuji_{side}_{k}J{j}" for j in (0, 2, 3)) for k in ("FF", "MF", "RF", "LF")]

    def tips(self, side):
        """Per finger: inner point of the fingertip (closest to the tray centre line): x, y (signed), z, radius.

        Sharpa: the inner end sphere centre of the fingertip capsule and its radius; Wuji: the mean of the distal
        collision-mesh vertices within 4 mm of the innermost one (radius 0, already the surface)."""
        import mujoco

        m, d = self.s.model, self.s.data
        out = []
        if self.s.hand == "sharpa":
            for f in FINGERS:
                g = m.geom(f"{side}_hand_{f}_fingertip_collision").id
                p, ax = d.geom_xpos[g], d.geom_xmat[g].reshape(3, 3)[:, 2]
                h, r = m.geom_size[g, 1], m.geom_size[g, 0]
                e = min((p + h * ax, p - h * ax), key=lambda q: abs(q[1]))
                out.append([*e, r])
            return np.array(out)
        for f in ("index_finger", "middle_finger", "ring_finger", "pinky"):
            pts = []
            for part in ("distal", "tip_sensor_frame"):
                g = m.geom(f"{side}_wuji_{side}_{f}_{part}_collision1").id
                mid = m.geom_dataid[g]
                v = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]]
                pts.append(v @ d.geom_xmat[g].reshape(3, 3).T + d.geom_xpos[g])
            P = np.vstack(pts)
            ay = np.abs(P[:, 1])
            near = P[ay <= ay.min() + 0.004]
            q = near.mean(0)
            q[1] = np.sign(q[1]) * ay.min()
            out.append([*q, 0.0])
        return np.array(out)

    def tray_rot(self):
        d = self.s.data
        R = d.body("tray").xmat.reshape(3, 3)
        # small-angle roll about y (z axis toward +x) and pitch about x (z axis toward -y)
        return float(np.arcsin(np.clip(R[0, 2], -1, 1))), float(-np.arcsin(np.clip(R[1, 2], -1, 1)))

    def roll(self, side, delta):
        """Rotate a wrist about world y by ``delta`` while keeping its fingertips (L below the wrist) in place."""
        ry = self.a(f"{side}_wrist_ry_act")
        old = self.ctrl[ry]
        self.ctrl[ry] = old + delta
        self.ctrl[self.a(f"{side}_wrist_x_act")] += self.L * (np.sin(old + delta) - np.sin(old))

    def level(self):
        about_y, about_x = self.tray_rot()
        g = self.p["level_gain"]
        for side in "lr":
            self.roll(side, -g * 0.2 * about_y)
        # rotation about +x raises the +y end: lower the left (+y) hand, raise the right (-y) hand
        dz = g * 0.2 * about_x * 0.26
        self.ctrl[self.a("l_wrist_z_act")] -= dz
        self.ctrl[self.a("r_wrist_z_act")] += dz

    # --------------------------------------------------------------- phases
    def run(self, slack=120):
        st = self._run()
        self.success_step = st["steps"] if st["success"] else None
        if st["success"]:
            # slack: hold rows after success (the episode ends at success; graders stop there)
            hold = self.rows[-1].copy()
            self.rows.extend(hold.copy() for _ in range(slack))
        return st

    def step_track(self, st):
        g = st["features"].get("glasses", {}) if st.get("features") else {}
        for v in g.values():
            self.max_tilt = max(getattr(self, "max_tilt", 0.0), v["tilt_deg"])
        self.max_tray_tilt = max(getattr(self, "max_tray_tilt", 0.0), st["features"].get("tray_tilt_deg", 0.0))

    def _run(self):
        p = self.p
        shape = {}
        for side in "lr":
            for mcp, pip, dip in self.finger_joints(side):
                shape[mcp], shape[pip], shape[dip] = p["mcp"], p["pip"], p["dip"]
            for name, value in p.get("abd", {}).items():  # Wuji: adduct the outer fingers toward the middle finger
                shape[f"{side}_wuji_{side}_{name}J1"] = value
        self.move(shape, 25)
        self.step(10)
        # level the four hooks: rotate each wrist about y so the fingertip line is horizontal
        self.L = float(self.s.data.body("l_hand_palm").xpos[2] - self.tips("l")[:, 2].mean())
        self.log.append(("shaped", self.s.status()["steps"], self.tips("l").round(4).tolist()))
        for side in "lr":
            e = self.tips(side)
            slope = np.polyfit(e[:, 0], e[:, 2], 1)[0]
            self.roll(side, float(np.arctan(slope)) * self.p.get("prelevel", 1.0))
        self.step(20)
        # equalise the four fingertip heights per hand (MCP down / DIP up keeps the distal phalanx direction)
        for _ in range(int(p.get("equalize", 0))):
            for side in "lr":
                e = self.tips(side)
                for (mcp, pip, dip), z in zip(self.finger_joints(side), e[:, 2]):
                    delta = (z - e[:, 2].mean()) / 0.08
                    self.ctrl[self.a(mcp)] -= delta
                    self.ctrl[self.a(dip)] += delta
            self.step(15)
        self.log.append(("equalised", self.s.status()["steps"], self.tips("l")[:, 2].round(4).tolist()))
        # hover outside the handle slots, fingertips 50 mm above slot height
        for z_extra, n in ((0.05, 25), (0.0, 45), (0.0, 12)):
            target = {}
            for side, sign in (("l", 1), ("r", -1)):
                e = self.tips(side)
                inner = np.abs(e[:, 1]) - e[:, 3]
                y_inner = inner.min() if p.get("clear_min") else inner.mean()
                z = e[:, 2].mean()
                target[f"{side}_wrist_y_act"] = self.ctrl[self.a(f"{side}_wrist_y_act")] + sign * (0.26 + p["clear"] - y_inner)
                target[f"{side}_wrist_z_act"] = self.ctrl[self.a(f"{side}_wrist_z_act")] + (p["slot_z"] + z_extra - z)
            self.move(target, n)
            self.step(5)
        self.log.append(("lowered", self.s.status()["steps"], self.tips("l")[:, 1:3].round(4).tolist()))
        # push the fingertips through the slots
        self.move({"l_wrist_y_act": self.ctrl[self.a("l_wrist_y_act")] - p["insert"],
                   "r_wrist_y_act": self.ctrl[self.a("r_wrist_y_act")] + p["insert"]}, 30)
        self.step(10)
        self.log.append(("inserted", self.s.status()["steps"], self.tips("l")[:, 1:3].round(4).tolist()))
        # lift 100 mm while levelling
        z0 = {s: self.ctrl[self.a(f"{s}_wrist_z_act")] for s in "lr"}
        st = self.move({"l_wrist_z_act": z0["l"] + p["lift"], "r_wrist_z_act": z0["r"] + p["lift"]}, 80, level=True)
        st = self.step(30, level=True)
        self.log.append(("lifted", st["steps"], st["stage"], self.s.data.body("tray").xpos.round(4).tolist(),
                         [round(np.degrees(x), 2) for x in self.tray_rot()]))
        if st["done"]:
            return st
        # carry: tray centre waypoints (relative displacement applied to both hands)
        start = self.s.data.body("tray").xpos[:2].copy()
        hand0 = {s: (self.ctrl[self.a(f"{s}_wrist_x_act")], self.ctrl[self.a(f"{s}_wrist_y_act")]) for s in "lr"}
        target = np.asarray(self.s.config["target_xy"], float)
        path = [(np.array([0.37, -0.17]), 110), (np.array([0.76, -0.17]), 160), (target, 110)]
        for goal, n in path:
            here = {s: (self.ctrl[self.a(f"{s}_wrist_x_act")], self.ctrl[self.a(f"{s}_wrist_y_act")]) for s in "lr"}
            tgt = {}
            for s in "lr":
                tgt[f"{s}_wrist_x_act"] = hand0[s][0] + goal[0] - start[0]
                tgt[f"{s}_wrist_y_act"] = hand0[s][1] + goal[1] - start[1]
            st = self.move(tgt, n, level=self.p["carry_level"])
            if st["done"]:
                return st
            self.log.append(("waypoint", st["steps"], self.s.data.body("tray").xpos.round(4).tolist()))
        st = self.step(20, level=True)
        # correct the residual xy error of the tray centre before lowering
        err = target - self.s.data.body("tray").xpos[:2]
        self.move({**{f"{s}_wrist_x_act": self.ctrl[self.a(f"{s}_wrist_x_act")] + err[0] for s in "lr"},
                   **{f"{s}_wrist_y_act": self.ctrl[self.a(f"{s}_wrist_y_act")] + err[1] for s in "lr"}}, 25,
                  level=True)
        st = self.step(15, level=True)
        self.log.append(("aligned", st["steps"], self.s.data.body("tray").xpos.round(4).tolist()))
        # lower onto the receiving counter
        drop = self.s.data.body("tray").xpos[2] - self.s.config["table_top_z"]
        z0 = {s: self.ctrl[self.a(f"{s}_wrist_z_act")] for s in "lr"}
        st = self.move({f"{s}_wrist_z_act": z0[s] - drop + 0.006 for s in "lr"}, 90, level=True)
        st = self.move({f"{s}_wrist_z_act": z0[s] - drop - p["unload"] for s in "lr"}, 40)
        st = self.step(15)
        self.log.append(("set down", st["steps"], st["features"]["tray_on_target_counter"],
                         self.s.data.body("tray").xpos.round(4).tolist()))
        if st["done"]:
            return st
        # pull the fingertips out of the slots, open the hands and rise
        if p.get("open_before_withdraw"):
            st = self.move({k: p["open_before_withdraw"] * v for k, v in shape.items()}, 30)
            if st["done"]:
                return st
            self.log.append(("opened", st["steps"], st["features"]["tray_tilt_deg"]))
        st = self.move({"l_wrist_y_act": self.ctrl[self.a("l_wrist_y_act")] + p["insert"] + 0.012,
                        "r_wrist_y_act": self.ctrl[self.a("r_wrist_y_act")] - p["insert"] - 0.012}, 35)
        if st["done"]:
            return st
        self.log.append(("withdrawn", st["steps"], self.tips("l")[:, 1:3].round(4).tolist()))
        if p.get("open_first"):
            st = self.move({k: 0.0 for k in shape}, 30)
            if st["done"]:
                return st
        z0 = {s: self.ctrl[self.a(f"{s}_wrist_z_act")] for s in "lr"}
        st = self.move({**{f"{s}_wrist_z_act": z0[s] + 0.08 for s in "lr"}, **{k: 0.0 for k in shape}}, 45)
        if st["done"]:
            return st
        for _ in range(400):
            st = self.step(1)
            if st["done"]:
                break
        return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hand", default="sharpa")
    ap.add_argument("--out")
    ap.add_argument("--slack", type=int, default=120)
    ap.add_argument("--params", default="{}")
    args = ap.parse_args()
    params = json.loads((HERE / "tools/oracle_params.json").read_text())[args.hand]
    drv = Driver(args.hand, {**params, **json.loads(args.params)})
    st = drv.run(args.slack)
    for item in drv.log:
        print(item)
    st.pop("features", None)
    print(json.dumps(st))
    print("rows", len(drv.rows), "success_step", drv.success_step, "max_glass_tilt_deg", round(drv.max_tilt, 2),
          "max_tray_tilt_deg", round(drv.max_tray_tilt, 2))
    if args.out:
        drv.s.save_trajectory(np.asarray(drv.rows), args.out)
        print("saved", args.out)


if __name__ == "__main__":
    main()
