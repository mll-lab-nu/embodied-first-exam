"""High bar: from a dead hang on the FIG horizontal bar (2.80 m high), one giant swing: a full circle of the extended
body around the bar, the hands on the bar throughout."""
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
    name = "high-bar-swing"
    title = "High bar: giant swing"
    category = "parkour-apparatus-balance"
    robot = "unitree_g1"
    rulebook = ("FIG Apparatus Norms, men's artistic gymnastics, horizontal bar: the bar 2.80 m above the floor (2.60 m "
                "above the 0.20 m landing mats), 2.40 m between the uprights, 28 mm in diameter; FIG Code of Points, "
                "horizontal bar: the giant swing (a full circle round the bar with the body extended)")
    deviations = [
        "the grip (no fingers on this robot): each hand's grip is a rigid hold on the bar (the simulator's weld), and "
        "the bar turns freely in its bearings about its own axis in place of the hands turning round a fixed bar, "
        "because the hands cannot wrap a bar; opening a grip lets go",
        "FIG Apparatus Norms, horizontal bar (elasticity): the bar is rigid, not the norm's elastic steel bar on "
        "tensioned cables, because the simulator has rigid bodies only (the real bar's spring helps the gymnast: this "
        "is not easier)",
        "FIG Code of Points (a routine is scored): one element is judged pass or fail from a dead hang, because the "
        "task is a single action; the mount to the hang is given",
    ]
    time_limit_s = 60.0
    start = (-0.011, 0.0, 0.0)
    stages = ["over the top", "full circle"]
    fall_rule = False                # the robot hangs: the task's own rules judge the ground and the grip
    params = dict(bar_height_m=2.80, bar_length_m=2.40, bar_diameter_m=0.028, circle_deg=360.0, min_radius_m=0.74,
                  reversal_deg=5.0)

    sentence = ("Hanging from the high bar by both hands, do one giant swing: take your extended body in a full "
                "circle around the bar, without letting go.")
    rules = ("The bar is a competition horizontal bar: {bar_diameter_m} m thick, {bar_height_m} m above the floor, "
             "{bar_length_m} m long between its two uprights, along the y axis; it turns freely about its own axis. "
             "Both hands grip it from the start. Your swing angle is the angle between straight down and the line "
             "from the bar to your centre of mass, seen from the side. The giant swing is a full circle of that line: "
             "the angle must travel {circle_deg} degrees in one direction (forwards or backwards) without turning "
             "back; a turn back of more than {reversal_deg} degrees starts the count again from where you turned. The "
             "body must be extended over the top: whenever your centre of mass is higher than the bar it must be at "
             "least {min_radius_m} m from the bar (nine tenths of the 0.82 m of your dead hang: a slight pike or arch "
             "passes, a tuck or bent arms do not); if it comes closer there, the count starts again from that point. You succeed "
             "the moment the count reaches {circle_deg} degrees. Below the bar you may bend as you like to build up "
             "the swing. You fail the moment either hand no longer grips the bar, any part of you touches the "
             "uprights, the mats or the floor, or after {time_limit_s} s.")
    venue = ("At t = 0 you hang still under the middle of the bar, facing +x: both arms straight up, both grips "
             "closed on the bar (hands about 0.39 m apart), legs in the standing posture, your pelvis 0.80 m below "
             "the bar and your soles about 1.25 m above the floor (1.05 m above the 0.20 m mats under the bar). A "
             "grip command below 0.5 opens that hand and lets go of the bar. Nothing holds the legs up here: the "
             "`stand` action keeps the legs in the stance with a feed-forward meant for standing on the ground; "
             "`joints` or `lowcmd` rows drive every joint. The uprights stand at the two ends of the bar, 1.2 m to "
             "either side of you.")
    difficulty = ("Nothing pushes you: the swing has to be pumped up from rest by moving the legs, the waist and the "
                  "shoulders in time with the pendulum, against motors of 88 N m at the hips and 25 N m in the arms, "
                  "until the body goes over the top of the bar extended. A simple leg pump is known to stall a little "
                  "above the horizontal.")

    def build(self, sc):
        p = self.p
        build_bar(sc, p["bar_height_m"], p["bar_length_m"], p["bar_diameter_m"])
        sc.camera("venue", (3.6, -4.6, 2.3), (0.0, 0.0, 1.75), fovy=50)

    def reset(self, w):
        hang(w, self.p["bar_height_m"])

    def referee_reset(self, w, ref):
        self.robot = ref.part("robot")
        self.posts = ref.geoms(prefix="post")
        ang, _ = swing_state(w, self.p["bar_height_m"])
        # s: the unwrapped swing angle (rad); anchor: where the present one-way travel started; ext: its far end;
        # sense: +1 forwards, -1 backwards, 0 not yet moving
        self.trackers = {"prev": ang, "s": 0.0, "anchor": 0.0, "ext": 0.0, "sense": 0, "best_deg": 0.0,
                         "max_deg": 0.0, "min_deg": 0.0}

    def substep(self, w, ref):
        if len(w.holder("bar")) < 2:
            ref.fail("let go of the bar", holding=w.holder("bar"))
        elif ref.touching(self.robot, self.posts):
            ref.fail("touched the uprights", parts=sorted(ref.parts_touching(self.posts)))
        elif ref.touching(self.robot, ref.ground):
            ref.fail("touched the ground", parts=sorted(ref.parts_touching(ref.ground)))

    def step(self, w, ref):
        p, tr = self.p, self.trackers
        if ref.failed:
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
        if above and radius < p["min_radius_m"]:                  # not extended over the top: the count starts again
            if abs(tr["ext"] - tr["anchor"]) > rev:
                ref.event("not extended over the bar", radius_m=round(radius, 3))
            tr["anchor"] = tr["ext"] = s
            tr["sense"] = 0
        travel = abs(tr["ext"] - tr["anchor"])
        tr["best_deg"] = max(tr["best_deg"], round(math.degrees(travel), 1))
        ref.metrics["travel_deg"] = tr["best_deg"]
        ref.metrics["max_forward_deg"] = round(tr["max_deg"], 1)
        ref.metrics["max_backward_deg"] = round(-tr["min_deg"], 1)
        # the top: the travel has taken the centre of mass through the vertical above the bar
        k0, k1 = sorted((tr["anchor"], tr["ext"]))
        n = math.ceil((k0 - math.pi) / (2 * math.pi))
        if math.pi + 2 * math.pi * n <= k1 and travel > rev:
            ref.stage("over the top", radius_m=round(radius, 3))
        if travel >= math.radians(p["circle_deg"]) and ref.stage("full circle"):
            ref.metrics["time_s"] = round(w.t, 2)
            ref.succeed()

    def privileged(self, w):
        ang, radius = swing_state(w, self.p["bar_height_m"])
        return {"swing_deg": math.degrees(ang), "com_radius_m": radius, "bar": [0.0, 0.0, self.p["bar_height_m"]],
                "travel_deg": self.trackers.get("best_deg", 0.0),
                "bar_angle_rad": float(w.d.qpos[w.m.joint("bar").qposadr[0]]), "holding": w.holder("bar")}
