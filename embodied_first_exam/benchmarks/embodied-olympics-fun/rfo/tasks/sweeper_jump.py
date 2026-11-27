"""Sweeper jump (the "Meltdown" party game): a padded boom on a motor-driven central pivot sweeps round at shin
height; standing on its podium, the robot jumps over it each time it comes round, a number of times in a row,
without being hit, and ends standing.

The machine is physical: the boom is a body on a vertical hinge at the motion base, driven by a speed-controlled,
torque-limited motor (MuJoCo `velocity` actuator with a force range: the variable-frequency drive's speed loop and
its rated torque). Nothing writes its pose or velocity after t = 0; at t = 0 it is already turning at the set speed
(the start state). A hit really pushes the robot (up to the motor's torque) and the boom really slows under the load.
"""
import math
import xml.etree.ElementTree as ET

import numpy as np

from rfo.referee import Flights
from rfo.task import TaskBase

SIDES = ("left", "right")
FOAM_RGBA = (0.95, 0.35, 0.10, 1)


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def zspan(w, ids):
    """The lowest and highest points of the geoms `ids` (their oriented bounding boxes)."""
    m, d = w.m, w.d
    R = d.geom_xmat[ids].reshape(-1, 3, 3)
    c = d.geom_xpos[ids] + np.einsum("gij,gj->gi", R, m.geom_aabb[ids, :3])
    half = np.sum(np.abs(R[:, 2, :]) * m.geom_aabb[ids, 3:], axis=1)
    return float(np.min(c[:, 2] - half)), float(np.max(c[:, 2] + half))


