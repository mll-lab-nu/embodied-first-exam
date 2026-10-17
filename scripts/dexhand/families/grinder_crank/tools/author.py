"""Authoring controller (not shipped): closed-loop scripted two-hand grinder operation, recorded as open-loop rows.

The controller reads simulator state (knob position, crank angle) only to choose the next actuator targets; the
recorded rows are plain motor targets and are later replayed open loop by ``replay.py``.

    python tools/author.py --hand sharpa --out rows.npz [--param key=value ...]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from rig import Layout, stage_angles  # noqa: E402
from runtime import Session  # noqa: E402

FINGERS = ("thumb", "index", "middle", "ring", "pinky")

DEFAULTS = dict(
    # right-hand pinch (Sharpa joint names without the side prefix)
    r_open=dict(index_MCP_FE=1.5, index_PIP=1.2, index_DIP=0.7, middle_MCP_FE=1.5, middle_PIP=1.2, middle_DIP=0.7,
                ring_MCP_FE=1.5, ring_PIP=1.6, ring_DIP=1.0, pinky_MCP_FE=1.5, pinky_PIP=1.6, pinky_DIP=1.0,
                thumb_CMC_FE=0.6, thumb_CMC_AA=0.0, thumb_MCP_FE=0.4, thumb_IP=0.0),
    r_thumb=dict(thumb_CMC_FE=1.2305, thumb_CMC_AA=-0.0605, thumb_MCP_FE=0.6219, thumb_IP=0.0),
    r_close=dict(index_MCP_FE=1.4689, index_PIP=0.753, index_DIP=0.4518, middle_MCP_FE=1.4689, middle_PIP=0.753,
                 middle_DIP=0.4518),
    # bulb centre relative to the right wrist root in world coordinates (claw pose, rx = pi); found by
    # tools/search_pinch.py (CEM scored by crank progress)
    r_knob_offset=(0.0902, 0.02, -0.0834),
    r_angles=(3.14, 0.0, 0.0),
    r_start=(0.30, -0.20, 1.10),
    # left-hand power grasp of the cup
    l_angles=(1.5707963267948966, 0.0, -3.14),
    l_grasp=(0.557, 0.053, 0.795),
    l_open=dict(index_MCP_FE=0.0, middle_MCP_FE=0.0, ring_MCP_FE=0.0, pinky_MCP_FE=0.0, thumb_CMC_FE=1.0,
                thumb_CMC_AA=-0.35, thumb_MCP_FE=1.4, thumb_MCP_AA=-0.35, thumb_IP=1.6),
    l_close=dict(index_MCP_FE=1.2, index_PIP=1.2, index_DIP=0.8, middle_MCP_FE=1.2, middle_PIP=1.2, middle_DIP=0.8,
                 ring_MCP_FE=0.5, ring_PIP=0.5, ring_DIP=0.5, pinky_MCP_FE=0.5, pinky_PIP=0.5, pinky_DIP=0.5,
                 thumb_CMC_FE=1.15, thumb_CMC_AA=-0.35, thumb_MCP_FE=1.4, thumb_MCP_AA=-0.35, thumb_IP=1.7),
    l_close_steps=20,
    l_path=((0.07, 0.03, 0.0), (0.0, 0.03, 0.0)),
    turn_rate=2 * math.pi / 2.5,  # rad/s commanded knob speed
    lead=0.12,  # rad ahead of the measured knob angle
    target_turns=2.06,
    lift=0.06,
    hold_extra=60,
    crank_max_steps=3000,
    search_only=False,
    direction=1,
    # wave 3: rotate the whole left counterhold (grasp pose, approach path and withdrawal) about the cup's vertical axis
    # by this angle (rad, +z); the cup is rotationally symmetric, so the grasp is the same physical grasp elsewhere on
    # the cup (lets the Marvin left arm reach it from the robot's side).
    l_rot=0.0,
    l_withdraw=((0.06, 0.005, 0.0), (0.07, 0.13, 0.03)),
)


class Author:
    def __init__(self, hand="sharpa", **params):
        self.p = {**DEFAULTS, **params}
        if self.p["l_angles"] is None:
            self.p["l_angles"] = tuple(stage_angles((0, -1, 0), (1, 0, 0)))
        if self.p["l_rot"]:
            from scipy.spatial.transform import Rotation

            Rz = Rotation.from_euler("z", self.p["l_rot"])
            centre = np.array([0.45, 0.0, 0.0])  # grinder base centre (task.json grinder.base_position), vertical axis
            g = np.asarray(self.p["l_grasp"], float)
            self.p["l_grasp"] = tuple(centre + Rz.apply(g - centre) * [1, 1, 0] + [0, 0, g[2]])
            self.p["l_angles"] = tuple((Rz * Rotation.from_euler("XYZ", self.p["l_angles"])).as_euler("XYZ"))
            self.p["l_path"] = tuple(tuple(Rz.apply(np.asarray(o, float))) for o in self.p["l_path"])
            self.p["l_withdraw"] = tuple(tuple(Rz.apply(np.asarray(o, float))) for o in self.p["l_withdraw"])
        self.s = Session(hand=hand)
        self.L = Layout(self.s)
        self.rows, self.phases = [], []
        self.row = self.s.hold_action()
        m = self.s.model
        self.knob = m.body("knob").id
        self.grinder = m.body("grinder").id

    # -------------------------------------------------------------- helpers
    def wrist(self, side, pos, ang):
        return {f"{side}_wrist_{a}_act": float(v) for a, v in zip(("x", "y", "z", "rx", "ry", "rz"), (*pos, *ang))}

    def fingers(self, side, values):
        return {f"{side}_{k}": float(v) for k, v in values.items()}

    def current(self, name):
        return float(self.row[self.L.index[name]])

    def emit(self, values, phase):
        self.row = self.L.set(self.row, values)
        st = self.s.step(self.row)
        self.rows.append(self.row.copy())
        self.phases.append(phase)
        return st

    def move(self, side, pos, ang, steps, phase, finger_to=None):
        names = ("x", "y", "z", "rx", "ry", "rz")
        start = np.array([self.current(f"{side}_wrist_{a}_act") for a in names])
        goal = np.array([*pos, *ang], dtype=float)
        finger_to = {k: v for k, v in (finger_to or {}).items() if f"{side}_{k}" in self.L.index}
        f_start = {k: self.current(f"{side}_{k}") for k in finger_to}
        st = None
        for k in range(1, steps + 1):
            u = 0.5 - 0.5 * math.cos(math.pi * k / steps)
            vals = {f"{side}_wrist_{a}_act": float(v) for a, v in zip(names, start + u * (goal - start))}
            for kname, v in (finger_to or {}).items():
                vals[f"{side}_{kname}"] = f_start[kname] + u * (v - f_start[kname])
            st = self.emit(vals, phase)
            if st["done"]:
                break
        return st

    def knob_angle(self):
        c = self.crank_center()
        k = self.s.data.xpos[self.knob]
        return math.atan2(k[1] - c[1], k[0] - c[0])

    def crank_center(self):
        d = self.s.data
        return d.xpos[self.grinder] + d.xmat[self.grinder].reshape(3, 3) @ np.array([0, 0, 0.175])

    # -------------------------------------------------------------- script
    def run(self, verbose=True):
        p, s = self.p, self.s
        # 0. settle
        for _ in range(10):
            self.emit({}, "settle")
        # 1. left hand: approach the cup with an open hand and close a power grasp around it
        here = [self.current(f"left_wrist_{a}_act") for a in "xyz"]
        self.move("left", here, p["l_angles"], 20, "left preshape", finger_to=p["l_open"])
        for k, off in enumerate(p["l_path"]):
            target = tuple(np.asarray(p["l_grasp"]) + np.asarray(off))
            self.move("left", target, p["l_angles"], 40 if k == 0 else 25, "left approach")
        self.move("left", p["l_grasp"], p["l_angles"], 25, "left approach")
        close = p["l_close"]
        for group in (("thumb",), ("index", "middle"), ("ring", "pinky")):
            part = {k: v for k, v in close.items() if k.split("_")[0] in group}
            st = self.move("left", p["l_grasp"], p["l_angles"], p["l_close_steps"], "left grasp", finger_to=part)
        for _ in range(10):
            st = self.emit({}, "left grasp")
        if verbose:
            print("after left grasp", {k: st[k] for k in ("hand_contacts", "tilt_deg", "slide_m", "reason")}, flush=True)
        # 2. right hand: preshape above the knob, descend, pinch
        knob = s.data.xpos[self.knob] + np.array([0, 0, 0.014])
        off = np.asarray(p["r_knob_offset"])
        above = knob - off + np.array([0, 0, 0.05])
        self.move("right", above, p["r_angles"], 50, "right approach", finger_to=p["r_open"])
        self.move("right", knob - off, p["r_angles"], 30, "right descend")
        st = self.move("right", knob - off, p["r_angles"], 15, "right pinch", finger_to=p["r_thumb"])
        st = self.move("right", knob - off, p["r_angles"], 20, "right pinch", finger_to=p["r_close"])
        for _ in range(10):
            st = self.emit({}, "right pinch")
        if verbose:
            print("after pinch", {k: st[k] for k in ("hand_contacts", "tilt_deg", "slide_m", "reason")}, flush=True)
        # 3. crank: wrist follows the knob circle clockwise (decreasing world angle), fixed hand orientation.
        target_rad = 2 * math.pi * p["target_turns"]
        root_minus_knob = np.array([self.current(f"right_wrist_{a}_act") for a in "xyz"]) - (
            s.data.xpos[self.knob] + np.array([0, 0, 0.014]))
        phi_cmd = self.knob_angle()
        z_knob = float(s.data.xpos[self.knob][2] + 0.014)
        dphi = p["turn_rate"] * s.control_dt
        k = 0
        while p["direction"] * st["net_clockwise_deg"] < math.degrees(target_rad) and not st["done"] and k < p["crank_max_steps"]:
            phi = self.knob_angle()
            # unwrap the measured angle near the command
            phi = phi_cmd + ((phi - phi_cmd + math.pi) % (2 * math.pi) - math.pi)
            if p["direction"] > 0:
                phi_cmd = max(phi_cmd - dphi, phi - p["lead"])  # clockwise = decreasing angle, bounded lead
            else:  # negative test only: counter-clockwise cranking
                phi_cmd = min(phi_cmd + dphi, phi + p["lead"])
            c = self.crank_center()
            knob_target = np.array([c[0] + 0.08 * math.cos(phi_cmd), c[1] + 0.08 * math.sin(phi_cmd), z_knob])
            st = self.emit(self.wrist("right", knob_target + root_minus_knob, p["r_angles"]), "crank")
            k += 1
            if verbose and k % 50 == 0:
                print(k, {kk: (round(st[kk], 3) if isinstance(st[kk], float) else st[kk]) for kk in
                          ("net_clockwise_deg", "hand_contacts", "tilt_deg", "slide_m", "body_yaw_deg", "reason")},
                      flush=True)
        if st["done"] or p["search_only"]:
            if verbose:
                print("failed", {k: st[k] for k in ("reason", "failure_detail", "steps", "net_clockwise_deg")}, flush=True)
            return st
        # 4. release: open the pinch, lift the right hand, open the left hand and withdraw it
        here = [self.current(f"right_wrist_{a}_act") for a in "xyz"]
        release = {k: v for k, v in p["r_open"].items() if k.split("_")[0] in ("index", "middle")}
        st = self.move("right", here, p["r_angles"], 15, "right release", finger_to=release)
        st = self.move("right", here, p["r_angles"], 10, "right release", finger_to=p["r_open"])
        st = self.move("right", (here[0], here[1], here[2] + p["lift"]), p["r_angles"], 25, "right lift")
        lh = [self.current(f"left_wrist_{a}_act") for a in "xyz"]
        fingers_open = {f"{f}_{j}": 0.0 for f in ("index", "middle", "ring", "pinky") for j in ("MCP_FE", "PIP", "DIP")}
        st = self.move("left", lh, p["l_angles"], 20, "left release", finger_to=fingers_open)
        w1, w2 = (np.asarray(lh) + np.asarray(o) for o in p["l_withdraw"])
        st = self.move("left", tuple(w1), p["l_angles"], 25, "left withdraw")
        st = self.move("left", tuple(w2), p["l_angles"], 35, "left withdraw")
        n = 0
        while not st["done"] and n < 200:
            st = self.emit({}, "hold")
            n += 1
        if verbose:
            print("final", {k: st[k] for k in ("success", "reason", "stage", "steps", "net_clockwise_deg",
                                               "hand_contacts", "released_hold_steps", "failure_detail")}, flush=True)
        return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hand", default="sharpa")
    ap.add_argument("--out")
    ap.add_argument("--param", action="append", default=[])
    args = ap.parse_args()
    params = {}
    for item in args.param:
        k, v = item.split("=", 1)
        params[k] = json.loads(v)
    a = Author(args.hand, **params)
    st = a.run()
    if args.out:
        np.savez(args.out, actions=np.asarray(a.rows), phases=np.asarray(a.phases), hand=np.asarray(a.s.hand))
        print("saved", args.out, len(a.rows), "rows; success", st["success"])


if __name__ == "__main__":
    main()
