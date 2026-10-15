"""Vertical jump (the Sargent jump-and-reach test): from a standstill, a two-foot jump whose hand touches a vane set
0.30 m above the robot's standing reach; land and stand."""
import xml.etree.ElementTree as ET

import numpy as np

from rfo.referee import Flights
from rfo.task import TaskBase

SIDES = ("left", "right")


class Task(TaskBase):
    name = "vertical-jump"
    title = "Vertical jump (jump and reach)"
    category = "track-and-jumps"
    robot = "unitree_g1"
    rulebook = ("The Sargent jump (the jump-and-reach vertical jump test of school and club fitness batteries; "
                "Sargent 1921): the standing reach is measured flat-footed with one arm stretched overhead; from a "
                "standstill, with no step or preliminary hop, the athlete jumps off both feet and touches a vane of "
                "the measuring stand (Vertec) at the top of the jump; the result is the height touched above the "
                "standing reach")
    deviations = [
        "the standing reach is not measured in the attempt: it is this robot's, {standing_reach_m} m (the top of a "
        "hand above the soles with the legs straight and the arm in its highest pose, from the robot's kinematics), "
        "and the stand has one vane, set {vane_above_reach_m} m above it",
        "the athlete cannot walk up to the stand: any step before the take-off is a foul, so the vane is placed over "
        "the place where the standing robot's raised hand is",
        "a jump is told from a loss of contact by two numbers the test does not have: a flight of at least "
        "{min_air_s} s in which the pelvis rises at least {rise_min_m} m above its height at lift-off",
        "the test ends at the touch; here the robot must also land on its feet and stand for {stand_s} s "
        "(FAMILIES.md: land and stand)",
        "the qualifying height, {vane_above_reach_m} m, is a round number below the adult average of the test (about "
        "0.4 to 0.5 m for men, 0.3 to 0.4 m for women)",
    ]
    time_limit_s = 20.0
    start = (0.0, 0.0, 0.0)
    stages = ["take-off", "touch", "landing", "stand"]
    params = dict(standing_reach_m=1.66, vane_above_reach_m=0.30, vane_length_m=0.90, vane_width_m=0.08,
                  vane_mass_kg=0.05, vane_ahead_m=0.04, two_foot_window_s=0.05, foot_shift_m=0.03, min_air_s=0.10, rise_min_m=0.05,
                  stand_s=1.0, fall_z_m=0.35)

    sentence = ("Do a vertical jump: from a standstill, jump off both feet without a step, touch the vane above you "
                "with a hand at the top of the jump, land on your feet and stand.")
    rules = ("Your standing reach (the top of a hand, flat-footed, legs straight, arm stretched up) is "
             "{standing_reach_m} m. A vane hangs over you with its underside {vane_above_reach_m} m above that: a "
             "light plate ({vane_mass_kg} kg) {vane_length_m} m long from your left to your right and "
             "{vane_width_m} m wide, on a hinge at its left end, so that it swings away when it is touched. Your "
             "jump is your first flight (nothing of you touches the ground or the stand) of at least {min_air_s} s. "
             "Until then: no step and no run-up: every point where a foot touches the ground must lie within "
             "{foot_shift_m} m of the place where that foot's sole stood at t = 0, and neither foot may be off the "
             "ground for more than {two_foot_window_s} s while the other is on it (so both feet leave the ground "
             "within {two_foot_window_s} s of each other: a two-foot take-off). Rising on the toes is allowed. The "
             "flight must be a jump: your pelvis has to rise at least {rise_min_m} m above its height at lift-off. "
             "The touch: during that flight a hand (the fist or the wrist beyond the forearm) touches the vane. The "
             "first contact after the flight must be with your feet only. After the landing you may step; you "
             "succeed once you stand for {stand_s} s without a break: only your feet on the ground, your torso within about 20 "
             "degrees of vertical, your pelvis slower than 0.35 m/s. A fall fails the attempt at any time: your "
             "pelvis lower than {fall_z_m} m, or any part of you other than your feet on the ground. You fail on a "
             "step or shuffle before the take-off, a foot that leaves the ground before the other, a touch of the "
             "vane that is not in the jump's flight or not with a hand, any touch of the stand (its post or its base "
             "plate on the floor, also after the landing), a jump that "
             "lands without having touched the vane, a flight that is not a jump, a landing that is not on the "
             "feet, a fall, or after {time_limit_s} s.")
    venue = ("You stand facing +x on a level, firm floor. The vane's middle line is {vane_ahead_m} m ahead of your "
             "pelvis, where your raised hand is; it reaches 0.45 m to each side of you. The stand's post is "
             "0.60 m to your left, 0.07 m ahead; it stands on a base plate 0.02 m high that covers x from -0.18 to "
             "0.32 m and y from 0.55 to 0.95 m (your pelvis is at x = 0, y = 0). The vane is yellow, the stand grey.")
    difficulty = ("Neither built-in gait can jump. The robot has to raise its hand 0.30 m beyond its reach: a "
                  "take-off at more than 2 m/s straight up from legs with real torque limits, an arm that is over "
                  "the right place at the top, and a landing from that height that ends standing.")

    def vane_z(self) -> float:
        return self.p["standing_reach_m"] + self.p["vane_above_reach_m"]

    def build(self, sc):
        p = self.p
        H, L, W = self.vane_z(), p["vane_length_m"], p["vane_width_m"]
        x, y_post, t = p["vane_ahead_m"], L / 2 + 0.15, 0.004
        sc.box("mat", (0.2, 0, 0.0003), (1.2, 1.2, 0.0003), rgba=(0.72, 0.25, 0.18, 1))
        sc.geom(sc.wb, "stand_base", type="box", pos=(x + 0.03, y_post + 0.15, 0.01), size=(0.25, 0.20, 0.01),
                rgba=(0.3, 0.3, 0.33, 1), contype="1", conaffinity="13")
        sc.geom(sc.wb, "stand_post", type="cylinder", pos=(x + 0.03, y_post, (H + 0.12) / 2), size=(0.02, (H + 0.12) / 2),
                rgba=(0.3, 0.3, 0.33, 1), contype="1", conaffinity="13")
        # the vane: a plate hinged about a vertical axis at the post; only the robot touches it (its body hulls and its
        # feet's strike boxes), like RoboOlympics' hinged hurdle
        b = sc.body("vane", (x, y_post - 0.03, H + t))
        ET.SubElement(b, "joint", name="vane", type="hinge", axis="0 0 1", range="-2.4 2.4", damping="0.002",
                      frictionloss="0.01", armature="0.0005")
        sc.geom(b, "vane", type="box", pos=(0, -(y_post - 0.03), 0), size=(W / 2, L / 2, t), mass=p["vane_mass_kg"],
                rgba=(0.98, 0.85, 0.1, 1), contype="0", conaffinity="12", condim="3", friction=(0.6, 0.005, 0.0001))
        sc.geom(b, "vane_arm", type="box", pos=(0, -0.06, 0), size=(0.008, 0.06, t), mass=0.005,
                rgba=(0.3, 0.3, 0.33, 1), contype="0", conaffinity="0")
        sc.camera("venue", (2.7, -2.6, 1.7), (0.0, 0.1, 1.05), fovy=52)

    def reset(self, w):
        j = w.m.joint("vane")
        w.d.qpos[int(j.qposadr[0])] = 0.0
        w.d.qvel[int(j.dofadr[0])] = 0.0

    def referee_reset(self, w, ref):
        m = w.m
        self.fall_z = self.p["fall_z_m"]
        self.sole = {s: ref.part(f"{s}_foot") for s in SIDES}
        self.robot = ref.part("robot")
        self.hands = ref.part("hands")
        self.vane = ref.geoms(names=["vane"])
        self.stand = ref.geoms(names=["stand_post", "stand_base"])
        box = {}
        for s in SIDES:                                  # where each sole stands at t = 0 (its contact geoms)
            g = [i for i in np.flatnonzero(self.sole[s]) if m.geom_contype[i] & 1]
            xy = w.d.geom_xpos[g][:, :2]
            box[s] = [float(xy[:, 0].min()), float(xy[:, 0].max()), float(xy[:, 1].min()), float(xy[:, 1].max())]
        # the vane and the stand are not the ground: a body on them is not "in flight" either
        self.trackers = {"flights": Flights(ref, min_air=self.p["min_air_s"], also_allowed=self.vane),
                         "footprint": box, "jumped": False, "last_on": {"left": 0.0, "right": 0.0}, "at_t0": None,
                         "touched_at": None}

    def _before_takeoff(self, w, ref, on) -> bool:
        """The standing start's rules, at every physics step until the jump. False: the attempt has failed."""
        tr, p = self.trackers, self.p
        for s in SIDES:
            other = "right" if s == "left" else "left"
            if on[s]:
                x0, x1, y0, y1 = tr["footprint"][s]
                pts = ref.contact_points(self.sole[s], ref.ground)
                d = np.maximum.reduce([x0 - pts[:, 0], pts[:, 0] - x1, y0 - pts[:, 1], pts[:, 1] - y1])
                if len(pts) and float(d.max()) > p["foot_shift_m"]:
                    ref.fail("a step or shuffle before the take-off", foot=s, moved_m=round(float(d.max()), 3))
                    return False
            elif on[other] and ref.time - tr["last_on"][s] > p["two_foot_window_s"]:
                ref.fail("a foot left the ground before the take-off", foot=s,
                         for_s=round(ref.time - tr["last_on"][s], 3))
                return False
        return True

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        fl = tr["flights"]
        on = {s: ref.touching(self.sole[s], ref.ground) for s in SIDES}
        if ref.touching(self.robot, self.stand):
            return ref.fail("touched the stand", parts=sorted(ref.parts_touching(self.stand)))
        touching = ref.parts_touching(self.vane)
        was_air = fl.air
        done = fl.update()                               # (touching the vane does not end a flight)
        if fl.air and not was_air:
            tr["at_t0"] = dict(tr["last_on"])
        for s in SIDES:
            if on[s]:
                tr["last_on"][s] = ref.time
        if touching and tr["touched_at"] is None and not ref.has("landing"):
            if not touching <= {"left_hand", "right_hand"}:
                return ref.fail("touched the vane with another part than a hand", parts=sorted(touching))
            if not fl.air:
                return ref.fail("touched the vane without a jump", parts=sorted(touching))
            tr["touched_at"] = ref.time
            ref.event("vane", hand=sorted(touching), t_after_liftoff=round(ref.time - fl.cur["t0"], 3))
        if tr["jumped"]:
            return
        if fl.air:                                       # in a flight: it is the jump once it has lasted min_air_s
            if ref.time - fl.cur["t0"] >= p["min_air_s"]:
                rise = fl.cur["apex_z"] - fl.cur["pelvis0"][2]
                if not ref.has("take-off") and rise >= p["rise_min_m"]:
                    ref.stage("take-off", rise_m=round(rise, 3))
                if tr["touched_at"] is not None:
                    ref.stage("touch", hand_t=tr["touched_at"])
            return
        if done is None:
            if tr["touched_at"] is not None:             # the flight of the touch was shorter than min_air_s
                return ref.fail("touched the vane without a jump", air_s=round(ref.time - tr["touched_at"], 3))
            self._before_takeoff(w, ref, on)
            return
        tr["jumped"] = True                              # the first flight of at least min_air_s has landed
        rise = done["apex_z"] - done["pelvis0"][2]
        ref.metrics["air_s"], ref.metrics["rise_m"] = done["air_s"], round(rise, 3)
        if rise < p["rise_min_m"]:
            return ref.fail("the flight was not a jump", rise_m=round(rise, 3))
        if not ref.has("touch"):
            return ref.fail("landed without touching the vane", rise_m=round(rise, 3))
        if not set(done["landing_parts"]) <= {"left_foot", "right_foot"}:
            return ref.fail("the landing was not on the feet", parts=done["landing_parts"])
        ref.stage("landing")

    def step(self, w, ref):
        if ref.has("landing") and ref.hold("stand", ref.standing(), self.p["stand_s"]):
            if ref.stage("stand"):
                ref.succeed()

    def privileged(self, w):
        j = w.m.joint("vane")
        return {"pelvis": w.pelvis().tolist(), "vane_underside_z": self.vane_z(),
                "vane_centre_xy": [self.p["vane_ahead_m"], 0.0], "vane_angle_rad": float(w.d.qpos[int(j.qposadr[0])]),
                "touched": self.trackers["touched_at"] is not None, "jumped": self.trackers["jumped"]}
