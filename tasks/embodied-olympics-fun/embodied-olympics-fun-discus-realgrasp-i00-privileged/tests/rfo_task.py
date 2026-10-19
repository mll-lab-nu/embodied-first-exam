"""Discus throw with a real hold (World Athletics TR 32 and 34): the discus family's circle, sector, discus, robot and
rules, but nothing is welded: the right hand is Unitree's Dex1-1 two-jaw gripper and holds the men's discus by its rim,
clamped between the jaws by friction only (it can slip, turn in the jaws and fly out early); throw it so that it lands
inside the sector at least the qualifying mark away, then leave the circle from its rear half. The Unitree H1-2."""
import math

import mujoco
import numpy as np

from rfo.scene import HITTABLE, STANDABLE
from rfo.task import TaskBase

APRON, RAMP = 1.0, 1.0                        # the ground outside the circle: level for APRON m, then down to the field
N_WEDGE = 48
# ---- the hold ----
# The right hand is a Dex1-1 gripper (rfo/realhand.py). The discus lies between its jaws with its axis along the closing
# axis (its faces on the pads, as a hand's palm and fingers lie on its flat), its rim RIM_GAP_M from the housing's face
# between the jaws: the pads cover the outer 80 mm of it, and the convex faces touch them at the pads' tips, about 30 mm
# from the discus' centre, where it is 43 mm thick (a clamp there pushes it out of the jaws with a slope of 0.06, far
# inside the pads' friction). Clamped at the full 120 N (measured, the robot still, a steady force at the discus'
# centre ramped up until the discus has moved 5 mm in the jaws): about 200 N out of the jaws, 100 N across them (the
# discus turns in the jaws), 110 N along the closing axis (it tips over a jaw's tip); its 2 kg hang in it for a minute.
RIM_GAP_M = 0.003
HOUSING_FACE_M = 0.063                         # the housing's face between the jaws, from the mount (realhand.HOUSING)
JAW_CENTRE_M = 0.103                           # the jaw centre's distance from the mount (realhand.CENTRE_Z)
# ---- end of the hold ----
# Flight in air: MuJoCo's ellipsoid fluid model on the discus' own ellipsoid. Coefficients (blunt drag, slender drag,
# angular drag, Kutta lift, Magnus lift) chosen so that the drag coefficient edge-on is 0.08 and the lift coefficient
# at 10 degrees 0.44 (on the planform area): the order of the published wind-tunnel data (Ganslen 1964); a 25 m/s
# release at 35 degrees then flies 59 m, a 12 m/s release 16 m (measured in this model).
FLUID = (0.2, 0.0, 1.5, 0.9, 1.0)


def set_arm(w, **angles) -> None:
    """Put arm joints (names without "_joint") at angles for t = 0, and their held targets with them."""
    r, d = w.robot, w.d
    for name, v in angles.items():
        i = w.L.JOINTS.index(name + "_joint")
        d.qpos[r.qadr[i]] = v
        r.arb.q_a[i] = r.arb.q_b[i] = v
    mujoco.mj_kinematics(w.m, d)


