"""Authoring controller (Sharpa Wave on the Marvin right arm), from the source film's start (spoon held upright above
the mug): dip the bowl into the coffee, stir six revolutions, lift it out, carry it beside the mug, turn it down onto
the worktop about its bowl, release and withdraw.

Closed loop on Session state (bowl-centre feedback on the commanded hand-mount pose, arm IK with a joint integral);
only the executed actuator rows are saved, and the fresh-process replay reproduces them open loop.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
FAMILY = HERE.parent
sys.path.insert(0, str(FAMILY))
sys.path.insert(1, str(HERE))
os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from runtime import Session
from armctl import ArmCtl, smooth
from rigtools import Rig


class Coffee:
    def __init__(self, s, p, log=print):
        self.s, self.p, self.log = s, p, log
        self.m, self.d = s.model, s.data
        self.rig = Rig(self.m, self.d, s.hand)
        self.c = ArmCtl(s, sides=("right",), ki=p["ki"], log=log)
        self.spoon = self.m.body("spoon").id
        self.cup = self.m.body("cup").id
        self.sites = {n: self.m.site(n).id for n in ("bowl_center", "spoon_top")}
        self.integ = np.zeros(3)

    def bowl(self):
        return self.d.site_xpos[self.sites["bowl_center"]].copy()

    def status(self, tag):
        f = self.s.features()
        keys = ("stage", "stage_name", "revolutions", "bowl_submerged", "bowl_height_m", "spoon_fingers",
                "spoon_axis_tilt_deg", "spoon_cup_clearance_m", "failure", "failure_detail", "steps",
                "cup_slide_m", "rest_hold_steps", "spoon_worktop_contacts")
        self.log(f"{tag:28s}", json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in f.items()
                                          if k in keys}, default=str), flush=True)
        if self.p.get("render_dir"):
            import imageio
            if not hasattr(self, "_r"):
                self._r, self._n = mujoco.Renderer(self.m, 360, 480), 0
            cam = mujoco.MjvCamera()
            look = self.bowl() * 0.5 + self.d.site_xpos[self.sites["spoon_top"]] * 0.5
            imgs = []
            for az, el in ((200, -25), (290, -15)):
                cam.lookat[:] = look
                cam.distance, cam.azimuth, cam.elevation = 0.45, az, el
                self._r.update_scene(self.d, cam)
                imgs.append(self._r.render())
            self._n += 1
            out = Path(self.p["render_dir"]) / f"{self._n:02d}_{tag.replace(' ', '_')}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            imageio.imwrite(out, np.concatenate(imgs, axis=1))

    def bowl_path(self, fn, count, phase, R=None):
        """Each control, command the hand so that the bowl centre follows fn(i) (proportional + integral feedback
        on the bowl error, rate-limited)."""
        c, p = self.c, self.p
        for i in range(count):
            want = np.asarray(fn(i), float)
            b = self.bowl()
            self.integ = np.clip(self.integ + p["k_int"] * (want - b), -p["int_limit"], p["int_limit"])
            hp, hR = c.pose("right")
            goal = hp + (want - b) * p["k_p"] + self.integ
            cur = c.goal["right"][0]
            goal = cur + np.clip(goal - cur, -p["max_step"], p["max_step"])
            if not c.step(phase, {"right": (goal, c.goal["right"][1] if R is None else R)}):
                return False
        return True

    # ---- pinch-point commands: the pinched spoon hangs like a pendulum below the thumb-index pinch (wave-2) ----
    def pinch(self):
        tips = [self.rig.tips["right"][f] for f in ("thumb", "index")]
        return self.d.geom_xpos[tips].mean(axis=0)

    def pinch_to(self, points, phase):
        """Command the hand so that the pinch point follows ``points`` (fixed hand orientation, fixed pinch offset
        measured at the start of the segment)."""
        c = self.c
        hp, _ = c.pose("right")
        rel = c.goal["right"][0] - self.pinch()
        R = c.goal["right"][1]
        for pt in points:
            if not c.step(phase, {"right": (np.asarray(pt) + rel, R)}):
                return False
        return True

    def run(self):
        s, c, p = self.s, self.c, self.p
        m, d = self.m, self.d
        c.hold("start", 10)
        # Tighten the thumb-index pinch a little before moving (the reset holds the hanging spoon lightly).
        rig = self.rig
        f = c.fingers("right")
        th_i = rig.groups["right"]["thumb"] - rig.fing["right"][0]
        ix_i = rig.groups["right"]["index"] - rig.fing["right"][0]
        f[th_i[0]] += p["tighten"]
        f[ix_i[0]] += p["tighten"]
        c.move("tighten the pinch", 20, fingers={"right": f})
        self.status("start")
        cup = d.xpos[self.cup].copy()
        p0 = self.pinch()
        L = float(np.linalg.norm(p0 - self.bowl()))
        # Above the cup axis, bowl bottom clear of the rim.
        top = np.array([cup[0], cup[1], max(p0[2], cup[2] + p["carry_bowl_z"] + L)])
        n = p["center_rows"]
        self.pinch_to([p0 + (top - p0) * smooth(i / n) for i in range(1, n + 1)], "centre the spoon over the mug")
        self.pinch_to([top] * p["settle_rows"], "let the spoon settle")
        self.status("over the mug")
        target_z = cup[2] + p["bowl_z"]
        low = top + np.array([0, 0, (target_z - self.bowl()[2])])
        n = p["dip_rows"]
        self.pinch_to([top + (low - top) * smooth(i / n) for i in range(1, n + 1)], "dip the bowl into the coffee")
        self.pinch_to([low] * 30, "dip the bowl into the coffee")
        for _ in range(2):
            low = low + np.array([0, 0, target_z - self.bowl()[2]])
            self.pinch_to([low] * 25, "dip the bowl into the coffee")
        self.status("dipped")
        # Stir (wave-2 closed loop): the pinch drives the hanging bowl like a pendulum pivot; proportional feedback
        # on the bowl position plus velocity damping keep the bowl on the circle and at depth.
        turns, rpt, r = p["turns"], p["rows_per_turn"], p["radius"]
        total = int(rpt * turns)
        a0 = p["start_angle"]
        site = self.sites["bowl_center"]
        prev = d.site_xpos[site].copy()
        z_cmd = low[2]
        center = low.copy()
        rel = c.goal["right"][0] - self.pinch()
        R = c.goal["right"][1]
        for i in range(1, total + 1):
            t = i / total
            a = a0 + 2 * np.pi * turns * t
            rad = r * smooth(i / (0.5 * rpt)) * (1 - smooth((i - total + 0.5 * rpt) / (0.5 * rpt)))
            want = center[:2] + np.array([rad * np.cos(a), rad * np.sin(a)])
            bowl = d.site_xpos[site].copy()
            vel = (bowl - prev) / s.control_dt
            prev = bowl
            cmd = want + p["kp"] * (want - bowl[:2]) - p["kd"] * vel[:2]
            z_cmd += p["kz"] * (target_z - bowl[2])
            if not c.step("stir six turns", {"right": (np.r_[cmd, z_cmd] + rel, R)}):
                break
            if i % 110 == 0:
                self.status(f"stir {i}")
        center = np.r_[center[:2], z_cmd]
        self.pinch_to([center] * p["settle_rows"], "stop stirring")
        self.status("stirred")
        # Lift out, carry beside the mug, lower the bowl onto the worktop, lay the spoon down about its bowl.
        up = center + np.array([0, 0, cup[2] + p["carry_bowl_z"] - self.bowl()[2]])
        n = p["lift_rows"]
        self.pinch_to([center + (up - center) * smooth(i / n) for i in range(1, n + 1)], "lift the spoon out")
        place = np.asarray(p["place_bowl"], float)
        above = np.array([place[0], place[1], up[2]])
        n = p["carry_rows"]
        self.pinch_to([up + (above - up) * smooth(i / n) for i in range(1, n + 1)], "carry beside the mug")
        self.pinch_to([above] * p["settle_rows"], "let the spoon settle")
        self.status("above the place")
        L = float(np.linalg.norm(self.pinch() - self.bowl()))
        touch = above + np.array([0, 0, p["bowl_touch_z"] - self.bowl()[2]])
        n = p["lower_rows"]
        self.pinch_to([above + (touch - above) * smooth(i / n) for i in range(1, n + 1)], "lower the bowl")
        self.status("bowl on the worktop")
        axis = cup[:2]
        out = np.r_[place[:2] - axis, 0.0]
        out /= np.linalg.norm(out)
        b = self.bowl()
        n = p["lay_rows"]
        pts = []
        for i in range(1, n + 1):
            u = smooth(i / n)
            th = p["lay_angle"] * u
            # Pivot about the bowl centre, kept at the height where the tilted bowl slab just rests on the worktop
            # (half length 21.5 mm, half thickness 3.2 mm) plus a small clearance.
            z_rest = s.config["table_z"] + 0.0215 * np.cos(th) + 0.0032 * np.sin(th) + p["lay_clear"]
            pivot = np.array([b[0], b[1], z_rest])
            pts.append(pivot + L * (np.sin(th) * out + np.cos(th) * np.array([0, 0, 1.0])))
        self.pinch_to(pts, "lay the spoon down")
        self.status("laid")
        rig = self.rig
        f = c.fingers("right")
        th_i = rig.groups["right"]["thumb"] - rig.fing["right"][0]
        ix_i = rig.groups["right"]["index"] - rig.fing["right"][0]
        f_open = f.copy()
        f_open[th_i[0]] += p["thumb_open"]
        f_open[th_i[2]] = 0.0
        f_open[th_i[4]] = 0.0
        f_open[ix_i[0]] += p["index_open"]
        f_open[ix_i[2]] = 0.0
        f_open[ix_i[3]] = 0.0
        c.move("release", p["release_rows"], fingers={"right": f_open})
        c.hold("release", 20)
        self.status("released")
        # Slide the hand off sideways first, toward the side of the index fingertip (away from the shaft), so no
        # finger lifts the handle; then lift it away.
        R = d.xmat[self.spoon].reshape(3, 3)
        tip = d.geom_xpos[rig.tips["right"]["index"]].copy()
        rel = tip - d.xpos[self.spoon]
        side = rel - R[:, 2] * (rel @ R[:, 2])
        side[2] = 0.0
        side = side / max(np.linalg.norm(side), 1e-9)
        g = c.goal["right"]
        c.move("slide the fingers off the handle", p["slide_rows"],
               {"right": (g[0] + side * p["slide_off"] + np.array([0, 0, 0.01]), g[1])})
        g = c.goal["right"]
        c.move("withdraw the hand", p["withdraw_rows"], {"right": (g[0] + np.array([0, 0, 0.10]), g[1])})
        self.status("withdrawn")
        while not s.done and len(c.rows) < s.max_control_steps:
            c.hold("hold", 1)
        self.status("end")
        return s.status()


DEFAULTS = dict(tighten=0.0, ki=0.2, carry_bowl_z=0.175, center_rows=60, settle_rows=50, bowl_z=0.032, dip_rows=80, turns=6.7,
                rows_per_turn=110, radius=0.015, start_angle=0.0, kp=0.0, kd=0.0, kz=0.05, lift_rows=100,
                place_bowl=[0.56, -0.20], carry_rows=220, bowl_touch_z=0.7735, lay_clear=0.0005, lower_rows=60, lay_angle=1.40,
                lay_rows=110, thumb_open=-0.6, index_open=-0.5, release_rows=40, withdraw_rows=90, slide_rows=40, slide_off=0.03, slack_rows=80,
                render_dir=None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--params", default="{}")
    ap.add_argument("--hand", default="sharpa")
    a = ap.parse_args()
    p = dict(DEFAULTS, **json.loads(a.params))
    s = Session(hand=a.hand)
    co = Coffee(s, p)
    st = co.run()
    print("RESULT", json.dumps({k: st.get(k) for k in ("success", "reason", "stage", "steps", "failure_detail")},
                               default=str))
    if a.out:
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        rows = np.asarray(co.c.rows, dtype=np.float64)
        rows = np.concatenate([rows, np.repeat(rows[-1:], p["slack_rows"], axis=0)])
        s.save_trajectory(rows, out)
        np.savez_compressed(out.with_suffix(".phases.npz"),
                            phases=np.asarray(co.c.phases + ["slack"] * p["slack_rows"]))
        print("rows", len(rows))


if __name__ == "__main__":
    main()
