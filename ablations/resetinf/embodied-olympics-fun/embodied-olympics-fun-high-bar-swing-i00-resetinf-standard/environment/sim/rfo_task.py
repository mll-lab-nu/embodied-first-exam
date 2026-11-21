"""High bar (FIG): from standing on a mounting block behind the FIG horizontal bar (2.80 m high, fixed in its
uprights), jump up and catch the bar, then one giant swing: a full circle of the extended body around the bar, the
hands on the bar throughout. Nothing is welded: both hands are the G1's own Dex3-1 three-finger hands (rfo.realhand,
"dex3": Menagerie's kinematics, Unitree's joint motors), whose fingers and thumb close round the 28 mm bar during the
jump; the bar stays in a hand only by the contact of its closed fingers (their drives' torque limits) and friction,
and it can be torn out of the hand.

THE GRIP FORCE (declared deviation; measured in the simulator image): the Dex3-1's own drives (0.49 N m
closing, 1.37 N m back-driven per finger joint; the thumb's rotation 0.86 / 3.1 N m) hold the hanging G1 but not the
bottom of a giant swing, which pulls about four body weights or more (the extended G1, centre of mass about 0.8 m
below the bar; gymnasts measure 3.5 to 3.7, Kopp & Reid 1980, strain gauges on the bar). This family raises the
hands' drive torques by the factor GRIP_SCALE (realhand's grip_scale: the active and passive limits, kp and kd);
the measured need is in GRIP_SCALE's comment and in the deviations. Nothing else about the hand changes.

The hand on the fixed bar: the bar does not turn (as the norm's does not); a hand turns on it only by its fingers
sliding round the bar or by the wrist's joints (5 N m in pitch and yaw). The body's extension over the top is judged
from the wrists (declared), so that a hand folding at the wrist on the bar is not a tuck.

The bar's and the venue's block (build_bar, swing_state, wrist_radius, bar_contacts, hang, BarGrip) is shared,
identically, with toes-to-bar (a task directory holds one module); hang() is not used here (the robot starts on the
block)."""
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

GRIP_SCALE = 5.0              # the Dex3-1 drives x this (declared): the measured need (4.5 lets go, 5 holds; see
#                               deviations); a declared exception to the families' 2 x cap