def build_circle(sc, R: float, rim_h: float, half_sector: float, mark: float, far: float) -> list[str]:
    """A throwing circle of inner radius R round the origin, its inside the floor: the ground outside is rim_h higher
    (TR 32.6), built as N_WEDGE convex wedges that are level for APRON m and then fall to the field over RAMP m; the
    white rim, the two 0.75 m lines through the centre, the sector lines (from the centre, 50 mm, outside the sector)
    and the qualifying mark. Returns the wedges' names (they are ground)."""
    asset = sc.root.find("asset")
    sc.disc("circle", (0.0, 0.0), R, rgba=(0.62, 0.62, 0.60, 1))
    names = []
    da = 2 * math.pi / N_WEDGE
    k = 1.0 / math.cos(da / 2)                               # the polygon lies outside the circle and touches it
    for i in range(N_WEDGE):
        a0, a1 = i * da, (i + 1) * da
        v = []
        for a in (a0, a1):
            c, s = math.cos(a), math.sin(a)
            for r, z in ((R * k, 0.0), (R * k, rim_h), ((R + APRON) * k, rim_h), ((R + APRON + RAMP) * k, 0.0)):
                v += [r * c, r * s, z]
        ET_mesh = asset.makeelement("mesh", dict(name=f"apron{i}", vertex=" ".join(f"{x:.6g}" for x in v)))
        asset.append(ET_mesh)
        sc.geom(sc.wb, f"apron{i}", type="mesh", mesh=f"apron{i}", rgba=(0.24, 0.50, 0.26, 1),
                friction=(1.0, 0.005, 0.0001), **STANDABLE)
        names.append(f"apron{i}")
        sc.line(f"rim{i}", ((R + 0.003) * math.cos(a0), (R + 0.003) * math.sin(a0)),
                ((R + 0.003) * math.cos(a1), (R + 0.003) * math.sin(a1)), width=0.006, z=rim_h + 0.0008)
    for s, tag in ((1, "L"), (-1, "R")):                     # TR 32.7: 50 mm lines, their rear edge through the centre
        sc.line(f"centre_line{tag}", (0.025, s * R), (0.025, s * (R + 0.75)), width=0.05, z=rim_h + 0.0008)
        a = s * half_sector
        n = (-math.sin(a) * s * 0.025, math.cos(a) * s * 0.025)
        r0 = R + APRON + RAMP
        sc.line(f"sector_line{tag}", (r0 * math.cos(a) + n[0], r0 * math.sin(a) + n[1]),
                (far * math.cos(a) + n[0], far * math.sin(a) + n[1]), width=0.05, z=0.0012)
    m = 12
    for i in range(m):
        a0, a1 = -half_sector + 2 * half_sector * i / m, -half_sector + 2 * half_sector * (i + 1) / m
        sc.line(f"mark{i}", ((R + mark) * math.cos(a0), (R + mark) * math.sin(a0)),
                ((R + mark) * math.cos(a1), (R + mark) * math.sin(a1)), width=0.05, rgba=(0.95, 0.85, 0.2, 1))
    return names


