"""Authoring only: closed-loop two-arm controller for batter_whisk on the Marvin rig; the executed rows are saved.

Left arm: hooks its fingers over the near bowl rim (thumb outside) and holds the bowl through the whisking.
Right arm: picks the whisk up off the bowl rim (palm-down power grasp of the handle), turns it upright, whisks the
batter, drains it over the bowl, lays it down on the counter, opens and withdraws. Every control the IK targets are
computed from measured state (whisk pose, hand pose); the rows are what graders replay (open loop).

    python tools/author_arm.py --hand sharpa --out solution/trajectory.npz [--params '{...}'] [--video out.mp4]
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

import mujoco  # noqa: E402

import armlib  # noqa: E402
from armlib import frame, root_for_grip, slerp, smooth  # noqa: E402
from runtime import Session  # noqa: E402

DEFAULTS = {
    # left hand: "cradle" (palm on the outer wall, fingers under the belly) or "hook" (fingers over the rim)
    "l_mode": "hook", "c_side_deg": 180.0, "c_r": 0.045, "c_z": 0.045, "c_out": 0.05, "c_up": 0.03,
    "c_curl": [0.4, 0.6, 0.4], "c_close": [0.9, 1.2, 0.8], "c_thumb": [0.6, 0.0, 0.0, 0.0, 0.0],
    "c_thumb_close": [1.2, 0.0, 0.6, 0.0, 0.8],
    "l_curl": [0.9, 1.2, 0.8],
    "l_close": [0.95, 1.3, 0.9],
    "l_thumb_open": [0.6, 0.0, 0.0, 0.0, 0.0],
    "l_thumb_close": [0.6, 0.0, 0.0, 0.0, 0.0],
    "l_side_deg": 135.0,     # hold the rim on the near-left side of the bowl (away from the resting whisk)
    "l_tip_in": 0.018,       # fingertip centre inside the inner rim radius (m): all four tips clear the curved rim
    "l_tuck": None,          # optional (MCP, PIP, DIP) for index/pinky; None = same as the hooking fingers
    "l_tip_below": 0.012,    # fingertip centre below the rim top (m)
    "l_tip_fwd": 0.085,      # fingertip forward of the hand root along the fingers (curl preset)
    "l_tip_down": 0.070,     # fingertip below the hand root along the palm normal (curl preset)
    "l_app_s": 2.0, "l_down_s": 1.2, "l_close_s": 1.0, "l_out": 0.05, "l_up": 0.045,
    # right hand: pickup
    "grip_z": 0.25, "roll_deg": -15.0, "idx_sign": -1, "grip_b": 0.008, "grip_n": -0.045, "above": 0.07,
    "r_app_s": 2.0, "r_down_s": 1.2, "close_s": 1.2, "thumb_delay": 0.0,
    "grasp": [1.8683, 0.0354, 1.2223, 0.349, 1.5388, 0.6632, 0, 1.1508, 0.7582, 0.6632, 0, 1.1508, 0.7582,
              0.6632, 0, 1.1508, 0.7582, 0.1, 0.6632, 0, 1.1508, 0.7582],
    "lift": 0.16, "lift_s": 1.4, "squeeze": [0.25, 0.25, 0.2], "thumb_squeeze": [0.0, 0.0, 0.15, 0.0, 0.15],
    # whisking
    "turn_s": 2.0, "upright_palm": [0, -1.0, 0], "upright_index": [0, 0, -1.0], "head_above_rim": 0.04,
    "stage_off": [-0.02, -0.17], "stage_dz": 0.10, "over_s": 1.4, "lean_deg": 0.0,
    "orbit_r": 0.016, "head_z": 0.028, "rev_hz": 0.6, "revs": 6.3, "lower_s": 1.6, "ki": 0.02,
    "tip_clear": 0.035, "out_s": 1.4, "drain_s": 0.9,
    # set down
    "set_grip": [0.50, -0.25], "set_axis": [-0.857, -0.514, -0.10], "set_palm": [0, 0, -1.0], "high_z": 0.05,
    "travel_s": 2.4, "touch_steps": 12, "touch_speed": 0.0006, "open_s": 1.2, "slide": [0.0, 0.0, 0.0],
    "away_s": 1.2, "away_z": 0.12, "hold_rows": 120,
    "l_release_after_drain": True,
    "l_release_after_pickup": True,
}


class Controller:
    def __init__(self, session, params, video=None):
        self.s = session
        self.p = {**DEFAULTS, **params}
        self.arm = armlib.TwoArm(session)
        m = session.model
        self.whisk = m.body("whisk").id
        self.bowl = m.body("bowl").id
        self.head = m.site("whisk_head").id
        lay = self.arm.lay
        self.fl, self.fr = lay["fingers"]["left"], lay["fingers"]["right"]
        names = [m.actuator(i).name for i in range(self.fl.start, self.fl.stop)]
        self.fnames = names
        self.left_f = np.array(session.data.ctrl[self.fl])
        self.right_f = np.array(session.data.ctrl[self.fr])
        self.left_target = None
        self.right_target = None
        self.video = video
        self.frames = []
        self.renderer = None

    # ------------------------------------------------------------------ helpers
    def fingers(self, curl, thumb, tuck=None):
        """Left-hand targets: ``curl`` (MCP, PIP, DIP) for the hooking fingers, ``tuck`` for index/pinky."""
        f = np.zeros(len(self.fnames))
        tuck = (self.p["l_tuck"] or curl) if tuck is None else tuck
        for k, nm in enumerate(self.fnames):
            if "thumb" in nm:
                continue
            c = tuck if ("index" in nm or "pinky" in nm) else curl
            if "MCP_FE" in nm:
                f[k] = c[0]
            elif "PIP" in nm:
                f[k] = c[1]
            elif "DIP" in nm:
                f[k] = c[2]
        f[:5] = thumb
        lo, hi = self.s.model.actuator_ctrlrange[self.fl].T
        return np.clip(f, lo, hi)

    def step(self, phase, left=None, right=None):
        targets = {}
        if left is not None:
            self.left_target = left
        if right is not None:
            self.right_target = right
        if self.left_target is not None:
            targets["left"] = self.left_target
        if self.right_target is not None:
            targets["right"] = self.right_target
        done = self.arm.command(targets, phase)
        if self.video and len(self.arm.rows) % 2 == 0:
            if self.renderer is None:
                self.renderer = mujoco.Renderer(self.s.model, 360, 640)
                self.cam = mujoco.MjvCamera()
                self.cam.lookat[:] = self.p.get("cam_look", [0.56, 0.0, 0.78])
                self.cam.distance, self.cam.azimuth, self.cam.elevation = self.p.get("cam_dae", [0.75, -135, -30])
            self.renderer.update_scene(self.s.data, camera=self.cam)
            a = self.renderer.render().copy()
            self.cam.azimuth += 90
            self.renderer.update_scene(self.s.data, camera=self.cam)
            self.cam.azimuth -= 90
            self.frames.append(np.concatenate([a, self.renderer.render().copy()], axis=1))
        return done

    def interp(self, side, p0, R0, p1, R1, f0, f1, seconds, phase, other=None):
        n = max(1, int(round(seconds / self.s.control_dt)))
        for k in range(n):
            a = smooth((k + 1) / n)
            t = {"pos": p0 + a * (p1 - p0), "R": slerp(R0, R1, a), "fingers": f0 + a * (f1 - f0)}
            kw = {side: t}
            if other:
                kw.update(other(k, n))
            if self.step(phase, **kw):
                return True
        return False

    def hold(self, n, phase):
        for _ in range(n):
            if self.step(phase):
                return True
        return False

    # ------------------------------------------------------------------ phases
    def left_hold(self):
        if self.p["l_mode"] == "none":
            self.left_hold_pose = None
            return False
        if self.p["l_mode"] == "cradle":
            return self.left_cradle()
        return self.left_hook()

    def left_cradle(self):
        """Left palm against the bowl's outer wall (near side), fingers pointing down and curled under its belly."""
        p, d = self.p, self.s.data
        bowl = d.xpos[self.bowl].copy()
        th = math.radians(p["c_side_deg"])
        out = np.array([math.cos(th), math.sin(th), 0.0])
        R = frame(-out, np.cross([0, 0, 1.0], out))  # palm toward the bowl axis, fingers down
        grip = bowl + out * p["c_r"] + [0, 0, p["c_z"]]
        root = root_for_grip(grip, R)
        f_open = self.fingers(p["c_curl"], p["c_thumb"])
        f_close = self.fingers(p["c_close"], p["c_thumb_close"])
        p0, R0 = self.arm.mount_pose("left")
        pre = root + out * p["c_out"] + [0, 0, p["c_up"]]
        if self.interp("left", p0, R0, pre, R, self.left_f, f_open, p["l_app_s"], "left: reach the bowl"):
            return True
        if self.interp("left", pre, R, root + out * p["c_out"], R, f_open, f_open, 0.8, "left: beside the bowl"):
            return True
        if self.interp("left", root + out * p["c_out"], R, root, R, f_open, f_open, p["l_down_s"], "left: palm to the bowl"):
            return True
        if self.interp("left", root, R, root, R, f_open, f_close, p["l_close_s"], "left: hold the bowl"):
            return True
        self.left_hold_pose = (root, R, f_close)
        return False

    def left_hook(self):
        p, d = self.p, self.s.data
        bowl = d.xpos[self.bowl].copy()
        th = math.radians(p["l_side_deg"])  # where on the rim the hand holds (azimuth from the bowl axis)
        out = np.array([math.cos(th), math.sin(th), 0.0])
        # left Wave: palm down, fingers pointing at the bowl axis (-out); its y axis = -thumb = fingers x palm
        R = frame([0, 0, -1.0], np.cross(out, [0, 0, 1.0]))
        tip = bowl + out * (0.060 - p["l_tip_in"]) + [0, 0, 0.078 - p["l_tip_below"]]
        root = tip - R @ np.array([p["l_tip_down"], 0.0, p["l_tip_fwd"]])
        f_open = self.fingers(p["l_curl"], p["l_thumb_open"])
        f_close = self.fingers(p["l_close"], p["l_thumb_close"])
        p0, R0 = self.arm.mount_pose("left")
        above = root + [0, 0, p["l_up"]]
        pre = above + out * p["l_out"]
        if self.interp("left", p0, R0, pre, R, self.left_f, f_open, p["l_app_s"], "left: reach the bowl rim"):
            return True
        if self.interp("left", pre, R, above, R, f_open, f_open, 0.8, "left: over the rim"):
            return True
        if self.interp("left", above, R, root, R, f_open, f_open, p["l_down_s"], "left: fingers over the rim"):
            return True
        if self.interp("left", root, R, root, R, f_open, f_close, p["l_close_s"], "left: hold the bowl"):
            return True
        self.left_hold_pose = (root, R, f_close)
        return False

    def pickup(self):
        p, d = self.p, self.s.data
        Rw = d.xmat[self.whisk].reshape(3, 3)
        a, tip = Rw[:, 2].copy(), d.xpos[self.whisk].copy()
        down = np.array([0, 0, -1.0])
        down = down - (down @ a) * a
        down /= np.linalg.norm(down)
        side = np.cross(a, down)
        r = math.radians(p["roll_deg"])
        palm = math.cos(r) * down + math.sin(r) * side
        R = frame(palm, p["idx_sign"] * a)  # -1: index toward the whisk head (fingers point forward)
        grip = tip + a * p["grip_z"] + p["grip_b"] * R[:, 0] + p["grip_n"] * R[:, 2]
        root = root_for_grip(grip, R)
        above = root - R[:, 0] * p["above"]
        p0, R0 = self.arm.mount_pose("right")
        f_open = np.clip(np.zeros(22), *self.s.model.actuator_ctrlrange[self.fr].T)
        grasp = np.asarray(p["grasp"], float)
        if self.interp("right", p0, R0, above, R, self.right_f, f_open, p["r_app_s"], "right: reach the whisk"):
            return True
        if self.interp("right", above, R, root, R, f_open, f_open, p["r_down_s"], "right: hand over the handle"):
            return True
        if self.interp("right", root, R, root, R, f_open, grasp, p["close_s"], "right: grasp the handle"):
            return True
        tight = grasp.copy()
        sq = np.asarray(p["squeeze"], float)  # extra curl (MCP, PIP, DIP) of the four fingers, thumb extra
        for k in range(4):
            base = 5 + 4 * k + (1 if k == 3 else 0)
            tight[base] += sq[0]
            tight[base + 2] += sq[1]
            tight[base + 3] += sq[2]
        tight[:5] += np.asarray(p["thumb_squeeze"], float)
        tight = np.clip(tight, *self.s.model.actuator_ctrlrange[self.fr].T)
        if self.interp("right", root, R, root, R, grasp, tight, 0.4, "right: squeeze"):
            return True
        up = root + [0, 0, p["lift"]]
        if self.interp("right", root, R, up, R, tight, tight, p["lift_s"], "right: pick the whisk up"):
            return True
        self.grasp = tight
        return False

    def align(self, R_hand, axis_goal, palm_goal):
        """Hand rotation that turns the measured whisk axis (tip -> handle) to ``axis_goal``, then yaws about that
        axis so that the palm normal is as close as possible to ``palm_goal``."""
        a = self.s.data.xmat[self.whisk].reshape(3, 3)[:, 2]
        a_h = R_hand.T @ a
        goal = np.asarray(axis_goal, float) / np.linalg.norm(axis_goal)
        best = None
        for psi in np.linspace(-math.pi, math.pi, 73):
            # candidate hand rotation: any R with R a_h = goal; parametrize by the palm direction about goal
            base = frame(np.asarray([math.cos(psi), math.sin(psi), 0.3]) if abs(goal[2]) > 0.7
                         else np.asarray([0, 0, 1.0]) * math.cos(psi) + np.cross(goal, [0, 0, 1.0]) * math.sin(psi),
                         goal)  # columns: palm ~ psi-dir, index = goal
            # rotate so that a_h (in hand coords) maps to goal: R = base @ M where M maps a_h -> y axis
            y = np.array([0, 1.0, 0])
            v = np.cross(a_h, y)
            s, c = np.linalg.norm(v), float(a_h @ y)
            if s < 1e-9:
                M = np.eye(3)
            else:
                k = v / s
                K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
                M = np.eye(3) + s * K + (1 - c) * K @ K  # rotation taking a_h to y
            R = base @ M
            score = float(R[:, 0] @ np.asarray(palm_goal, float))
            if best is None or score > best[0]:
                best = (score, R)
        return best[1]

    def release_after_pickup(self):
        return self.left_release() if self.p["l_release_after_pickup"] else False

    def grip_offset(self):
        """Head point minus hand root in the hand frame (rigid grasp, measured now)."""
        pos, R = self.arm.mount_pose("right")
        return R.T @ (self.s.data.site_xpos[self.head] - pos)

    def whisking(self):
        p, d = self.p, self.s.data
        bowl = d.xpos[self.bowl].copy()
        pos0, R0 = self.arm.mount_pose("right")
        th = math.radians(p["l_side_deg"])
        away = -np.array([math.cos(th), math.sin(th), 0.0])  # away from the bowl-holding hand
        lean = math.radians(p["lean_deg"])
        Rv = self.align(R0, away * math.sin(lean) + np.array([0, 0, 1.0]) * math.cos(lean), p["upright_palm"])
        off = self.grip_offset()
        # turn upright beside the bowl (head clear of the bowl and the holding hand), then move over it
        stage_head = bowl + np.r_[p["stage_off"], self.s.checker.rim_z + p["stage_dz"]]
        ps = stage_head - Rv @ off
        if self.interp("right", pos0, R0, ps, Rv, self.grasp, self.grasp, p["turn_s"], "right: turn the whisk upright"):
            return True
        head_goal = bowl + [0, 0, self.s.checker.rim_z + p["head_above_rim"]]
        pv = head_goal - Rv @ off
        if self.interp("right", ps, Rv, pv, Rv, self.grasp, self.grasp, p["over_s"], "right: over the bowl"):
            return True
        if self.hold(15, "right: steady"):
            return True
        integral = np.zeros(3)

        def head_to(desired, phase, fixed=None):
            nonlocal integral
            pos, R = self.arm.mount_pose("right")
            if fixed is None:
                o = d.site_xpos[self.head] - pos
                target = desired - o
            else:
                integral = integral + p["ki"] * (desired - d.site_xpos[self.head])
                target = desired - fixed + integral
            return self.step(phase, right={"pos": target, "R": Rv, "fingers": self.grasp})

        head0 = d.site_xpos[self.head].copy()
        start = bowl + [p["orbit_r"], 0.0, p["head_z"]]
        n = int(p["lower_s"] / self.s.control_dt)
        for k in range(n):
            if head_to(head0 + smooth((k + 1) / n) * (start - head0), "right: whisk into the batter"):
                return True
        pos, _ = self.arm.mount_pose("right")
        fixed = d.site_xpos[self.head] - pos
        n = int(p["revs"] / p["rev_hz"] / self.s.control_dt)
        for k in range(n):
            phi = 2 * math.pi * p["rev_hz"] * (k + 1) * self.s.control_dt
            goal = bowl + [p["orbit_r"] * math.cos(phi), p["orbit_r"] * math.sin(phi), p["head_z"]]
            if head_to(goal, "right: whisk", fixed):
                return True
            if self.s.checker.stage >= 3 and k > 10:
                break
        here = d.site_xpos[self.head].copy()
        top = bowl + [0, 0, self.s.checker.rim_z + p["tip_clear"] + self.s.config["head_point_z"]]
        n = int(p["out_s"] / self.s.control_dt)
        for k in range(n):
            if head_to(here + smooth((k + 1) / n) * (top - here), "right: lift out"):
                return True
        for _ in range(int(p["drain_s"] / self.s.control_dt)):
            if head_to(top, "right: drain over the bowl"):
                return True
        return False

    def left_release(self):
        if self.left_hold_pose is None:
            return False
        root, R, f_close = self.left_hold_pose
        f_open = self.fingers(self.p["l_curl"], self.p["l_thumb_open"])
        th = math.radians(self.p["l_side_deg"])
        out = np.array([math.cos(th), math.sin(th), 0.0])
        if self.interp("left", root, R, root, R, f_close, f_open, 0.6, "left: let go of the bowl"):
            return True
        if self.interp("left", root, R, root + [0, 0, 0.05], R, f_open, f_open, 0.8, "left: fingers out of the bowl"):
            return True
        if self.interp("left", root + [0, 0, 0.05], R, root + out * 0.12 + [0, 0, 0.10], R, f_open, f_open, 1.0,
                       "left: withdraw"):
            return True
        self.left_hold_pose = None
        return False

    def set_down(self):
        p, d = self.p, self.s.data
        if p["l_release_after_drain"] and self.left_release():
            return True
        pos0, R0 = self.arm.mount_pose("right")
        Rset = self.align(R0, p["set_axis"], p["set_palm"])
        # grip point of the current grasp, as seen from the hand: keep it, move it to set_grip at a safe height
        Rw = d.xmat[self.whisk].reshape(3, 3)
        grip_world = d.xpos[self.whisk] + Rw[:, 2] * p["grip_z"]
        g_local = R0.T @ (grip_world - pos0)
        target_grip = np.r_[p["set_grip"], grip_world[2] + p["high_z"]]
        p1 = target_grip - Rset @ g_local
        if self.interp("right", pos0, R0, p1, Rset, self.grasp, self.grasp, p["travel_s"], "right: carry and turn"):
            return True
        from scene import HANDLE_BOTTOM, HANDLE_RADIUS, HANDLE_TOP, wire_centerlines

        ring = [(HANDLE_RADIUS * math.cos(t), HANDLE_RADIUS * math.sin(t), z)
                for z in (HANDLE_BOTTOM, HANDLE_TOP) for t in np.linspace(0, 2 * math.pi, 24, endpoint=False)]
        pts = np.vstack([*wire_centerlines(self.s.config["wire_points_per_strand"]), ring])

        def lowest():
            Rw_ = d.xmat[self.whisk].reshape(3, 3)
            return float((pts @ Rw_.T + d.xpos[self.whisk])[:, 2].min()) - self.s.config["wire_proxy_radius_m"]

        pos = p1.copy()
        touched = None
        for k in range(1500):
            if touched is None and self.s.checker.f["whisk_counter"]:
                touched = k
            if touched is not None and k - touched >= p["touch_steps"]:
                break
            gap = lowest() - self.s.checker.table_z
            pos = pos - [0, 0, float(np.clip(0.08 * gap, p["touch_speed"], 0.004))]
            if self.step("right: lay the whisk down", right={"pos": pos.copy(), "R": Rset, "fingers": self.grasp}):
                return True
        f_open = np.clip(np.zeros(22), *self.s.model.actuator_ctrlrange[self.fr].T)
        if self.interp("right", pos, Rset, pos + np.asarray(p["slide"]), Rset, self.grasp, f_open, p["open_s"],
                       "right: open the hand"):
            return True
        p2 = pos + np.asarray(p["slide"])
        if self.interp("right", p2, Rset, p2 + [0, 0, p["away_z"]], Rset, f_open, f_open, p["away_s"],
                       "right: withdraw"):
            return True
        return self.hold(p["hold_rows"], "rest")

    def run(self, until=None):
        for name in ("left_hold", "pickup", "release_after_pickup", "whisking", "set_down"):
            if getattr(self, name)():
                return
            if until == name:
                return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hand", default="sharpa")
    parser.add_argument("--out")
    parser.add_argument("--params", default="{}")
    parser.add_argument("--until")
    parser.add_argument("--video")
    parser.add_argument("--slack", type=int, default=100)
    args = parser.parse_args()
    s = Session(hand=args.hand)
    c = Controller(s, json.loads(args.params), video=args.video)
    c.run(args.until)
    st = s.status()
    print(json.dumps({k: st.get(k) for k in ("success", "reason", "stage", "steps", "revolutions", "failure_detail",
                                             "max_bowl_tilt_deg", "max_bowl_slide_m", "holder_bowl", "hand_whisk")},
                     default=str))
    ph = c.arm.phases
    print("phases", [(i + 1, x) for i, x in enumerate(ph) if i == 0 or ph[i - 1] != x])
    errs = [e for e in c.arm.log if e]
    if errs:
        mx = {side: max(e[side][0] for e in errs if side in e) for side in ("left", "right") if any(side in e for e in errs)}
        print("max IK pos err", mx)
    if args.video and c.frames:
        import imageio

        imageio.mimwrite(args.video, c.frames, fps=25, macro_block_size=8)
    if args.out and st["success"]:
        rows = np.asarray(c.arm.rows)
        rows = np.vstack([rows, np.repeat(rows[-1:], args.slack, axis=0)])
        s.save_trajectory(rows, args.out)
        Path(args.out).with_suffix(".phases.json").write_text(json.dumps(ph))
        print("saved", args.out, rows.shape, "success_step", st["steps"])


if __name__ == "__main__":
    main()
