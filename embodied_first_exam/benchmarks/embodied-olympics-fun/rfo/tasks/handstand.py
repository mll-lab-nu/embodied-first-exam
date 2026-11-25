"""Handstand: the floor-exercise handstand held for 2 s (FIG MAG Code of Points 2025-2028, floor element I.19), from a
stand and back to the feet.

Robot: the G1. A handstand puts the whole body weight on the arms. The G1 weighs 33 kg (324 N, 162 N per arm); its
shoulders give 25 N m each, so the body above them (27 kg, its centre about 0.45 m from the shoulder line) may lean at
most 50 / (27 x 9.81 x 0.45) = 0.42 rad off the arms' line before the shoulders give way, and in a straight handstand
the static shoulder torque is close to zero. Its wrists (pitch and yaw 5 N m) cannot hold a flat-hand handstand: with
the wrist bent 90 degrees the pad lies 0.12 to 0.22 m beside the wrist axis, i.e. 160 N x 0.17 m = 27 N m, more than
five times the motor, so the weight would rest on the wrist's mechanical stop and its housing; on the fist (the pad's
end face, 4.4 x 8 cm, the forearm's line through it) the wrist torque is near zero and the pads' 8 cm give a support
the balance can use. The H1-2 (67 kg: 330 N per arm, 40 N m shoulders) has half the G1's torque per kilogram, wrists
that bend 0.47 rad at most and fixed Inspire fingers: the G1 is the robot that can do it."""
import math

import numpy as np

from rfo.task import TaskBase


