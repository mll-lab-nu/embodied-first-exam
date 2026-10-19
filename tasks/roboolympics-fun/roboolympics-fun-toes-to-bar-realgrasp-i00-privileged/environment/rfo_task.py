"""Toes-to-bar with a real grip: toes-to-bar's task (hanging from the FIG horizontal bar, five toes-to-bar: both feet
touch the bar between the hands, then back to the full hang, each time), but nothing is welded: both hands are
Unitree's Dex1-1 two-finger grippers clamped on the bar, and the robot hangs from it by the friction of the jaws alone,
so the bar can slide along the jaws and out of them.

Official setting: toes-to-bar's (the CrossFit Games movement standard on the FIG horizontal bar: 2.80 m high, 2.40 m
between the uprights, 28 mm, over 0.20 m mats), its rules and numbers; only the hold differs. Nothing is scaled to
the robot.

The hold (measured in the simulator image, the core's Dex1-1 model, rfo.realhand: pads of friction 1.0, at most 120 N
per jaw, elliptic cones, impratio 100; nothing raised): as in high-bar-swing-realgrasp (see its docstring): each
gripper closes fore and aft across the bar, the fingers up along the forearm, the bar's axis 15 mm from the gripper's
body; the only hold whose pull goes straight through the 5 N m wrists, carried by friction. It slides the bar out of
the jaws at 238 N per hand: 476 N for both = 1.41 times the weight of the robot with its grippers (34.4 kg); the dead
hang holds (the bar settles 3.8 mm in the first second, then creeps about 0.02 mm/s). Whatever slips is lost: the
pull is always away from the gripper's body, so the bar never slides back in, and it leaves the 80 mm jaws at about
0.08 m.
What the movement needs: toes-to-bar's reference solution (a kipped snap: the feet thrown onto the bar in 0.3 s)
loads each hand with up to 2200 N over 50 ms (the weld's force in toes-to-bar's world) and tears the bar out of the
jaws within 0.15 s here; on the bar, what the feet push it with is carried by the grippers on top of the body's
weight (a foot arriving at speed: 300-400 N). A slow, strict toes-to-bar fits: the reference solution here
(oracles/toes-to-bar-realgrasp) folds in about 3 s, touches the bar gently, lowers the legs over 5.5 s and calms the
swing before the next one; it slides the bar about 7 mm along the jaws per repetition (from 20 mm to 50-67 mm after
five) and takes about 40 s of the 60 s.

The bar's and the venue's block (build_bar, hang, clamp_bar, jaws_on, bar_in_jaws, swing_state, BarGrip) is
high-bar-swing-realgrasp's, copied byte for byte (a task directory holds one module)."""
import math
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from rfo import realhand
from rfo.task import TaskBase

# ------------------------------------------------------------------------------------------- the bar and the hang
# (shared, identically, by high-bar-swing-realgrasp and toes-to-bar-realgrasp)
# The hanging pose of the G1's left arm (shoulder pitch, roll, yaw, elbow, wrist roll, pitch, yaw; the right arm
# mirrors the roll and the yaws): high-bar-swing's, straight up, with the wrist rolled 0.97 rad so that the gripper's
# closing axis lies along x (across the bar, horizontal) and the fingers point up along the forearm.
HANG_ARM = np.array([-3.06, 0.57, 1.0, 1.4, 0.97, 0.0, 0.0])
MIRROR = np.array([1.0, -1.0, -1.0, 1.0, -1.0, 1.0, -1.0])
ARMS = slice(15, 29)
MAT = 0.20                    # FIG landing mats under the bar (m)
SIDES = ("left", "right")


