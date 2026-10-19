"""Discus throw (World Athletics TR 32 and 34): from the circle, throw the men's discus so that it lands inside the
sector at least the qualifying mark away; then leave the circle from its rear half. Official circle, sector and discus;
the Unitree H1-2."""
import math

import mujoco
import numpy as np

from rfo.scene import HITTABLE, STANDABLE
from rfo.task import TaskBase

APRON, RAMP = 1.0, 1.0                        # the ground outside the circle: level for APRON m, then down to the field
N_WEDGE = 48
PALM_OFFSET = 0.022 + 0.003                   # the palm face of the hand's pad, and a gap, from the wrist mount's axis
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
    name = "discus"
    title = "Athletics: discus throw"
    category = "throwing-catching-striking"
    robot = "unitree_h1"
    rulebook = ("World Athletics Competition and Technical Rules 2024: TR 32.5-32.8 (the circle, 2.50 m for the "
                "discus), TR 32.12 (the 34.92 degree sector), TR 32.13, 32.14, 32.16, 32.17 and 32.20 (throwing "
                "events: the start, failures, the landing, leaving the circle, the measurement), TR 34 (the men's "
                "discus), TR 35 (the discus cage)")
    deviations = [
        "TR 34 (the discus): the hand holds the discus flat against its palm by a grip switched on and off, not by fingertips "
        "over the rim; it is released when the grip is switched off. The discus is an ellipsoid of the official "
        "diameter, thickness and mass (no separate metal rim: its moment of inertia is that of a uniform body).",
        "TR 35 (the cage): there is no cage.",
        "TR 32.5-32.6: the ground outside the circle is level with the rim's top for " + f"{APRON:g} m and then falls to "
        f"the field's level over {RAMP:g} m" + " (the circle's inside is the field's level, {rim_height_m} m below the "
        "rim, instead of the field being level with the rim).",
        "TR 32.20: the mark is the point where the discus first touches the ground.",
        "TR 32.15 (interrupting a trial, laying the implement down): not modelled; the first release is the throw, "
        "and the discus cannot be gripped again.",
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
                  rim_height_m=0.02, rim_edge_m=0.003, sector_deg=34.92, qualifying_mark_m=15.0, retouch_grace_s=0.20, stand_s=1.0,
                  fall_pelvis_m=0.50)

    sentence = ("Throw the discus in your right hand from inside the circle so that it lands inside the sector at "
                "least {qualifying_mark_m} m from the circle, then leave the circle from its rear half and stand.")
    rules = ("The men's discus ({discus_mass_kg} kg, {discus_diameter_m} m across, {discus_thickness_m} m thick at "
             "its centre) starts gripped flat against your right palm. The circle is {circle_diameter_m} m across "
             "inside its rim; the ground outside is {rim_height_m} m higher than its inside. The sector opens from "
             "the circle's centre, {sector_deg} degrees wide, symmetric about the direction you face at the start. "
             "The throw: you let go of the discus (once: it cannot be gripped again). Its first touch of the ground "
             "must be inside the sector lines (on a line is out); the throw is measured from that point to the inside "
             "of the rim along the line through the circle's centre. You succeed when a valid throw measures at "
             "least {qualifying_mark_m} m and you have then left the circle correctly and stood for {stand_s} s. "
             "Leaving correctly: after the discus has landed, your first touch of the rim's top or of the ground "
             "outside the circle is behind the line through the circle's centre across the throwing direction (the "
             "rear half). Standing: only your feet on the ground, the torso within about 20 degrees of upright, the "
             "pelvis slower than 0.35 m/s. You fail if any part of you touches the rim's top (its top inside edge "
             "included) or the ground outside the circle before the discus has landed, or in the front half before "
             "you have left correctly; if the discus lands outside the sector or short of {qualifying_mark_m} m; if "
             "any part of you touches it after the release (your right arm may still brush it during the first "
             "{retouch_grace_s} s); if you fall (your pelvis lower than {fall_pelvis_m} m above the circle's floor, "
             "or any part of you other than your feet on the ground); or after {time_limit_s} s. Where you touch the "
             "ground is judged on the points of contact; a contact within {rim_edge_m} m of the rim's top counts as on "
             "it.")
    venue = ("You stand in the rear half of the circle facing the sector (+x), your pelvis 0.55 m behind the circle's "
             "centre. Your right arm hangs straight down, a little away from the leg, the discus flat against its "
             "palm (the palm faces your leg). There is no cage. Still air. The discus is released when the hand's "
             "grip is switched off.")
    difficulty = ("{qualifying_mark_m} m needs a release at about 12 m/s near 35 to 40 degrees with the discus flat "
                  "to its flight and spinning, or the air turns it over. The H1-2's arm motors give 40 N m at the "
                  "shoulder, so the speed has to come from the trunk's turn, inside a circle of 2.5 m that the "
                  "robot may not leave until the discus is down.")

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
        sc.grippables["discus"] = {"radius": p["discus_thickness_m"] / 2}
        sc.camera("venue", (-3.0, -3.8, 2.6), (1.5, 0.0, 0.8), fovy=55)
        sc.camera("sector", (-3.0, 0.0, 14.0), (9.0, 0.0, 0.0), fovy=70)

    def reset(self, w):
        set_arm(w, right_elbow_pitch=1.57, right_shoulder_roll=-0.20)
        d = w.d
        b = w.robot.mount["right"]
        R = d.xmat[b].reshape(3, 3)
        Rb = np.column_stack([R[:, 1], R[:, 2], R[:, 0]])     # the discus' axis: the palm's normal (the mount's x)
        q = np.zeros(4)
        mujoco.mju_mat2Quat(q, Rb.reshape(-1))
        w.put("discus", d.xpos[b] + R @ np.array([PALM_OFFSET + self.p["discus_thickness_m"] / 2, 0.0, 0.05]), quat=q)
        w.grab("right", "discus", event=False)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        self.disc = ref.geoms(body="discus")
        self.robot = ref.part("robot")
        self.arm = ref.part("right_arm")
        self.not_arm = self.robot & ~self.arm
        self.apron = ref.geoms(prefix="apron")
        self.floor = ref.geoms(names=["floor"])
        self.disc_id = w.m.body("discus").id
        self.trackers = {"released": None, "landed": None, "exit": False}

    def may_grip(self, w, side, name):
        return False                                          # held from t = 0; once let go it cannot be gripped again

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
        held = bool(w.holder("discus"))
        if tr["released"] is None:
            if held:
                return
            tr["released"] = ref.time
            c, v = w.pos("discus"), w.vel("discus")
            ax = w.d.xmat[self.disc_id].reshape(3, 3)[:, 2]
            _, va = w.free["discus"]
            ref.metrics["release_speed_m_s"] = round(float(np.linalg.norm(v)), 2)
            ref.metrics["release_height_m"] = round(float(c[2]), 3)
            ref.metrics["release_tilt_deg"] = round(math.degrees(math.acos(min(1.0, abs(float(ax[2]))))), 1)
            ref.metrics["release_spin_rad_s"] = round(abs(float(w.d.qvel[va + 5])), 1)
            ref.stage("release")
        elif (ref.touching(self.disc, self.not_arm)
              or (ref.time - tr["released"] > p["retouch_grace_s"] and ref.touching(self.disc, self.arm))):
            return ref.fail("the discus was touched after the release", parts=sorted(ref.parts_touching(self.disc)))
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
                "discus_axis": w.d.xmat[self.disc_id].reshape(3, 3)[:, 2].tolist(), "held": bool(w.holder("discus")),
                "circle_radius": self.R, "sector_half_angle_deg": math.degrees(self.half_sector)}