class Task(TaskBase):
    name = "handstand"
    title = "Handstand"
    category = "parkour-apparatus-balance"
    robot = "unitree_g1"
    rulebook = ("FIG Men's Artistic Gymnastics Code of Points 2025-2028: floor exercise, element I.19 'Handstand "
                "(2 s.)' (EG I, non-acrobatic elements); Art. 9.2.15 (a hold element is held at least 2 s, measured "
                "from the moment a complete stop has been reached; no stop is not recognised); Art. 9.2.13 (a "
                "handstand deviating more than 45 degrees from the vertical is not recognised); Art. 10.1 (the floor "
                "area, 12 m x 12 m); Art. 10.2.1.2a (the exercise inside the floor area, the lines included)")
    deviations = [
        "FIG Apparatus Norms, floor: the floor is rigid and level (friction 1.0), not the norm's sprung floor with "
        "its elastic surface, because the simulator's ground is rigid and no sourced stiffness of the sprung floor "
        "is used here (a sprung floor would give energy back at the jump into the handstand: this is not easier)",
        "Art. 10.1 / I.19 (a handstand on the hands): the G1 has no fingers and no palm that opens; each hand is a "
        "rigid rubber fist (a 4.4 x 8 x 10 cm pad on the wrist). Any part of the hand (the pad, the wrist's "
        "housing) may bear the weight: a knuckle (fist) handstand counts as a handstand",
        "Art. 9.2.13 (deviation from the perfect handstand): judged pass or fail with the Code's non-recognition "
        "limit of {max_dev_deg} degrees, on two lines of the body: from the middle of the hands' support to the "
        "pelvis and from the pelvis to the middle of the ankles; the 15 and 30 degree execution deductions are not "
        "applied, as there is no E-Jury",
        "Art. 9.2.13 / I.19 (the handstand's shape: a straight body, legs together and extended): the Code treats "
        "bent legs and a bent body as execution faults and sets no number for when a balance stops being a "
        "handstand; here, judged pass or fail, the knees (the knee joints' angle, 0 = straight) may bend at most "
        "{max_knee_deg} degrees and the hips at most {max_hip_deg} degrees (the angle, measured towards the front, "
        "between the line from the middle of the shoulder joints to the middle of the hip joints and each line "
        "from a hip joint to its knee joint), during the whole hold; both limits lie in the medium band (15-30 "
        "degrees) of the Code's angle-fault scale, so a slightly bent handstand counts (its deductions are not "
        "applied) and a tucked or piked balance does not",
        "Art. 9.2.15 (a complete stop): without judges a stop is the pelvis slower than {still_m_s} m/s",
        "Art. 10.2.1.1 (the exercise begins from a still stand, legs together): the robot starts in its own stance, "
        "feet 0.24 m apart, because that is how it stands; the task is one element and the way back to the feet, "
        "not a 70 s exercise",
    ]
    time_limit_s = 30.0
    start = (0.0, 0.0, 0.0)
    fall_rule = True
    legal_ground = ("left_foot", "right_foot", "left_hand", "right_hand")
    stages = ["handstand", "held 2 s", "on the feet", "stand"]
    params = dict(hold_s=2.0, max_dev_deg=45.0, max_knee_deg=20.0, max_hip_deg=25.0, still_m_s=0.15,
                  stand_s=1.0, stand_tilt_deg=20.0,
                  stand_still_m_s=0.35, fall_pelvis_m=0.25, area_m=12.0)

    sentence = ("Do a handstand: get up onto your hands, hold a straight handstand still for 2 s, then come back "
                "down onto your feet and stand.")
    rules = ("A handstand is: only your hands on the floor (nothing else of you touches it), your pelvis above your "
             "hands and your ankles above your pelvis, and both lines of your body, from the middle of where your "
             "hands touch the floor to your pelvis and from your pelvis to the middle of your ankles, within "
             "{max_dev_deg} degrees of vertical (the Code of Points does not recognise a handstand that deviates "
             "more), and your body extended: your knees bent at most {max_knee_deg} degrees (the knee joints' "
             "angle, 0 is straight) and your hips bent at most {max_hip_deg} degrees (the angle, towards your "
             "front, between the line from the middle of your shoulder joints to the middle of your hip joints and "
             "the line from each hip joint to its knee joint); a tucked or piked balance is not a handstand. Any part of "
             "your hand counts as the hand (you have fists, not fingers). The handstand is held "
             "while you stay in it with your pelvis slower than {still_m_s} m/s (a complete stop); it counts once it "
             "has been held without a break for {hold_s} s. After that you come back down so that only your feet "
             "touch the floor (your hands off it), and then you stand for {stand_s} s without a break: only your feet "
             "on the floor, your torso within {stand_tilt_deg} degrees of vertical, your pelvis slower than "
             "{stand_still_m_s} m/s. You fail if any part of you other than your hands and feet touches the floor, "
             "or your pelvis is lower than {fall_pelvis_m} m (a fall); if any part of you touches the floor outside "
             "the {area_m} m x {area_m} m floor area (its lines are inside); or after {time_limit_s} s. Your feet "
             "may leave the floor in a jump; nothing limits how you get onto your hands or back to your feet.")
    venue = ("You stand in the middle of a gymnastics floor-exercise area, {area_m} m by {area_m} m, marked by white "
             "lines, flat, level and rigid, with nothing on it; you face +x.")
    difficulty = ("Your whole 33 kg rests on two small fists and arms whose shoulders give 25 N m: the body has to be "
                  "balanced over a support a few centimetres long, actively, as an inverted pendulum, and no built-in "
                  "action does that. Getting from standing onto the hands, and from the hands back onto the feet, are "
                  "as hard as the hold.")

    @property
    def fall_z(self):
        return self.p["fall_pelvis_m"]

    def build(self, sc):
        h = self.p["area_m"] / 2
        sc.box("mat", (0.0, 0, 0.0003), (h, h, 0.0003), rgba=(0.25, 0.35, 0.65, 1))
        for i, (a, b) in enumerate((((-h, -h), (h, -h)), ((h, -h), (h, h)), ((h, h), (-h, h)), ((-h, h), (-h, -h)))):
            sc.line(f"area_line{i}", a, b)
        sc.camera("venue", (0.3, -3.6, 1.2), (0.2, 0.0, 0.6), fovy=50)

    def referee_reset(self, w, ref):
        self.hands = ref.part("hands")
        self.feet = ref.part("feet")
        self.min_upright = math.cos(math.radians(self.p["stand_tilt_deg"]))
        m = w.m
        self.ankles = [m.body(f"{s}_ankle_roll_link").id for s in ("left", "right")]
        jid = lambda n: m.joint(n).id
        self.knees = [int(m.jnt_qposadr[jid(f"{s}_knee_joint")]) for s in ("left", "right")]
        self.hip_j = [jid(f"{s}_hip_pitch_joint") for s in ("left", "right")]
        self.knee_j = [jid(f"{s}_knee_joint") for s in ("left", "right")]
        self.shoulder_j = [jid(f"{s}_shoulder_pitch_joint") for s in ("left", "right")]
        self.torso = m.body("torso_link").id
        # off_hands: something other than the hands touched the floor during this control step (seen every 1 ms)
        self.trackers = {"best_hold_s": 0.0, "in_handstand": False, "hold_n": 0, "off_hands": False}

    def shape(self, w):
        """(the knees' bend, the hips' bend) in degrees, the larger of the two sides. Knee: the knee joint's angle
        (0 = straight). Hip: the angle from the trunk line (the shoulder joints' middle to the hip joints' middle)
        to the thigh line (a hip joint to its knee joint), positive towards the torso's front (flexion, a pike);
        0 in the robot's zero pose."""
        d = w.d
        knee = max(math.degrees(float(d.qpos[a])) for a in self.knees)
        sh = 0.5 * (d.xanchor[self.shoulder_j[0]] + d.xanchor[self.shoulder_j[1]])
        hp = 0.5 * (d.xanchor[self.hip_j[0]] + d.xanchor[self.hip_j[1]])
        trunk = hp - sh
        side = d.xmat[self.torso].reshape(3, 3)[:, 1]
        hip = -180.0
        for h, k in zip(self.hip_j, self.knee_j):
            thigh = d.xanchor[k] - d.xanchor[h]
            c = float(trunk @ thigh) / max(1e-9, float(np.linalg.norm(trunk) * np.linalg.norm(thigh)))
            a = math.degrees(math.acos(max(-1.0, min(1.0, c))))
            hip = max(hip, a if float(np.cross(trunk, thigh) @ side) <= 0.0 else -a)
        return knee, hip

    def geometry(self, w, ref):
        """(in a handstand now, the two lines' deviations in degrees, the hands' support middle)."""
        d = w.d
        parts = ref.parts_touching(ref.ground)
        pts = ref.contact_points(self.hands, ref.ground)
        if not parts or not parts <= {"left_hand", "right_hand"} or not len(pts):
            return False, None, None
        h = pts.mean(axis=0)
        pel = d.qpos[w.robot.fq:w.robot.fq + 3]
        ank = 0.5 * (d.xpos[self.ankles[0]] + d.xpos[self.ankles[1]])
        devs = []
        for a, b in ((h, pel), (pel, ank)):
            v = b - a
            n = float(np.linalg.norm(v))
            devs.append(180.0 if n < 1e-9 else math.degrees(math.acos(max(-1.0, min(1.0, v[2] / n)))))
        knee, hip = self.shape(w)
        ok = (max(devs) <= self.p["max_dev_deg"] and pel[2] > h[2] and ank[2] > pel[2]
              and knee <= self.p["max_knee_deg"] and hip <= self.p["max_hip_deg"])
        return ok, devs, h

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        if not (ref.failed or ref.success):              # the fall rule, also after every physics step (1 ms):
            z = float(w.d.qpos[w.robot.fq + 2])            # a touch shorter than a control step is not missed
            bad = ref.parts_touching(ref.ground) - set(self.legal_ground)
            if z < self.fall_z:
                return ref.fail("fell", pelvis_z=round(z, 3))
            if bad:
                return ref.fail("fell", on_the_ground=sorted(bad))
        half = p["area_m"] / 2
        pts = ref.contact_points(ref.robot_mask, ref.ground)       # after every physics step (1 ms)
        if len(pts) and (np.abs(pts[:, :2]) > half + 1e-9).any():
            return ref.fail("outside the floor area")
        if ref.parts_touching(ref.ground) - {"left_hand", "right_hand"}:
            tr["off_hands"] = True

    def step(self, w, ref):
        p, tr = self.p, self.trackers
        off, tr["off_hands"] = tr["off_hands"], False
        if not ref.has("held 2 s"):
            ok, devs, h = self.geometry(w, ref)
            ok = ok and not off                            # a foot down in between breaks the handstand
            tr["in_handstand"] = bool(ok)
            if ok:
                knee, hip = self.shape(w)
                ref.stage("handstand", dev_deg=[round(x, 1) for x in devs], knee_deg=round(knee, 1),
                          hip_deg=round(hip, 1))
            v = float(np.linalg.norm(w.d.qvel[w.robot.fv:w.robot.fv + 3]))
            still = ok and v <= p["still_m_s"]
            tr["hold_n"] = tr["hold_n"] + 1 if still else 0
            if tr["hold_n"] * w.CONTROL_DT >= p["hold_s"] - 1e-9:
                ref.stage("held 2 s")
            tr["best_hold_s"] = round(max(tr["best_hold_s"], tr["hold_n"] * w.CONTROL_DT), 2)
            ref.metrics["hold_s"] = tr["best_hold_s"]
            return
        parts = ref.parts_touching(ref.ground)
        if parts and parts <= {"left_foot", "right_foot"}:
            ref.stage("on the feet")
        still = ref.standing(max_speed=p["stand_still_m_s"], min_upright=self.min_upright)
        if ref.has("on the feet") and ref.hold("stand", still, p["stand_s"]):
            if ref.stage("stand"):
                ref.succeed()

    def privileged(self, w):
        ref = w.ref
        ok, devs, h = self.geometry(w, ref)
        knee, hip = self.shape(w)
        return {"pelvis": w.pelvis().tolist(), "com": w.com().tolist(), "in_handstand": bool(ok),
                "dev_deg": devs, "knee_bend_deg": knee, "hip_bend_deg": hip,
                "hands_support": None if h is None else h.tolist(),
                "hold_s": self.trackers.get("best_hold_s", 0.0)}
