"""Toes-to-bar on the FIG horizontal bar (CrossFit Games movement standard): from a dead hang, five toes-to-bar (both
feet touch the bar between the hands, then back to the full hang, each time). Nothing is welded: both hands are the
G1's own Dex3-1 three-finger hands (rfo.realhand, "dex3"), closed round the bar, and the robot hangs from it by the
contact and friction of the fingers, the thumb and the palm alone: the bar can be torn out of a hand. The bar is fixed
in its uprights, as a real one is: it does not turn; a hand turns on it only by sliding round it, or by the wrist's
joints.

Official setting: the FIG horizontal bar (2.80 m high, 2.40 m between the uprights, 28 mm) over 0.20 m mats; the
CrossFit standard's rules. Nothing is scaled to the robot.

THE GRIP FORCE (measured in the simulator image): the two Dex3-1 hold about one body weight on the bar at the device's
drive torques (the dead hang slips out within 3 s), 1.55 at 1.5 times, 2.05 at 2 times. GRIP_SCALE = 1.5
(realhand's grip_scale: the drives' active and passive limits, kp and kd) is the hands' declared force margin
over the device's rating, declared in the deviations.

The bar's and the venue's block (build_bar, swing_state, wrist_radius, bar_contacts, hang, BarGrip) is shared,
identically, with high-bar-swing (a task directory holds one module)."""
import math

import mujoco
import numpy as np

from rfo import realhand
from rfo.task import TaskBase

# ------------------------------------------------------------------------------------------- the bar and the grip
# (shared, identically, by high-bar-swing and toes-to-bar)
MAT = 0.20                    # FIG landing mats under the bar (m)
SIDES = ("left", "right")
# The catch / hang pose of the G1's left arm (shoulder pitch, roll, yaw, elbow, wrist roll, pitch, yaw; the right arm
# mirrors the roll and the yaws): straight up, the fingers up, the palm forwards (+x), the finger joints' axes along
# the bar.
CATCH_ARM = np.array([-2.81, 0.72, 0.3583, 1.3808, 1.8, -0.2208, 0.1125])
MIRROR = np.array([1.0, -1.0, -1.0, 1.0, -1.0, 1.0, -1.0])
ARMS = slice(15, 29)


def build_bar(sc, height, length, diameter, grip_scale):
    """The horizontal bar along y at (0, 0, height) between two uprights `length` apart, over the landing mats; the
    G1's Dex3-1 on each wrist, its drives x grip_scale. The bar is fixed in the world, as the real one is fixed in its
    uprights: it does not turn (a hand turns round it only by sliding round it, or by the wrist's joints). Nothing is
    grippable (no weld): the bar meets every collision geom of the robot, the hands included. Steel on the finger
    pads: the pads' contact parameters win (priority 2, realhand.py); the bar's own friction 0.8 meets the hulls."""
    half, r = length / 2, diameter / 2
    grey = (0.3, 0.3, 0.33, 1)
    for s, tag in ((1, "L"), (-1, "R")):
        sc.geom(sc.wb, f"post{tag}", type="cylinder", pos=(0, s * (half + 0.03), (height + 0.06) / 2),
                size=(0.03, (height + 0.06) / 2), rgba=grey, contype="1", conaffinity="13")
        sc.box(f"post_foot{tag}", (0, s * (half + 0.03), 0.01), (0.60, 0.05, 0.01), rgba=grey)
    sc.platform("mat", (0.0, 0.0), (3.0, 1.0, MAT / 2), rgba=(0.20, 0.35, 0.60, 1), ground=True)
    sc.geom(sc.wb, "bar", type="capsule", fromto=(0, -half, height, 0, half, height), size=(r,),
            rgba=(0.85, 0.85, 0.88, 1), contype="0", conaffinity="12", friction=(0.8, 0.005, 0.0001))
    for s in SIDES:
        sc.real_hands[s] = "dex3"
        if grip_scale != 1.0:
            sc.real_hand_options[s] = {"grip_scale": grip_scale}


def swing_state(w, height):
    """(angle of the line bar -> centre of mass from straight down, rad, positive forwards, in (-pi, pi]; its length, m)."""
    c = w.com()
    dx, dz = float(c[0]), height - float(c[2])
    return math.atan2(dx, dz), math.hypot(dx, dz)


