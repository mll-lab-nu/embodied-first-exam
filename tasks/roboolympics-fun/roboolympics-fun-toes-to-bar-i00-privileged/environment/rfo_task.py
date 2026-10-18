"""Toes-to-bar: hanging from the FIG horizontal bar by both hands, five toes-to-bar: both feet touch the bar between the
hands, then back to the full hang, each time. Kipping is legal; the hands stay on the bar."""
import math
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from rfo.task import TaskBase

# The hanging pose of the G1's left arm (shoulder pitch, roll, yaw, elbow, wrist roll, pitch, yaw; the right arm
# mirrors the roll and the yaws): straight up, the palms 0.39 m apart, 0.805 m above the pelvis and over the centre of
# mass.
HANG_ARM = np.array([-3.06, 0.57, 1.0, 1.4, 0.0, 0.0, 0.0])
MIRROR = np.array([1.0, -1.0, -1.0, 1.0, -1.0, 1.0, -1.0])
ARMS = slice(15, 29)
MAT = 0.20                    # FIG landing mats under the bar (m)


def build_bar(sc, height, length, diameter):
    """The horizontal bar along y at (0, 0, height) between two uprights `length` apart, over the landing mats. The
    bar turns freely about its own axis (a hinge fixed in the world): with the grip a weld, that is the hands turning
    round the bar. The bar meets the robot's body hulls and the feet's strike boxes, not the gripping hands and wrists."""
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
    sc.grippables["bar"] = {"radius": r, "half_length": half, "axis": "y"}
    con = sc.root.find("contact")
    for side in ("left", "right"):
        for link in ("mount", "wrist_yaw_link", "wrist_pitch_link", "wrist_roll_link"):
            ET.SubElement(con, "exclude", body1="bar", body2=f"{side}_{link}")


def hang(w, height):
    """Put the robot under the bar, arms straight up, both hands gripping it (the arms' targets held at that pose)."""
    r, d = w.robot, w.d
    pose = np.r_[HANG_ARM, HANG_ARM * MIRROR]
    d.qpos[r.qadr[ARMS]] = pose
    r.arb.q_a[ARMS] = r.arb.q_b[ARMS] = pose
    mujoco.mj_kinematics(w.m, d)
    mid = 0.5 * (d.site_xpos[r.palm["left"]] + d.site_xpos[r.palm["right"]])
    d.qpos[r.fq] += 0.0 - mid[0]
    d.qpos[r.fq + 2] += height - mid[2]
    w.grab("left", "bar", event=False)
    w.grab("right", "bar", event=False)


def swing_state(w, height):
    """(angle of the line bar -> centre of mass from straight down, rad, positive forwards, in (-pi, pi]; its length, m)."""
    c = w.com()
    dx, dz = float(c[0]), height - float(c[2])
    return math.atan2(dx, dz), math.hypot(dx, dz)


