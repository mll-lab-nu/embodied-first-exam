"""Authoring controller (closed loop over Session state, recorded as open-loop actuator rows).

Phases: all four clips start open; close the two lower clips with the index fingertip (hand beside the rim, pointing
down along it), grasp the hub cap of the flat guard, lift, turn it upright (dome toward the operator), carry it in
front of the fan raised above the lower clips, press it onto the rear rim, lower it into the two lower clip channels,
release, then close the two upper clips one after the other with the index fingertip and withdraw.
Only actuator targets are produced; the recorded rows are replayed in fresh processes by replay.py.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import pickle
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from fanplan import Kinematics, hand_frame, stage_angles, stage_rotation  # noqa: E402
from geometry import AXIAL, CAP_AXIAL, CAP_HALF, FAN_POSITION, GUARD_REST, GUARD_SEAT  # noqa: E402
from runtime import Session  # noqa: E402
from scipy.spatial.transform import Rotation, Slerp  # noqa: E402


class Recorder:
    def __init__(self, session):
        self.s = session
        self.rows = []
        self.phases = []
        self.origin = np.asarray(session.config["wrist_stage"]["origin"], float)
        self.lo, self.hi = session.model.actuator_ctrlrange.T

    def step(self, q, phase):
        q = np.clip(np.asarray(q, float), self.lo + 1e-6, self.hi - 1e-6)
        self.rows.append(q.copy())
        self.phases.append(phase)
        # The plan continues after the episode ends (rows after success are never executed; they give slack).
        if not self.s.done:
            self.success_row = len(self.rows) if False else getattr(self, "success_row", None)
            f = self.s.step(q)
            if self.s.success and self.success_row is None:
                self.success_row = len(self.rows)
            return f
        return self.s.features()

    def move(self, q_from, q_to, n, phase, smooth=True):
        q_from, q_to = np.asarray(q_from, float), np.asarray(q_to, float)
        for i in range(1, n + 1):
            t = i / n
            if smooth:
                t = 0.5 - 0.5 * np.cos(np.pi * t)
            f = self.step(q_from + (q_to - q_from) * t, phase)
            if self.s.failure:
                return f
        return f

    def hold(self, q, n, phase):
        f = None
        for _ in range(n):
            f = self.step(q, phase)
            if self.s.failure:
                break
        return f

    def wrist_pose(self, q):
        """(world wrist point, stage rotation) of target row q."""
        return self.origin + q[:3], stage_rotation(q[3:6])

    def with_pose(self, q, point, rotation):
        q = np.array(q, float)
        q[3:6] = stage_angles(rotation, q[3:6])
        q[:3] = point - self.origin
        return q


def report(s, tag):
    f = s.features()
    g = s.data.body("front_guard")
    print(f"[{s.steps:5d}] {tag:24s} stage={f['stage']} fail={f['failure']} guard={np.round(g.xpos, 4)} "
          f"conc={f['concentric_m']*1000:.1f}mm ax={f['seat_axial_m']*1000:.1f}mm par={np.degrees(f['parallel_rad']):.1f}deg "
          f"clips={np.round(f['clip_angles_rad'], 3)} hand={f['hand_contact']} fan={f['fan_displacement_m']*1000:.2f}mm",
          flush=True)


def grasp_rows(s, rec, k, grasp_q, open_q):
    q0 = s.hold_action()
    rec.hold(q0, 10, "settle")
    above = open_q.copy()
    above[2] += 0.06
    mid = above.copy()
    mid[2] += 0.06
    rec.move(q0, mid, 90, "reach above the hub cap")
    rec.move(mid, above, 30, "reach above the hub cap")
    report(s, "above")
    rec.move(above, open_q, 50, "descend around the cap")
    report(s, "pre-grasp")
    return open_q


def run(args):
    s = Session(hand=args.hand)
    k = Kinematics(s)
    rec = Recorder(s)
    grasp_q = np.load(args.grasp)
    squeeze = np.load(args.squeeze)
    q = s.hold_action()
    rec.hold(q, 10, "settle")
    # All four clips start open: close the two lower clips first so they become hanger channels.
    for clip in args.lower_clips:
        q = close_clip(s, rec, k, q, clip, args)
        report(s, f"lower clip {clip} closed")
        if s.failure:
            return s, rec
    if args.lower_clips:
        q_free = q.copy()
        q_free[0] -= 0.10
        q_free[2] += 0.10
        rec.move(q, q_free, 60, "withdraw from the lower clips")
    if args.stop == "lower":
        return s, rec
    pre = grasp_rows(s, rec, k, grasp_q, np.load(args.open))
    rec.move(pre, grasp_q, 30, "close on the cap")
    rec.move(grasp_q, squeeze, 25, "squeeze the cap")
    rec.hold(squeeze, 15, "squeeze the cap")
    report(s, "grasped")
    # lift straight up
    lifted = squeeze.copy()
    lifted[2] += 0.30
    rec.move(squeeze, lifted, 110, "lift the guard")
    report(s, "lifted")
    if args.stop == "lift":
        return s, rec
    # rotate about the cap centre: R_y(-90 deg) in world, carried with a translation toward the fan
    cap = s.data.body("front_guard").xpos + s.data.body("front_guard").xmat.reshape(3, 3)[:, 0] * CAP_AXIAL
    w0, r0 = rec.wrist_pose(lifted)
    turn = Rotation.from_euler("y", -np.pi / 2)
    seat_center = FAN_POSITION + GUARD_SEAT * AXIAL
    pre_center = seat_center + args.standoff * AXIAL + np.array([0, 0, args.raise_z])
    # guard centre after the turn sits at cap - (CAP_AXIAL) * new guard axis (= AXIAL) -> centre = cap_new + CAP_AXIAL*(+x)
    n = args.turn_steps
    key = Rotation.concatenate([Rotation.identity(), turn])
    slerp = Slerp([0, 1], key)
    cap_target_final = pre_center + CAP_AXIAL * AXIAL
    q_prev = lifted
    for i in range(1, n + 1):
        t = 0.5 - 0.5 * np.cos(np.pi * i / n)
        rd = slerp([t])[0]
        cap_t = cap + (cap_target_final - cap) * t
        w = cap_t + rd.apply(w0 - cap)
        q = rec.with_pose(q_prev, w, rd.as_matrix() @ r0)
        rec.step(q, "turn the guard upright and carry it to the fan")
        q_prev = q
        if s.failure:
            break
    report(s, "carried")
    rec.hold(q_prev, 30, "settle in front of the fan")
    report(s, "settled")
    if args.stop == "carry":
        return s, rec
    q_prev = seat_guard(s, rec, q_prev, seat_center, args)
    if args.stop == "seat":
        return s, rec
    q_prev = release_cap(s, rec, q_prev, np.load(args.open))
    if args.stop == "release":
        return s, rec
    for clip in args.clips:
        q_prev = close_clip(s, rec, k, q_prev, clip, args)
        if s.failure:
            break
    q_prev = withdraw(s, rec, q_prev)
    if not s.failure:
        rec.hold(q_prev, args.tail, "hands off: hold")
    report(s, "end")
    return s, rec


def guard_center(s):
    return s.data.body("front_guard").xpos.copy()


def track_guard(s, rec, q_prev, path, phase, gain=0.08, limit=0.01, rot_gain=0.0, rot_limit=0.08):
    """Move the wrist so the held guard centre follows ``path`` (world points) with a bounded integral correction;
    with ``rot_gain`` the wrist also turns about the guard centre to keep the guard axis on the fan axis."""
    w, rot = rec.wrist_pose(q_prev)
    corr = np.zeros(3)
    rcorr = np.zeros(3)
    last = path[0]
    q = q_prev
    for target in path:
        w = w + (target - last)
        last = target
        c = guard_center(s)
        err = target - c
        corr = np.clip(corr + gain * err, -limit, limit)
        if rot_gain:
            axis = s.data.body("front_guard").xmat.reshape(3, 3)[:, 0]
            e = np.cross(axis, AXIAL)
            rcorr = np.clip(rcorr + rot_gain * e, -rot_limit, rot_limit)
        R = Rotation.from_rotvec(rcorr).as_matrix()
        wc = c + R @ (w - c)
        q = rec.with_pose(q, wc + corr, R @ rot)
        rec.step(q, phase)
        if s.failure:
            break
    return q


def seat_guard(s, rec, q_prev, seat_center, args):
    start = guard_center(s)
    above = seat_center + np.array([0, 0, args.raise_z])
    n = 80
    path = [start + (above - start) * (0.5 - 0.5 * np.cos(np.pi * i / n)) for i in range(1, n + 1)]
    q_prev = track_guard(s, rec, q_prev, path, "press the guard onto the rear rim", limit=0.004, rot_gain=0.05)
    report(s, "on rear rim (raised)")
    # press slightly into the rim while lowering into the two lower clip channels
    press = seat_center + args.press * (-AXIAL)
    low = press + np.array([0, 0, -args.lower_extra])
    n = 70
    a = above + args.press * (-AXIAL)
    path = [a + (low - a) * (0.5 - 0.5 * np.cos(np.pi * i / n)) for i in range(1, n + 1)]
    q_prev = track_guard(s, rec, q_prev, path, "lower the guard into the lower clips", gain=0.0, rot_gain=0.03)
    rec.hold(q_prev, 20, "lower the guard into the lower clips")
    report(s, "seated in lower clips")
    return q_prev


def release_cap(s, rec, q_prev, open_q):
    q = q_prev.copy()
    q[6:] = open_q[6:]
    rec.move(q_prev, q, 30, "release the hub cap")
    rec.hold(q, 15, "release the hub cap")
    report(s, "released")
    back = q.copy()
    back[0] -= 0.08
    rec.move(q, back, 50, "withdraw from the cap")
    report(s, "withdrawn")
    return back


POINTS = {}
POINT = [0.6, 0.15, 0.5, 0.0, 0.8,   # thumb tucked
         0.15, 0.0, 0.35, 0.25,       # index nearly straight
         1.45, 0.0, 1.6, 1.2,         # middle curled
         1.45, 0.0, 1.6, 1.2,         # ring curled
         0.1, 1.45, 0.0, 1.6, 1.2]    # pinky curled


POINTS["sharpa"] = POINT
POINTS["wuji"] = [0.9, -0.6, 0.6, 0.6,   # thumb tucked across the palm
                  0.15, 0.0, 0.3, 0.2,    # index nearly straight
                  1.5, 0.0, 1.9, 1.3,     # middle curled
                  1.5, 0.0, 1.9, 1.3,     # ring curled
                  1.5, 0.0, 1.9, 1.3]     # pinky curled


def clip_frame(s, clip):
    b = s.data.body(f"clip_{clip}_snap_bracket")
    r = b.xmat.reshape(3, 3)
    return b.xpos.copy(), r[:, 0], r[:, 1]


def finger_direction(s, clip, xc, yc):
    """Index direction while swinging ``clip``: radially inward for the upper clips (hand above the clip); along the
    rim toward the bottom of the cage for the lower clips (hand beside the clip, clear of the worktop)."""
    if clip in (0, 1):
        return -yc
    zc = np.cross(xc, yc)
    down = zc if zc[2] < 0 else -zc
    return down - 0.0 * yc


def close_clip(s, rec, k, q_prev, clip, args):
    hinge, xc, yc = clip_frame(s, clip)
    if clip in (0, 1):
        palm = np.array([-1.0, 0.0, 0.0])
    else:  # palm roll about the finger axis, measured from -x (operator side) toward the clip's radial axis
        a = np.radians(args.palm_deg[clip - 2])
        palm = np.cos(a) * np.array([-1.0, 0.0, 0.0]) + np.sin(a) * yc
    rot = hand_frame(finger_direction(s, clip, xc, yc), palm)
    q = q_prev.copy()
    q[6:] = POINTS[s.hand]
    r_f = args.arc_radius

    def tip_point(phi, lift=0.0):
        return hinge + r_f * (np.cos(phi) * xc + np.sin(phi) * yc) + lift * yc

    phi0, phi1 = args.arc_from, args.arc_to
    approach_front = tip_point(phi0, args.approach_lift) + 0.05 * xc
    approach = tip_point(phi0, args.approach_lift)
    q_a = k.wrist_for_tip(q, "index", approach_front, rot)
    far = approach_front + 0.12 * xc + 0.04 * yc
    q_far = k.wrist_for_tip(q, "index", far, rot)
    if clip in (2, 3) and getattr(args, "retreat", 0.0) > 0:
        # back away toward the operator before swinging across the front of the fan
        q_ret = q_prev.copy()
        q_ret[0] = min(q_prev[0], q_far[0]) - args.retreat
        rec.move(q_prev, q_ret, 40, f"move to lower clip {clip}")
        q_prev = q_ret
    q_back = q_prev.copy()
    q_back[0] = min(q_back[0], q_far[0])
    q_back[1:3] = q_far[1:3]
    rec.move(q_prev, q_back, 60, f"move to {'upper' if clip in (0, 1) else 'lower'} clip {clip}")
    rec.move(q_back, q_far, 70, f"move to {'upper' if clip in (0, 1) else 'lower'} clip {clip}")
    rec.move(q_far, q_a, 50, f"move to {'upper' if clip in (0, 1) else 'lower'} clip {clip}")
    report(s, f"in front of clip {clip}")
    q_b = k.wrist_for_tip(q, "index", approach, rot)
    rec.move(q_a, q_b, 40, f"reach behind clip {clip}")
    q_c = k.wrist_for_tip(q, "index", tip_point(phi0), rot)
    rec.move(q_b, q_c, 30, f"reach behind clip {clip}")
    report(s, f"behind clip {clip}")
    n = args.arc_steps
    q_last = q_c
    for i in range(1, n + 1):
        t = 0.5 - 0.5 * np.cos(np.pi * i / n)
        phi = phi0 + (phi1 - phi0) * t
        q_last = k.wrist_for_tip(q, "index", tip_point(phi), rot)
        rec.step(q_last, f"swing clip {clip} closed")
        if s.failure:
            return q_last
    report(s, f"clip {clip} swung")
    q_up = k.wrist_for_tip(q, "index", tip_point(phi1, 0.03), rot)
    rec.move(q_last, q_up, 30, f"lift off clip {clip}")
    q_out = q_up.copy()
    q_out[0] -= 0.05
    rec.move(q_up, q_out, 30, f"lift off clip {clip}")
    report(s, f"after clip {clip}")
    return q_out


def withdraw(s, rec, q_prev):
    q = q_prev.copy()
    q[0] -= 0.12
    q[2] += 0.08
    rec.move(q_prev, q, 60, "withdraw the hand")
    return q


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--hand", default="sharpa")
    p.add_argument("--grasp")
    p.add_argument("--squeeze")
    p.add_argument("--open")
    p.add_argument("--stop", default="")
    p.add_argument("--standoff", type=float, default=0.04)
    p.add_argument("--raise-z", type=float, default=0.020)
    p.add_argument("--turn-steps", type=int, default=200)
    p.add_argument("--press", type=float, default=0.002)
    p.add_argument("--lower-extra", type=float, default=0.004)
    p.add_argument("--clips", type=int, nargs="*", default=[0, 1])
    p.add_argument("--lower-clips", type=int, nargs="*", default=[2, 3])
    p.add_argument("--palm-deg", type=float, nargs=2, default=[45.0, -60.0])
    p.add_argument("--retreat", type=float, default=0.12)
    p.add_argument("--arc-radius", type=float, default=0.0165)
    p.add_argument("--arc-from", type=float, default=2.3)
    p.add_argument("--arc-to", type=float, default=0.95)
    p.add_argument("--arc-steps", type=int, default=60)
    p.add_argument("--approach-lift", type=float, default=0.03)
    p.add_argument("--tail", type=int, default=120)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    prefix = "" if args.hand == "sharpa" else args.hand + "_"
    for key in ("grasp", "squeeze", "open"):
        if getattr(args, key) is None:
            setattr(args, key, str(HERE / "seeds" / f"{prefix}{key}.npy"))
    t = time.time()
    s, rec = run(args)
    np.savez(args.out, actions=np.asarray(rec.rows), phases=np.asarray(rec.phases))
    with open(args.out + ".snap.pkl", "wb") as fh:
        pickle.dump(s.snapshot(), fh)
    print("success_row", getattr(rec, "success_row", None))
    print("rows", len(rec.rows), "time", round(time.time() - t, 1), "status", {k: s.status()[k] for k in ("stage", "reason")})