def wrist_radius(w):
    """The distance from the midpoint of the two wrists (the wrist pitch joints) to the centre of mass: the body's
    extension, whatever the hands and the wrists do on the bar."""
    d, m = w.d, w.m
    mid = 0.5 * (d.xpos[m.body("left_wrist_pitch_link").id] + d.xpos[m.body("right_wrist_pitch_link").id])
    return float(np.linalg.norm(w.com() - mid))


def bar_contacts(w, side):
    """(the bar touches the hand's fingers, the bar touches its thumb or palm) now, by contact."""
    m, d = w.m, w.d
    bar = m.geom("bar").id
    fing = set(w.hands.group_geoms(w, side, "fingers"))
    tp = set(w.hands.group_geoms(w, side, "thumb_palm"))
    a = b = False
    for c in d.contact[:d.ncon]:
        g1, g2 = int(c.geom[0]), int(c.geom[1])
        o = g2 if g1 == bar else g1 if g2 == bar else None
        if o is None or c.dist > 0.0:
            continue
        a, b = a or o in fing, b or o in tp
    return a, b


def hang(w, height, settle_s=0.4):
    """At t = 0: the robot under the bar in the hang pose (CATCH_ARM), each hand's grasp centre on the bar's axis, and
    both hands closed on the bar with the rest of the world held still (as realhand's close_on, which takes free bodies
    only: the bar is fixed): the hands close at their drives' speed until every drive has stalled on the bar or
    reached its target and both hands grasp it, then settle_s more. The robot is let go at t = 0 (deterministic: a
    function of the state). Raises if a hand does not grasp the bar."""
    r, d, m, hands = w.robot, w.d, w.m, w.hands
    pose = np.r_[CATCH_ARM, CATCH_ARM * MIRROR]
    d.qpos[r.qadr[ARMS]] = pose
    r.arb.q_a[ARMS] = r.arb.q_b[ARMS] = pose
    mujoco.mj_kinematics(m, d)
    c = 0.5 * (d.site_xpos[m.site("left_grasp").id] + d.site_xpos[m.site("right_grasp").id])
    d.qpos[r.fq] += 0.0 - c[0]
    d.qpos[r.fq + 2] += height - c[2]
    keep_q = np.ones(m.nq, dtype=bool)
    keep_v = np.ones(m.nv, dtype=bool)
    for s in SIDES:
        hands.cmd[s] = 1.0
        keep_q[hands.hq[s]] = keep_v[hands.hv[s]] = False
    mujoco.mj_forward(m, d)
    q0 = d.qpos.copy()
    arm0 = m.dof_armature.copy()
    m.dof_armature[keep_v] = realhand.FREEZE_ARMATURE
    n_settle = int(round(settle_s / m.opt.timestep))
    held_at, still = None, 0
    try:
        for k in range(int(round(2.0 / m.opt.timestep))):
            sp0 = hands._sp.copy()
            hands.substep()
            mujoco.mj_step(m, d)
            d.qpos[keep_q] = q0[keep_q]
            d.qvel[keep_v] = 0.0
            still = still + 1 if np.allclose(hands._sp, sp0, atol=1e-9) else 0
            if held_at is None and still >= 20 and all(bar_contacts(w, s) == (True, True) for s in SIDES):
                held_at = k
            if held_at is not None and k - held_at >= n_settle:
                break
    finally:
        m.dof_armature[:] = arm0
    for s in SIDES:
        d.qvel[hands.hv[s]] = 0.0
    hands._vs[:] = 0.0
    mujoco.mj_forward(m, d)
    if held_at is None:
        raise RuntimeError("the hands did not close on the bar")