def build_bar(sc, height, length, diameter):
    """The horizontal bar along y at (0, 0, height) between two uprights `length` apart, over the landing mats; a
    Dex1-1 gripper on each wrist. The bar turns freely about its own axis (a hinge fixed in the world). Nothing is
    grippable (no weld): the bar meets every collision geom of the robot, the grippers' jaws and bodies included."""
    half, r = length / 2, diameter / 2
    grey = (0.3, 0.3, 0.33, 1)
    for s, tag in ((1, "L"), (-1, "R")):
        sc.geom(sc.wb, f"post{tag}", type="cylinder", pos=(0, s * (half + 0.03), (height + 0.06) / 2),
                size=(0.03, (height + 0.06) / 2), rgba=grey, contype="1", conaffinity="13")
        sc.box(f"post_foot{tag}", (0, s * (half + 0.03), 0.01), (0.60, 0.05, 0.01), rgba=grey)
    sc.platform("mat", (0.0, 0.0), (3.0, 1.0, MAT / 2), rgba=(0.20, 0.35, 0.60, 1), ground=True)
    b = sc.body("bar", (0.0, 0.0, height))
    ET.SubElement(b, "joint", name="bar", type="hinge", axis="0 1 0", damping="0.02", armature="0.005")
    sc.geom(b, "bar", type="capsule", fromto=(0, -half, 0, 0, half, 0), size=(r,), mass=2.0 * length / 1.2,
            rgba=(0.85, 0.85, 0.88, 1), contype="0", conaffinity="12", friction=(0.8, 0.005, 0.0001))
    for s in SIDES:
        sc.real_hands[s] = "dex1"


def hang(w, height, bar_depth):
    """Put the robot under the bar, arms straight up, the bar between each gripper's open jaws with its axis
    `bar_depth` m from the gripper's body along the fingers; then both grippers close on it."""
    r, d, m = w.robot, w.d, w.m
    pose = np.r_[HANG_ARM, HANG_ARM * MIRROR]
    d.qpos[r.qadr[ARMS]] = pose
    r.arb.q_a[ARMS] = r.arb.q_b[ARMS] = pose
    mujoco.mj_kinematics(m, d)
    off = (2 * realhand.HOUSING[2] + bar_depth) - realhand.CENTRE_Z      # from the jaws' centre along the fingers
    pts = []
    for s in SIDES:
        k = m.site(f"{s}_jaw_centre").id
        pts.append(d.site_xpos[k] + off * d.site_xmat[k].reshape(3, 3)[:, 2])
    mid = 0.5 * (pts[0] + pts[1])
    d.qpos[r.fq] += 0.0 - mid[0]
    d.qpos[r.fq + 2] += height - mid[2]
    clamp_bar(w)


def clamp_bar(w, closure=1.0, extra_s=0.05):
    """Close both grippers on the bar with the rest of the world held still: realhand.close_on's procedure (which
    takes free bodies only; the bar is a hinge in the world): the jaws close at their speed limit until both jaws of
    both hands touch the bar and the servos' setpoints are at the command, then extra_s more for the pads to take the
    clamp. The robot is let go at t = 0 (deterministic: a function of the state). Raises if a hand does not hold it."""
    hands, m, d = w.hands, w.m, w.d
    keep_q = np.ones(m.nq, dtype=bool)
    keep_v = np.ones(m.nv, dtype=bool)
    for s in SIDES:
        hands.cmd[s] = closure
        keep_q[hands.jq[s]] = keep_v[hands.jv[s]] = False
    mujoco.mj_forward(m, d)
    q0 = d.qpos.copy()
    arm0 = m.dof_armature.copy()
    m.dof_armature[keep_v] = realhand.FREEZE_ARMATURE
    bar = m.geom("bar").id
    n_close = int(math.ceil((realhand.HALF / (realhand.SPEED / 2) + 0.05) / m.opt.timestep))
    n_extra = int(round(extra_s / m.opt.timestep))
    on_since = None
    try:
        for k in range(n_close + n_extra):
            hands.substep()
            mujoco.mj_step(m, d)
            d.qpos[keep_q] = q0[keep_q]
            d.qvel[keep_v] = 0.0
            if on_since is None and all(jaws_on(w, s, bar) == (True, True) for s in SIDES) and all(
                    abs(hands.setpoint[s] - realhand.HALF * closure) < 1e-12 for s in SIDES):
                on_since = k
            if on_since is not None and k - on_since >= n_extra:
                break
    finally:
        m.dof_armature[:] = arm0
    for s in SIDES:
        d.qvel[hands.jv[s]] = 0.0
    mujoco.mj_forward(m, d)
    if on_since is None:
        raise RuntimeError("the grippers did not close on the bar")


