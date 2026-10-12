"""Clean and jerk (IWF): the loaded men's barbell from the platform to the shoulders, then to locked arms overhead, and
held motionless there until the referee's "down" signal."""
import math
import xml.etree.ElementTree as ET

import numpy as np

from rfo.scene import HITTABLE, bounce_solref
from rfo.task import TaskBase

# What the IWF barbell rule does not fix (estimates, stated in `deviations`): how the bar's 20 kg is split between the
# shaft and the two revolving sleeves, the width of a disc and of a collar, the bumpers' bounce on the platform.
SHAFT_KG, SLEEVE_KG = 7.0, 6.5
FLANGE_M, DISC_W_M, COLLAR_W_M, COLLAR_R_M = 0.030, 0.034, 0.070, 0.045
BUMPER_BOUNCE = 0.4
SIDES = ("left", "right")


class Task(TaskBase):
    name = "clean-and-jerk"
    title = "Weightlifting: clean and jerk"
    category = "parkour-apparatus-balance"
    robot = "unitree_h1"
    rulebook = ("IWF Technical and Competition Rules & Regulations (International Weightlifting Federation; quoted "
                "from memory of the 2020s editions): 2.3 the clean and jerk, 2.5 incorrect movements, 3.1 the "
                "platform, 3.3 the barbell")
    deviations = [
        "3.3 (the barbell's load): the barbell is the lightest one the men's equipment gives on full-size discs: the "
        "{bar_mass_kg} kg bar, one {disc_mass_kg} kg disc of {disc_diameter_m} m (the lightest disc of the full "
        "diameter) and one {collar_mass_kg} kg collar on each sleeve, {total_mass_kg} kg; there is no choice of weight "
        "and no progression of attempts, because the task is one attempt",
        "3.3 (what the rule leaves open): the bar's {bar_mass_kg} kg are split 7 kg for the shaft and 6.5 kg for each "
        "revolving sleeve, a disc is 0.034 m wide and a collar 0.07 m, and a disc keeps 0.4 of its speed when it "
        "bounces on the platform; these are estimates, the rule gives no numbers for them",
        "3.3 (the grip): the robot's hands have no fingers; a closed grip holds the bar's grip section rigidly to the "
        "palm when the bar's surface is within 3.5 cm of the palm point, so the hook grip, chalk and the strength of "
        "the fingers are not simulated",
        "2.3.1 (the clean): the referee judges the end of the clean, not the movement: the bar at the shoulders (its "
        "axis within {clean_rack_m} m of both shoulder joints; the robot's rigid chest stands 0.07 m ahead of them, "
        "so the bar cannot lie on the collarbones) with the legs extended, the feet on one line and everything "
        "motionless for {clean_hold_s} s (the rule says \"motionless\" and gives no time); that the bar came there in "
        "a single movement is not judged, because that needs a human reading of the pull",
        "the rules' \"at the shoulders\" and \"overhead\" assume a lifter who stands under the bar; so that neither "
        "position can be reached bent over or with the bar behind the back, in both the trunk must be upright (the "
        "cosine of its tilt at least {upright_cos}), the bar's centre no more than {bar_centre_m} m (horizontally) "
        "from the point midway between the shoulder joints, and the bar within {bar_align_deg} degrees of the line "
        "through the shoulder joints (seen from above)",
        "2.5 (incorrect movements): judged here are the unfinished attempt above knee height, a part other than the "
        "feet on the platform, leaving the platform, the incomplete extension of the arms and legs at the finish and "
        "the feet not on one line; not judged, because they need a human judge's reading of the movement: the "
        "press-out and a pause while the arms extend, pulling from the hang, the bar touching the thighs, the elbows "
        "or upper arms touching the knees or thighs, an uneven extension of the arms, the oscillation of the bar "
        "before the jerk",
        "2.3.2 (the finish): \"fully extended\" is read from the robot's joints: each elbow within {elbow_lock_deg} "
        "degrees and each knee within {knee_lock_deg} degrees of straight; \"motionless\" is the bar and the pelvis "
        "slower than {still_m_s} m/s; the three referees' \"down\" signal is given by the simulator when the final "
        "position has been held for {hold_s} s, and the attempt ends there: lowering the bar after the signal is "
        "not part of the task",
        "6.6 (the clock): the athlete's one minute runs here from the start of the episode to the down signal "
        "({time_limit_s} s for the whole attempt); the rule's minute runs from the call to the platform to the start "
        "of the lift, and there is no call here",
    ]
    time_limit_s = 60.0
    start = (0.0, 0.0, 0.0)
    stages = ["lift-off", "clean", "overhead", "down signal"]
    fall_rule = False                # the family's own contact rules (2.5): feet only on the platform, nothing off it
    params = dict(platform_size_m=4.0, platform_height_m=0.10,
                  bar_mass_kg=20.0, bar_length_m=2.20, grip_diameter_m=0.028, grip_length_m=1.31,
                  sleeve_diameter_m=0.050, sleeve_length_m=0.415, disc_mass_kg=10.0, disc_diameter_m=0.45,
                  collar_mass_kg=2.5, total_mass_kg=45.0, bar_ahead_m=0.10,
                  lift_tolerance_m=0.03, knee_height_m=0.48, clean_rack_m=0.15, clean_hold_s=0.5, overhead_m=0.25,
                  elbow_lock_deg=10.0, knee_lock_deg=10.0, feet_line_m=0.05, bar_tilt_max_deg=60.0, still_m_s=0.10,
                  upright_cos=0.94, bar_centre_m=0.25, bar_align_deg=20.0,
                  hold_s=2.0)

    sentence = ("Clean and jerk the barbell: lift it from the platform to your shoulders, then to locked arms "
                "overhead, and hold it there motionless until the down signal.")
    rules = ("The barbell is the IWF men's bar ({bar_mass_kg} kg, {bar_length_m} m long; the grip section between the "
             "sleeves is {grip_length_m} m long and {grip_diameter_m} m thick; the sleeves are {sleeve_length_m} m "
             "long and {sleeve_diameter_m} m thick and revolve on the bar) with one {disc_mass_kg} kg rubber disc of "
             "{disc_diameter_m} m and one {collar_mass_kg} kg collar on each sleeve: {total_mass_kg} kg. It lies on "
             "the competition platform ({platform_size_m} m by {platform_size_m} m, {platform_height_m} m high), on "
             "which you stand. A hand can grip the grip section anywhere along it. "
             "Lift-off: the bar may leave the platform only in both hands: you fail the moment the bar's axis is more "
             "than {lift_tolerance_m} m above where it lies at rest while fewer than two hands grip it. "
             "The attempt: once the bar's centre has been {knee_height_m} m above the platform (knee height) the lift "
             "must be finished: from then on you fail if either hand lets go or if any part of the barbell touches the "
             "platform before the down signal. "
             "The clean: the bar must first rest at your shoulders: its axis within {clean_rack_m} m of both shoulder "
             "joints, both hands on it, both knees within {knee_lock_deg} degrees of straight, both feet on the "
             "platform and on one line, the bar and your pelvis slower than {still_m_s} m/s, and you under the "
             "bar (your trunk upright: the cosine of its tilt at least {upright_cos}; the bar's centre no more than "
             "{bar_centre_m} m, horizontally, from the point midway between your shoulder joints; the bar, seen from "
             "above, within {bar_align_deg} degrees of the line through them), with the attempt begun (the bar has "
             "been above knee height and touches nothing but you), all of it without a "
             "break for {clean_hold_s} s. You fail if the bar's axis is more than {overhead_m} m above the centre of "
             "your head before that (a lift from the platform to overhead in one movement is a snatch). "
             "The jerk and the finish: after the clean, bring the bar overhead. The final position is: the bar's axis "
             "at least {overhead_m} m above the centre of your head, both hands on it, both elbows within "
             "{elbow_lock_deg} degrees of straight (the angle between the upper arm's and the forearm's long axes), "
             "both knees within {knee_lock_deg} degrees of straight (the angle hip, knee, ankle), both feet on the "
             "platform and on one line (their centres no more than {feet_line_m} m apart along the horizontal "
             "direction square to the bar; under a bar tilted more than {bar_tilt_max_deg} degrees from level the "
             "feet never count as on one line), the bar and your pelvis slower than {still_m_s} m/s, and you under "
             "the bar as in the clean (trunk upright, the bar's centre over the middle of your shoulders, the bar "
             "along your shoulder line). Once it is held "
             "for {hold_s} s without a break the down signal is given: that is success, and the attempt ends. "
             "At any time you fail if a part of you other than your feet touches the platform, if any part of you or "
             "of the barbell touches the floor beside the platform, or after {time_limit_s} s. There is no other fall "
             "rule: you may squat as low as you like, and the bar may touch your body.")
    venue = ("You stand upright in the middle of the platform, facing +x, your soles {platform_height_m} m above the "
             "floor, in the rest pose (upper arms down, forearms forward). The barbell lies on the platform across "
             "your front, parallel to your shoulders and centred on you: its axis is {bar_ahead_m} m ahead of your "
             "pelvis and 0.225 m above the platform (above your feet, just clear of your shins), the discs 0.69 m "
             "to each side of its middle. Your shoulder joints are 1.46 m above the platform when you stand, 0.30 m "
             "apart; the centre of your head is at 1.70 m, its top at 1.79 m; your knee joints are at 0.48 m. In "
             "the `stand` action's stance your knees are bent by about 21 degrees, and your elbows are at a right "
             "angle in the rest pose: neither is extended. Your elbow joints have no stop at the straight arm (they "
             "bend both ways from it). The platform's edges are 2 m away in every direction.")
    difficulty = ("The barbell weighs two thirds of the robot: held at the shoulders it asks about twice the torque "
                  "the elbow motors give (18 N m), so the arms cannot simply carry it there. Nothing balances the "
                  "robot under a load, and no built-in action bends down to the bar or straightens the knees.")

    # ------------------------------------------------------------------ the venue
    def build(self, sc):
        p = self.p
        H, S = p["platform_height_m"], p["platform_size_m"] / 2
        r_grip, r_sleeve, r_disc = p["grip_diameter_m"] / 2, p["sleeve_diameter_m"] / 2, p["disc_diameter_m"] / 2
        half_grip, half = p["grip_length_m"] / 2, p["bar_length_m"] / 2
        total = p["bar_mass_kg"] + 2 * p["disc_mass_kg"] + 2 * p["collar_mass_kg"]
        if abs(total - p["total_mass_kg"]) > 1e-6:
            raise ValueError(f"clean-and-jerk: total_mass_kg must be the bar, two discs and two collars ({total:g} kg)")
        if abs(half - (half_grip + FLANGE_M + p["sleeve_length_m"])) > 1e-6:
            raise ValueError("clean-and-jerk: bar_length_m must be the grip section, two 0.03 m flanges and two sleeves")
        sc.platform("platform", (0.0, 0.0), (S, S, H / 2), rgba=(0.72, 0.60, 0.42, 1))
        # The H1-2's feet are convex hulls: against a box MuJoCo gives a hull one contact point unless multi-point
        # convex contacts are on (with one point a foot sinks 5 cm into the platform and slides); on the floor's plane
        # it gets several by itself.
        opt = sc.root.find("option")
        flag = opt.find("flag") if opt.find("flag") is not None else ET.SubElement(opt, "flag")
        flag.set("multiccd", "enable")
        self.rest = np.array([p["bar_ahead_m"], 0.0, H + r_disc])
        self.rest_z = float(self.rest[2])
        steel, kw = (0.78, 0.78, 0.80, 1), dict(friction=(0.8, 0.005, 0.0001), **HITTABLE)
        b = sc.body("bar", tuple(self.rest), free=True)
        sc.geom(b, "bar_shaft", type="cylinder", fromto=(0, -half_grip, 0, 0, half_grip, 0), size=(r_grip,),
                mass=SHAFT_KG, rgba=steel, **kw)
        split = p["bar_mass_kg"] - SHAFT_KG
        for s, tag in ((1, "L"), (-1, "R")):
            y0 = half_grip                                   # the sleeve assembly, on a hinge about the bar's axis
            sl = sc.body(f"bar_sleeve{tag}", (0.0, s * y0, 0.0), parent=b)
            ET.SubElement(sl, "joint", name=f"bar_sleeve{tag}", type="hinge", axis="0 1 0", damping="0.002",
                          armature="0.0005")
            sc.geom(sl, f"bar_flange{tag}", type="cylinder", fromto=(0, 0, 0, 0, s * FLANGE_M, 0), size=(0.04,),
                    mass=0.5, rgba=steel, **kw)
            sc.geom(sl, f"bar_sleeve{tag}", type="cylinder", fromto=(0, s * FLANGE_M, 0, 0, s * (half - y0), 0),
                    size=(r_sleeve,), mass=split / 2 - 0.5, rgba=steel, **kw)
            y1 = FLANGE_M + DISC_W_M
            sc.geom(sl, f"bar_disc{tag}", type="cylinder", fromto=(0, s * FLANGE_M, 0, 0, s * y1, 0), size=(r_disc,),
                    mass=p["disc_mass_kg"], rgba=(0.10, 0.55, 0.22, 1), priority=1, solref=bounce_solref(BUMPER_BOUNCE),
                    friction=(0.9, 0.005, 0.0005), **HITTABLE)
            sc.geom(sl, f"bar_collar{tag}", type="cylinder", fromto=(0, s * y1, 0, 0, s * (y1 + COLLAR_W_M), 0),
                    size=(COLLAR_R_M,), mass=p["collar_mass_kg"], rgba=(0.55, 0.55, 0.58, 1), **kw)
        sc.grippables["bar"] = {"radius": r_grip, "half_length": half_grip, "axis": "y"}
        sc.camera("venue", (3.3, -3.0, 1.9), (0.1, 0.0, 0.95), fovy=50)

    def reset(self, w):
        w.d.qpos[w.robot.fq + 2] += self.p["platform_height_m"]      # the robot stands on the platform
        w.put("bar", self.rest)

    # ------------------------------------------------------------------ what the referee measures
    def bar_state(self, w):
        """(the bar's centre, the unit vector along its axis, its speed)."""
        b = self._bar
        return w.d.xpos[b].copy(), w.d.xmat[b].reshape(3, 3)[:, 1].copy(), float(np.linalg.norm(w.vel("bar")))

    def rack_distance(self, w):
        """The larger of the two shoulder joints' distances from the bar's axis (m)."""
        c, a, _ = self.bar_state(w)
        out = 0.0
        for s in SIDES:
            v = w.d.xpos[self._shoulder[s]] - c
            out = max(out, float(np.linalg.norm(v - (v @ a) * a)))
        return out

    def under_the_bar(self, w) -> bool:
        """The lifter stands under the bar: the trunk upright, the bar's centre over the middle of the shoulders, the
        bar along the shoulder line (seen from above)."""
        p = self.p
        c, a, _ = self.bar_state(w)
        sl, sr = (w.d.xpos[self._shoulder[s]] for s in SIDES)
        mid, line = (sl + sr) / 2, (sl - sr)[:2]
        ah = a[:2]
        n = float(np.linalg.norm(line) * np.linalg.norm(ah))
        along = n > 1e-9 and abs(float(line @ ah)) / n >= math.cos(math.radians(p["bar_align_deg"]))
        return bool(w.upright() >= p["upright_cos"] and along
                    and float(np.linalg.norm((c - mid)[:2])) <= p["bar_centre_m"])

    def elbow_flex_deg(self, w, side):
        """The angle between the upper arm's and the forearm's long axes (0: a straight arm), degrees. The axes are the
        shoulder yaw joint's and the elbow roll joint's, each taken pointing towards the hand."""
        d = w.d
        yaw, pitch, roll, wrist = self._arm_joints[side]
        up, fore = d.xaxis[yaw], d.xaxis[roll]
        if float(up @ (d.xanchor[pitch] - d.xanchor[yaw])) < 0:
            up = -up
        if float(fore @ (d.xanchor[wrist] - d.xanchor[roll])) < 0:
            fore = -fore
        return math.degrees(math.acos(float(np.clip(up @ fore, -1.0, 1.0))))

    def knee_flex_deg(self, w, side):
        """180 degrees less the angle hip, knee, ankle (0: a straight leg)."""
        hip, knee, ankle = (w.d.xpos[b] for b in self._leg[side])
        u, v = hip - knee, ankle - knee
        c = float(u @ v) / (float(np.linalg.norm(u)) * float(np.linalg.norm(v)))
        return 180.0 - math.degrees(math.acos(float(np.clip(c, -1.0, 1.0))))

    def feet_offset_m(self, w):
        """How far the feet's centres are apart along the horizontal direction square to the bar (m)."""
        _, a, _ = self.bar_state(w)
        h = math.hypot(a[0], a[1])
        if h < math.cos(math.radians(self.p["bar_tilt_max_deg"])):   # a bar far from level has no such direction
            return float("inf")
        n = np.array([-a[1], a[0]]) / h
        d = w.d.site_xpos[w.robot.foot_site["left"]][:2] - w.d.site_xpos[w.robot.foot_site["right"]][:2]
        return abs(float(d @ n))

    def head_z(self, w):
        return float(w.d.site_xpos[w.robot.head_site][2])

    def referee_reset(self, w, ref):
        m = w.m
        self._bar = m.body("bar").id
        self._shoulder = {s: m.body(f"{s}_shoulder_pitch_link").id for s in SIDES}
        self._leg = {s: tuple(m.body(f"{s}_{n}").id for n in ("hip_pitch_link", "knee_link", "ankle_pitch_link"))
                     for s in SIDES}
        self._arm_joints = {s: tuple(m.joint(f"{s}_{n}_joint").id for n in
                                     ("shoulder_yaw", "elbow_pitch", "elbow_roll", "wrist_pitch")) for s in SIDES}
        self.platform = ref.geoms(names=["platform"])
        self.floor = ref.geoms(names=["floor"])
        self.bar_g = ref.geoms(body="bar")
        self.robot = ref.part("robot")
        self.foot = {s: ref.part(f"{s}_foot") for s in SIDES}
        self.not_feet = self.robot & ~ref.part("feet")
        self.trackers = {"attempt": False, "max_height_m": 0.0}

    # ------------------------------------------------------------------ the referee
    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        if ref.touching(self.robot, self.floor):
            return ref.fail("left the platform", parts=sorted(ref.parts_touching(self.floor)))
        if ref.touching(self.bar_g, self.floor):
            return ref.fail("the barbell left the platform")
        if ref.touching(self.not_feet, self.platform):
            return ref.fail("touched the platform with a part other than the feet",
                            parts=sorted(ref.parts_touching(self.platform) - {"left_foot", "right_foot"}))
        z = float(w.d.xpos[self._bar][2])
        hands = len(w.holder("bar"))
        if tr["attempt"]:
            if hands < 2:
                return ref.fail("let go of the bar", holding=w.holder("bar"))
            if ref.touching(self.bar_g, self.platform):
                return ref.fail("the bar came down before the down signal")
        elif z > self.rest_z + p["lift_tolerance_m"]:
            if hands < 2:
                return ref.fail("the bar left the platform without both hands on it", holding=w.holder("bar"))
            ref.stage("lift-off")
            if z >= p["platform_height_m"] + p["knee_height_m"]:
                tr["attempt"] = True
                ref.event("attempt", bar_height_m=round(z - p["platform_height_m"], 3))

    def final_checks(self, w, ref) -> dict:
        """Every condition of the motionless positions, by name (the clean's and the finish's share most of them)."""
        p = self.p
        c, _, v_bar = self.bar_state(w)
        v_pelvis = float(np.linalg.norm(w.d.qvel[w.robot.fv:w.robot.fv + 3]))
        return {
            "both hands": len(w.holder("bar")) == 2,
            "knees": max(self.knee_flex_deg(w, s) for s in SIDES) <= p["knee_lock_deg"],
            "elbows": max(self.elbow_flex_deg(w, s) for s in SIDES) <= p["elbow_lock_deg"],
            "feet on the platform": all(ref.touching(self.foot[s], self.platform) for s in SIDES),
            "feet in line": self.feet_offset_m(w) <= p["feet_line_m"],
            "motionless": v_bar <= p["still_m_s"] and v_pelvis <= p["still_m_s"],
            "at the shoulders": self.rack_distance(w) <= p["clean_rack_m"],
            "overhead": float(c[2]) >= self.head_z(w) + p["overhead_m"],
            "under the bar": self.under_the_bar(w),
        }

    def step(self, w, ref):
        p, tr = self.p, self.trackers
        if ref.failed:
            return
        ok = self.final_checks(w, ref)
        h = float(w.d.xpos[self._bar][2]) - p["platform_height_m"]
        tr["max_height_m"] = max(tr["max_height_m"], round(h, 3))
        ref.metrics["bar_height_m"] = round(h, 3)
        ref.metrics["bar_max_height_m"] = tr["max_height_m"]
        ref.metrics["elbow_flex_deg"] = round(max(self.elbow_flex_deg(w, s) for s in SIDES), 1)
        ref.metrics["knee_flex_deg"] = round(max(self.knee_flex_deg(w, s) for s in SIDES), 1)
        common = (ok["both hands"] and ok["knees"] and ok["feet on the platform"] and ok["feet in line"]
                  and ok["motionless"] and ok["under the bar"])
        if not ref.has("clean"):
            if ok["overhead"]:
                return ref.fail("the bar went overhead without a clean", bar_height_m=round(h, 3))
            if ref.hold("clean", ref.has("lift-off") and tr["attempt"] and common and ok["at the shoulders"],
                        p["clean_hold_s"]):
                ref.stage("clean", shoulder_distance_m=round(self.rack_distance(w), 3))
            return
        final = common and ok["overhead"] and ok["elbows"]
        if ok["overhead"] and ok["elbows"] and ok["both hands"]:
            ref.stage("overhead", bar_height_m=round(h, 3))
        if ref.hold("final", final, p["hold_s"]) and ref.has("overhead"):
            if ref.stage("down signal"):
                ref.metrics["time_s"] = round(w.t, 2)
                ref.succeed()

    def privileged(self, w):
        c, a, v = self.bar_state(w)
        return {"bar_centre": c.tolist(), "bar_axis": a.tolist(), "bar_speed_m_s": v, "bar_rest": self.rest.tolist(),
                "held_by": w.holder("bar"), "shoulder_distance_m": self.rack_distance(w),
                "elbow_flex_deg": [self.elbow_flex_deg(w, s) for s in SIDES],
                "knee_flex_deg": [self.knee_flex_deg(w, s) for s in SIDES],
                "feet_offset_m": self.feet_offset_m(w), "head_centre_z": self.head_z(w),
                "attempt": bool(self.trackers.get("attempt", False)), "platform_top_z": self.p["platform_height_m"]}
