"""Pole vault (World Athletics TR 28): the sunken box, a 4.5 m bar on pegs between uprights 4.3 m apart, the
5 m x 5 m x 0.8 m landing mat; the pole planted in the box, over the bar, and the bar stays on. The pole is rigid."""
import math
import xml.etree.ElementTree as ET

import numpy as np

import mujoco

from rfo.referee import Flights
from rfo.task import TaskBase

SIDES = ("left", "right")
STEEL = (0.3, 0.3, 0.33, 1)
POLE_ONLY = dict(contype="2", conaffinity="2")           # what only the pole (and the bar) touches: the box, its ground
# The box (TR 28.8), in the vertical plane of the runway's middle: the bottom is 1.00 m long and slopes from the
# runway's level at the front down to 0.20 m below it at the stop board; the stop board stands at 105 degrees to the
# bottom, so it leans towards the landing area and its top inside edge (the "zero line", x = 0) is 0.10 m beyond its
# foot; the box is 0.60 m wide at the front and 0.15 m at the foot of the stop board, its sides slope outwards
# (about 120 degrees to the bottom).
BOX_DEPTH = 0.20
BOX_FOOT_X = -BOX_DEPTH / math.tan(math.radians(180.0 - 105.0 - math.degrees(math.asin(BOX_DEPTH))))   # -0.0999 m
BOX_FRONT_X = BOX_FOOT_X - math.sqrt(1.0 - BOX_DEPTH ** 2)                                      # -1.0797 m
BOX_HALF_FRONT, BOX_HALF_FOOT = 0.30, 0.075
BOX_HALF_TOP = BOX_HALF_FOOT + BOX_DEPTH * math.tan(math.radians(30.0))                         # 0.19 m at the zero line
PAD = (-1.30, 0.30, 0.60)        # the ground cut out for the box pieces: x from, x to, half width


def _mesh(sc, name, pts):
    ET.SubElement(sc.root.find("asset"), "mesh", name=name, vertex=" ".join(f"{v:.6g}" for q in pts for v in q))
    sc.geom(sc.wb, name, type="mesh", mesh=name, rgba=(0.55, 0.57, 0.6, 1), friction=(0.5, 0.005, 0.0001), **POLE_ONLY)
    return name


def vault_box(sc):
    """The sunken box, and level ground around it, for the pole alone: the core's floor plane has no hole, so the pole
    does not touch that plane; it touches these pieces instead (the robot's feet stand on the plane: for them the box
    is covered). Returns (the box's geoms, the pole's ground geoms)."""
    xf, xb, D, B = BOX_FRONT_X, BOX_FOOT_X, BOX_DEPTH, 0.35
    x0, x1, hw = PAD
    box = [_mesh(sc, "box_bottom", [(xf, s * hw, z) for s in (1, -1) for z in (0.0, -B)]
                 + [(xb, s * hw, z) for s in (1, -1) for z in (-D, -B)]),
           _mesh(sc, "box_stop", [(xb, s * hw, z) for s in (1, -1) for z in (-D, -B)]
                 + [(x, s * hw, z) for s in (1, -1) for x in (0.0, x1) for z in (0.0, -B) if (x, z) != (0.0, -B)])]
    for s, tag in ((1, "L"), (-1, "R")):                 # the sloping side walls
        box.append(_mesh(sc, f"box_side{tag}", [(xf, s * BOX_HALF_FRONT, 0.0), (xb, s * BOX_HALF_FOOT, -D),
                                                (0.0, s * BOX_HALF_TOP, 0.0), (xf, s * BOX_HALF_FRONT, -B),
                                                (xb, s * BOX_HALF_FOOT, -B), (xf, s * hw, 0.0), (0.0, s * hw, 0.0),
                                                (xf, s * hw, -B), (0.0, s * hw, -B)]))
    ground = []
    for name, (a, b, c, d) in {"pole_ground_back": (-60.0, x0, -20.0, 20.0), "pole_ground_far": (x1, 30.0, -20.0, 20.0),
                               "pole_ground_left": (x0, x1, hw, 20.0), "pole_ground_right": (x0, x1, -20.0, -hw),
                               "pole_ground_lip": (x0, xf, -hw, hw)}.items():
        sc.geom(sc.wb, name, type="box", pos=((a + b) / 2, (c + d) / 2, -0.15), size=((b - a) / 2, (d - c) / 2, 0.15),
                rgba=(0, 0, 0, 0), friction=(1.0, 0.005, 0.0001), **POLE_ONLY)
        ground.append(name)
    # what the eye sees of the box (the plane's texture covers it): its outline and its dark inside, painted
    sc.geom(sc.wb, "box_paint", type="box", pos=((xf + 0.0) / 2, 0, 0.0012), size=((0.0 - xf) / 2, BOX_HALF_TOP, 0.0005),
            rgba=(0.25, 0.26, 0.28, 1), contype="0", conaffinity="0")
    sc.line("zero_line", (0.0, -1.0), (0.0, 1.0), width=0.01, z=0.0015)
    return box, ground


