"""Authoring controller: closed-loop turner-pose servo through the wrist stage, recorded as open-loop rows.

Each control step reads the simulator state (the current grasp transform between the wrist stage and the turner),
computes the wrist-stage targets that place the turner blade at the scripted waypoint, adds the wrist gravity
feed-forward, and records the resulting actuator row. Fingers keep the reset grasp targets. The recorded rows alone
reproduce the episode in a fresh process (they are plain actuator targets).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from runtime import Session  # noqa: E402

TIP_LOCAL = np.array([0.0, 0.2575, -0.07055])  # front-centre of the blade's lower face, turner frame
PAN = np.array([0.50, 0.10])
PLATE = np.array([0.76, 0.18])
FLOOR_Z = 0.8503 + 0.006  # pan floor top (pan base + 6 mm)
PLATE_Z = 0.8503 + 0.006  # plate floor top


def turner_rotation(pitch, yaw, roll=0.0):
    """Blade direction = turner +y rotated by yaw about world z; pitch > 0 lowers the tip."""
    return Rotation.from_euler("ZXY", [yaw, -pitch, roll]).as_matrix()


class Controller:
    def __init__(self, session, params=None):
        self.s = session
        self.p = dict(params or {})
        m = session.model
        self.turner = m.body("turner").id
        self.stage_body = m.body("wrist_stage").id
        self.dofs = m.jnt_dofadr[m.actuator_trnid[:6, 0]]
        self.kp = m.actuator_gainprm[:6, 0].copy()
        self.lo, self.hi = m.actuator_ctrlrange.T
        self.fingers = session.initial_targets[6:].copy()
        self.prev = session.data.qpos[session.qadr[:6]].copy()
        self.rows = []
        self.phases = []

    def tip_pose(self):
        d = self.s.data
        R = d.xmat[self.turner].reshape(3, 3)
        return d.xpos[self.turner] + R @ TIP_LOCAL, R

    def wrist_targets(self, tip, R_des):
        d = self.s.data
        Rw = d.xmat[self.stage_body].reshape(3, 3)
        Rt = d.xmat[self.turner].reshape(3, 3)
        R_wt = Rw.T @ Rt
        p_wt = Rw.T @ (d.xpos[self.turner] - d.xpos[self.stage_body])
        p_turner = tip - R_des @ TIP_LOCAL
        R_wrist = R_des @ R_wt.T
        p_wrist = p_turner - R_wrist @ p_wt
        angles = Rotation.from_matrix(R_wrist).as_euler("XYZ")
        # unwrap to the joint values closest to the previous command
        angles = self.prev[3:] + (angles - self.prev[3:] + np.pi) % (2 * np.pi) - np.pi
        return np.r_[p_wrist, angles]

    def command(self, target, phase):
        d = self.s.data
        row = np.empty(self.s.action_dim)
        row[:6] = target + d.qfrc_bias[self.dofs] / self.kp
        row[6:] = self.fingers
        row = np.clip(row, self.lo, self.hi)
        self.prev = target.copy()
        self.s.step(row)
        self.rows.append(row)
        self.phases.append(phase)

    def move(self, tip, pitch, yaw, controls, phase, roll=0.0):
        """Smoothly move the blade tip/orientation from the current measured pose to the waypoint."""
        tip0, R0 = self.tip_pose()
        r0 = Rotation.from_matrix(R0)
        r1 = Rotation.from_matrix(turner_rotation(pitch, yaw, roll))
        key = Rotation.concatenate([r0, r1])
        from scipy.spatial.transform import Slerp

        slerp = Slerp([0, 1], key)
        for k in range(controls):
            if self.s.done:
                return
            a = (k + 1) / controls
            a = a * a * (3 - 2 * a)
            tip_k = tip0 + (np.asarray(tip) - tip0) * a
            R_k = slerp([a]).as_matrix()[0]
            self.command(self.wrist_targets(tip_k, R_k), phase)

    def slide(self, t0, t1, z, yaw, controls, phase, margin_deg=3.0, min_pitch=0.08, center=PAN):
        """Advance the pressed tip along the pan floor; the pitch keeps the blade above the near rim."""
        fwd = np.array([-np.sin(yaw), np.cos(yaw)])
        for k in range(controls):
            if self.s.done:
                return
            a = (k + 1) / controls
            a = a * a * (3 - 2 * a)
            t = t0 + (t1 - t0) * a
            press = FLOOR_Z - z
            pitch = max(np.arctan2(0.022 + press, max(t + 0.096, 1e-3)) + np.radians(margin_deg), min_pitch)
            tip = np.r_[center + fwd * t, z]
            self.command(self.wrist_targets(tip, turner_rotation(pitch, yaw)), phase)

    def prepush(self, P, yaw):
        """Nudge the pancake away from the near wall with the blade edge (tip just above the floor)."""
        if P.get("push_to") is None:
            return
        fwd = np.array([-np.sin(yaw), np.cos(yaw)])
        self.move([*(PAN + fwd * P["push_from"]), FLOOR_Z + P["push_z"]], P["push_pitch"], yaw, 40, "push down")
        self.move([*(PAN + fwd * P["push_to"]), FLOOR_Z + P["push_z"]], P["push_pitch"], yaw, 50, "push")
        self.move([*(PAN + fwd * (P["push_to"] - 0.01)), FLOOR_Z + 0.03], P["enter_pitch"], yaw, 25, "push back off")
        self.move([*(PAN + fwd * P["tip_start"]), FLOOR_Z + 0.02], P["enter_pitch"], yaw, 25, "re-approach")

    def hold(self, controls, phase):
        tip, R = self.tip_pose()
        for _ in range(controls):
            if self.s.done:
                return
            self.command(self.wrist_targets(tip, R), phase)

    def log(self, phase):
        f = self.s.features()
        tip, _ = self.tip_pose()
        print(f"[{self.s.steps:4d}] {phase:28s} stage={f['stage']} fail={f['failure']} tip={np.round(tip, 3)} "
              f"cake={np.round(f['pancake_pos'], 3)} partners={f['pancake_partners']} tilt={f['pancake_tilt_deg']:.1f} "
              f"plate_d={f['pancake_plate_dist_m']:.3f} hold={f['hold_controls']} grip={f['hand_holds_spatula']}",
              flush=True)


def run(params=None, out=None, verbose=True, phases_out=None):
    P = {"press": 0.008, "push_from": -0.082, "push_to": -0.062, "push_z": 0.004, "push_pitch": 0.70, "enter_pitch": 0.66, "slide_controls": 120, "margin_deg": 3.0, "min_pitch": 0.08,
         "tip_start": -0.068, "tip_end": 0.072, "scoop_z": 0.02, "scoop_pitch": -0.06, "scoop_controls": 40, "yaw": 0.0,
         "lift_pitch": -0.06, "lift_z": 0.07, "lift_back": 0.03, "carry_z": 0.075, "deposit_offset": 0.03,
         "deposit_z": 0.012, "deposit_pitch": 0.14, "withdraw": 0.16, "withdraw_controls": 40, "slack_rows": 150}
    P.update(params or {})
    config = None
    if "override" in P:  # authoring experiments only (e.g. a candidate threshold); the oracle uses task.json
        config = json.loads((HERE / "task.json").read_text())
        config.update(P["override"])
    s = Session(hand=P.get("hand", "sharpa"), config=config)
    c = Controller(s, P)
    yaw = P["yaw"]
    fwd = np.array([-np.sin(yaw), np.cos(yaw)])  # blade direction in the plane
    steps = [
        ("approach above pan", lambda: c.move([*(PAN + fwd * (P["push_from"] if P.get("push_to") is not None else P["tip_start"])), FLOOR_Z + 0.07], P["enter_pitch"], yaw, 75, "approach")),
        ("pre-push pancake", lambda: c.prepush(P, yaw)),
        ("lower tip to floor", lambda: c.move([*(PAN + fwd * P["tip_start"]), FLOOR_Z - P["press"]], P["enter_pitch"], yaw, 40, "lower")),
        ("slide under pancake", lambda: c.slide(P["tip_start"], P["tip_end"], FLOOR_Z - P["press"], yaw, P["slide_controls"], "slide", P["margin_deg"], P["min_pitch"])),
        ("scoop", lambda: c.move([*(PAN + fwd * P["tip_end"]), FLOOR_Z + P["scoop_z"]], P["scoop_pitch"], yaw, P["scoop_controls"], "scoop")),
        ("lift", lambda: c.move([*(PAN + fwd * (P["tip_end"] - P["lift_back"])), FLOOR_Z + P["lift_z"]], P["lift_pitch"], yaw, 60, "lift")),
        ("carry to plate", lambda: c.move([*(PLATE + fwd * P["deposit_offset"]), PLATE_Z + P["carry_z"]], P["lift_pitch"], yaw, 90, "carry")),
        ("lower over plate", lambda: c.move([*(PLATE + fwd * P["deposit_offset"]), PLATE_Z + P["deposit_z"]], P["lift_pitch"], yaw, 50, "lower to plate")),
        ("tilt tip down", lambda: c.move([*(PLATE + fwd * P["deposit_offset"]), PLATE_Z + 0.002], P["deposit_pitch"], yaw, 30, "tilt")),
        ("withdraw", lambda: c.move([*(PLATE + fwd * (P["deposit_offset"] - P["withdraw"])), PLATE_Z + 0.004], P["deposit_pitch"], yaw, P["withdraw_controls"], "withdraw")),
        ("lift away", lambda: c.move([*(PLATE + fwd * (P["deposit_offset"] - P["withdraw"] - 0.03)), PLATE_Z + 0.10], 0.0, yaw, 40, "lift away")),
        ("hold", lambda: c.hold(120, "hold")),
    ]
    if P.get("variant") == "drop":
        # Negative test: carry the pancake over the bare counter and roll the blade so it slides off.
        spot = np.array([0.62, -0.12])
        steps = steps[:5] + [
            ("carry over counter", lambda: c.move([*spot, PLATE_Z + 0.09], P["lift_pitch"], yaw, 80, "carry over counter")),
            ("roll blade", lambda: c.move([*spot, PLATE_Z + 0.09], P["lift_pitch"], yaw, 50, "roll", roll=1.1)),
            ("hold", lambda: c.hold(150, "hold")),
        ]
    elif P.get("variant") == "toss":
        # Negative test: lift the loaded blade high between pan and plate and tip it so the pancake falls off.
        spot = np.array([0.63, 0.02])
        steps = steps[:5] + [
            ("raise", lambda: c.move([*spot, PLATE_Z + 0.20], P["lift_pitch"], yaw, 80, "raise")),
            ("tip blade", lambda: c.move([*spot, PLATE_Z + 0.20], 0.9, yaw, 25, "tip")),
            ("hold", lambda: c.hold(100, "hold")),
        ]
    elif P.get("variant") == "knock":
        # Negative test: slide the blade under the pan handle and lever the pan up (knocks it off its rest).
        steps = [
            ("approach pan handle", lambda: c.move([0.30, -0.04, 0.92], 0.0, yaw, 75, "approach handle")),
            ("lower beside handle", lambda: c.move([0.30, -0.04, 0.879], 0.0, yaw, 40, "lower")),
            ("slide under handle", lambda: c.move([0.30, 0.17, 0.880], 0.0, yaw, 60, "under handle")),
            ("lever the pan", lambda: c.move([0.30, 0.17, 0.95], -0.25, yaw, 60, "lever")),
            ("shove the pan", lambda: c.move([0.30, 0.33, 0.95], -0.25, yaw, 60, "shove")),
            ("hold", lambda: c.hold(100, "hold")),
        ]
    for name, fn in steps:
        fn()
        if verbose:
            c.log(name)
        if s.done:
            break
    status = s.status()
    if s.success and P.get("slack_rows", 0):
        # Episodes end at success; the extra hold rows are never executed, they only give the oracle slack
        # (a replay that reaches success a little later still finds rows that keep the hand still).
        c.rows.extend([c.rows[-1].copy() for _ in range(P["slack_rows"])])
        c.phases.extend(["slack hold"] * P["slack_rows"])
    if out:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        s.save_trajectory(np.asarray(c.rows), out)  # actions + hand + task only
    if phases_out:
        Path(phases_out).write_text(json.dumps(c.phases) + "\n")
    return status, c


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    parser.add_argument("--params", default="{}")
    parser.add_argument("--phases", help="optional JSON file with the phase label of every row")
    args = parser.parse_args()
    status, c = run(json.loads(args.params), args.out, phases_out=args.phases)
    print(json.dumps({k: status[k] for k in ("success", "reason", "stage", "steps", "failure_detail")}))
