"""Backflip: a standing back tuck on the floor: one jump from the feet in which the body turns backwards through a full
turn before the feet land, then stand."""
import math

import numpy as np

from rfo.referee import Flights
from rfo.task import TaskBase


class Task(TaskBase):
    name = "backflip"
    title = "Backflip"
    category = "parkour-apparatus-balance"
    robot = "unitree_g1"
    rulebook = ("FIG Code of Points, floor exercise: the salto backward tucked from a stand (a standing back tuck), "
                "landed on the feet; FIG Apparatus Norms, floor: a 12 m x 12 m performance area")
    deviations = [
        "FIG Apparatus Norms, floor: the floor is rigid and level, not the norm's sprung floor with its elastic "
        "surface, because the simulator's ground is rigid (a sprung floor would give energy back: this is not easier)",
        "FIG Code of Points (execution is scored): the salto is judged pass or fail on the rotation, the feet-first "
        "landing and the stand, because the task is a single action without a judging panel",
        "the Code of Points has no number for a completed salto; here the pelvis must have turned {turn_deg} degrees "
        "backwards between lift-off and the first touch (a full turn less the backward lean at lift-off and the "
        "forward lean a salto still has when its feet touch down); the feet-first landing and the stand judge the rest",
    ]
    time_limit_s = 20.0
    start = (0.0, 0.0, 0.0)
    stages = ["take-off", "full turn", "landing", "stand"]
    params = dict(turn_deg=300.0, min_air_s=0.20, stand_s=2.0, fall_pelvis_m=0.20, stand_tilt_deg=20.0,
                  still_m_s=0.35, area_m=12.0)

    sentence = "Do a standing backflip: jump, turn backwards through a full turn in the air, land on your feet and stand."
    rules = ("The flip is one flight phase (nothing of you touches the ground) of at least {min_air_s} s that starts "
             "from your feet (at lift-off the last things on the ground were your feet, nothing else); shorter hops "
             "are ignored, and your first flight of at least {min_air_s} s is your attempt. The turn is measured on "
             "your pelvis: the angle it rotates backwards (head going back, feet coming forward) about the "
             "horizontal axis that was its left-right axis at lift-off, added up from lift-off while you are in the "
             "air; a rotation on the ground and a twist about the vertical do not count. It must reach {turn_deg} "
             "degrees before anything touches the ground (a full turn less the backward lean a standing take-off "
             "already has when the feet leave the ground and the lean a salto still has when its feet touch down: "
             "the landing and the stand have to finish the turn). The first touch after the flight must be with the "
             "feet only. You then stand for {stand_s} s without a break: only your feet "
             "on the ground, your torso within {stand_tilt_deg} degrees of vertical, your pelvis slower than "
             "{still_m_s} m/s. You fail if the attempt did not start from the feet alone, if it lands with less than "
             "{turn_deg} degrees turned, if it lands on anything but the feet, if you fall at any time (a fall is: a "
             "part of you other than a foot touches the ground, or your pelvis is lower than {fall_pelvis_m} m; a "
             "crouch above that is not a fall), or after {time_limit_s} s.")
    venue = ("You stand in the middle of a floor-exercise area, {area_m} m by {area_m} m, flat, level and rigid, "
             "with nothing on it.")
    difficulty = ("A full backward turn needs about 0.6 s of flight with a fast rotation, from legs whose motors give "
                  "88 to 139 N m, and a landing on the feet that stops the rotation. No built-in action jumps at all.")

    @property
    def fall_z(self):                 # a deep crouch before the jump is not a fall; a part on the ground is
        return self.p["fall_pelvis_m"]

    def build(self, sc):
        h = self.p["area_m"] / 2
        sc.box("mat", (0.0, 0, 0.0003), (h, h, 0.0003), rgba=(0.25, 0.35, 0.65, 1))
        for i, (a, b) in enumerate((((-h, -h), (h, -h)), ((h, -h), (h, h)), ((h, h), (-h, h)), ((-h, h), (-h, -h)))):
            sc.line(f"area_line{i}", a, b)
        sc.camera("venue", (0.3, -3.4, 1.3), (0.0, 0.0, 0.8), fovy=50)

    def referee_reset(self, w, ref):
        self.min_upright = math.cos(math.radians(self.p["stand_tilt_deg"]))
        self.trackers = {"flights": Flights(ref, min_air=self.p["min_air_s"]), "turn_rad": 0.0, "axis": [0.0, 1.0, 0.0],
                         "landed": False}

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        if tr["landed"]:
            return
        fl = tr["flights"]
        was_air = fl.air
        done = fl.update()
        if fl.air:
            if not was_air:
                tr["turn_rad"] = 0.0                                          # a new flight: the count starts again
                left = w.d.xmat[w.robot.pelvis].reshape(3, 3)[:, 1] * (1.0, 1.0, 0.0)
                n = float(np.linalg.norm(left))                               # the pelvis' left-right axis, levelled
                tr["axis"] = (left / n).tolist() if n > 1e-6 else [0.0, 1.0, 0.0]
            R = w.d.xmat[w.robot.pelvis].reshape(3, 3)                        # the free joint's angular velocity is in
            omega = R @ w.d.qvel[w.robot.fv + 3:w.robot.fv + 6]               # the pelvis' frame; backwards is -left
            tr["turn_rad"] -= float(omega @ np.asarray(tr["axis"])) * w.PHYS_DT
            if ref.time - fl.cur["t0"] >= p["min_air_s"] and not ref.has("take-off"):
                parts = set(fl.cur["takeoff"].get("parts", []))
                if not parts or not parts <= {"left_foot", "right_foot"}:
                    return ref.fail("did not take off from the feet", parts=sorted(parts))
                ref.stage("take-off")
            if ref.has("take-off") and math.degrees(tr["turn_rad"]) >= p["turn_deg"]:
                ref.stage("full turn")
        elif done is not None:                                                # the attempt has landed
            tr["landed"] = True
            deg = round(math.degrees(tr["turn_rad"]), 1)
            ref.metrics["turn_deg"] = deg
            ref.metrics["air_s"] = done["air_s"]
            if not ref.has("full turn"):
                return ref.fail("not a full backward turn", turn_deg=deg)
            parts = set(done["landing_parts"])
            if not parts <= {"left_foot", "right_foot"}:
                return ref.fail("did not land on the feet", parts=sorted(parts))
            ref.stage("landing", turn_deg=deg)

    def step(self, w, ref):
        p = self.p
        still = ref.standing(max_speed=p["still_m_s"], min_upright=self.min_upright)
        if ref.has("landing") and ref.hold("stand", still, p["stand_s"]):
            if ref.stage("stand"):
                ref.succeed()

    def privileged(self, w):
        return {"pelvis": w.pelvis().tolist(), "turn_deg": math.degrees(self.trackers.get("turn_rad", 0.0))}
