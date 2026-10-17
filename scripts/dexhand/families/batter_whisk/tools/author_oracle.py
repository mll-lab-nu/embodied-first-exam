"""Authoring only: closed-loop scripted wrist controller that whisks, drains and sets the whisk down.

It reads Session state (whisk head/tip, stage joints) every control, writes only actuator targets, and the
executed rows are saved as an open-loop trajectory (the rows are what graders replay). Finger targets stay at
the frozen reset grasp until the release phase.

    python tools/author_oracle.py --hand sharpa --out /path/trajectory.npz [--params '{...}']
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

from runtime import Session  # noqa: E402

DEFAULTS = {
    "lower_s": 1.6,
    "head_z": 0.030,  # head point height above the bowl origin while whisking
    "orbit_r": 0.017,
    "rev_hz": 0.8,
    "revs": 6.3,
    "ramp_s": 0.6,
    "lift_s": 1.4,
    "tip_clear": 0.035,  # tip above rim while draining
    "drain_s": 0.9,
    "set_xy": [0.68, 0.22],
    "set_ry": 1.48,
    "travel_s": 2.2,
    "high_z": 0.06,  # extra grip height during the transfer
    "lower2_s": 2.0,
    "touch_steps": 12,
    "touch_speed": 0.0006,
    "open_s": 1.2,
    "away_z": 0.12,
    "away_y": 0.0,
    "slide_s": 2.0,
    "slide_x": 0.12,
    "slide_y": 0.0,
    "slide_z": 0.015,
    "slide_lift": 0.0,  # extra lift during the second half of the slide (the hand clears the whisk visibly)
    "away_s": 1.0,
    "hold_rows": 140,
    "gain": 1.0,
    "ki": 0.02,
}


# Hand-specific release: the Wuji thumb hooks the handle's top end when the open hand slides toward it, so the
# Wuji hand slides off toward the head end instead.
# The Sharpa hand also rises during the second half of its slide so that it is visibly clear of the whisk.
HAND_DEFAULTS = {"wuji": {"slide_x": -0.10}, "sharpa": {"slide_s": 1.6, "slide_lift": 0.12}}


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * x * (10 + x * (-15 + 6 * x))


class Controller:
    def __init__(self, session, params):
        self.s = session
        self.p = {**DEFAULTS, **HAND_DEFAULTS.get(session.hand, {}), **params}
        m = session.model
        self.origin = np.zeros(3)  # wrist-slide targets are world coordinates of the grip point
        self.slide_q = [m.jnt_qposadr[m.joint(n).id] for n in ("wrist_x", "wrist_y", "wrist_z")]
        self.head = m.site("whisk_head").id
        self.whisk = m.body("whisk").id
        self.bowl = m.body("bowl").id
        self.rows = []
        self.phases = []
        self.grasp = session.hold_action()[6:].copy()
        from scene import HANDLE_BOTTOM, HANDLE_RADIUS, HANDLE_TOP, wire_centerlines

        ring = [(HANDLE_RADIUS * math.cos(a), HANDLE_RADIUS * math.sin(a), z)
                for z in (HANDLE_BOTTOM, HANDLE_TOP) for a in np.linspace(0, 2 * math.pi, 24, endpoint=False)]
        self.points = np.vstack([*wire_centerlines(session.config["wire_points_per_strand"]), ring])
        self.target = session.hold_action()[:6].copy()

    def lowest(self):
        """Lowest point of the whisk wire centerlines / handle rim (world z), minus the proxy radius."""
        d = self.s.data
        R = d.xmat[self.whisk].reshape(3, 3)
        pts = self.points @ R.T + d.xpos[self.whisk]
        return float(pts[:, 2].min()) - self.s.config["wire_proxy_radius_m"]

    def grip(self):
        return self.origin + self.s.data.qpos[self.slide_q]

    def send(self, wrist, fingers=None, phase=""):
        lo, hi = self.s.model.actuator_ctrlrange.T
        row = np.empty(self.s.action_dim)
        row[:6] = wrist
        row[6:] = self.grasp if fingers is None else fingers
        row = np.clip(row, lo, hi)
        self.target = row[:6].copy()
        self.s.step(row)
        self.rows.append(row)
        self.phases.append(phase)
        return self.s.done

    def head_to(self, desired, phase, offset=None):
        """Wrist-slide target that places the head point at ``desired``.

        With ``offset`` (head minus grip, frozen) the grip follows a feed-forward path plus a slow integral
        correction of the measured head error; without it the current rigid offset is used (closed loop)."""
        d = self.s.data
        wrist = self.target.copy()
        if offset is None:
            offset = d.site_xpos[self.head] - self.grip()
            wrist[:3] = desired - offset - self.origin
        else:
            self.integral += self.p["ki"] * (desired - d.site_xpos[self.head])
            wrist[:3] = desired - offset - self.origin + self.integral
        return self.send(wrist, phase=phase)

    def run(self):
        p, d, dt = self.p, self.s.data, self.s.control_dt
        bowl = d.xpos[self.bowl].copy()
        head0 = d.site_xpos[self.head].copy()
        # 1. lower the head into the batter, offset onto the orbit start
        start = bowl + [p["orbit_r"], 0.0, p["head_z"]]
        n = int(p["lower_s"] / dt)
        for k in range(n):
            a = smooth((k + 1) / n)
            if self.head_to(head0 + a * (start - head0), "lower into batter"):
                return
        # 2. orbit the bowl axis
        n = int(p["revs"] / p["rev_hz"] / dt)
        offset = d.site_xpos[self.head] - self.grip()
        self.integral = np.zeros(3)
        for k in range(n):
            t = (k + 1) * dt
            phi = 2 * math.pi * p["rev_hz"] * t
            desired = bowl + [p["orbit_r"] * math.cos(phi), p["orbit_r"] * math.sin(phi), p["head_z"]]
            if self.head_to(desired, "whisk", offset):
                return
            if self.s.checker.stage >= 2 and k > n - 5:
                break
        # 3. back to the axis and lift out to drain
        here = d.site_xpos[self.head].copy()
        top = bowl + [0, 0, self.s.checker.rim_z + p["tip_clear"] + self.s.config["head_point_z"]]
        n = int(p["lift_s"] / dt)
        for k in range(n):
            a = smooth((k + 1) / n)
            if self.head_to(here + a * (top - here), "lift out"):
                return
        for k in range(int(p["drain_s"] / dt)):
            if self.head_to(top, "drain over bowl"):
                return
        # 4. carry clear (up and sideways), turning the whisk to lie head-down along -x
        w0 = self.target.copy()
        w1 = w0.copy()
        w1[0] = p["set_xy"][0] - self.origin[0]
        w1[1] = p["set_xy"][1] - self.origin[1]
        w1[2] = w0[2] + p["high_z"]
        w1[4] = p["set_ry"]
        n = int(p["travel_s"] / dt)
        for k in range(n):
            a = smooth((k + 1) / n)
            w = w0 + a * (w1 - w0)
            # rise first, then turn
            w[2] = w0[2] + smooth(min(1.0, 2.0 * (k + 1) / n)) * (w1[2] - w0[2])
            if self.send(w, phase="carry and turn"):
                return
        # 5. lower until the whisk touches the counter (fast while high, slow near the top)
        w = self.target.copy()
        touched = None
        for k in range(1500):
            if touched is None and self.s.checker.f["whisk_counter"]:
                touched = k
            if touched is not None and k - touched >= p["touch_steps"]:
                break
            gap = self.lowest() - self.s.checker.table_z
            w = w.copy()
            w[2] -= float(np.clip(0.08 * gap, p["touch_speed"], 0.004))
            if self.send(w, phase="set down"):
                return
        # 6. open the fingers, then lift the hand away
        open_pose = np.zeros(len(self.grasp))
        lo, hi = self.s.model.actuator_ctrlrange[6:].T
        open_pose = np.clip(open_pose, lo, hi)
        n = int(p["open_s"] / dt)
        for k in range(n):
            a = smooth((k + 1) / n)
            if self.send(w, (1 - a) * self.grasp + a * open_pose, "release"):
                return
        # slide the open hand off the handle's top end (+x, along the whisk axis), then lift it away
        w0 = w.copy()
        n = int(p["slide_s"] / dt)
        for k in range(n):
            a = smooth((k + 1) / n)
            w = w0.copy()
            w[0] += a * p["slide_x"]
            w[1] += a * p["slide_y"]
            w[2] += a * p["slide_z"] + smooth(2.0 * (k + 1) / n - 1.0) * p["slide_lift"]
            if self.send(w, open_pose, "slide off"):
                return
        w0 = w.copy()
        n = int(p["away_s"] / dt)
        for k in range(n):
            a = smooth((k + 1) / n)
            w = w0.copy()
            w[1] += a * p["away_y"]
            w[2] += a * p["away_z"]
            if self.send(w, open_pose, "hand away"):
                return
        for k in range(p["hold_rows"]):
            if self.send(w, open_pose, "hold"):
                return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hand", default="sharpa")
    parser.add_argument("--out")
    parser.add_argument("--params", default="{}")
    parser.add_argument("--slack", type=int, default=80, help="hold rows appended after the last executed row")
    args = parser.parse_args()
    s = Session(hand=args.hand)
    c = Controller(s, json.loads(args.params))
    c.run()
    st = s.status()
    print(json.dumps({k: st[k] for k in ("success", "reason", "stage", "steps", "revolutions", "failure_detail",
                                          "max_bowl_tilt_deg", "max_bowl_slide_m")}, default=str))
    rows = np.asarray(c.rows)
    if args.out and st["success"]:
        rows = np.vstack([rows, np.repeat(rows[-1:], args.slack, axis=0)])
        s.save_trajectory(rows, args.out)
        Path(args.out).with_suffix(".phases.json").write_text(json.dumps(c.phases))
        print("saved", args.out, rows.shape, "success_step", st["steps"])


if __name__ == "__main__":
    main()
