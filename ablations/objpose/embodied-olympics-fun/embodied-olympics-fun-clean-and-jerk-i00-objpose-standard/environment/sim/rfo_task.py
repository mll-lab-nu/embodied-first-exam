"""Clean and jerk (IWF): a 5 kg aluminium technique bar from lifting blocks to the shoulders, then to locked arms
overhead, held motionless there until the referee's "down" signal. Nothing is welded: the hands are the H1-2's own
Inspire five-finger hands (rfo/realhand.py, "inspire": six self-locking drives, the fingers moving), open at the
start, at the device's forces; the bar (a free body: the shaft and two revolving sleeves with their inner collars) is
held only by the contact and friction of the fingers and palms closed round its 25 mm grip section, and can slip,
turn in the hands and drop.

The load (a deviation): American Barbell's ATB-5-E aluminium technique bar, 5 kg (49 N), 1.835 m, 25 mm
(ironcompany.com / americanbarbell.com listing: aluminium shaft and sleeves, 25 mm, 1835 mm), resting by its sleeves
on two lifting blocks 0.35 m high, which put its axis 0.375 m above the platform (a competition bar on its 0.45 m
discs lies at 0.225 m). The IWF's women's bar is 15 kg and the lightest competition barbell 21 kg (IWF TCRR 2020).

The blocks (a deviation; a block clean & jerk is a standard training form, its reason in the deviations): on its
inner collars the bar's axis would be 0.04 m above the platform.

The hold: each Inspire hand holds a 25 mm bar against about 73 N pulled along its fingers and about 92 N out of the
palm before the bar moves 2 cm in the hand (measured with the hand alone at the device's forces).

The hold's other surfaces: the bar touches every collision geom of the robot (it may rest on the trunk, as in a front
rack); the fingers' pads win the contact parameters on it (priority 2, friction 1.0, realhand.py)."""
import math
import xml.etree.ElementTree as ET

import numpy as np

from rfo.scene import HITTABLE, bounce_solref
from rfo.task import TaskBase
# A rigid barbell's steel (shaft, sleeves, collars; the bumper discs keep their bounce)'s contact with the robot, the
# venue's fixtures and the other props (the ground keeps its own: rfo/world.py GROUND_SOLMIX): the stiff contact of
# the core's shells (rfo/world.py SHELL_CONTACT: solref 0.004 s, solimp 0.99 0.999 0.0005, from roboolympics'
# weightlifting fix, a rigid prop on the robot's aluminium) with a solmix that wins over a default-contact geom; a
# ball (priority 1) keeps its own bounce. With MuJoCo's default soft contact (solref 0.02 1, solimp 0.9 0.95) it sank
# 36 mm into the platform (stress test).
from rfo.world import SHELL_CONTACT as RIGID  # noqa: E402

# What the bar's maker does not give (estimates, stated in `deviations`): how the technique bar's 5 kg is split between
# the shaft (a 25 mm x 1.31 m aluminium rod: 1.74 kg) and the two revolving sleeves with their inner collars (flanges,
# 0.08 m across, 0.03 m wide), the width of a disc and of a collar, the bumpers' bounce on the platform.
FLANGE_M, FLANGE_R_M, DISC_W_M, COLLAR_W_M, COLLAR_R_M = 0.030, 0.040, 0.034, 0.070, 0.045
BUMPER_BOUNCE = 0.4
SIDES = ("left", "right")