def vault_bar(sc, name, x, height, p):
    """The crossbar on its pegs (TR 28.9-28.10): the bar's end pieces rest on two horizontal pegs (55 mm long, 13 mm
    thick; modelled square, not round) that point towards the landing area from the uprights; pushed towards the
    landing area by half a peg's length, or lifted, it falls. `height` is the bar's upper side."""
    r, L, gap, pl, pt = p["bar_diameter_m"] / 2, p["bar_length_m"], p["peg_gap_m"], p["peg_length_m"], p["peg_thickness_m"]
    xp = x - pl / 2                                      # the uprights' face the pegs stick out of
    solid = dict(contype="1", conaffinity="15")          # ... the pole touches them too
    for s, tag in ((1, "L"), (-1, "R")):
        sc.geom(sc.wb, f"{name}_upright{tag}", type="box", pos=(xp - 0.03, s * gap / 2, (height + 0.2) / 2),
                size=(0.03, 0.03, (height + 0.2) / 2), rgba=STEEL, **solid)
        sc.geom(sc.wb, f"{name}_peg{tag}", type="box", pos=(xp + pl / 2, s * gap / 2, height - 2 * r - pt / 2),
                size=(pl / 2, pt / 2, pt / 2), rgba=STEEL, friction=(0.6, 0.005, 0.0001), **solid)
    b = sc.body(name, (x, 0.0, height - r), free=True)
    end, m_end = 0.075, 0.10
    sc.geom(b, name, type="capsule", fromto=(0, -L / 2 + r, 0, 0, L / 2 - r, 0), size=(r,),
            mass=p["bar_mass_kg"] - 2 * m_end, rgba=(0.95, 0.2, 0.2, 1), friction=(0.6, 0.005, 0.0001), **solid)
    for s, tag in ((1, "L"), (-1, "R")):                 # the end pieces: flat undersides on the pegs
        sc.geom(b, f"{name}_end{tag}", type="box", pos=(0, s * (L / 2 - end), 0), size=(r, end, r), mass=m_end,
                rgba=(0.95, 0.95, 0.95, 1), friction=(0.6, 0.005, 0.0001), **solid)
    return dict(x=x, height=height, rest_z=height - r, plane_x=x - r, half_gap=gap / 2)