class Task(BarGrip, TaskBase):
    name = "high-bar-swing"
    title = "High bar: jump to the bar and giant swing"
    category = "parkour-apparatus-balance"
    robot = "unitree_g1"
    rulebook = ("FIG Apparatus Norms, men's artistic gymnastics, horizontal bar: the bar 2.80 m above the floor (2.60 m "
                "above the 0.20 m landing mats), 2.40 m between the uprights, 28 mm in diameter, fixed in the "
                "uprights; FIG Code of Points (men's artistic gymnastics), horizontal bar: the giant swing (a full "
                "circle round the bar with the body extended, in hang)")
    deviations = [
        "the grip (the hands on the bar): each hand is the G1's own Dex3-1 three-finger hand (thumb 3 joints, index "
        "and middle 2 each, one motor per joint), closed round the bar; it holds the bar by its fingers' contact and "
        "friction alone, nothing is welded, and the bar can be torn out of the hand; the bar is fixed, as the norm's "
        "is, and a hand turns on it only by sliding round it or by the wrist's joints",
        "the grip force: the hands' drives are {grip_scale} times the Dex3-1's (closing 0.49 N m, back-driven 1.37 N m "
        "per finger joint; the thumb's rotation 0.86 / 3.1 N m), because with the device's torques the two hands hold "
        "about one body weight on the bar (measured: torn off by the catch itself; 1.5 times: 1.55, 2 times: 2.05 body "
        "weights) while the bottom of a giant swing pulls about four or more (up to 8.6 in 10 ms here; gymnasts 3.5 "
        "to 3.7, Kopp & Reid 1980); in a giant swing in this venue 4.5 times the device's lets go and "
        "{grip_scale} times holds, forwards and backwards (measured). No Unitree hand is this strong",
        "the grip (the hands stay on the bar): defined by contact: the catch is both hands grasping the bar (the bar "
        "touching each hand's index or middle finger and its thumb or palm); after it a hand is on the bar while the "
        "bar touches any part of it (a hook grip counts), and a break of up to {off_bar_s} s (contacts flickering "
        "under a load) is not letting go",
        "the mount: the robot (1.32 m) starts standing on a {block_top_m} m mounting block behind the bar and jumps "
        "to it (a rise of about 0.15 m), because it cannot reach a 2.80 m bar from the mats (a gymnast is lifted to "
        "the bar or jumps from a springboard)",
        "FIG Code of Points (the body extended, judged by eye): the extension is measured from the wrists: whenever "
        "the centre of mass is above the bar it must be at least {min_radius_m} m from the midpoint of the wrists "
        "(nine tenths of the dead hang's), because the referee has positions, not a judge's eye, and the hands may "
        "fold at the wrists on the fixed bar",
        "FIG Apparatus Norms, horizontal bar (elasticity): the bar is rigid, not the norm's elastic steel bar on "
        "tensioned cables, because the simulator has rigid bodies only (the real bar's spring helps the gymnast: this "
        "is not easier)",
        "FIG Code of Points (a routine is scored): one element is judged pass or fail, because the task is a single "
        "action",
    ]
    time_limit_s = 60.0
    start = (-0.225, 0.0, 0.0)
    stages = ["jumped", "caught the bar", "over the top", "full circle"]
    fall_rule = False                # the task's own rules judge the ground, the block and the grip
    bar_ok = ()                      # only the hands may touch the bar
    params = dict(bar_height_m=2.80, bar_length_m=2.40, bar_diameter_m=0.028, circle_deg=360.0, min_radius_m=0.59,
                  reversal_deg=5.0, off_bar_s=0.05, block_top_m=1.1, block_x_m=-0.30, grip_scale=GRIP_SCALE)

    sentence = ("Standing on the block behind the high bar, jump up and catch the bar with both hands, then do one "
                "giant swing: take your extended body in a full circle around the bar, without letting go.")
    rules = ("The bar is a competition horizontal bar: {bar_diameter_m} m thick, {bar_height_m} m above the floor, "
             "{bar_length_m} m long between its two uprights, along the y axis; it is fixed and does not turn. Your "
             "hands are three-finger hands (a thumb, an index and a middle finger; each hand's drives {grip_scale} "
             "times the stock hand's torques); they hold the bar by their fingers' contact and friction only, so the "
             "bar can be torn out of a hand. A hand grasps the bar while the bar touches its index or middle finger "
             "and its thumb or palm; a hand is on the bar while the bar touches any part of it (fingers, thumb or "
             "palm: a hook grip counts). You start standing on the block and must jump to the bar: the catch is the "
             "moment both hands grasp the bar after you have left the block (grasping it before leaving the block "
             "fails). Before the catch you fail if you touch the mats or the floor; you may land back on the block "
             "and jump again. After the catch, when for more than {off_bar_s} s a hand has not been on the bar you have "
             "let go (whether you opened the hand or the bar was torn out), and there is no regrip; only the hands "
             "may touch the bar; touching the block, the uprights, the mats or the floor fails. Your swing angle is "
             "the angle between straight down and the line from the bar to your centre of mass, seen from the side. "
             "The giant swing is a full circle of that line after the catch: the angle must travel {circle_deg} "
             "degrees in one direction (forwards or backwards) without turning back; a turn back of more than "
             "{reversal_deg} degrees starts the count again from where you turned. The body must be extended over "
             "the top: whenever your centre of mass is higher than the bar it must be at least {min_radius_m} m from "
             "the midpoint of your two wrists (nine tenths of the dead hang's: a slight pike or arch passes, a tuck "
             "or bent arms do not); if it comes closer there, the count starts again from that point. You succeed "
             "the moment the count reaches {circle_deg} degrees. Below the bar you may bend as you like to build up "
             "the swing. You fail after {time_limit_s} s.")
    venue = ("At t = 0 you stand on a {block_top_m} m block (0.40 m along x, 0.80 m along y) behind the bar, its "
             "centre {block_x_m} m from the bar along x, facing +x: both arms straight up, the wrists turned so that "
             "the palms face forwards and the fingers point up, the hands open (grip values 0), the bar about 0.15 m "
             "above and 0.12 m ahead of the palms. A grip value is that hand's closure command (0 open, 1 every "
             "finger and thumb joint closing towards its closed angle; a finger stops on what it touches); a full "
             "close takes about 0.1 s. The bar is not a free body: the `held` flags of your state stay empty for it; "
             "the grip is judged as the rules say. The `stand` action keeps the legs in the stance; `joints` or "
             "`lowcmd` rows drive every joint. The uprights stand at the two ends of the bar, 1.2 m to either side "
             "of you; the landing mats (0.20 m) cover the floor under the bar around the block.")
    difficulty = ("A real jump: the legs must lift the whole robot about 0.15 m and forwards so that the bar enters "
                  "the open hands, and the fingers must close round it in flight. Then nothing pushes you: the swing "
                  "has to be pumped up from a hang by the legs, the waist and the shoulders, against motors of 88 N m "
                  "at the hips and 25 N m in the arms, until the body goes over the top of the bar extended; the "
                  "bottom of a giant swing pulls about four times your weight through the fingers and the arms, and "
                  "the hands slide round the fixed bar against their own friction.")

    def configure(self, params):
        super().configure(params)
        self.start = (self.p["block_x_m"] + 0.075, 0.0, 0.0)     # standing near the block's front edge

    def build(self, sc):
        p = self.p
        build_bar(sc, p["bar_height_m"], p["bar_length_m"], p["bar_diameter_m"], float(p["grip_scale"]))
        sc.platform("block", (p["block_x_m"], 0.0), (0.20, 0.40, p["block_top_m"] / 2), rgba=(0.75, 0.55, 0.25, 1))
        sc.camera("venue", (3.6, -4.6, 2.3), (0.0, 0.0, 1.75), fovy=50)
        sc.camera("side", (0.5, -3.6, 2.7), (0.0, 0.0, 2.7), fovy=56)

    def reset(self, w):
        """Standing on the block, arms straight up in the catch pose, hands open."""
        r, d = w.robot, w.d
        pose = np.r_[CATCH_ARM, CATCH_ARM * MIRROR]
        d.qpos[r.qadr[ARMS]] = pose
        r.arb.q_a[ARMS] = r.arb.q_b[ARMS] = pose
        d.qpos[r.fq + 2] += self.p["block_top_m"]

    def referee_reset(self, w, ref):
        self.robot = ref.part("robot")
        self.posts = ref.geoms(prefix="post")
        self.block = ref.geoms(names=["block"])
        ang, _ = swing_state(w, self.p["bar_height_m"])
        self.trackers = {"prev": ang, "s": 0.0, "anchor": 0.0, "ext": 0.0, "sense": 0, "best_deg": 0.0,
                         "max_deg": 0.0, "min_deg": 0.0, "on_block": False, "flown": False, "caught": False}
        self.grip_reset(w, ref)

    def substep(self, w, ref):
        tr = self.trackers
        if not tr["caught"]:
            if ref.touching(self.not_on_bar, self.bar_g):
                return ref.fail("touched the bar with a part other than the hands",
                                parts=sorted(ref.parts_touching(self.bar_g)))
            if ref.touching(self.robot, ref.ground):
                return ref.fail("touched the ground", parts=sorted(ref.parts_touching(ref.ground)))
            held = self.holding(ref)
            on_block = ref.touching(self.robot, self.block)
            tr["on_block"] = tr["on_block"] or on_block
            if tr["on_block"] and not on_block and not held and not tr["flown"]:
                tr["flown"] = True
                ref.stage("jumped")
            if len(held) == 2:
                if not tr["flown"] or on_block:
                    return ref.fail("held the bar without jumping to it")
                tr["caught"] = True
                self.trackers["on_t"] = {s: round(ref.time, 4) for s in SIDES}
                tr["prev"] = swing_state(w, self.p["bar_height_m"])[0]
                ref.stage("caught the bar")
            return
        if self.grip_substep(w, ref):
            return
        if ref.touching(self.robot, self.posts):
            return ref.fail("touched the uprights", parts=sorted(ref.parts_touching(self.posts)))
        if ref.touching(self.robot, self.block):
            return ref.fail("touched the block after the catch", parts=sorted(ref.parts_touching(self.block)))
        if ref.touching(self.robot, ref.ground):
            return ref.fail("touched the ground", parts=sorted(ref.parts_touching(ref.ground)))

    def step(self, w, ref):
        p, tr = self.p, self.trackers
        if ref.failed or not tr["caught"]:
            return
        ang, radius = swing_state(w, p["bar_height_m"])
        step = (ang - tr["prev"] + math.pi) % (2 * math.pi) - math.pi
        tr["prev"] = ang
        s = tr["s"] = tr["s"] + step
        tr["max_deg"], tr["min_deg"] = max(tr["max_deg"], math.degrees(s)), min(tr["min_deg"], math.degrees(s))
        rev = math.radians(p["reversal_deg"])
        if tr["sense"] == 0:
            if abs(s - tr["anchor"]) > rev:
                tr["sense"] = 1 if s > tr["anchor"] else -1
                tr["ext"] = s
        elif (s - tr["ext"]) * tr["sense"] > 0:
            tr["ext"] = s
        elif (tr["ext"] - s) * tr["sense"] > rev:                 # turned back: the travel starts again there
            tr["anchor"], tr["ext"], tr["sense"] = tr["ext"], s, -tr["sense"]
        above = w.com()[2] > p["bar_height_m"]
        if above and wrist_radius(w) < p["min_radius_m"]:         # not extended over the top: the count starts again
            if abs(tr["ext"] - tr["anchor"]) > rev:
                ref.event("not extended over the bar", wrist_radius_m=round(wrist_radius(w), 3))
            tr["anchor"] = tr["ext"] = s
            tr["sense"] = 0
        travel = abs(tr["ext"] - tr["anchor"])
        tr["best_deg"] = max(tr["best_deg"], round(math.degrees(travel), 1))
        ref.metrics["travel_deg"] = tr["best_deg"]
        ref.metrics["max_forward_deg"] = round(tr["max_deg"], 1)
        ref.metrics["max_backward_deg"] = round(-tr["min_deg"], 1)
        k0, k1 = sorted((tr["anchor"], tr["ext"]))
        n = math.ceil((k0 - math.pi) / (2 * math.pi))
        if math.pi + 2 * math.pi * n <= k1 and travel > rev:
            ref.stage("over the top", wrist_radius_m=round(wrist_radius(w), 3))
        if travel >= math.radians(p["circle_deg"]) and ref.stage("full circle"):
            ref.metrics["time_s"] = round(w.t, 2)
            ref.succeed()

    def privileged(self, w):
        ang, radius = swing_state(w, self.p["bar_height_m"])
        return {"swing_deg": math.degrees(ang), "com_radius_m": radius, "wrist_radius_m": wrist_radius(w),
                "bar": [0.0, 0.0, self.p["bar_height_m"]], "travel_deg": self.trackers.get("best_deg", 0.0),
                "holding": self.holding(w.ref), "caught": self.trackers.get("caught", False),
                "grasp_centres": {s: w.hands.grasp_frame(s)[0].tolist() for s in SIDES}}