class BarGrip:
    """The grip rules: a hand grasps the bar while the bar touches its fingers (index or middle) and its thumb or palm
    (holding: the catch); after the catch a hand is on the bar while the bar touches any part of it (fingers, thumb or
    palm: a hook grip of the fingers alone counts, as in gymnastics); a hand off the bar for longer than
    params["off_bar_s"] has let go (no re-grip). Only the hands and the parts in `bar_ok` may touch the bar."""
    bar_ok: tuple = ()

    def grip_reset(self, w, ref):
        self.bar_g = ref.geoms(names=["bar"])
        ng = w.m.ngeom
        mask = lambda ids: np.isin(np.arange(ng), ids)  # noqa: E731
        self.fingers = {s: mask(w.hands.group_geoms(w, s, "fingers")) for s in SIDES}
        self.thumb_palm = {s: mask(w.hands.group_geoms(w, s, "thumb_palm")) for s in SIDES}
        self.hand_g = {s: self.fingers[s] | self.thumb_palm[s] for s in SIDES}
        allowed = ref.part("hands")
        if self.bar_ok:
            allowed |= ref.part(*self.bar_ok)
        self.not_on_bar = ref.part("robot") & ~allowed
        self.trackers["on_t"] = {s: 0.0 for s in SIDES}

    def holding(self, ref):
        return [s for s in SIDES if ref.touching(self.bar_g, self.fingers[s])
                and ref.touching(self.bar_g, self.thumb_palm[s])]

    def on_bar(self, ref):
        return [s for s in SIDES if ref.touching(self.bar_g, self.hand_g[s])]

    def grip_substep(self, w, ref) -> bool:
        """The grip rules on this physics step; True if one was broken (the attempt has failed)."""
        p, on = self.p, self.trackers["on_t"]
        held = self.on_bar(ref)
        for s in SIDES:
            if s in held:
                on[s] = round(ref.time, 4)
                continue
            gap = round(ref.time - on[s], 4)
            if gap > ref.metrics.get("grip_break_max_s", 0.0):
                ref.metrics["grip_break_max_s"] = gap   # (reported: the longest time a hand was off the bar)
            if gap > p["off_bar_s"] + 1e-9:
                ref.fail("let go of the bar", hand=s, off_s=gap)
                return True
        if ref.touching(self.not_on_bar, self.bar_g):
            ref.fail("held the bar with a part other than the hands", parts=sorted(ref.parts_touching(self.bar_g)))
            return True
        return False
# ------------------------------------------------------------------------------- (end of the shared bar block)


GRIP_SCALE = 1.5              # the Dex3-1 drives x this (declared): the measured need is 1.4 (see deviations)


