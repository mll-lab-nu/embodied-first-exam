"""Box jump (CrossFit's movement standard): from the floor, one two-foot jump onto the 24 in side of a 20 x 24 x 30 in
plyometric box, landing with both feet on its top face, then standing up straight on it."""
import math
import xml.etree.ElementTree as ET

import numpy as np

from rfo.referee import Flights
from rfo.scene import STANDABLE
from rfo.task import TaskBase

FEET = {"left_foot", "right_foot"}


class Task(TaskBase):
    name = "box-jump"
    title = "Box jump"
    category = "parkour-apparatus-balance"
    robot = "unitree_h1"
    rulebook = ("CrossFit's box jump movement standard (the CrossFit Games Open workout descriptions: both feet start "
                "on the floor, both feet end on the box, hips and knees fully extended on top) on the men's "
                "prescribed box: 24 in (0.61 m) high, the 20 x 24 x 30 in plyometric box standing on its 20 x 30 in "
                "face")
    deviations = [
        "the step-up that some Open workouts permit is not a box jump here: the take-off is from both feet and there "
        "is a flight (the family is the jump, not the step-up)",
        "full extension on top is judged by the pelvis' height above the box's top ({upright_pelvis_m} m; this "
        "robot's pelvis is 1.04 m above its soles with straight legs, 1.02 to 1.03 m in its own standing posture, "
        "whose knees stay bent 0.36 rad, and below {upright_pelvis_m} m once the knees bend more than about 0.65 "
        "rad) and by the torso's tilt: a referee cannot see \"open hips\" on a robot otherwise",
        "one repetition, judged to a held stand of {stand_s} s on the box (a workout counts repetitions; here the "
        "repetition is one attempt and the stand shows control)",
    ]
    time_limit_s = 20.0
    start = (0.0, 0.0, 0.0)
    stages = ["take-off", "landing", "stand"]
    fall_rule = False                # the family's own ground rule: see "a fall" in the rules
    params = dict(box_height_m=0.61, box_length_m=0.51, box_width_m=0.76, box_mass_kg=25.0, box_friction=1.0,
                  box_contact_s=0.005,
                  box_distance_m=0.60, min_air_s=0.10, two_foot_s=0.10, min_rise_m=0.10, landing_window_s=0.50,
                  top_tol_m=0.02, top_normal_deg=20.0, upright_pelvis_m=1.00, stand_tilt_deg=20.0, still_m_s=0.35,
                  stand_s=2.0)

    sentence = ("Jump from the floor onto the 0.61 m box in front of you with a two-foot take-off, land on its top with "
                "both feet, and stand up straight on it.")
    rules = ("The box is a free rigid body of {box_mass_kg} kg (not fixed to the floor; friction coefficient "
             "{box_friction}, a stiff wooden surface: contact time constant {box_contact_s} s): {box_height_m} m high, its top {box_length_m} m long (along +x, the way you face) and "
             "{box_width_m} m wide. You must get onto it with one jump. Your jump is your first flight phase of at "
             "least {min_air_s} s (nothing of you touches anything). It counts only if: nothing of you touched the "
             "box before it (no stepping or climbing up); it left the floor from both feet (each foot was on the "
             "floor within the last {two_foot_s} s before lift-off); it was a real take-off (your pelvis rose at "
             "least {min_rise_m} m above its height at lift-off: tucking the legs while falling is not a jump). The "
             "landing is judged over the {landing_window_s} s that follow the first contact: in that time only your "
             "feet may touch anything, and only the box's top face (each contact within {top_tol_m} m of the top "
             "plane and pushing within {top_normal_deg} degrees of straight out of it: a foot against a side face "
             "or jammed on an edge is not on the top), and at its end both feet are on the top. Then you stand up "
             "straight on the box for {stand_s} s without a break: both feet on the top face and nothing else "
             "touching anything, your torso within {stand_tilt_deg} degrees of vertical, your pelvis moving no "
             "faster than {still_m_s} m/s and at least {upright_pelvis_m} m above the box's top (hips and knees "
             "extended). You fail if the jump breaks one of these rules, if any part of you touches the floor "
             "after the landing, if a part other than a foot touches the box, if you fall before the jump (a fall is any part "
             "of you other than your feet touching the floor; there is no pelvis-height limit, a deep squat is not "
             "a fall), or after {time_limit_s} s. You may walk on the floor before the jump.")
    venue = ("You stand on the floor facing the box (+x); its near face is {box_distance_m} m ahead of your pelvis "
             "(your toes reach about 0.16 m ahead of your pelvis) and it is centred on your line. The box rests on "
             "the floor on its 0.51 m by 0.76 m face and can slide or tip if it is pushed.")
    difficulty = ("No built-in action of this robot leaves the ground: the jump is whole-body joint control, and it "
                  "must lift 67 kg far enough for the soles to clear {box_height_m} m, more than half the length of "
                  "the legs. The landing has to be absorbed on a box only {box_length_m} m deep that is free to "
                  "slide, and the robot must then straighten up on it.")

    def build(self, sc):
        p = self.p
        H, Lx, Wy, D = p["box_height_m"], p["box_length_m"], p["box_width_m"], p["box_distance_m"]
        self.half = np.array([Lx / 2, Wy / 2, H / 2])
        # The H1-2's sole is one convex hull: on a box (unlike the floor plane) MuJoCo gives a convex pair a single
        # contact point unless multiccd is on, and a foot on one point does not stand.
        ET.SubElement(sc.root.find("option"), "flag", multiccd="enable")
        self.box0 = (D + Lx / 2, 0.0, H / 2)
        b = sc.body("box", self.box0, free=True)
        sc.geom(b, "box", type="box", size=tuple(self.half), mass=p["box_mass_kg"], rgba=(0.72, 0.56, 0.36, 1),
                friction=(p["box_friction"], 0.005, 0.0001), priority=1, solref=(p["box_contact_s"], 1.0), **STANDABLE)
        sc.box("mat", (0.5, 0, 0.0003), (1.8, 1.2, 0.0003), rgba=(0.20, 0.22, 0.26, 1))
        sc.camera("venue", (0.0, -3.9, 1.5), (0.55, 0.0, 0.85), fovy=50)

    def referee_reset(self, w, ref):
        self.floor = ref.geoms(names=["floor"])
        self.box_g = ref.geoms(names=["box"])
        self.box_id = int(w.m.geom("box").id)
        self.box_body = int(w.m.body("box").id)
        self.robot = ref.part("robot")
        self.not_feet = ref.part("robot") & ~ref.part("feet")
        self.foot = {s: ref.part(f"{s}_foot") for s in ("left", "right")}
        self.trackers = {"flights": Flights(ref, min_air=self.p["min_air_s"]), "feet_down": {"left": -9.0, "right": -9.0},
                         "landed_at": None}

    # ------------------------------------------------------------------ the box's top face
    def top_z(self, w) -> float:
        """The height of the centre of the box's top face."""
        R = w.d.xmat[self.box_body].reshape(3, 3)
        return float(w.d.xpos[self.box_body][2] + R[2, 2] * self.half[2])

    def feet_on_box(self, w) -> dict:
        """For each foot that touches the box: True if every contact is on the top face, else False."""
        p, d, m = self.p, w.d, w.m
        R = d.xmat[self.box_body].reshape(3, 3)
        c0 = d.xpos[self.box_body]
        cos_min = math.cos(math.radians(p["top_normal_deg"]))
        out = {}
        for i in range(d.ncon):
            c = d.contact[i]
            if c.dist > 0.0 or self.box_id not in (c.geom1, c.geom2):
                continue
            other = int(c.geom2 if c.geom1 == self.box_id else c.geom1)
            for s in ("left", "right"):
                if self.foot[s][other]:
                    local = R.T @ (np.asarray(c.pos) - c0)
                    n = (R.T @ np.asarray(c.frame[:3])) * (1.0 if c.geom1 == self.box_id else -1.0)   # out of the box
                    top = local[2] >= self.half[2] - p["top_tol_m"] and float(n[2]) >= cos_min
                    out[s] = out.get(s, True) and bool(top)
        return out

    # ------------------------------------------------------------------ the referee
    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        if not ref.has("take-off"):
            if ref.touching(self.not_feet, self.floor):
                return ref.fail("fell", on_the_floor=sorted(ref.parts_touching(self.floor) - FEET))
            for s in ("left", "right"):
                if ref.touching(self.foot[s], self.floor):
                    tr["feet_down"][s] = ref.time
            done = tr["flights"].update()
            if done is not None:                              # the first counted flight: the jump
                rise = done["apex_z"] - done["pelvis0"][2]
                ref.metrics["air_s"] = done["air_s"]
                ref.metrics["pelvis_rise_m"] = round(rise, 3)
                if min(tr["feet_down"].values()) < done["t0"] - p["two_foot_s"]:
                    return ref.fail("not a two-foot take-off")
                if rise < p["min_rise_m"]:
                    return ref.fail("not a real take-off", pelvis_rise_m=round(rise, 3))
                ref.stage("take-off", air_s=done["air_s"], pelvis_rise_m=round(rise, 3))
                tr["landed_at"] = done["t1"]
            elif ref.touching(self.robot, self.box_g):
                return ref.fail("touched the box before the jump", parts=sorted(ref.parts_touching(self.box_g)))
        if not ref.has("take-off"):
            return
        if ref.touching(self.robot, self.floor):
            return ref.fail("touched the floor after the landing" if ref.has("landing") else "the jump landed on the floor",
                            parts=sorted(ref.parts_touching(self.floor)))
        if ref.touching(self.not_feet, self.box_g):
            return ref.fail("touched the box with something other than the feet" if ref.has("landing")
                            else "did not land on the feet", parts=sorted(ref.parts_touching(self.box_g) - FEET))
        if not ref.has("landing"):
            on = self.feet_on_box(w)
            if not all(on.values()):
                return ref.fail("landed on the side of the box", feet=sorted(s for s, ok in on.items() if not ok))
            if ref.time - tr["landed_at"] >= p["landing_window_s"]:
                if len(on) == 2:
                    ref.stage("landing")
                else:
                    ref.fail("did not land with both feet on the box", feet_on_top=sorted(on))

    def step(self, w, ref):
        p = self.p
        if not ref.has("landing") or ref.failed:
            return
        on = self.feet_on_box(w)
        height = float(w.pelvis()[2]) - self.top_z(w)
        ref.metrics["pelvis_above_box_m"] = round(height, 3)
        ok = (len(on) == 2 and all(on.values()) and height >= p["upright_pelvis_m"]
              and ref.standing(max_speed=p["still_m_s"], min_upright=math.cos(math.radians(p["stand_tilt_deg"])),
                               on=self.box_g))
        if ref.hold("stand", ok, p["stand_s"]):
            if ref.stage("stand"):
                ref.succeed()

    def privileged(self, w):
        return {"pelvis": w.pelvis().tolist(), "box_centre": w.pos("box").tolist(), "box_half_m": self.half.tolist(),
                "box_top_z": self.top_z(w)}