class Task(TaskBase):
    name = "discus-realgrasp"
    title = "Athletics: discus throw, real hold"
    category = "throwing-catching-striking"
    robot = "unitree_h1"
    rulebook = ("World Athletics Competition and Technical Rules 2024: TR 32.5-32.8 (the circle, 2.50 m for the "
                "discus), TR 32.12 (the 34.92 degree sector), TR 32.13, 32.14, 32.16, 32.17 and 32.20 (throwing "
                "events: the start, failures, the landing, leaving the circle, the measurement), TR 34 (the men's "
                "discus), TR 35 (the discus cage)")
    deviations = [
        "TR 34 (the discus; the thrower's hand): the right hand is Unitree's Dex1-1 two-jaw gripper (sold for the G1, "
        "the H2 and the R1, not for the H1-2; mounted on the wrist where the H1-2's palm ends): 90 mm stroke, 80 mm "
        "jaws with rubber pads, at most 120 N of grip, opening at most 375 mm/s. It holds the discus by its rim, the "
        "discus' faces between the jaws (where a hand's palm and fingertips hold it), by friction only: nothing is "
        "welded or grippable, and the discus slips, turns in the jaws or flies out when the throw pulls harder than "
        "the clamp's friction (at the full clamp a steady pull at the discus' centre moves it in the jaws at about "
        "200 N out of them and 100 N across them). The release is the gripper's last hold (both jaws on the discus) "
        "before it is clear of the robot.",
        "TR 34 (the discus' shape): an ellipsoid of the official diameter, thickness and mass (no separate metal "
        "rim: its moment of inertia is that of a uniform body; near the rim it is 13 to 19 mm thick, as the rule "
        "book's rim).",
        "TR 35 (the cage): there is no cage.",
        "TR 32.5-32.6: the ground outside the circle is level with the rim's top for " + f"{APRON:g} m and then falls to "
        f"the field's level over {RAMP:g} m" + " (the circle's inside is the field's level, {rim_height_m} m below the "
        "rim, instead of the field being level with the rim).",
        "TR 32.20: the mark is the point where the discus first touches the ground.",
        "TR 32.15 (interrupting a trial, laying the implement down): not modelled; the first release is the throw, "
        "and the discus may not be gripped again.",
        "TR 32.14 names no fall: here a fall ends the trial as a failure, as in every task of this benchmark; the "
        "trial ends when the robot has left the circle correctly and stands.",
        "TR 25.17 (one minute for a trial): the whole trial, leaving the circle included, has {time_limit_s} s.",
        "Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model: drag, lift and the pitching moment of an "
        "ellipsoid, coefficients of the order of the published wind-tunnel data), still air, no wind.",
        "The qualifying mark of {qualifying_mark_m} m is this benchmark's (a school standard for the 2 kg discus); "
        "the rule book only measures.",
    ]
    time_limit_s = 60.0
    start = (-0.55, 0.0, 0.0)
    stages = ["release", "landing", "exit"]
    fall_z = 0.50
    params = dict(discus_mass_kg=2.000, discus_diameter_m=0.220, discus_thickness_m=0.045, circle_diameter_m=2.50,
                  rim_height_m=0.02, rim_edge_m=0.003, sector_deg=34.92, qualifying_mark_m=15.0, retouch_grace_s=0.20, carry_s=0.20,
                  release_gap_s=0.03, stand_s=1.0,
                  fall_pelvis_m=0.50)

    sentence = ("Throw the discus that your right gripper holds by its rim from inside the circle so that it lands "
                "inside the sector at least {qualifying_mark_m} m from the circle, then leave the circle from its "
                "rear half and stand.")
    rules = ("The men's discus ({discus_mass_kg} kg, {discus_diameter_m} m across, {discus_thickness_m} m thick at "
             "its centre) starts clamped by its rim between the two jaws of your right hand's Dex1-1 gripper (the "
             "row's right grip value is the gripper's closure command, 0 open to 1 closed; nothing is welded or "
             "grippable: friction alone holds it, and it slips, turns or flies out when the throw pulls harder than "
             "the clamp). The circle is {circle_diameter_m} m across inside its rim; the ground outside is "
             "{rim_height_m} m higher than its inside. The sector opens from the circle's centre, {sector_deg} "
             "degrees wide, symmetric about the direction you face at the start. Holding: the discus touches both "
             "jaws of the right gripper. Before the release nothing of you but your right hand (the gripper and the "
             "wrist) may touch it, and it may not stay on the hand without the gripper's hold (touching the hand but "
             "not both jaws) for more than {carry_s} s. The release is the gripper's last hold before the discus has "
             "touched nothing of you for {release_gap_s} s; there is one release: after it the discus may not be "
             "held by the gripper again, nothing of you but the right hand may touch it, and the right hand only "
             "during the first {retouch_grace_s} s (brushing it as it leaves). Its first touch of the ground must be "
             "inside the sector lines (on a line is out); the throw is measured from that point to the inside of the "
             "rim along the line through the circle's centre. You succeed when a valid throw measures at least "
             "{qualifying_mark_m} m and you have then left the circle correctly and stood for {stand_s} s. Leaving "
             "correctly: after the discus has landed, your first touch of the rim's top or of the ground outside the "
             "circle is behind the line through the circle's centre across the throwing direction (the rear half). "
             "Standing: only your feet on the ground, the torso within about 20 degrees of upright, the pelvis "
             "slower than 0.35 m/s. You fail if any part of you touches the rim's top (its top inside edge included) "
             "or the ground outside the circle before the discus has landed, or in the front half before you have "
             "left correctly; if the discus is touched by anything but the right hand before the release, stays on "
             "the hand without the gripper's hold, is gripped again or touched after the release (but for the right "
             "hand's brush); if it lands outside the sector or short of {qualifying_mark_m} m; if you fall (your "
             "pelvis lower than {fall_pelvis_m} m above the circle's floor, or any part of you other than your feet "
             "on the ground); or after {time_limit_s} s. Where you touch the ground is judged on the points of "
             "contact; a contact within {rim_edge_m} m of the rim's top counts as on it.")
    venue = ("You stand in the rear half of the circle facing the sector (+x), your pelvis 0.55 m behind the circle's "
             "centre. Your right arm hangs straight down, a little away from the leg; the gripper's fingers point "
             "down and its jaws, closed at the full command, clamp the discus by its rim, the discus hanging below "
             "the hand with its faces towards and away from your leg. There is no cage. Still air.")
    difficulty = ("{qualifying_mark_m} m needs a release at about 12 m/s near 35 to 40 degrees with the discus flat "
                  "to its flight and spinning, or the air turns it over. The H1-2's arm motors give 40 N m at the "
                  "shoulder, so the speed has to come from the trunk's turn, inside a circle of 2.5 m that the "
                  "robot may not leave until the discus is down. At that speed the discus pulls on the hand with some "
                  "300 N, and the gripper's friction gives way earlier (measured on the still robot, a steady force "
                  "at the discus' centre moves it 5 mm in the jaws at about 200 N out of the jaws, 100 N across them "
                  "and 110 N along the closing axis): the hand's path and the discus' place in the jaws decide whether "
                  "it stays in until the release.")

    def build(self, sc):
        p = self.p
        self.fall_z = p["fall_pelvis_m"]
        self.R = R = p["circle_diameter_m"] / 2
        self.half_sector = math.radians(p["sector_deg"]) / 2
        sc.root.find("option").append(sc.root.makeelement("flag", dict(multiccd="enable")))   # feet (hulls) on the apron
        sc.ground += build_circle(sc, R, p["rim_height_m"], self.half_sector, p["qualifying_mark_m"], 40.0)
        b = sc.body("discus", (0.3, -0.4, 0.7), free=True)       # the body's z axis: the discus' axis
        sc.geom(b, "discus", type="ellipsoid", size=(p["discus_diameter_m"] / 2, p["discus_diameter_m"] / 2,
                                                     p["discus_thickness_m"] / 2), mass=p["discus_mass_kg"],
                rgba=(0.75, 0.3, 0.15, 1), friction=(0.7, 0.005, 0.0001), condim=4, fluidshape="ellipsoid",
                fluidcoef=FLUID, **HITTABLE)
        sc.real_hands["right"] = "dex1"                           # nothing grippable: the gripper holds by friction
        sc.camera("venue", (-3.0, -3.8, 2.6), (1.5, 0.0, 0.8), fovy=55)
        sc.camera("sector", (-3.0, 0.0, 14.0), (9.0, 0.0, 0.0), fovy=70)

    def reset(self, w):
        set_arm(w, right_elbow_pitch=1.57, right_shoulder_roll=-0.20)
        c, R = w.jaw_frame("right")                 # x: the closing axis, y: across the jaws, z: along the fingers
        Rb = np.column_stack([R[:, 1], R[:, 2], R[:, 0]])     # the discus' axis: the closing axis
        q = np.zeros(4)
        mujoco.mju_mat2Quat(q, Rb.reshape(-1))
        out = HOUSING_FACE_M + RIM_GAP_M + self.p["discus_diameter_m"] / 2 - JAW_CENTRE_M
        w.put("discus", c + R[:, 2] * out, quat=q)
        w.close_on("right", "discus", closure=1.0)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        self.disc = ref.geoms(body="discus")
        self.robot = ref.part("robot")
        self.apron = ref.geoms(prefix="apron")
        self.floor = ref.geoms(names=["floor"])
        self.disc_id = w.m.body("discus").id
        # last: the discus' state when the gripper last held it (time, centre, velocity, axis, spin about the axis);
        # clear: since when it has touched nothing of the robot after the hold ended
        self.trackers = {"released": None, "landed": None, "exit": False, "last": self._state(w, 0.0), "clear": None}

    def _state(self, w, t) -> list:
        ax = w.d.xmat[self.disc_id].reshape(3, 3)[:, 2]
        _, va = w.free["discus"]
        return [round(t, 4), *w.pos("discus").tolist(), *w.vel("discus").tolist(), *ax.tolist(),
                float(w.d.qvel[va + 5])]

    def _marks(self, w, ref):
        """Where the robot touches now outside the circle: (in the rear half?, in the front half?). Outside = the
        ground beyond the rim or the rim's top (its top inside edge included)."""
        p, R = self.p, self.R
        rear = front = False
        pts = ref.contact_points(self.robot, self.apron)
        if len(pts):
            out = pts[pts[:, 2] >= p["rim_height_m"] - p["rim_edge_m"]]
            rear, front = bool((out[:, 0] < 0).any()), bool((out[:, 0] >= 0).any())
        pts = ref.contact_points(self.robot, self.floor)
        if len(pts):
            out = pts[np.hypot(pts[:, 0], pts[:, 1]) >= R]
            rear, front = rear or bool((out[:, 0] < 0).any()), front or bool((out[:, 0] >= 0).any())
        return rear, front

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        rear, front = self._marks(w, ref)
        if not tr["exit"]:
            if tr["landed"] is None and (rear or front):
                return ref.fail("touched the rim's top or the ground outside the circle before the discus had landed")
            if front:
                return ref.fail("left the circle from its front half")
            if rear and ref.has("landing"):
                tr["exit"] = True
                ref.stage("exit")
        if tr["landed"] is not None:
            return
        on = ref.parts_touching(self.disc)
        if tr["released"] is None:
            if on - {"right_hand"}:
                return ref.fail("the discus was touched by something other than the throwing hand",
                                parts=sorted(on - {"right_hand"}))
            if w.held["right"] == "discus":                    # both jaws on it: in the hand
                tr["last"], tr["clear"] = self._state(w, ref.time), None
                return
            if on:                                             # on the hand, but not between both jaws
                tr["clear"] = None
                if ref.time - tr["last"][0] > p["carry_s"] + 1e-9:
                    return ref.fail("the discus stayed on the hand without the gripper's hold",
                                    unheld_s=round(ref.time - tr["last"][0], 3))
                return
            if tr["clear"] is None:
                tr["clear"] = round(ref.time, 4)
            if ref.time - tr["clear"] < p["release_gap_s"] - 1e-9:
                return
            tr["released"] = tr["last"][0]                     # the release: the gripper's last hold
            now = self._state(w, ref.time)                     # (the flight's start: measured now, free of the hand)
            v, ax = np.array(now[4:7]), np.array(now[7:10])
            ref.metrics["release_time_s"] = tr["released"]
            ref.metrics["release_speed_m_s"] = round(float(np.linalg.norm(v)), 2)
            ref.metrics["release_height_m"] = round(float(now[3]), 3)
            ref.metrics["release_tilt_deg"] = round(math.degrees(math.acos(min(1.0, abs(float(ax[2]))))), 1)
            ref.metrics["release_spin_rad_s"] = round(abs(float(now[10])), 1)
            ref.stage("release")
        elif w.held["right"] == "discus":
            return ref.fail("the discus was gripped again after the release")
        elif on - {"right_hand"} or (on and ref.time - tr["released"] > p["retouch_grace_s"]):
            return ref.fail("the discus was touched after the release", parts=sorted(on))
        pts = ref.contact_points(self.disc, ref.ground)
        if not len(pts):
            return
        x, y = float(pts[0][0]), float(pts[0][1])                # the landing: the first touch of the ground
        dist = math.hypot(x, y) - self.R
        tr["landed"] = [round(x, 4), round(y, 4)]
        ref.metrics["distance_m"] = round(dist, 3)
        if dist <= 0 or abs(math.atan2(y, x)) >= self.half_sector:
            ref.fail("the discus landed outside the sector", x=round(x, 3), y=round(y, 3))
        elif dist < p["qualifying_mark_m"]:
            ref.fail("the throw is short of the qualifying mark", distance_m=round(dist, 3))
        else:
            ref.stage("landing", distance_m=round(dist, 3))

    def step(self, w, ref):
        if ref.has("exit") and ref.hold("stand", ref.standing(), self.p["stand_s"]):
            ref.succeed()

    def privileged(self, w):
        return {"discus": w.pos("discus").tolist(), "discus_velocity": w.vel("discus").tolist(),
                "discus_axis": w.d.xmat[self.disc_id].reshape(3, 3)[:, 2].tolist(), "held": w.held["right"] == "discus",
                "circle_radius": self.R, "sector_half_angle_deg": math.degrees(self.half_sector)}