class Task(BarGrip, TaskBase):
    name = "toes-to-bar"
    title = "High bar: toes-to-bar"
    category = "parkour-apparatus-balance"
    robot = "unitree_g1"
    rulebook = ("CrossFit Games movement standard, toes-to-bar: from a full hang with the arms extended and the heels "
                "behind the bar, both feet touch the bar at the same time between the hands; kipping is allowed. The "
                "bar is the FIG horizontal bar (FIG Apparatus Norms: 2.80 m above the floor, 2.40 m between the "
                "uprights, 28 mm in diameter) over 0.20 m mats")
    deviations = [
        "the grip (the hands on the bar): each hand is the G1's own Dex3-1 three-finger hand (thumb 3 joints, index "
        "and middle 2 each, one motor per joint: 0.49 N m closing, 1.37 N m back-driven per finger joint), closed "
        "round the bar; it holds the bar by its fingers' contact and friction alone, nothing is welded, and the bar "
        "can be torn out of the hand; the bar is fixed, as the norm's is, and a hand turns on it only by sliding round "
        "it or by the wrist's joints",
        "the grip (the hands stay on the bar): defined by contact: a hand is on the bar while the bar touches any part "
        "of it (fingers, thumb or palm: a hook grip counts); a break of up to {off_bar_s} s (contacts flickering "
        "under a load) is not letting go",
        "the grip force: the hands' drives are {grip_scale} times the Dex3-1's, because at the device's torques the "
        "two hands hold about one body weight on the bar (measured: the dead hang itself slips out within 3 s), at "
        "1.5 times about 1.55 body weights (measured): {grip_scale} times is the hands' declared force margin "
        "over the device's rating. No Unitree hand is rated for this",
        "CrossFit standard (the full hang is judged by eye: arms extended, heels behind the bar): the hang is judged "
        "by where the feet are (both feet's centres at least {hang_feet_below_bar_m} m below the bar, about "
        "nine tenths of the dead hang's, and behind the bar), because the referee has positions, not a judge's eye",
        "FIG Apparatus Norms, horizontal bar (elasticity): the bar is rigid, because the simulator has rigid bodies "
        "only",
    ]
    time_limit_s = 60.0
    start = (0.0, 0.0, 0.0)
    stages = ["rep 1", "rep 2", "rep 3", "rep 4", "rep 5"]
    fall_rule = False                # the robot hangs: the task's own rules judge the ground and the grip
    bar_ok = ("legs",)               # the feet (and shins, knees, thighs) may touch the bar; arms, trunk, head not
    params = dict(bar_height_m=2.80, bar_length_m=2.40, bar_diameter_m=0.028, reps=5, hang_feet_below_bar_m=1.40,
                  off_bar_s=0.05, grip_scale=GRIP_SCALE)

    sentence = ("Hanging from the high bar by your two hands, do five toes-to-bar: bring both feet up to touch the bar "
                "between your hands, and come back to the full hang each time, without letting go.")
    rules = ("The bar is {bar_diameter_m} m thick, {bar_height_m} m above the floor, {bar_length_m} m long between its "
             "two uprights, along the y axis; it is fixed and does not turn. Your hands are three-finger hands (a "
             "thumb, an index and a middle finger; their drives {grip_scale} times the stock hand's torques), and at the start each is closed round the bar; they hold it by "
             "their fingers' contact and friction only, so the bar can be torn out of a hand. A hand is on the bar "
             "while the bar touches any part of it (fingers, thumb or palm); when for more than {off_bar_s} s a hand "
             "has not been on it, you have let go (whether you opened the hand or the bar was torn out), and there is "
             "no re-grip. Besides the hands only your legs may touch the bar: an arm, the trunk or the head on it "
             "fails. A repetition has two parts, in this order. The touch: both feet touch the bar at the same "
             "moment, each at a point between your two hands (their grasp centres; shins, knees or anything else of "
             "the legs on the bar is not a touch, and does not fail). The hang: afterwards the centres of both feet "
             "are at least {hang_feet_below_bar_m} m below the bar and behind it (x less than the bar's; the heels "
             "back behind the bar), both at the same moment. You succeed when the hang of repetition {reps} is "
             "reached. Swinging is allowed (a kip is legal), as is bending the knees on the way. You fail the moment "
             "you let go of the bar, an arm, the trunk or the head touches the bar, any part of you touches the "
             "uprights, the mats or the floor, or after {time_limit_s} s.")
    venue = ("At t = 0 you hang still under the middle of the bar, facing +x: both arms straight up, the wrists turned "
             "so that the palms face forwards and the fingers point up, each hand closed round the bar (grip values "
             "1), your legs in the standing posture. A grip value is that hand's closure command (0 open, 1 every "
             "finger and thumb joint closing towards its closed angle; a finger stops on what it touches). The bar "
             "is not a free body: the `held` flags of your state stay empty for it; the grip is judged as the rules "
             "say. Nothing holds the legs up here: the `stand` action keeps the legs in the stance with a "
             "feed-forward meant for standing on the ground; `joints` or `lowcmd` rows drive every joint. The "
             "uprights stand at the two ends of the bar, 1.2 m to either side of you.")
    difficulty = ("The hands hold little more than your weight on the bar: a kip or a quick snap of the legs, and the "
                  "feet striking the bar, pull harder than that, so the feet have to be brought up and lowered with "
                  "little more than your weight on the bar. The bar is high above your pelvis and your legs are short: "
                  "hip flexion alone does not bring the toes to the bar, the trunk has to lean back as well, against "
                  "shoulders of 25 N m, five times within the time. The bar does not turn, so a twist of the hands on "
                  "it is resisted by the same friction that holds you up.")

    def build(self, sc):
        p = self.p
        build_bar(sc, p["bar_height_m"], p["bar_length_m"], p["bar_diameter_m"], float(p["grip_scale"]))
        sc.camera("venue", (3.6, -4.6, 2.3), (0.0, 0.0, 1.75), fovy=50)

    def reset(self, w):
        hang(w, self.p["bar_height_m"])

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
        """Both feet on the bar now, each at a point between the hands (their grasp centres)."""
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
                "holding": self.on_bar(w.ref),
                "grasp_centres": {s: w.hands.grasp_frame(s)[0].tolist() for s in SIDES}}