def jaws_on(w, side, bar):
    """(jaw a touches the bar, jaw b touches the bar) now, by contact (penetrating: dist <= 0)."""
    m, d, hands = w.m, w.d, w.hands
    n = d.ncon
    if not n:
        return (False, False)
    g = d.contact.geom[:n]
    keep = d.contact.dist[:n] <= 0.0
    i = 1 + 2 * hands.sides.index(side)
    out = [False, False]
    for a, b in g[keep]:
        o = b if a == bar else a if b == bar else None
        if o is None:
            continue
        c = int(hands.jaw_code[o])
        if c in (i, i + 1):
            out[c - i] = True
    return tuple(out)


def bar_in_jaws(w, height):
    """Per hand: where the bar's axis is in the gripper (m): along the fingers from the face of the gripper's body (the
    jaws' pads run from 0 to 0.08), and off the jaws' centre line along the closing axis."""
    m, d = w.m, w.d
    out = {}
    for s in SIDES:
        k = m.site(f"{s}_jaw_centre").id
        c, R = d.site_xpos[k], d.site_xmat[k].reshape(3, 3)
        rel = np.array([0.0, c[1], height]) - c
        out[s] = (float(R[:, 2] @ rel) + realhand.CENTRE_Z - 2 * realhand.HOUSING[2], float(R[:, 0] @ rel))
    return out


def swing_state(w, height):
    """(angle of the line bar -> centre of mass from straight down, rad, positive forwards, in (-pi, pi]; its length, m)."""
    c = w.com()
    dx, dz = float(c[0]), height - float(c[2])
    return math.atan2(dx, dz), math.hypot(dx, dz)


class BarGrip:
    """The grip rules: a hand holds the bar while the bar touches both of its gripper's jaws; a break longer than
    params["off_bar_s"] is letting go (no re-grip). Only the grippers (their jaws and bodies) and the parts in
    `bar_ok` may touch the bar."""
    bar_ok: tuple = ()

    def grip_reset(self, w, ref):
        self.bar_g = ref.geoms(names=["bar"])
        self.jaws = {s: (ref.geoms(body=f"{s}_hand_jaw_a"), ref.geoms(body=f"{s}_hand_jaw_b")) for s in SIDES}
        allowed = ref.geoms(body="left_mount") | ref.geoms(body="right_mount")      # the grippers: body and jaws
        if self.bar_ok:
            allowed |= ref.part(*self.bar_ok)
        self.not_on_bar = ref.part("robot") & ~allowed
        self.trackers["on_t"] = {s: 0.0 for s in SIDES}

    def holding(self, ref):
        return [s for s in SIDES if ref.touching(self.bar_g, self.jaws[s][0]) and ref.touching(self.bar_g, self.jaws[s][1])]

    def grip_substep(self, w, ref) -> bool:
        """The grip rules on this physics step; True if one was broken (the attempt has failed)."""
        p, on = self.p, self.trackers["on_t"]
        held = self.holding(ref)
        for s in SIDES:
            if s in held:
                on[s] = round(ref.time, 4)
                continue
            gap = round(ref.time - on[s], 4)
            if gap > ref.metrics.get("grip_break_max_s", 0.0):
                ref.metrics["grip_break_max_s"] = gap   # (reported: the longest break of a hand's two-jaw contact)
            if gap > p["off_bar_s"] + 1e-9:
                ref.fail("let go of the bar", hand=s, off_s=gap)
                return True
        if ref.touching(self.not_on_bar, self.bar_g):
            ref.fail("held the bar with a part other than the grippers", parts=sorted(ref.parts_touching(self.bar_g)))
            return True
        return False
# ------------------------------------------------------------------------------- (end of the shared bar block)