class Task(TaskBase):
    name = "pole-vault"
    title = "Pole vault"
    category = "track-and-jumps"
    robot = "unitree_h1"
    rulebook = ("World Athletics Competition and Technical Rules, 2024 edition: TR 28 (28.1 the bar may be moved up "
                "to 0.80 m from the zero line towards the landing area; 28.2 failures: (a) the bar does not remain "
                "on both pegs, (b) touching the ground or the landing area beyond the zero line with the body or "
                "the pole without first clearing the bar, (c) moving a hand up the pole after leaving the ground, "
                "(d) steadying the bar with a hand; 28.6 a runway of at least 40 m; 28.8 the box; 28.9-28.10 the "
                "uprights and pegs 4.28 to 4.37 m apart, the 4.50 m bar of at most 2.25 kg; 28.12 a landing area "
                "of at least 5 m x 5 m x 0.8 m with front pieces 2 m long), TR 25.17 (one minute for a trial)")
    deviations = [
        "TR 28.11 (vaulting poles: any material, length and diameter, a smooth surface): the pole is rigid: a "
        "{pole_length_m} m, {pole_mass_kg} kg rod that does not bend and stores no energy (the simulator has no "
        "validated model of a bending pole)",
        "the grip: the robot's hand holds the pole by the benchmark's grip (a weld at the palm, anywhere along the "
        "pole), not by fingers; the pole passes through the robot's own body and is stopped only by the grip",
        "TR 28.8 (the box): it is sunk below the runway as the rule draws it, but only the pole (and the bar) can "
        "enter it; for the robot's feet it is covered at runway level; its side walls are planes",
        "TR 28.2(b), (c), (d) are judged geometrically: any contact of the robot or the pole with the ground or the "
        "mats beyond the zero line before the bar is cleared; a hand that closes on the pole more than {climb_m} m "
        "farther from its tip than the upper hand's grip was at lift-off; a hand on the bar for more than "
        "{bar_hand_s} s in all",
        "a vault is told from a jump by a number: in the flight that clears the bar the robot must hang on the pole "
        "(a hand gripping it, its tip in the box, nothing of the robot on the ground) for at least "
        "{min_support_s} s; the pelvis and the feet (the ankle joints) must pass the bar's plane between the pegs "
        "and above the bar; the bar is cleared when every part of the robot is beyond its plane",
        "TR 28.2(a): the bar is judged {bar_wait_s} s after the landing; it is off its pegs when its centre is more "
        "than {bar_drop_m} m below its resting height; the pegs are square in section, the bar rigid",
        "TR 28.12 (the landing area): the mats are boxes with a soft, overdamped contact (time constant "
        "{mat_timeconst_s} s, full stiffness only {mat_give_m} m deep); the mat's face behind the box slopes away "
        "at 45 degrees as the rule asks, the front pieces' faces beside the box are vertical, and the uprights "
        "stand in the mat without a recess; no wind; one trial at one height, {bar_height_m} m (FAMILIES.md; the "
        "men's world record is 6.30 m)",
        "TR 28.1 (the athlete chooses where the bar stands, 0 to 0.80 m beyond the zero line): it stands "
        "{bar_setback_m} m beyond it",
    ]
    time_limit_s = 60.0
    start = (-10.0, 0.0, 0.0)
    stages = ["plant", "take-off", "clearance", "bar stays"]
    fall_rule = False                # no rule of the event says a fall is a failure; the contacts below judge it
    params = dict(bar_height_m=2.00, bar_setback_m=0.80, bar_length_m=4.50, bar_diameter_m=0.030, bar_mass_kg=2.25,
                  peg_gap_m=4.30, peg_length_m=0.055, peg_thickness_m=0.013, pole_length_m=4.0, pole_mass_kg=2.0,
                  pole_diameter_m=0.040, runway_m=40.0, runway_width_m=1.22, mat_length_m=5.0, mat_width_m=5.0,
                  mat_height_m=0.80, mat_gap_m=0.15, front_piece_m=2.0, mat_timeconst_s=0.08, mat_give_m=0.10,
                  min_support_s=0.15, climb_m=0.05, bar_hand_s=0.10, bar_drop_m=0.05, bar_wait_s=2.0)

    sentence = ("Vault over the bar with the pole you carry: plant its tip in the box, leave the ground hanging on "
                "it, go over the bar between the uprights and come down on the mat, with the bar still on its pegs.")
    rules = ("World Athletics rules for the pole vault. You carry the pole ({pole_length_m} m long, "
             "{pole_diameter_m} m thick, {pole_mass_kg} kg; rigid: it does not bend) gripped in your right hand at "
             "its middle; either hand can grip it anywhere along its length, and it can be let go and gripped "
             "again. The pole touches the ground, the box, the mats, the uprights and the bar, not your body. The "
             "runway ({runway_m} m, {runway_width_m} m wide) leads along +x to the box, which is sunk into the "
             "ground: its bottom is 1.00 m long and slopes down from the runway's level at x = -1.08 m to 0.20 m "
             "below it at the foot of the stop board (x = -0.10 m); the stop board leans back to the zero line "
             "x = 0 at runway level; the box is 0.60 m wide at its front and 0.15 m at the foot of the stop board "
             "(your feet do not sink into it: for them it is covered). The bar ({bar_length_m} m long, "
             "{bar_diameter_m} m thick, {bar_mass_kg} kg) rests with its upper side {bar_height_m} m above the "
             "ground on two pegs ({peg_length_m} m long, {peg_thickness_m} m thick, {peg_gap_m} m apart) that point towards the landing area, "
             "{bar_setback_m} m beyond the zero line; pushed towards the landing area by half a peg's length, or "
             "lifted, it falls. The landing mat ({mat_length_m} m x {mat_width_m} m, {mat_height_m} m high, soft) "
             "begins {mat_gap_m} m beyond the zero line (behind the box its face slopes away at 45 degrees, so the "
             "pole can lean on over it); two front pieces of the same height flank the box for {front_piece_m} m "
             "before it. The vault: (1) plant: the pole's tip is in the box while a hand grips "
             "the pole. (2) take-off: you hang on the planted pole: for at least {min_support_s} s in one flight "
             "nothing of you touches anything but the pole and the bar while a hand grips the pole and its tip rests in the "
             "box. (3) clearance: in that same flight your pelvis and both feet (the ankle joints) cross the plane "
             "of the bar's nearer edge between the pegs and higher than the bar's upper side (one that comes back "
             "over the plane has not passed it), and every part of "
             "you gets beyond that plane; you may touch the bar. (4) You come down, on any part of your body, with "
             "or without the pole. You succeed when {bar_wait_s} s after your landing the bar is still on its "
             "pegs. A fall is not a failure by itself. You fail if the bar drops more than {bar_drop_m} m at any "
             "time, whether you or the pole knocked it; if, before you have cleared the bar, anything of you or the "
             "pole touches the ground or the mats beyond the zero line; if your pelvis or a foot passes the bar's "
             "plane outside the pegs or not higher than the bar; if you clear the bar without the "
             "{min_support_s} s on the planted pole (a jump without the pole); if, in the flight of the vault, a "
             "hand grips the pole more than {climb_m} m farther from its tip than your upper hand did at lift-off "
             "(climbing); if your hands touch the bar for more than {bar_hand_s} s in all (steadying it); or after "
             "{time_limit_s} s (the time allowed for a trial).")
    venue = ("You stand on the runway facing the box (+x), your pelvis 10 m before the zero line, in the middle of "
             "the runway; the runway goes on 30 m behind you. The pole lies level in your right fist, pointing "
             "forward, gripped at its middle. The bar is red with white ends, the uprights grey, the mats blue; "
             "the box is the dark patch at the runway's end, the zero line white.")
    difficulty = ("The bar is 0.2 m above the robot's head: the 67 kg body has to be carried over it hanging on a "
                  "rigid pole that gives nothing back, by arms whose motors hold 18 to 40 N m, from a run-up that "
                  "the robot's only gait makes at 0.7 m/s. Nothing built in grips, plants, swings or lets go.")

    # ------------------------------------------------------------------ the venue
    def build(self, sc):
        p = self.p
        sc.box("runway", (-p["runway_m"] / 2, 0, 0.0003), (p["runway_m"] / 2, p["runway_width_m"] / 2, 0.0003),
               rgba=(0.72, 0.25, 0.18, 1))
        self.box_geoms, self.pole_ground = vault_box(sc)
        self.bar = vault_bar(sc, "bar", p["bar_setback_m"], p["bar_height_m"], p)
        soft = dict(rgba=(0.15, 0.35, 0.75, 1), friction=(1.0, 0.005, 0.0001), solref=(p["mat_timeconst_s"], 1.0),
                    solimp=(0.3, 0.9, p["mat_give_m"], 0.5, 2), priority=1, contype="3", conaffinity="7")
        hz, hw, g = p["mat_height_m"] / 2, p["mat_width_m"] / 2, p["mat_gap_m"]
        y0, x1, Hm = BOX_HALF_FRONT + g, g + p["mat_length_m"], p["mat_height_m"]
        # the mat behind the box: its face towards the box slopes away at 45 degrees (TR 28.12), so that the pole can
        # lean on past vertical; beside it the mat's face is vertical, mat_gap_m beyond the zero line
        ET.SubElement(sc.root.find("asset"), "mesh", name="mat_slope", vertex=" ".join(
            f"{v:.6g}" for q in [(x, s * y0, z) for s in (1, -1) for (x, z) in ((g, 0.0), (g + Hm, 0.0), (g + Hm, Hm))]
            for v in q))
        sc.geom(sc.wb, "mat_slope", type="mesh", mesh="mat_slope", **soft)
        sc.geom(sc.wb, "mat", type="box", pos=((g + Hm + x1) / 2, 0.0, hz), size=((x1 - g - Hm) / 2, y0, hz), **soft)
        for s, tag in ((1, "L"), (-1, "R")):             # ... and the front pieces beside the box, mat_gap_m from its edge
            sc.geom(sc.wb, f"mat_side{tag}", type="box", pos=((g + x1) / 2, s * (y0 + hw) / 2, hz),
                    size=((x1 - g) / 2, (hw - y0) / 2, hz), **soft)
            sc.geom(sc.wb, f"front_piece{tag}", type="box", pos=(g - p["front_piece_m"] / 2, s * (y0 + hw) / 2, hz),
                    size=(p["front_piece_m"] / 2, (hw - y0) / 2, hz), **soft)
        self.mats = ["mat", "mat_slope", "mat_sideL", "mat_sideR", "front_pieceL", "front_pieceR"]
        sc.ground += self.mats
        L, r = p["pole_length_m"], p["pole_diameter_m"] / 2
        b = sc.body("pole", (-8.0, -0.3, 1.0), free=True)            # a rigid rod along its own x axis: the tip is its +x end
        sc.geom(b, "pole", type="capsule", fromto=(-L / 2 + r, 0, 0, L / 2 - r, 0, 0), size=(r,), mass=p["pole_mass_kg"],
                rgba=(0.9, 0.9, 0.95, 1), friction=(1.0, 0.005, 0.0001), priority=1, solref=(0.004, 1.0),
                solimp=(0.95, 0.99, 0.001), **POLE_ONLY)
        sc.geom(b, "pole_tip", type="sphere", pos=(L / 2 - r, 0, 0), size=(r * 1.02,), mass=0.0001,
                rgba=(0.85, 0.15, 0.15, 1), contype="0", conaffinity="0")
        sc.grippables["pole"] = {"radius": r, "half_length": L / 2, "axis": "x"}
        sc.camera("venue", (-6.5, -7.5, 3.2), (-0.5, 0.0, 1.3), fovy=58)
        sc.camera("box", (-3.4, -0.3, 1.5), (-0.5, 0.0, 0.2), fovy=50)

    def reset(self, w):
        p = self.p
        w.put("bar", (self.bar["x"], 0.0, self.bar["rest_z"]))
        mujoco.mj_kinematics(w.m, w.d)                   # the pole level through the right fist, pointing forward
        yaw = self.start[2]
        palm = w.d.site_xpos[w.robot.palm["right"]]
        w.put("pole", palm, quat=(np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)))
        w.grab("right", "pole", event=False)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        m = w.m
        self.points = {"left foot": m.body("left_ankle_roll_link").id, "right foot": m.body("right_ankle_roll_link").id,
                       "pelvis": w.robot.pelvis}
        self.pole_id = m.body("pole").id
        self.pole_mask = ref.geoms(body="pole")
        self.bar_mask = ref.geoms(body="bar")
        self.box_mask = ref.geoms(names=self.box_geoms)
        self.pole_floor = ref.geoms(names=self.pole_ground + self.mats)       # what the pole may not touch beyond x = 0
        self.robot = ref.part("robot")
        self.hands = ref.part("hands")
        # support_s: time on the planted pole in the current flight; grip0: the upper hand's place on the pole at
        # lift-off (m from the tip); hand_bar_s: the hands' time on the bar; crossed: who has passed the bar's plane
        # grip: where each hand grips the pole (m from the tip, taken when it closes; None: not gripping)
        self.trackers = {"flights": Flights(ref, also_allowed=self.bar_mask),
                         "support_s": 0.0, "grip0": None, "grip": {"left": None, "right": None}, "hand_bar_s": 0.0,
                         "crossed": [], "prev": None, "t_clear": None, "t_land": None, "bar_z0": None}

    def tip(self, w) -> np.ndarray:
        """The pole's tip (the centre of its +x end)."""
        R = w.d.xmat[self.pole_id].reshape(3, 3)
        return w.d.xpos[self.pole_id] + R[:, 0] * (self.p["pole_length_m"] / 2)

    def grip_from_tip(self, w, side) -> float:
        """Where a hand is along the pole: the distance of its palm from the tip, measured along the pole."""
        R = w.d.xmat[self.pole_id].reshape(3, 3)
        return float((self.tip(w) - w.d.site_xpos[w.robot.palm[side]]) @ R[:, 0])

    def planted(self, w, ref) -> bool:
        """The pole in the box (touching its bottom, stop board or sides, its tip below the runway's level between
        the box's front and the zero line) while a hand grips it."""
        t = self.tip(w)
        return bool(w.holder("pole") and ref.touching(self.pole_mask, self.box_mask)
                    and BOX_FRONT_X <= t[0] <= 0.02 and t[2] < 0.0 and abs(t[1]) <= BOX_HALF_FRONT)

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        dt = w.m.opt.timestep
        fl = tr["flights"]
        plane, half, H = self.bar["plane_x"], self.bar["half_gap"], p["bar_height_m"]
        if tr["bar_z0"] is None:
            tr["bar_z0"] = float(w.pos("bar")[2])
        if float(w.pos("bar")[2]) < tr["bar_z0"] - p["bar_drop_m"]:
            return ref.fail("the bar did not stay on its pegs")
        if tr["t_land"] is not None:
            return
        if ref.touching(self.hands, self.bar_mask):      # TR 28.2(d)
            tr["hand_bar_s"] = round(tr["hand_bar_s"] + dt, 6)
            if tr["hand_bar_s"] > p["bar_hand_s"]:
                return ref.fail("steadied the bar with a hand", hand_on_bar_s=tr["hand_bar_s"])
        cp = ref.contact_points(self.robot, ref.ground)
        if tr["t_clear"] is not None:                    # cleared: the next contact is the landing
            if len(cp):
                tr["t_land"] = ref.time
                ref.event("landing", parts=sorted(ref.parts_touching(ref.ground)), pole_in_hand=w.holder("pole"),
                          on_the_mat=bool(ref.touching(self.robot, ref.geoms(names=self.mats))))
            return
        fl.update()
        for s in SIDES:                                  # a grip is where the hand is on the pole when it closes (the
            if w.held[s] != "pole":                      # grip's weld gives under load: the palm's place later is not it)
                tr["grip"][s] = None
            elif tr["grip"][s] is None:
                tr["grip"][s] = round(self.grip_from_tip(w, s), 4)
        grips = [tr["grip"][s] for s in SIDES if tr["grip"][s] is not None]
        planted = self.planted(w, ref)
        if planted:
            ref.stage("plant", grip_from_tip_m=grips)
        if not fl.air:
            tr["support_s"], tr["grip0"] = 0.0, None
        else:
            if tr["grip0"] is None and grips:                # lift-off: where the upper hand is on the pole
                tr["grip0"] = max(grips)
            if planted:
                tr["support_s"] = round(tr["support_s"] + dt, 6)
                if tr["support_s"] >= p["min_support_s"]:
                    ref.stage("take-off", support_s=tr["support_s"])
            if grips and max(grips) > tr["grip0"] + p["climb_m"]:        # TR 28.2(c)
                return ref.fail("moved a hand up the pole after leaving the ground", from_tip_m=round(max(grips), 3),
                                at_lift_off_m=round(tr["grip0"], 3))
        if len(cp) and float(cp[:, 0].max()) > 0.0:      # TR 28.2(b): the body
            q = cp[cp[:, 0].argmax()]
            return ref.fail("touched the ground or the mats beyond the zero line before clearing the bar",
                            what=sorted(ref.parts_touching(ref.ground)), at=[round(float(q[0]), 3), round(float(q[1]), 3)])
        pc = ref.contact_points(self.pole_mask, self.pole_floor)
        if len(pc) and float(pc[:, 0].max()) > 0.0:      # TR 28.2(b): the pole
            q = pc[pc[:, 0].argmax()]
            return ref.fail("touched the ground or the mats beyond the zero line before clearing the bar",
                            what=["pole"], at=[round(float(q[0]), 3), round(float(q[1]), 3)])
        pts = {k: [float(x) for x in w.d.xpos[b]] for k, b in self.points.items()}
        prev, tr["prev"] = tr["prev"], pts
        for k, (x1, y1, z1) in pts.items():              # the pelvis or an ankle through the bar's plane: where?
            if prev is None:
                continue
            x0, y0, z0 = prev[k]
            if x1 < plane <= x0 and k in tr["crossed"] and tr["t_clear"] is None:
                tr["crossed"] = [c for c in tr["crossed"] if c != k]       # came back: it has not passed the bar
                continue
            if k in tr["crossed"] or not x0 < plane <= x1:
                continue
            f = (plane - x0) / (x1 - x0)
            y, z = y0 + (y1 - y0) * f, z0 + (z1 - z0) * f
            if abs(y) >= half:
                return ref.fail("went round the bar", what=k, y=round(y, 3))
            if z <= H:
                return ref.fail("passed under the bar", what=k, z=round(z, 3))
            tr["crossed"] = sorted(tr["crossed"] + [k])
        if len(tr["crossed"]) == 3 and ref.robot_span((1.0, 0.0, 0.0))[0] > plane:
            ref.metrics["support_s"] = round(tr["support_s"], 3)
            if not fl.air or tr["support_s"] < p["min_support_s"]:
                return ref.fail("cleared the bar without the pole planted in the box", support_s=tr["support_s"])
            tr["t_clear"] = ref.time
            ref.stage("clearance", support_s=tr["support_s"])

    def step(self, w, ref):
        tr, p = self.trackers, self.p
        if tr["t_land"] is not None and ref.time - tr["t_land"] >= p["bar_wait_s"]:
            if ref.stage("bar stays"):
                ref.succeed()

    def privileged(self, w):
        tr = self.trackers
        return {"pelvis": w.pelvis().tolist(), "pole_centre": w.pos("pole").tolist(), "pole_tip": self.tip(w).tolist(),
                "pole_held_by": w.holder("pole"), "planted": self.planted(w, w.ref), "bar": w.pos("bar").tolist(),
                "bar_top_m": self.p["bar_height_m"], "bar_plane_x": self.bar["plane_x"], "zero_line_x": 0.0,
                "box_front_x": BOX_FRONT_X, "box_foot": [BOX_FOOT_X, -BOX_DEPTH], "support_s": tr["support_s"],
                "cleared": tr["t_clear"] is not None}
