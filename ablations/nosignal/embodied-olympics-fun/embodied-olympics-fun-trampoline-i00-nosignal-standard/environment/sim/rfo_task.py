"""Trampoline (FIG Trampoline Gymnastics): on a competition trampoline whose bed is a spring-supported surface, bounce
as you like, perform one tuck jump, land on both feet, stop the bed (at most one controlled out-bounce) and stand
still."""
import math
import xml.etree.ElementTree as ET

import numpy as np

from rfo.referee import Flights
from rfo.scene import STANDABLE, VISUAL
from rfo.task import TaskBase

SIDES = ("left", "right")
G = 9.81
RED = (0.85, 0.12, 0.12, 1)


class Task(TaskBase):
    name = "trampoline"
    title = "Trampoline: tuck jump and stop"
    category = "parkour-apparatus-balance"
    robot = "unitree_g1"
    rulebook = ("FIG Code of Points 2022-2024, Trampoline Gymnastics (valid from 1 January 2022; the edition the "
                "family was written from): Part I §14.2-14.3 "
                "(the tuck position: the angle between the upper body and the thighs and the angle between the "
                "thighs and the lower legs each 135 degrees or less; straight: the upper body-thigh angle greater "
                "than 135 degrees), §16.1 (an interruption: not landing simultaneously on both feet, landing on a "
                "part of the body other than the feet, seat, front or back, touching anything other than the bed, "
                "leaving the trampoline), §17.1-17.3 (the end: upright on the bed with the feet less than shoulder "
                "width apart, at most one controlled out-bounce in a straight position, then standing still for "
                "about 3 seconds), Part II §14 (a shape is judged in the middle phase of the element). FIG Apparatus "
                "Norms TRA 1 (01.01.2017): the frame 5.05 x 2.91 m inside, the bed 4.28 x 2.14 m at 1.155 m, area A "
                "2.15 x 1.08 m and area B 1.08 x 1.08 m marked in red lines 13-24 mm wide with a 0.70 m red cross at "
                "the centre; the frame and springs padded 3-5 cm thick; end platforms with mats; and FIG Apparatus "
                "Norms IV TRA 1 (01.04.2024): the impact test, a 60 kg, 0.40 m sphere dropped from 4.00 m onto the "
                "centre: deflection 940-1010 mm, rebound 3410-3660 mm")
    deviations = [
        "Apparatus Norms TRA 1 (the bed): the web bed and its 118 springs are one flat plate on a vertical slide "
        "with a linear spring of {bed_stiffness_n_m} N/m, the equivalent vertical stiffness measured at the centre "
        "of a 5.05 x 2.91 x 1.15 m competition trampoline (Qian et al. 2020, J Hum Kinet 73: 59-72), its moving "
        "mass {bed_mass_kg} kg (an estimate: the literature's models treat the bed as massless) and a damping "
        "{bed_damping_n_s_m} N s/m chosen so that the norm's impact test passes (the family's test drops the 60 kg "
        "sphere from 4.00 m). The plate stays level: a real bed dips locally under the feet and throws an off-centre "
        "landing towards the middle (the norm's 1.67-2.02 m sideways rebound at its point 4); here an off-centre "
        "landing goes straight up, and the bed's stiffness does not grow with depth",
        "Code of Points §1 and §16.1.3 (the exercise): one element, a tuck jump, instead of ten; straight bounces "
        "before it are free (in-bounces), as before an exercise starts; no execution, difficulty, time-of-flight or "
        "horizontal-displacement score: the attempt is valid or not",
        "Code of Points §14.2-14.3 / Part II §14 (the tuck): judged on the robot's joint centres: in each leg the "
        "angle at the hip between the shoulder and the knee, and at the knee between the hip and the ankle, both at "
        "most {tuck_max_deg} degrees, held at least {tuck_hold_s} s within the middle half of the flight (a shape "
        "passed through on the way is not shown); the hands on the shins and "
        "the pointed toes (§14.3, §14.5: execution deductions) are not judged",
        "Code of Points §14 (a jump): the rule book scores height (time of flight) but sets no minimum; a tuck "
        "counts only in a flight whose centre of mass rises at least {min_rise_m} m above its height standing at "
        "the start, so that lifting the legs off the bed is not a jump",
        "Code of Points §16.1.1 (both feet simultaneously): the second foot must touch the bed within "
        "{two_foot_window_s} s of the first; a flight counts from {min_air_s} s in the air",
        "Code of Points §16.1.4 (the landing): only the feet: seat, front and back landings, legal in an exercise, "
        "end this attempt as falls",
        "Code of Points §17.1-17.3 (the stop): standing still is judged as {stand_s} s without a break with only the "
        "feet on the bed, the torso within 20 degrees of vertical, the pelvis slower than {still_m_s} m/s and the "
        "ankles at most {feet_max_m} m apart (the robot's shoulder width: the distance between its shoulder "
        "joints); the out-bounce must be straight (hips and "
        "knees more than {tuck_max_deg} degrees open through its middle half)",
        "the robot starts standing at the centre of the bed (placed there at t = 0, the bed bent under its weight), "
        "not climbing on",
    ]
    time_limit_s = 30.0
    start = (0.0, 0.0, 0.0)
    stages = ["tuck jump", "landing", "stop"]
    fall_rule = False                # the robot is above the floor on purpose; the family's own rules judge falls
    params = dict(bed_length_m=4.28, bed_width_m=2.14, bed_height_m=1.155, frame_length_m=5.05, frame_width_m=2.91,
                  pad_thickness_m=0.05, bed_stiffness_n_m=5690.0, bed_mass_kg=3.0, bed_damping_n_s_m=3.0,
                  bed_contact_s=0.002, bed_contact_ratio=1.0,
                  area_a_m=(2.15, 1.08), area_b_m=(1.08, 1.08), cross_m=0.70, line_m=0.02,
                  min_air_s=0.10, two_foot_window_s=0.10, tuck_max_deg=135.0, tuck_hold_s=0.05, min_rise_m=0.10,
                  stand_s=3.0, still_m_s=0.35,
                  feet_max_m=0.28, bed_friction=1.0)

    sentence = ("On the trampoline, bounce as you like, then do one tuck jump, land on both feet, stop the bounce "
                "(one more straight out-bounce at most) and stand still.")
    rules = ("You stand at the centre of the trampoline's bed, {bed_height_m} m above the floor, facing +x along its "
             "length. A flight is a time of at least {min_air_s} s in which nothing of you touches anything; your "
             "centre of "
             "mass's height when you stand at the start is the reference height. Straight "
             "bounces first are free. The tuck jump is your first flight in which your body is not straight: at some "
             "moment of its middle half (from a quarter to three quarters of the flight's time) each leg must be "
             "tucked: the angle at the hip between your shoulder and your knee, and the angle at the knee between "
             "your hip and your ankle, both {tuck_max_deg} degrees or less (180 is straight), held for at least "
             "{tuck_hold_s} s without a break, "
             "and it must be a jump: in it your centre of mass "
             "rises at least {min_rise_m} m above the reference height (a tuck without that height fails). A flight "
             "before it in "
             "which a hip or a knee closes to {tuck_max_deg} degrees or less in the middle half without the tuck is "
             "another element and fails. Every landing must be on the bed, on your feet only, both feet within "
             "{two_foot_window_s} s of each other. After the tuck jump's landing you may make one more flight, an "
             "out-bounce, which must be straight (hips and knees more open than {tuck_max_deg} degrees through its "
             "middle half); a second flight fails. Then stop: stand still for {stand_s} s without a break: only your "
             "feet on the bed, your torso within about 20 degrees of vertical, your pelvis slower than {still_m_s} "
             "m/s, your ankles at most {feet_max_m} m apart. You fail on a landing with any other part of you on the "
             "bed, on touching anything other than the bed (the padding over the frame and springs, the end "
             "platforms, the floor), or after {time_limit_s} s. Success: the tuck jump, its landing and the stop, in "
             "that order.")
    venue = ("The bed is {bed_length_m} m long (along x) and {bed_width_m} m wide, its surface {bed_height_m} m above "
             "the floor at rest, centred under you. It is held by springs: it gives under load, about "
             "{bed_stiffness_n_m} N per metre of depth, and springs back. Around it, over the springs and the frame "
             "({frame_length_m} x {frame_width_m} m inside), lies padding {pad_thickness_m} m thick; safety "
             "platforms with mats stand at both ends and mats lie on the floor around. Red lines mark area A "
             "(2.15 x 1.08 m) and area B (1.08 x 1.08 m) round the centre, and a 0.70 m red cross the centre. "
             "Nothing moves but the bed.")
    difficulty = ("The robot must time its leg push with a bed that drops "
                  "and recoils under it to gain height, tuck and open again in the air, land on both feet, and then "
                  "kill the bounce of a springy bed with its legs until it stands still.")

    # ------------------------------------------------------------------ the venue
    def build(self, sc):
        p = self.p
        L, W, H = p["bed_length_m"], p["bed_width_m"], p["bed_height_m"]
        FL, FW, pt = p["frame_length_m"], p["frame_width_m"], p["pad_thickness_m"]
        th = 0.02
        # the bed: a plate on a vertical slide, on a spring whose rest length holds it at H under its own weight
        b = sc.body("bed", (0.0, 0.0, H - th / 2))
        ET.SubElement(b, "joint", name="bed", type="slide", axis="0 0 1", stiffness=f"{p['bed_stiffness_n_m']:g}",
                      springref=f"{p['bed_mass_kg'] * G / p['bed_stiffness_n_m']:.6g}",
                      damping=f"{p['bed_damping_n_s_m']:g}", range="-1.1 0.3", armature="0.0")
        # the bed is an open web (4-6 mm bands 1.6 cm apart at most, TRA 1 2.3): air passes through it, so the plate
        # feels no air drag (the venue's air would otherwise brake a 9 m2 solid plate hard)
        sc.geom(b, "bed", type="box", size=(L / 2, W / 2, th / 2), mass=p["bed_mass_kg"], rgba=(0.20, 0.20, 0.22, 1),
                friction=(p["bed_friction"], 0.005, 0.0001), priority="2",
                solref=(p["bed_contact_s"], p["bed_contact_ratio"]), fluidshape="ellipsoid", fluidcoef=(0, 0, 0, 0, 0),
                **STANDABLE)
        # the red markings (FIG TRA 1 2.5), drawn on the bed
        lw, z = p["line_m"], th / 2 + 0.0005
        ax, ay = p["area_a_m"]
        bx, by = p["area_b_m"]
        for name, (cx, cy, hx, hy) in {
                "a_x0": (-ax / 2, 0, lw / 2, W / 2), "a_x1": (ax / 2, 0, lw / 2, W / 2),
                "a_y0": (0, -ay / 2, ax / 2, lw / 2), "a_y1": (0, ay / 2, ax / 2, lw / 2),
                "b_x0": (-bx / 2, 0, lw / 2, by / 2), "b_x1": (bx / 2, 0, lw / 2, by / 2),
                "a_ext0": (-(ax / 2 + L / 2) / 2, -ay / 2, (L / 2 - ax / 2) / 2, lw / 2),
                "a_ext1": (-(ax / 2 + L / 2) / 2, ay / 2, (L / 2 - ax / 2) / 2, lw / 2),
                "a_ext2": ((ax / 2 + L / 2) / 2, -ay / 2, (L / 2 - ax / 2) / 2, lw / 2),
                "a_ext3": ((ax / 2 + L / 2) / 2, ay / 2, (L / 2 - ax / 2) / 2, lw / 2),
                "cross_x": (0, 0, p["cross_m"] / 2, lw / 2), "cross_y": (0, 0, lw / 2, p["cross_m"] / 2)}.items():
            sc.geom(b, f"mark_{name}", type="box", pos=(cx, cy, z), size=(hx, hy, 0.0004), rgba=RED, **VISUAL)
        # the padding over the springs and the frame: four slabs, clear of the bed (TRA 1 5.1: 3-5 cm thick, its
        # underside at most 6 cm above the bed)
        gap = 0.01
        pz = H + 0.01 + pt / 2
        sc.box("pad_x0", (-(L / 2 + FL / 2) / 2 - gap / 2, 0, pz), ((FL - L) / 4 + 0.06, FW / 2 + 0.08, pt / 2),
               rgba=(0.15, 0.30, 0.75, 1), solid="stand")
        sc.box("pad_x1", ((L / 2 + FL / 2) / 2 + gap / 2, 0, pz), ((FL - L) / 4 + 0.06, FW / 2 + 0.08, pt / 2),
               rgba=(0.15, 0.30, 0.75, 1), solid="stand")
        sc.box("pad_y0", (0, -(W / 2 + FW / 2) / 2 - gap / 2, pz), (L / 2 + gap, (FW - W) / 4 + 0.06, pt / 2),
               rgba=(0.15, 0.30, 0.75, 1), solid="stand")
        sc.box("pad_y1", (0, (W / 2 + FW / 2) / 2 + gap / 2, pz), (L / 2 + gap, (FW - W) / 4 + 0.06, pt / 2),
               rgba=(0.15, 0.30, 0.75, 1), solid="stand")
        # the springs under the padding (drawn), the frame's legs, the end platforms and the floor mats
        for i, x in enumerate(np.linspace(-L / 2 + 0.1, L / 2 - 0.1, 12)):
            for s in (1, -1):
                sc.geom(sc.wb, f"spring_y{i}_{s + 1}", type="capsule",
                        fromto=(x, s * (W / 2 + 0.01), H - 0.01, x, s * FW / 2, H - 0.01), size=(0.012,),
                        rgba=(0.6, 0.6, 0.62, 1), **VISUAL)
        for sx in (1, -1):
            for sy in (1, -1):
                sc.box(f"leg_{sx + 1}{sy + 1}", (sx * (FL / 2 + 0.03), sy * (FW / 2 + 0.03), H / 2),
                       (0.03, 0.03, H / 2), rgba=(0.55, 0.55, 0.58, 1), solid="hit")
            sc.box(f"deck_{sx + 1}", (sx * (FL / 2 + 0.12 + 1.2), 0.0, (H + 0.075) / 2), (1.2, 1.5, (H + 0.075) / 2),
                   rgba=(0.15, 0.30, 0.75, 1), solid="stand")
        for sy in (1, -1):
            sc.box(f"floormat_{sy + 1}", (0.0, sy * (FW / 2 + 1.2), 0.1), (FL / 2 + 1.5, 1.0, 0.1),
                   rgba=(0.15, 0.30, 0.75, 1), solid="stand")
        sc.camera("venue", (0.5, -6.0, 3.6), (0.0, 0.0, 1.7), fovy=45)

    def reset(self, w):
        r, d, m, p = w.robot, w.d, w.m, self.p
        sag = r.mass * G / p["bed_stiffness_n_m"]               # the bed bent under the standing robot
        j = m.joint("bed")
        d.qpos[int(j.qposadr[0])] = -sag
        d.qvel[int(j.dofadr[0])] = 0.0
        d.qpos[r.fq + 2] = p["bed_height_m"] - sag + r.stand_z

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        m = w.m
        jid = lambda n: m.joint(n).id  # noqa: E731
        self.J = {k: {s: jid(f"{s}_{k}_joint") for s in SIDES} for k in ("hip_pitch", "knee", "ankle_pitch",
                                                                           "shoulder_pitch")}
        self.bed = ref.geoms(names=["bed"])
        self.other = ref.geoms(prefix="pad_") | ref.geoms(prefix="leg_") | ref.geoms(prefix="deck_") \
            | ref.geoms(prefix="floormat_") | ref.geoms(names=["floor"])
        self.sole = {s: ref.part(f"{s}_foot") for s in SIDES}
        self.not_feet = ref.part("robot") & ~ref.part("feet")
        self.trackers = {"flights": Flights(ref, min_air=self.p["min_air_s"]), "samples": [], "n_after": 0,
                         "first_foot": None, "landed_ok": True, "settled": False, "com0": round(float(w.com()[2]), 6),
                         "com_max": None}

    def angles(self, w):
        """(the smaller hip angle, the smaller knee angle) over the two legs, degrees: 180 is straight."""
        a = lambda j: w.d.xanchor[j]  # noqa: E731

        def ang(pv, p1, p2):
            u, v = p1 - pv, p2 - pv
            c = float(u @ v) / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-12)
            return math.degrees(math.acos(max(-1.0, min(1.0, c))))
        J = self.J
        hip = max(ang(a(J["hip_pitch"][s]), a(J["shoulder_pitch"][s]), a(J["knee"][s])) for s in SIDES)
        knee = max(ang(a(J["knee"][s]), a(J["hip_pitch"][s]), a(J["ankle_pitch"][s])) for s in SIDES)
        return hip, knee                                # the more open leg: both legs must be tucked

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        fl = tr["flights"]
        if ref.touching(ref.robot_mask, self.other):
            return ref.fail("touched something other than the bed (CoP 16.1.6, 16.1.8)",
                            parts=sorted(ref.parts_touching(self.other)))
        if not tr["settled"]:                          # the robot is placed a few mm above the bed: it settles first
            if all(ref.touching(self.sole[s], self.bed) for s in SIDES):
                tr["settled"] = True
                fl.reset()
            return
        if ref.touching(self.not_feet, self.bed):
            return ref.fail("on the bed with a part other than the feet (CoP 16.1.4)",
                            parts=sorted(ref.parts_touching(self.bed) - {"left_foot", "right_foot"}))
        was_air = fl.air
        done = fl.update()
        if fl.air:
            cz = round(float(w.com()[2]), 6)
            tr["com_max"] = cz if not was_air or tr["com_max"] is None else max(tr["com_max"], cz)
            hip, knee = self.angles(w)
            tr["samples"].append([round(ref.time - fl.cur["t0"], 4), round(hip, 2), round(knee, 2)])
        elif was_air and done is None:
            tr["samples"] = []                         # a flight shorter than min_air_s: not a flight
        on = [ref.touching(self.sole[s], self.bed) for s in SIDES]
        if done is not None:                           # a landing: the flight's shape, then both feet
            T = done["air_s"]
            mid = [s for s in tr["samples"] if 0.25 * T <= s[0] <= 0.75 * T]
            tr["samples"] = []
            run = best = 0                             # the tuck held without a break in the middle half
            for _, h, k in mid:
                run = run + 1 if h <= p["tuck_max_deg"] and k <= p["tuck_max_deg"] else 0
                best = max(best, run)
            tuck = best * w.PHYS_DT >= p["tuck_hold_s"] - 1e-9
            bent = any(h <= p["tuck_max_deg"] or k <= p["tuck_max_deg"] for _, h, k in mid)
            rise = round((tr["com_max"] or 0.0) - tr["com0"], 4)
            ref.event("flight", air_s=T, com_rise_m=rise, tuck=tuck, bent=bent)
            ref.metrics["flights"] = ref.metrics.get("flights", 0) + 1
            if not ref.has("tuck jump"):
                if tuck and rise < p["min_rise_m"]:
                    return ref.fail("the tuck was not a jump: the centre of mass did not rise enough", com_rise_m=rise)
                if tuck:
                    ref.stage("tuck jump", air_s=T)
                    ref.metrics["tuck_jump_air_s"] = T
                    ref.metrics["tuck_jump_com_rise_m"] = rise
                elif bent:
                    return ref.fail("a different element before the tuck jump (a pike or a bent jump)", air_s=T)
            else:
                tr["n_after"] += 1
                if tr["n_after"] > 1:
                    return ref.fail("did not stop: a second flight after the tuck jump (CoP 17.2)")
                if bent:
                    return ref.fail("the out-bounce is not straight (CoP 17.2)", air_s=T)
            tr["first_foot"] = ref.time
            tr["landed_ok"] = False
        if not tr["landed_ok"] and not fl.air:
            if all(on):
                tr["landed_ok"] = True
                if ref.has("tuck jump") and tr["n_after"] == 0:
                    ref.stage("landing")
            elif ref.time - tr["first_foot"] > p["two_foot_window_s"]:
                return ref.fail("did not land on both feet simultaneously (CoP 16.1.1)")

    def step(self, w, ref):
        tr, p = self.trackers, self.p
        if not ref.has("landing") or not tr["landed_ok"]:
            return
        feet = float(np.linalg.norm(w.d.xanchor[self.J["ankle_pitch"]["left"]]
                                    - w.d.xanchor[self.J["ankle_pitch"]["right"]]))
        ok = ref.standing(max_speed=p["still_m_s"], on=self.bed) and feet <= p["feet_max_m"] \
            and not tr["flights"].air
        if ref.hold("stop", ok, p["stand_s"]) and ref.stage("stop"):
            ref.succeed()

    def privileged(self, w):
        j = w.m.joint("bed")
        return {"pelvis": w.pelvis().tolist(), "com": w.com().tolist(),
                "bed_z": self.p["bed_height_m"] + float(w.d.qpos[int(j.qposadr[0])]),
                "bed_vz": float(w.d.qvel[int(j.dofadr[0])]), "in_air": bool(self.trackers["flights"].air),
                "hip_knee_deg": list(self.angles(w))}