class Task(TaskBase):
    name = "toes-to-bar"
    title = "High bar: toes-to-bar"
    category = "parkour-apparatus-balance"
    robot = "unitree_g1"
    rulebook = ("CrossFit Games movement standard, toes-to-bar: from a full hang with the arms extended and the heels "
                "behind the bar, both feet touch the bar at the same time between the hands; kipping is allowed. The "
                "bar is the FIG horizontal bar (FIG Apparatus Norms: 2.80 m above the floor, 2.40 m between the "
                "uprights, 28 mm in diameter) over 0.20 m mats")
    deviations = [
        "the grip (no fingers on this robot): each hand's grip is a rigid hold on the bar (the simulator's weld), and "
        "the bar turns freely in its bearings about its own axis in place of the hands turning round a fixed bar, "
        "because the hands cannot wrap a bar; opening a grip lets go",
        "CrossFit standard (the full hang is judged by eye: arms extended, heels behind the bar): the hang is judged "
        "by where the feet are (both feet's centres at least {hang_feet_below_bar_m} m below the bar, nine tenths of "
        "the dead hang's 1.55 m, and behind the bar), because the referee has positions, not a judge's eye",
        "FIG Apparatus Norms, horizontal bar (elasticity): the bar is rigid, because the simulator has rigid bodies "
        "only",
    ]
    time_limit_s = 60.0
    start = (-0.011, 0.0, 0.0)
    stages = ["rep 1", "rep 2", "rep 3", "rep 4", "rep 5"]
    fall_rule = False                # the robot hangs: the task's own rules judge the ground and the grip
    params = dict(bar_height_m=2.80, bar_length_m=2.40, bar_diameter_m=0.028, reps=5, hang_feet_below_bar_m=1.40)

    sentence = ("Hanging from the high bar by both hands, do five toes-to-bar: bring both feet up to touch the bar "
                "between your hands, and come back to the full hang each time, without letting go.")
    rules = ("The bar is {bar_diameter_m} m thick, {bar_height_m} m above the floor, {bar_length_m} m long between its "
             "two uprights, along the y axis; it turns freely about its own axis. Both hands grip it from the start. "
             "A repetition has two parts, in this order. The touch: both feet touch the bar at the same moment, each "
             "at a point between your two hands (shins, knees or anything else on the bar is not a touch, and does "
             "not fail). The hang: afterwards the centres of both feet are at least {hang_feet_below_bar_m} m below "
             "the bar and behind it (x less than the bar's; the heels back behind the bar), both at the same moment "
             "(in your dead hang they are 1.55 m below it). You succeed when the hang of repetition {reps} is "
             "reached. Swinging is allowed (a kip is legal), as is bending the knees on the way. You fail the moment "
             "either hand no longer grips the bar, any part of you touches the uprights, the mats or the floor, or "
             "after {time_limit_s} s.")
    venue = ("At t = 0 you hang still under the middle of the bar, facing +x: both arms straight up, both grips "
             "closed on the bar (hands 0.39 m apart: the palms at y = +0.195 and -0.195 m), legs in the standing "
             "posture, your pelvis 0.80 m below the bar, your feet 1.55 m below it and 0.04 m behind it, your soles "
             "about 1.25 m above the floor (1.05 m above the 0.20 m mats under the bar). Your feet are 0.24 m apart, "
             "each 0.08 m wide. A grip command below 0.5 opens that hand and lets go of the bar. Nothing holds the "
             "legs up here: the `stand` action keeps the legs in the stance with a feed-forward meant for standing on "
             "the ground; `joints` or `lowcmd` rows drive every joint. The uprights stand at the two ends of the bar, "
             "1.2 m to either side of you.")
    difficulty = ("The bar is 0.80 m above your pelvis and your legs are 0.75 m long: hip flexion alone does not "
                  "bring the toes to the bar, the trunk has to lean back or swing as well, against shoulders of "
                  "25 N m, and the legs have to come all the way down again, five times within the time.")

    def build(self, sc):
        p = self.p
        build_bar(sc, p["bar_height_m"], p["bar_length_m"], p["bar_diameter_m"])
        sc.camera("venue", (3.6, -4.6, 2.3), (0.0, 0.0, 1.75), fovy=50)

    def reset(self, w):
        hang(w, self.p["bar_height_m"])

    def referee_reset(self, w, ref):
        self.robot = ref.part("robot")
        self.posts = ref.geoms(prefix="post")
        self.bar_g = ref.geoms(names=["bar"])
        self.foot = {s: ref.part(f"{s}_foot") for s in ("left", "right")}
        self.trackers = {"reps": 0, "touched": False, "touches": 0}

    def feet(self, w):
        """Per foot centre: (how far below the bar, how far ahead of it), m."""
        d, r, H = w.d, w.robot, self.p["bar_height_m"]
        return {s: (H - float(d.site_xpos[r.foot_site[s]][2]), float(d.site_xpos[r.foot_site[s]][0]))
                for s in ("left", "right")}

    def toes_on_bar(self, w, ref) -> bool:
        """Both feet on the bar now, each at a point between the hands."""
        d, r = w.d, w.robot
        y0, y1 = sorted(float(d.site_xpos[r.palm[s]][1]) for s in ("left", "right"))
        for s in ("left", "right"):
            pts = ref.contact_points(self.foot[s], self.bar_g)
            if not len(pts) or not np.any((pts[:, 1] > y0) & (pts[:, 1] < y1)):
                return False
        return True

    def substep(self, w, ref):
        tr = self.trackers
        if len(w.holder("bar")) < 2:
            return ref.fail("let go of the bar", holding=w.holder("bar"))
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
                "holding": w.holder("bar")}