class Task(TaskBase):
    name = "sweeper-jump"
    title = "Sweeper jump (jumping the boom of a Meltdown sweeper)"
    category = "parkour-apparatus-balance"
    robot = "unitree_g1"
    rulebook = ("No official rule book exists: the sweeper is a party and amusement game, not a sport. The closest "
                "real device is Galaxy Multi Rides' 'Meltdown' (US Meltdown operator manual: an eight-player game, "
                "each player standing on a podium round a motion base whose foam booms spin round, 'the aim of the "
                "game is to either duck under, or jump over the boom as it spins around'; players must not grab, "
                "hold or ride the booms; a player who is hit is out; one 1 hp spin motor on a speed dial, at most "
                "{max_rpm} rpm; foam boom attachments 220 lb for the two booms; riders at least 48 in (1.22 m) tall "
                "and at most 200 lb), the same game as the 'Sweeper' of the TV show Wipeout. Its rules as played: "
                "stay on your podium, jump the low boom each time it comes round, the last player not hit wins")
    deviations = [
        "the booms: Meltdown's dual attachment has two foam booms; here there is only the low boom you jump (the "
        "duck boom is left off: this family tests the jump), so the rotor is that one boom, {boom_mass_kg} kg, "
        "half of the attachment's 220 lb",
        "the dimensions: the manual gives none of the boom's height, length or thickness, nor of the podiums. The "
        "boom's axis is {boom_axis_above_podium_m} m above the podium's top, the mid-shin of a rider of the "
        "minimum height (1.22 m), its foam {boom_diameter_m} m thick, reaching {boom_length_m} m from the axis "
        "over the podiums of a 30 ft bed, whose centres are {podium_radius_m} m from the axis; each podium a "
        "{podium_diameter_m} m disc {podium_height_m} m high (reasonable sizes, not published ones)",
        "the podium and the bed: the inflatable podium is a rigid platform and the inflatable bed a firm floor "
        "(neither's give is modelled; touching the bed is out anyway)",
        "the speed: the operator's dial is set to a steady {rpm} rpm (about half the machine's top speed), "
        "already turning at the start; the machine's program, which changes speed, is not used",
        "the count: one player, and a run of {jumps_required} jumps in a row with no hit is the success (a "
        "round number: the game has no count, its last player standing wins); after the last jump the robot "
        "must stand still for {stand_s} s on its podium before the boom comes round again",
        "a hit is any touch of the boom on the robot (in the game a light touch may leave a player standing); "
        "a jump is a pass of the boom under both feet while nothing of the robot touches anything",
        "the motor: the 1 hp drive is a speed loop with a torque limit of {motor_torque_nm} N m at the boom "
        "(1 hp at the top speed of {max_rpm} rpm, through the gearbox), no gearbox backlash or compliance; the "
        "foam's contact is a critically damped spring of {foam_timeconst_s} s time constant (an estimate for a "
        "soft polyurethane pad)",
    ]
    time_limit_s = 30.0
    start = (3.2, 0.0, math.pi)
    params = dict(rpm=8.0, max_rpm=15.82, motor_torque_nm=450.0, motor_kv=4000.0, bearing_friction_nm=5.0,
                  boom_mass_kg=50.0, boom_length_m=4.0, boom_inner_m=0.62, boom_diameter_m=0.20,
                  boom_axis_above_podium_m=0.20, boom_angle0_deg=-200.0, foam_timeconst_s=0.02, foam_friction=0.5,
                  podium_radius_m=3.2, podium_diameter_m=0.90, podium_height_m=0.40, base_radius_m=0.40,
                  base_height_m=0.75, jumps_required=3, stand_s=1.0, fall_z_above_podium_m=0.35,
                  period_s=7.5, angle0_abs_deg=200.0, first_pass_s=4.17)       # (the last three: derived, for the texts)

    def __init__(self):
        super().__init__()
        self._sync()

    def configure(self, params):
        super().configure(params)
        self._sync()

    def _sync(self):
        p = self.p
        self.start = (p["podium_radius_m"], 0.0, math.pi)
        self.stages = [f"jump {i}" for i in range(1, int(p["jumps_required"]) + 1)] + ["landing", "stand"]
        self._derived()

    sentence = (("Jump the sweeping boom 3 times in a row without being hit, then land on your podium and stand "
                 "still before it comes round again."))
    rules = ("You stand on a round podium, {podium_diameter_m} m across and {podium_height_m} m high, whose centre "
             "is {podium_radius_m} m from the axis of the motion base, facing the base. A foam boom "
             "{boom_diameter_m} m thick, its axis {boom_axis_above_podium_m} m above the podium's top, turns round "
             "the base counter-clockwise (seen from above) at {rpm} revolutions per minute, driven by a motor of "
             "at most {motor_torque_nm} N m; it reaches {boom_length_m} m from the axis, over the whole podium, and "
             "comes round once every {period_s} s. It is already turning at the start. A jump counts when the boom "
             "passes under both your feet while nothing of you touches anything (at the moment it passes each foot). "
             "You succeed when, after {jumps_required} counted jumps, your first contact is your feet on the podium "
             "and you then stand still for {stand_s} s (only your feet on the podium, your torso within about 20 "
             "degrees of vertical, your pelvis slower than 0.35 m/s), before the boom comes round again. You fail "
             "at once if the boom touches any part of you (a hit; grabbing or holding it is a hit too), if any part "
             "of you touches the bed (the floor round the podium) or the motion base, if the boom passes through a "
             "foot that is not above it, on a fall (your pelvis less than {fall_z_above_podium_m} m above the "
             "podium's top, or any part of you other than your feet on the podium), on a landing after the last "
             "jump that is not on the feet, or after {time_limit_s} s.")
    venue = ("A Meltdown sweeper on a level bed: the motion base, a column {base_radius_m} m in radius, stands "
             "{podium_radius_m} m in front of you (you face it); you stand in the middle of your podium, its top "
             "{podium_height_m} m above the bed. The boom sticks out from the base at shin height and turns "
             "counter-clockwise seen from above: it comes at you from your left. At the start it points "
             "{angle0_abs_deg} degrees of its turn before your podium (on the far side of the base), turning; it "
             "will be over your podium in about {first_pass_s} s.")
    difficulty = ("Neither built-in gait can jump: the robot must jump with its feet above a boom almost as high as "
                  "its knees, at the moment a fast boom arrives, and land on a small podium in balance, three times. "
                  "Each landing has to be absorbed and the robot re-centred on the podium before the boom comes "
                  "round again.")

    # ------------------------------------------------------------------ the venue
    def _derived(self):
        p = self.p
        om = 2 * math.pi * p["rpm"] / 60.0
        a0 = math.radians(p["boom_angle0_deg"])
        p["period_s"] = round(60.0 / p["rpm"], 3)
        p["angle0_abs_deg"] = round(abs(p["boom_angle0_deg"]), 3)
        p["first_pass_s"] = round(-a0 / om, 2) if a0 < 0 else round((2 * math.pi - a0) / om, 2)
        return om, a0

    def build(self, sc):
        p = self.p
        self._derived()
        top = p["podium_height_m"]
        zb = top + p["boom_axis_above_podium_m"]
        rb = p["boom_diameter_m"] / 2
        sc.box("bed", (0, 0, 0.0003), (5.0, 5.0, 0.0003), rgba=(0.15, 0.35, 0.80, 1))
        # the podium: a fixed platform (it is the ground the feet stand on)
        sc.geom(sc.wb, "podium", type="cylinder", pos=(p["podium_radius_m"], 0, top / 2),
                size=(p["podium_diameter_m"] / 2, top / 2), rgba=(0.95, 0.80, 0.15, 1), contype="1", conaffinity="5",
                friction=(0.9, 0.005, 0.0001))
        sc.ground.append("podium")
        for k in range(1, 8):                             # the other seven podiums of the eight-player machine
            a = 2 * math.pi * k / 8
            sc.geom(sc.wb, f"podium{k}", type="cylinder",
                    pos=(p["podium_radius_m"] * math.cos(a), p["podium_radius_m"] * math.sin(a), top / 2),
                    size=(p["podium_diameter_m"] / 2, top / 2), rgba=(0.95, 0.80, 0.15, 1), contype="1",
                    conaffinity="5")
        sc.geom(sc.wb, "motion_base", type="cylinder", pos=(0, 0, p["base_height_m"] / 2),
                size=(p["base_radius_m"], p["base_height_m"] / 2), rgba=(0.30, 0.30, 0.34, 1), contype="1",
                conaffinity="13")
        # the rotor: the boom on a vertical hinge at the base's axis, its motor a speed loop with a torque limit
        b = sc.body("boom", (0, 0, zb))
        ET.SubElement(b, "joint", name="boom", type="hinge", axis="0 0 1", damping="0",
                      frictionloss=f"{p['bearing_friction_nm']:g}", armature="0.5")
        r0, r1 = p["boom_inner_m"], p["boom_length_m"]
        sc.geom(b, "boom_foam", type="capsule", fromto=(r0, 0, 0, r1 - rb, 0, 0), size=(rb,), mass=p["boom_mass_kg"],
                rgba=FOAM_RGBA, contype="1", conaffinity="13", condim="3", priority="1",
                friction=(p["foam_friction"], 0.005, 0.0001), solref=f"{p['foam_timeconst_s']:g} 1",
                solimp="0.9 0.95 0.001")
        sc.geom(b, "boom_hub", type="cylinder", pos=(0, 0, 0), size=(p["boom_inner_m"] + 0.02, 0.07), mass=5.0,
                rgba=(0.55, 0.55, 0.6, 1), contype="0", conaffinity="0")
        ET.SubElement(sc.root.find("actuator"), "velocity", name="boom_motor", joint="boom", kv=f"{p['motor_kv']:g}",
                      forcelimited="true", forcerange=f"{-p['motor_torque_nm']:g} {p['motor_torque_nm']:g}",
                      ctrllimited="true", ctrlrange="-2 2")
        R = p["podium_radius_m"]
        sc.camera("venue", (R + 3.2, -2.6, 1.9), (R - 0.6, 0.0, 0.7), fovy=55)
        sc.camera("overview", (R + 4.5, 0.0, 4.5), (0.0, 0.0, 0.5), fovy=60)

    def reset(self, w):
        m, d, r = w.m, w.d, w.robot
        om, a0 = self._derived()
        d.qpos[r.fq + 2] += self.p["podium_height_m"]        # the robot stands on its podium
        j = m.joint("boom")
        d.qpos[int(j.qposadr[0])] = a0
        d.qvel[int(j.dofadr[0])] = om                       # already turning at the set speed

    def before_step(self, w):
        # the drive's speed setting (the world clears the controls after reset; the operator's dial stays put)
        w.d.ctrl[self._motor] = self.om

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        m, p = w.m, self.p
        self.fall_z = p["podium_height_m"] + p["fall_z_above_podium_m"]
        self.om, _ = self._derived()
        self.boom = ref.geoms(names=["boom_foam"])
        self.robot_sel = ref.part("robot")
        self.bed = ref.geoms(names=["floor", "bed", "motion_base"] + [f"podium{k}" for k in range(1, 8)])
        self.podium = ref.geoms(names=["podium"])
        self.foot_ids = {s: np.flatnonzero(ref.part(f"{s}_foot")) for s in SIDES}
        j = m.joint("boom")
        self._qa, self._va = int(j.qposadr[0]), int(j.dofadr[0])
        self._motor = m.actuator("boom_motor").id
        self.boom_top = p["podium_height_m"] + p["boom_axis_above_podium_m"] + p["boom_diameter_m"] / 2
        self.trackers = {"flights": Flights(ref, min_air=0.0), "jumps": 0, "prev": {"left": None, "right": None},
                         "under": {"left": None, "right": None}, "last_jump_t": None}

    def boom_angle(self, w) -> float:
        return float(w.d.qpos[self._qa])

    def substep(self, w, ref):
        tr, d, r = self.trackers, w.d, w.robot
        landed = tr["flights"].update()
        if ref.touching(self.boom, self.robot_sel):
            return ref.fail("hit by the boom", parts=sorted(ref.parts_touching(self.boom)))
        if ref.touching(self.bed, self.robot_sel):
            return ref.fail("left the podium", parts=sorted(ref.parts_touching(self.bed)))
        if ref.has(self.stages[-3]):                     # the last jump is in: the landing, then the stand
            if landed is not None and not ref.has("landing"):
                if set(landed["landing_parts"]) <= {"left_foot", "right_foot"}:
                    ref.stage("landing")
                else:
                    ref.fail("the landing was not on the feet", parts=landed["landing_parts"])
            return
        th = self.boom_angle(w)
        for s in SIDES:
            q = d.site_xpos[r.foot_site[s]]
            rel = _wrap(th - math.atan2(float(q[1]), float(q[0])))
            prev, tr["prev"][s] = tr["prev"][s], rel
            if prev is None or not (prev < 0.0 <= rel and rel - prev < 1.0):
                continue                                 # the boom passes this foot now (counter-clockwise)
            sole = zspan(w, self.foot_ids[s])[0]
            if sole <= self.boom_top:
                return ref.fail("the boom passed through a foot", foot=s, sole_z=round(sole, 3),
                                boom_top_z=round(self.boom_top, 3))
            if not ref.airborne():
                return ref.fail("the boom passed under a foot while the robot was touching something", foot=s)
            tr["under"][s] = round(ref.time, 4)
            ref.event("under", foot=s, clearance_m=round(sole - self.boom_top, 4))
            if tr["under"]["left"] is not None and tr["under"]["right"] is not None:
                tr["jumps"] += 1
                tr["under"] = {"left": None, "right": None}
                tr["last_jump_t"] = round(ref.time, 4)
                ref.metrics["jumps"] = tr["jumps"]
                ref.stage(f"jump {tr['jumps']}")

    def step(self, w, ref):
        tr = self.trackers
        # half a turn after a foot was passed, the other one must have been passed too (a jump is both feet)
        for s in SIDES:
            t0 = tr["under"][s]
            if t0 is not None and ref.time - t0 > math.pi / self.om:
                return ref.fail("the boom passed under only one foot", foot=s)
        if ref.has("landing") and ref.hold("stand", ref.standing(on=self.podium), self.p["stand_s"]):
            if ref.stage("stand"):
                ref.succeed()

    def privileged(self, w):
        th = self.boom_angle(w)
        px, py = w.pelvis()[:2]
        rel = _wrap(th - math.atan2(py, px))
        om = float(w.d.qvel[self._va])
        return {"pelvis": w.pelvis().tolist(), "boom_angle_rad": th, "boom_speed_rad_s": om,
                "boom_angle_to_robot_rad": rel, "time_to_pass_s": (-rel / om) if om > 0.05 and rel < 0 else None,
                "boom_top_z": self.boom_top, "podium_top_z": self.p["podium_height_m"],
                "podium_centre_xy": [self.p["podium_radius_m"], 0.0], "jumps": self.trackers["jumps"]}