class Task(TaskBase):
    name = "clean-and-jerk"
    title = "Weightlifting: clean and jerk"
    category = "parkour-apparatus-balance"
    robot = "unitree_h1"
    rulebook = ("IWF Technical and Competition Rules & Regulations (International Weightlifting Federation; 2020 "
                "edition, article numbers quoted from memory of the 2020s editions): 2.3 the clean and jerk, 2.5 "
                "incorrect movements, 3.1 the platform, 3.3 the barbell (the women's bar: 15 kg, 2.01 m, a 25 mm grip "
                "section 1.31 m long, sleeves 50 mm thick; collars 2.5 kg; the lightest barbell in competition, "
                "women: 21 kg = the bar, two collars and two 0.5 kg discs)")
    deviations = [
        "3.3 (the barbell): the barbell is an aluminium technique bar, American Barbell's ATB-5-E (5 kg, 1.835 m, "
        "a 25 mm grip section 1.31 m long as the women's bar's, sleeves 50 mm thick), training equipment, not a "
        "competition barbell (the women's bar is 15 kg, the lightest competition barbell {min_load_kg} kg), without "
        "collars or discs. The reason is the robot's arms: with the women's 15 kg bar the turnover from the hang to "
        "the shoulders asks 1.08 to 1.17 times what the elbow and shoulder motors give, and with 10 kg the robot "
        "topples at the turnover, so neither a heavier bar nor a faster turnover is open. There is no choice of "
        "weight and no progression of attempts, because the task is one attempt",
        "3.1 and 3.3 (the bar on the platform, on its discs): the bar rests by its sleeves on two lifting blocks "
        "{block_height_m} m high (a block clean & jerk, a standard training form), so that its axis is 0.375 m above "
        "the platform; a competition bar on its 0.45 m discs lies at 0.225 m, but the squat to that height is out of "
        "the robot's reach: its hips would have to flex past where the hip links meet the pelvis (the robot's own "
        "body collides with itself), and every squat tried fell back onto a thigh. Without discs or blocks the bar "
        "would lie on its inner collars 0.04 m above the platform, where the hands' "
        "curled fingers cannot close round it without touching the platform",
        "3.3 (what the maker does not give): the bar's {bar_mass_kg} kg are split {shaft_mass_kg} kg for the shaft "
        "and the rest between the two revolving sleeves with their inner collars (0.08 m across, 0.03 m wide); "
        "these are estimates",
        "3.3 (the grip): each hand is the H1-2's own Inspire five-finger hand (six self-locking drives; 20 N at each "
        "fingertip, 30 N at the thumb), open at the start; it holds the bar by its fingers' and palm's contact and "
        "friction alone (nothing is welded; no chalk, no hook grip with the thumb under the fingers), and the bar "
        "can slip, turn in the hand and drop. A hand holds the bar while the grip section touches that hand's "
        "fingers (closed round it; a break of up to {off_bar_s} s, the contact flickering under a load, is not "
        "letting go)",
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
                  bar_mass_kg=5.0, bar_length_m=1.835, grip_diameter_m=0.025, grip_length_m=1.31,
                  sleeve_diameter_m=0.050, sleeve_length_m=0.2325, shaft_mass_kg=1.74, disc_mass_kg=0.0,
                  disc_diameter_m=0.45, collar_mass_kg=0.0, total_mass_kg=5.0, min_load_kg=21.0, bar_ahead_m=0.20,
                  lift_tolerance_m=0.03, knee_height_m=0.48, clean_rack_m=0.15, clean_hold_s=0.5, overhead_m=0.25,
                  elbow_lock_deg=10.0, knee_lock_deg=10.0, feet_line_m=0.05, bar_tilt_max_deg=60.0, still_m_s=0.10,
                  upright_cos=0.94, bar_centre_m=0.25, bar_align_deg=20.0,
                  hold_s=2.0, off_bar_s=0.05, block_height_m=0.35, block_y_m=0.80)

    sentence = ("Clean and jerk the barbell: lift it from its blocks to your shoulders, then to locked arms "
                "overhead, and hold it there motionless until the down signal.")
    rules = ("The barbell is an aluminium technique bar ({bar_mass_kg} kg, {bar_length_m} m long; the grip section "
             "between the inner collars is {grip_length_m} m long and {grip_diameter_m} m thick; the sleeves are "
             "{sleeve_length_m} m long and {sleeve_diameter_m} m thick and revolve on the bar), without discs or "
             "collars: {total_mass_kg} kg. It rests by its sleeves "
             "on two lifting blocks ({block_height_m} m high) standing on the competition platform "
             "({platform_size_m} m by {platform_size_m} m, {platform_height_m} m high), on which you stand. Your "
             "hands are five-finger hands, open at the start; a hand holds the bar while the bar's grip section "
             "touches that hand's fingers (a break of up to {off_bar_s} s is not letting go); they hold it by "
             "contact and friction only, so it can slip, turn in the hands and drop. "
             "Lift-off: the bar may leave its blocks only in both hands: you fail the moment the bar's axis is more "
             "than {lift_tolerance_m} m above where it lies at rest while fewer than two hands hold it. "
             "The attempt: once the bar's centre has been {knee_height_m} m above the platform (knee height) the lift "
             "must be finished: from then on you fail if either hand lets go or if any part of the barbell touches the "
             "platform or a block before the down signal. "
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
             "At any time you fail if a part of you other than your feet touches the platform, if any part of you "
             "touches a block, if any part of you or "
             "of the barbell touches the floor beside the platform, or after {time_limit_s} s. There is no other fall "
             "rule: you may squat as low as you like, and the bar may touch your body.")
    venue = ("You stand upright in the middle of the platform, facing +x, your soles {platform_height_m} m above the "
             "floor, in the rest pose (upper arms down, forearms forward). The barbell lies across your front, "
             "parallel to your shoulders and centred on you, its sleeves on two blocks (0.30 m along x, 0.20 m along "
             "y, {block_height_m} m high, centred {block_y_m} m to either side of you): its axis is {bar_ahead_m} m "
             "ahead of your pelvis and 0.375 m above the platform, just beyond your toes (they reach 0.164 m ahead of "
             "your pelvis). Your shoulder joints are "
             "1.46 m above the platform when you stand, 0.30 m apart; the centre of your head is at 1.70 m, its "
             "top at 1.79 m; your knee joints are at 0.48 m. In "
             "the `stand` action's stance your knees are bent by about 21 degrees, and your elbows are at a right "
             "angle in the rest pose: neither is extended. Your elbow joints have no stop at the straight arm (they "
             "bend both ways from it). Both hands are open (grip values 0): a grip value is that hand's closure "
             "command (0 open, the fingers straight; 1 every finger and the thumb closing; a finger stops on what it "
             "touches). The barbell is a free body: `held` in your state says which hand grasps it with its fingers "
             "and its thumb or palm. The platform's edges are 2 m away in every direction.")
    difficulty = ("The bar is light, but the hands hold it only by their fingers' friction. Turning it over from "
                  "the hang to the shoulders, slowly, asks about half of what the elbow and shoulder motors give; too "
                  "fast, and the bar slides out of the hands. Nothing balances the robot under a load, and no built-in action bends "
                  "down to the bar or straightens the knees.")

    # ------------------------------------------------------------------ the venue
    def build(self, sc):
        p = self.p
        H, S = p["platform_height_m"], p["platform_size_m"] / 2
        r_grip, r_sleeve, r_disc = p["grip_diameter_m"] / 2, p["sleeve_diameter_m"] / 2, p["disc_diameter_m"] / 2
        half_grip, half = p["grip_length_m"] / 2, p["bar_length_m"] / 2
        total = p["bar_mass_kg"] + 2 * p["disc_mass_kg"] + 2 * p["collar_mass_kg"]
        if abs(total - p["total_mass_kg"]) > 1e-6:
            raise ValueError(f"clean-and-jerk: total_mass_kg must be the bar, two discs and two collars ({total:g} kg)")
        loaded = [(p["disc_mass_kg"], r_disc), (p["collar_mass_kg"], COLLAR_R_M)]
        if abs(half - (half_grip + FLANGE_M + p["sleeve_length_m"])) > 1e-6:
            raise ValueError("clean-and-jerk: bar_length_m must be the grip section, two 0.03 m flanges and two sleeves")
        sc.platform("platform", (0.0, 0.0), (S, S, H / 2), rgba=(0.72, 0.60, 0.42, 1))
        # The H1-2's feet are convex hulls: against a box MuJoCo gives a hull one contact point unless multi-point
        # convex contacts are on (with one point a foot sinks 5 cm into the platform and slides); on the floor's plane
        # it gets several by itself.
        opt = sc.root.find("option")
        flag = opt.find("flag") if opt.find("flag") is not None else ET.SubElement(opt, "flag")
        flag.set("multiccd", "enable")
        r_rest = max([FLANGE_R_M, r_sleeve] + [r for mass, r in loaded if mass > 0])    # what it lies on
        bh = p["block_height_m"]
        if bh > 0:                                           # lifting blocks under the sleeves: the bar's axis at the
            r_rest = r_sleeve                                # blocks' height + the sleeve's radius (0.375 m on 0.35 m)
            for s, tag in ((1, "L"), (-1, "R")):
                sc.box(f"block{tag}", (p["bar_ahead_m"], s * p["block_y_m"], H + bh / 2), (0.15, 0.10, bh / 2),
                       rgba=(0.55, 0.38, 0.22, 1), solid="hit", friction=(0.8, 0.005, 0.001), **RIGID)
        self.rest = np.array([p["bar_ahead_m"], 0.0, H + bh + r_rest])
        self.rest_z = float(self.rest[2])
        steel, kw = (0.78, 0.78, 0.80, 1), dict(friction=(0.8, 0.005, 0.0001), **HITTABLE, **RIGID)
        b = sc.body("bar", tuple(self.rest), free=True)
        sc.geom(b, "bar_shaft", type="cylinder", fromto=(0, -half_grip, 0, 0, half_grip, 0), size=(r_grip,),
                mass=p["shaft_mass_kg"], rgba=steel, **kw)
        split = p["bar_mass_kg"] - p["shaft_mass_kg"]
        for s, tag in ((1, "L"), (-1, "R")):
            y0 = half_grip                                   # the sleeve assembly, on a hinge about the bar's axis
            sl = sc.body(f"bar_sleeve{tag}", (0.0, s * y0, 0.0), parent=b)
            ET.SubElement(sl, "joint", name=f"bar_sleeve{tag}", type="hinge", axis="0 1 0", damping="0.002",
                          armature="0.0005")
            # the inner collar, on which the bar alone lies: rolling resistance of steel on the hardwood platform,
            # about 1 mm (engineering tables: steel on wood 0.0005-0.0015 m; condim 6 so that it applies)
            sc.geom(sl, f"bar_flange{tag}", type="cylinder", fromto=(0, 0, 0, 0, s * FLANGE_M, 0), size=(FLANGE_R_M,),
                    mass=0.5, rgba=steel, condim="6", **dict(kw, friction=(0.8, 0.005, 0.001)))
            sc.geom(sl, f"bar_sleeve{tag}", type="cylinder", fromto=(0, s * FLANGE_M, 0, 0, s * (half - y0), 0),
                    size=(r_sleeve,), mass=split / 2 - 0.5, rgba=steel, **kw)
            y1 = FLANGE_M + (DISC_W_M if p["disc_mass_kg"] > 0 else 0.0)
            if p["disc_mass_kg"] > 0:                        # (none on the women's bar alone)
                sc.geom(sl, f"bar_disc{tag}", type="cylinder", fromto=(0, s * FLANGE_M, 0, 0, s * y1, 0),
                        size=(r_disc,), mass=p["disc_mass_kg"], rgba=(0.10, 0.55, 0.22, 1), priority=1,
                        solref=bounce_solref(BUMPER_BOUNCE), friction=(0.9, 0.005, 0.0005), **HITTABLE)
            if p["collar_mass_kg"] > 0:
                sc.geom(sl, f"bar_collar{tag}", type="cylinder", fromto=(0, s * y1, 0, 0, s * (y1 + COLLAR_W_M), 0),
                        size=(COLLAR_R_M,), mass=p["collar_mass_kg"], rgba=(0.55, 0.55, 0.58, 1), **kw)
        for side in SIDES:                                   # the hands: the H1-2's Inspire hands (rfo.realhand), no weld
            sc.real_hands[side] = "inspire"
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
        self.blocks = ref.geoms(prefix="block")
        self.floor = ref.geoms(names=["floor"])
        self.bar_g = ref.geoms(body="bar")
        self.grip_g = ref.geoms(names=["bar_shaft"])
        ng = m.ngeom
        self.fingers = {s: np.isin(np.arange(ng), w.hands.group_geoms(w, s, "fingers")) for s in SIDES}
        self.robot = ref.part("robot")
        self.foot = {s: ref.part(f"{s}_foot") for s in SIDES}
        self.not_feet = self.robot & ~ref.part("feet")
        self.trackers = {"attempt": False, "max_height_m": 0.0, "on_t": {s: None for s in SIDES}}

    def hands_on(self, w) -> list:
        """The hands that hold the bar: the grip section touching the hand's fingers now, or within the last
        off_bar_s."""
        on = self.trackers["on_t"]
        return [s for s in SIDES if on[s] is not None and w.ref.time - on[s] <= self.p["off_bar_s"] + 1e-9]

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
        if ref.touching(self.robot, self.blocks):
            return ref.fail("touched a lifting block", parts=sorted(ref.parts_touching(self.blocks)))
        z = float(w.d.xpos[self._bar][2])
        for s in SIDES:
            if ref.touching(self.grip_g, self.fingers[s]):    # a hand holds the bar: its fingers round the grip section
                tr["on_t"][s] = round(ref.time, 4)
        hands = len(self.hands_on(w))
        if tr["attempt"]:
            if hands < 2:
                return ref.fail("let go of the bar", holding=self.hands_on(w))
            if ref.touching(self.bar_g, self.platform | self.blocks):
                return ref.fail("the bar came down before the down signal")
        elif z > self.rest_z + p["lift_tolerance_m"]:
            if hands < 2:
                return ref.fail("the bar left the platform without both hands on it", holding=self.hands_on(w))
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
            "both hands": len(self.hands_on(w)) == 2,
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
                "held_by": w.holder("bar"), "hands_on": self.hands_on(w), "shoulder_distance_m": self.rack_distance(w),
                "elbow_flex_deg": [self.elbow_flex_deg(w, s) for s in SIDES],
                "knee_flex_deg": [self.knee_flex_deg(w, s) for s in SIDES],
                "feet_offset_m": self.feet_offset_m(w), "head_centre_z": self.head_z(w),
                "attempt": bool(self.trackers.get("attempt", False)), "platform_top_z": self.p["platform_height_m"]}