class Task(BarGrip, TaskBase):
    name = "toes-to-bar-realgrasp"
    title = "High bar: toes-to-bar, real grip"
    category = "parkour-apparatus-balance"
    robot = "unitree_g1"
    rulebook = ("CrossFit Games movement standard, toes-to-bar: from a full hang with the arms extended and the heels "
                "behind the bar, both feet touch the bar at the same time between the hands; kipping is allowed. The "
                "bar is the FIG horizontal bar (FIG Apparatus Norms: 2.80 m above the floor, 2.40 m between the "
                "uprights, 28 mm in diameter) over 0.20 m mats")
    deviations = [
        "the grip (the hands on the bar): each hand is a two-finger gripper, Unitree's Dex1-1 (90 mm stroke, 80 mm "
        "jaws with rubber pads, at most 120 N; sold for the G1), closed across the bar; it holds the bar by the jaws' "
        "friction alone, nothing is welded, and the bar can slide along the jaws and out of them. Flat jaws clamp the "
        "bar but cannot wrap round it, so the bar turns freely in its bearings about its own axis in place of the "
        "hands turning round a fixed bar",
        "the grip (the hands stay on the bar): defined by contact: a hand holds the bar while the bar touches both of "
        "its gripper's jaws; a break of up to {off_bar_s} s (the pads' contact flickering under a load; measured "
        "breaks last 1 to 3 ms) is not letting go",
        "CrossFit standard (the full hang is judged by eye: arms extended, heels behind the bar): the hang is judged "
        "by where the feet are (both feet's centres at least {hang_feet_below_bar_m} m below the bar, toes-to-bar's "
        "nine tenths of its dead hang's 1.55 m, and behind the bar), because the referee has positions, not a "
        "judge's eye",
        "FIG Apparatus Norms, horizontal bar (elasticity): the bar is rigid, because the simulator has rigid bodies "
        "only",
    ]
    time_limit_s = 60.0
    start = (-0.011, 0.0, 0.0)
    stages = ["rep 1", "rep 2", "rep 3", "rep 4", "rep 5"]
    fall_rule = False                # the robot hangs: the task's own rules judge the ground and the grip
    bar_ok = ("legs",)               # the feet (and shins, knees, thighs) may touch the bar; arms, trunk, head not
    params = dict(bar_height_m=2.80, bar_length_m=2.40, bar_diameter_m=0.028, reps=5, hang_feet_below_bar_m=1.40,
                  bar_depth_m=0.015, off_bar_s=0.05)

    sentence = ("Hanging from the high bar by the two grippers that are your hands, do five toes-to-bar: bring both "
                "feet up to touch the bar between your hands, and come back to the full hang each time, without "
                "letting go.")
    rules = ("The bar is {bar_diameter_m} m thick, {bar_height_m} m above the floor, {bar_length_m} m long between its "
             "two uprights, along the y axis; it turns freely about its own axis. Your hands are two-finger grippers, "
             "and at the start each is closed on the bar; they hold it by the friction of their jaws only, so the bar "
             "can slide along the jaws and out of them. A hand holds the bar while the bar touches both of that "
             "gripper's jaws; when for more than {off_bar_s} s a hand has not held it, you have let go (whether you "
             "opened the gripper or the bar slipped out), and there is no re-grip. Besides the grippers only your "
             "legs may touch the bar: an arm, the trunk or the head on it fails. A repetition has two parts, in this "
             "order. The touch: both feet touch the bar at the same moment, each at a point between your two hands "
             "(the jaws' centres; shins, knees or anything else of the legs on the bar is not a touch, and does not "
             "fail). The hang: afterwards the centres of both feet are at least {hang_feet_below_bar_m} m below the "
             "bar and behind it (x less than the bar's; the heels back behind the bar), both at the same moment (in "
             "your dead hang they are 1.59 m below it). You succeed when the hang of repetition {reps} is reached. "
             "Swinging is allowed (a kip is legal), as is bending the knees on the way. You fail the moment you let "
             "go of the bar, an arm, the trunk or the head touches the bar, any part of you touches the uprights, the "
             "mats or the floor, or after {time_limit_s} s.")
    venue = ("At t = 0 you hang still under the middle of the bar, facing +x: both arms straight up, the wrists turned "
             "so that each gripper's jaws close fore and aft on the bar, the fingers pointing up and the bar between "
             "them {bar_depth_m} m from the gripper's body (1 mm clear of it; the jaws are 0.08 m long beyond it), "
             "the jaws' centres at y = +0.207 and -0.207 m, your legs in the standing posture, your pelvis 0.84 m "
             "below the bar, your feet 1.59 m below it and 0.03 m behind it, your soles about 1.21 m above the floor "
             "(1.01 m above the 0.20 m mats under the bar). Your feet are 0.24 m apart, each 0.08 m wide. Both grip "
             "values are 1: the clamp's full 120 N on each jaw. A grip value is that gripper's closure command (0 "
             "open, 1 closed): on the 28 mm bar, about 0.82 or more clamps at 120 N, less clamps more lightly (10 N "
             "per mm that the commanded opening, 90 mm times one less the value, is below 28 mm), and below about "
             "0.69 the jaws no longer clamp it. The bar is not a free body: the `held` flags of your state stay empty "
             "for it; the grip is judged as the rules say. Nothing holds the legs up here: the `stand` action keeps "
             "the legs in the stance with a feed-forward meant for standing on the ground; `joints` or `lowcmd` rows "
             "drive every joint. The uprights stand at the two ends of the bar, 1.2 m to either side of you.")
    difficulty = ("The grippers' friction holds about 1.4 times your weight in all, and the bar never slides back in: "
                  "a kip or a quick snap of the legs, and the feet striking the bar, pull harder than that, so the "
                  "feet have to be brought up and lowered with little more than your weight on the bar. The bar is "
                  "0.84 m above your pelvis and your legs are 0.75 m long: hip flexion alone does not bring the toes "
                  "to the bar, the trunk has to lean back as well, against shoulders of 25 N m, five times within the "
                  "time.")

    def build(self, sc):
        p = self.p
        build_bar(sc, p["bar_height_m"], p["bar_length_m"], p["bar_diameter_m"])
        sc.camera("venue", (3.6, -4.6, 2.3), (0.0, 0.0, 1.75), fovy=50)

    def reset(self, w):
        hang(w, self.p["bar_height_m"], self.p["bar_depth_m"])

    def referee_reset(self, w, ref):
        self.robot = ref.part("robot")
        self.posts = ref.geoms(prefix="post")
        self.foot = {s: ref.part(f"{s}_foot") for s in SIDES}
        self.trackers = {"reps": 0, "touched": False, "touches": 0}
        self.grip_reset(w, ref)

    def feet(self, w):
        """Per foot centre: (how far below the bar, how far ahead of it), m."""
        d, r, H = w.d, w.robot, self.p["bar_height_m"]
        return {s: (H - float(d.site_xpos[r.foot_site[s]][2]), float(d.site_xpos[r.foot_site[s]][0])) for s in SIDES}

    def toes_on_bar(self, w, ref) -> bool:
        """Both feet on the bar now, each at a point between the hands (the jaws' centres)."""
        d, r = w.d, w.robot
        y0, y1 = sorted(float(d.site_xpos[r.palm[s]][1]) for s in SIDES)
        for s in SIDES:
            pts = ref.contact_points(self.foot[s], self.bar_g)
            if not len(pts) or not np.any((pts[:, 1] > y0) & (pts[:, 1] < y1)):
                return False
        return True

    def substep(self, w, ref):
        tr = self.trackers
        if self.grip_substep(w, ref):
            return
        if ref.touching(self.robot, self.posts):
            return ref.fail("touched the uprights", parts=sorted(ref.parts_touching(self.posts)))
        if ref.touching(self.robot, ref.ground):
            return ref.fail("touched the ground", parts=sorted(ref.parts_touching(ref.ground)))
        if not tr["touched"] and self.toes_on_bar(w, ref):
            tr["touched"] = True
            tr["touches"] += 1
            ref.metrics["touches"] = tr["touches"]
            ref.event("toes on the bar", rep=tr["reps"] + 1)

    def step(self, w, ref):
        p, tr = self.p, self.trackers
        if ref.failed:
            return
        f = self.feet(w)
        hanging = all(below >= p["hang_feet_below_bar_m"] and ahead < 0.0 for below, ahead in f.values())
        if tr["touched"] and hanging:
            tr["touched"] = False
            tr["reps"] += 1
            ref.metrics["reps"] = tr["reps"]
            if ref.stage(f"rep {tr['reps']}") and tr["reps"] == p["reps"]:
                ref.metrics["time_s"] = round(w.t, 2)
                ref.succeed()

    def privileged(self, w):
        ang, radius = swing_state(w, self.p["bar_height_m"])
        return {"swing_deg": math.degrees(ang), "com_radius_m": radius, "bar": [0.0, 0.0, self.p["bar_height_m"]],
                "feet_below_bar_m": {s: v[0] for s, v in self.feet(w).items()},
                "feet_ahead_of_bar_m": {s: v[1] for s, v in self.feet(w).items()},
                "reps": self.trackers.get("reps", 0), "touched": self.trackers.get("touched", False),
                "holding": self.holding(w.ref),
                "bar_in_jaws_m": {k: v[0] for k, v in bar_in_jaws(w, self.p["bar_height_m"]).items()}}
