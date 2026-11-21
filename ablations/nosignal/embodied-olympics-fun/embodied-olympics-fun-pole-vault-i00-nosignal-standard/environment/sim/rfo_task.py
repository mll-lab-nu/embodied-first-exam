"""Pole vault (World Athletics TR 28): the sunken box, a 4.5 m bar on pegs between uprights 4.3 m apart, the
5 m x 5 m x 0.8 m landing mat; the pole planted in the box, over the bar, and the bar stays on. The pole is rigid and a
free body that collides with everything, the robot's own body included; nothing is welded: the hands are the G1's own
Dex3-1 three-finger hands (rfo.realhand, "dex3") and hold the pole by the contact and friction of their fingers alone.

The robot is the G1 (34.8 kg with its hands, 341 N), the pole the lightest one rated for it: UCS's Junior
Spirit, 2.35 m (7 ft 8 in), rated 90 lb (40.8 kg), the makers' rule being a pole rated at or above the athlete's
weight (athleticsdirect.co.uk, UCS Junior Spirit poles: 2.35 m rated 55/65/75/90 lb; a top-hand grip 6 to 18 in
below the top); its mass (1.1 kg) and thickness (32 mm) are estimates. The bar is at 1.00 m, set for this robot.

The take-off (TR 28: the athlete hangs on the planted pole): the referee asks the pole to carry at least half the
robot's weight then, a run-up of at least 2.5 m/s over the last 0.5 s before the take-off, the pole at least 20
degrees from vertical at the take-off, and a hand above the pelvis while the pole carries the robot. A Dex3-1 hand
closed on the pole holds it across its palm, square to the forearm; it lets the pole slide along its axis at about
157 N (measured).

The landing area (TR 28.12): urethane foam, the soft contact set from a pit's foam: the top pads of UCS pole-vault
pits (World Athletics / NFHS pits) are "23 lb ILD urethane foam" (ucsspirit.com, pole vault pit 1750-2200 series):
ASTM D3574's ILD, 23 lbf (102 N) to indent a 4 in (0.10 m) sample by 25 % with a 50 in^2 (0.0323 m^2) foot, is 3.2 kPa
at 25 % strain, a modulus of about 12.7 kPa. A 0.8 m deep mat under the 0.5 m^2 of a back landing gives
12.7 kPa x 0.5 m^2 / 0.8 m = 7.9 kN/m; MuJoCo's soft
contact is a law per kilogram, so its time constant is set for the robot's mass: for the G1 (34.4 kg) 15.2 rad/s,
1 / (0.95 x 15.2 rad/s) = 0.069 s, critically
damped (a body lands dead in a pit; foam's loss is high), the full stiffness from the first millimetre (solimp
0.9-0.95 over 1 mm). Measured: the G1 dropped flat on its back from 1 m above the mat sinks to its pelvis 0.04 m
below the mat's top and comes to rest with it 0.06 m above the top. The mat's
boxes reach below the floor (their middle at the floor) so a deep landing is not pushed out through their bottom.
The box (TR 28.8): sheet metal; the pole's tip (a nylon plug on fibreglass) on it at friction 0.4 (nylon on steel,
dry: 0.3-0.5, engineering tables), the pole's friction on everything but the hands' finger pads (whose rubber wins)."""
import math
import xml.etree.ElementTree as ET

import numpy as np

import mujoco

from rfo.referee import Flights
from rfo.task import TaskBase
# A rigid crossbar (fibreglass; the landing mats keep their foam)'s contact with the robot, the venue's fixtures and
# the other props (the ground keeps its own: rfo/world.py GROUND_SOLMIX): the stiff contact of the core's shells
# (rfo/world.py SHELL_CONTACT: solref 0.004 s, solimp 0.99 0.999 0.0005, from Embodied Olympics' weightlifting fix, a rigid
# prop on the robot's aluminium) with a solmix that wins over a default- contact geom; a ball (priority 1) keeps its
# own bounce. With MuJoCo's default soft contact (solref 0.02 1, solimp 0.9 0.95) it sank 27 mm into the mats' sides
# and 16 mm into a foot (stress test).
from rfo.world import SHELL_CONTACT as RIGID  # noqa: E402

SIDES = ("left", "right")
STEEL = (0.3, 0.3, 0.33, 1)
POLE_ONLY = dict(contype="2", conaffinity="2")           # what only the pole (and the bar) touches: the box, its ground
POLE = dict(contype="2", conaffinity="14")               # the pole: the box and its ground (2), the robot's hulls and
#                                                          grippers (4), the feet's strike boxes (8); props meet it by
#                                                          their own conaffinity (bar, uprights 15, mats 7)
POLE_FRICTION = (0.4, 0.005, 0.0001)                     # fibreglass / the tip's nylon plug on sheet steel (see above)
CARRY_ARM = (0.0, -0.5, 0.5, 1.0, 0.633, 0.5, 0.0)       # the right arm carrying the pole: out to the side, the forearm
#                                                          forwards and down, the hand turned so that the pole across
#                                                          the palm lies level along +x, clear of the hip
FREE_ARM_ROLL = 0.2                                       # rad: the free left arm's shoulder roll above the G1's rest
#                                                          pose: at rest (0.2) the Dex3-1's thumb lies 32.8 mm inside
#                                                          the hip's hull; at 0.4 it clears it by 46 mm (38 mm over 2 s
#                                                          of the start command)
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
            mass=p["bar_mass_kg"] - 2 * m_end, rgba=(0.95, 0.2, 0.2, 1), friction=(0.6, 0.005, 0.0001), **solid,
            **RIGID)
    for s, tag in ((1, "L"), (-1, "R")):                 # the end pieces: flat undersides on the pegs
        sc.geom(b, f"{name}_end{tag}", type="box", pos=(0, s * (L / 2 - end), 0), size=(r, end, r), mass=m_end,
                rgba=(0.95, 0.95, 0.95, 1), friction=(0.6, 0.005, 0.0001), **solid, **RIGID)
    return dict(x=x, height=height, rest_z=height - r, plane_x=x - r, half_gap=gap / 2)


class Task(TaskBase):
    name = "pole-vault"
    title = "Pole vault"
    category = "track-and-jumps"
    robot = "unitree_g1"
    rulebook = ("World Athletics Competition and Technical Rules, 2024 edition: TR 28 (28.1 the bar may be moved up "
                "to 0.80 m from the zero line towards the landing area; 28.2 failures: (a) the bar does not remain "
                "on both pegs, (b) touching the ground or the landing area beyond the zero line with the body or "
                "the pole without first clearing the bar, (c) moving a hand up the pole after leaving the ground, "
                "(d) steadying the bar with a hand; 28.6 a runway of at least 40 m; 28.8 the box; 28.9-28.10 the "
                "uprights and pegs 4.28 to 4.37 m apart, the 4.50 m bar of at most 2.25 kg; 28.12 a landing area "
                "of at least 5 m x 5 m x 0.8 m with front pieces 2 m long), TR 25.17 (one minute for a trial)")
    deviations = [
        "TR 28.11 (vaulting poles: any material, length and diameter, a smooth surface): the pole is a {pole_length_m} "
        "m (7 ft 8 in) pole rated {pole_rating_kg} kg (90 lb), UCS's Junior Spirit, the lightest rating at or above "
        "the robot's 34.8 kg with its hands (the makers' rule: a pole rated at or above the athlete's weight); its "
        "mass ({pole_mass_kg} kg) and thickness ({pole_diameter_m} m) are estimates, the makers give none; it is "
        "rigid: it does not bend and stores no energy (the simulator has no validated model of a bending pole)",
        "the grip: each hand is the G1's own Dex3-1 three-finger hand (thumb 3 joints, index and middle 2 each, one "
        "motor per joint, at the device's torques); it holds the pole by its fingers' contact and friction alone "
        "(nothing is welded), so the pole can slide in the hand, turn in it and drop; a hand holds the pole while "
        "the pole touches its fingers and its thumb or palm. The pole collides with the robot's body as with "
        "everything else",
        "TR 28.8 (the box): it is sunk below the runway as the rule draws it, but only the pole (and the bar) can "
        "enter it; for the robot's feet it is covered at runway level; its side walls are planes",
        "TR 28.2(b), (c), (d) are judged geometrically: any contact of the robot or the pole with the ground or the "
        "mats beyond the zero line before the bar is cleared; a hand that holds the pole more than {climb_m} m "
        "farther from its tip than the upper hand's grip was at lift-off; a hand on the bar for more than "
        "{bar_hand_s} s in all",
        "a vault is told from a jump by numbers (TR 28 does not define one): the take-off (the robot's last ground "
        "contact before the flight that clears the bar) must end a run-up, the pelvis' forward speed averaged over "
        "the last {runup_window_s} s before it at least {runup_min_m_s} m/s (a novice's short run-up is some 4 to "
        "6 m/s), with the pole at least {pole_min_deg} degrees from vertical then (a planted pole leans some 25 to "
        "35 degrees at a vault's take-off); in that flight the robot must hang on the pole for at least "
        "{min_support_s} s: a hand gripping it higher than the pelvis, its tip in the box pressed into it with at "
        "least {min_pole_load} of the robot's weight, nothing of the robot on the ground; pushing down on the top "
        "of a pole (the pelvis above the hands) is not a hang; the pelvis and the feet (the ankle joints) must pass "
        "the bar's plane between the pegs and above the bar; the bar is cleared when every part of the robot is "
        "beyond its plane",
        "TR 28.2(a): the bar is judged {bar_wait_s} s after the landing; it is off its pegs when its centre is more "
        "than {bar_drop_m} m below its resting height; the pegs are square in section, the bar rigid",
        "TR 28.12 (the landing area): the mats are rigid boxes with a soft contact set from a pit's urethane foam (23 "
        "lb ILD: about 12.7 kPa; under a 0.5 m^2 back landing on the 0.8 m mat, 7.9 kN/m: MuJoCo's contact time "
        "constant {mat_timeconst_s} s for the robot's mass, critically damped), not a deforming foam; the mat's face "
        "behind the box slopes away "
        "at 45 degrees as the rule asks, the front pieces' faces beside the box are vertical, and the uprights "
        "stand in the mat without a recess; no wind",
        "TR 28 (the heights are the competition's: no rule sets a lowest one): one trial at one height, "
        "{bar_height_m} m, set for this robot: its run-up (the running policy's 4 m/s) carries about 0.8 m of "
        "height above a centre of mass about 0.65 m up, and a rigid pole returns none of what the plant takes; a "
        "lower bar would lie on the landing area, which TR 28.12 makes {mat_height_m} m high",
        "TR 28.1 (the athlete chooses where the bar stands, 0 to 0.80 m beyond the zero line): it stands "
        "{bar_setback_m} m beyond it, set for the short pole (there is no choice: the task is one trial)",
    ]
    time_limit_s = 60.0
    start = (-20.0, 0.0, 0.0)
    stages = ["plant", "take-off", "clearance", "bar stays"]
    fall_rule = False                # no rule of the event says a fall is a failure; the contacts below judge it
    params = dict(bar_height_m=1.00, bar_setback_m=0.20, bar_length_m=4.50, bar_diameter_m=0.030, bar_mass_kg=2.25,
                  peg_gap_m=4.30, peg_length_m=0.055, peg_thickness_m=0.013, pole_length_m=2.35, pole_mass_kg=1.1,
                  pole_diameter_m=0.032, pole_rating_kg=40.8, runway_m=40.0, runway_width_m=1.22, mat_length_m=5.0,
                  mat_width_m=5.0,
                  mat_height_m=0.80, mat_gap_m=0.15, front_piece_m=2.0, mat_timeconst_s=0.069,
                  min_support_s=0.15, min_pole_load=0.5, runup_min_m_s=2.5, runup_window_s=0.5, pole_min_deg=20.0, climb_m=0.05, bar_hand_s=0.10, bar_drop_m=0.05, bar_wait_s=2.0)

    sentence = ("Vault over the bar with the pole you carry: plant its tip in the box, leave the ground hanging on "
                "it, go over the bar between the uprights and come down on the mat, with the bar still on its pegs.")
    rules = ("World Athletics rules for the pole vault. You carry the pole ({pole_length_m} m long, "
             "{pole_diameter_m} m thick, {pole_mass_kg} kg; rigid: it does not bend) held at its middle in your right "
             "hand. Your hands are three-finger hands (a thumb, an index and a middle finger) that hold by contact and "
             "friction only, so the pole can slide in a hand, turn in it and drop; a hand holds the pole while the "
             "pole touches that hand's index or middle finger and its thumb or palm, anywhere along its length, and "
             "it can be let go and taken again. The pole touches the "
             "box, the mats, the uprights, the bar and your body (not the runway's surface around the box: it rests "
             "on the ground beside it as on a level floor). The "
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
             "the pole. (2) take-off: you leave the ground from a run-up, your pelvis' forward (+x) speed averaged "
             "over the last {runup_window_s} s before the lift-off at least {runup_min_m_s} m/s, with the pole at "
             "least {pole_min_deg} degrees from vertical at the lift-off; then you hang on the planted pole: for at "
             "least {min_support_s} s in that flight nothing of you touches anything but the pole and the bar while "
             "a hand grips the pole higher than your pelvis and the pole's tip rests in the box, pressed into it "
             "with at least {min_pole_load} of your weight (the pole carries you: pushing down on its top with your "
             "pelvis above your hands is not a hang). (3) clearance: in that same flight your pelvis and both feet (the ankle joints) cross the plane "
             "of the bar's nearer edge between the pegs and higher than the bar's upper side (one that comes back "
             "over the plane has not passed it), and every part of "
             "you gets beyond that plane; you may touch the bar. (4) You come down, on any part of your body, with "
             "or without the pole. You succeed when {bar_wait_s} s after your landing the bar is still on its "
             "pegs. A fall is not a failure by itself. You fail if the bar drops more than {bar_drop_m} m at any "
             "time, whether you or the pole knocked it; if, before you have cleared the bar, anything of you or the "
             "pole touches the ground or the mats beyond the zero line; if your pelvis or a foot passes the bar's "
             "plane outside the pegs or not higher than the bar; if you clear the bar without such a "
             "take-off and hang (a jump without the pole, a standing jump on it, or a push on its top); if, in the flight of the vault, a "
             "hand holds the pole more than {climb_m} m farther from its tip than your upper hand did at lift-off "
             "(climbing); if your hands touch the bar for more than {bar_hand_s} s in all (steadying it); or after "
             "{time_limit_s} s (the time allowed for a trial).")
    venue = ("You stand on the runway facing the box (+x), your pelvis 20 m before the zero line, in the middle of "
             "the runway; the runway goes on 20 m behind you. The pole lies level along +x in your right hand, "
             "held at its middle across the palm (grip value 1), the right arm hanging, the forearm pointing forwards "
             "and down; "
             "the left hand is open (grip value 0). A grip value is that hand's closure command (0 open, 1 every "
             "finger and thumb joint closing towards its closed angle; a finger stops on what it touches). The pole "
             "is a free body: `held` in your state says which hand holds it. "
             "The bar is red with white ends, the uprights grey, the mats blue; "
             "the box is the dark patch at the runway's end, the zero line white.")
    difficulty = ("The bar is 1.0 m up and the robot 1.32 m tall: its whole body has to pass over it on a rigid "
                  "pole that gives nothing back, from a run-up that the running policy makes at about 4 m/s, with "
                  "arms whose motors give 25 N m, and three-finger hands that hold little along the pole: the "
                  "plant's jolt slides the pole through the hands. Nothing built in grips, "
                  "plants, swings or lets go.")

    # ------------------------------------------------------------------ the venue
    def build(self, sc):
        p = self.p
        sc.box("runway", (-p["runway_m"] / 2, 0, 0.0003), (p["runway_m"] / 2, p["runway_width_m"] / 2, 0.0003),
               rgba=(0.72, 0.25, 0.18, 1))
        self.box_geoms, self.pole_ground = vault_box(sc)
        self.bar = vault_bar(sc, "bar", p["bar_setback_m"], p["bar_height_m"], p)
        soft = dict(rgba=(0.15, 0.35, 0.75, 1), friction=(1.0, 0.005, 0.0001), solref=(p["mat_timeconst_s"], 1.0),
                    solimp=(0.9, 0.95, 0.001, 0.5, 2), priority=1, contype="3", conaffinity="7")
        hz, hw, g = p["mat_height_m"] / 2, p["mat_width_m"] / 2, p["mat_gap_m"]
        y0, x1, Hm = BOX_HALF_FRONT + g, g + p["mat_length_m"], p["mat_height_m"]
        # the mat behind the box: its face towards the box slopes away at 45 degrees (TR 28.12), so that the pole can
        # lean on past vertical; beside it the mat's face is vertical, mat_gap_m beyond the zero line
        ET.SubElement(sc.root.find("asset"), "mesh", name="mat_slope", vertex=" ".join(
            f"{v:.6g}" for q in [(x, s * y0, z) for s in (1, -1) for (x, z) in ((g, 0.0), (g + Hm, 0.0), (g + Hm, Hm))]
            for v in q))
        sc.geom(sc.wb, "mat_slope", type="mesh", mesh="mat_slope", **soft)
        # the boxes reach as far below the floor as the mat is high (their middle at the floor): a deep landing in
        # the soft contact never passes their middle, where the box's contact would push it out through the bottom
        sc.geom(sc.wb, "mat", type="box", pos=((g + Hm + x1) / 2, 0.0, 0.0), size=((x1 - g - Hm) / 2, y0, 2 * hz), **soft)
        for s, tag in ((1, "L"), (-1, "R")):             # ... and the front pieces beside the box, mat_gap_m from its edge
            sc.geom(sc.wb, f"mat_side{tag}", type="box", pos=((g + x1) / 2, s * (y0 + hw) / 2, 0.0),
                    size=((x1 - g) / 2, (hw - y0) / 2, 2 * hz), **soft)
            sc.geom(sc.wb, f"front_piece{tag}", type="box", pos=(g - p["front_piece_m"] / 2, s * (y0 + hw) / 2, 0.0),
                    size=(p["front_piece_m"] / 2, (hw - y0) / 2, 2 * hz), **soft)
        self.mats = ["mat", "mat_slope", "mat_sideL", "mat_sideR", "front_pieceL", "front_pieceR"]
        sc.ground += self.mats
        L, r = p["pole_length_m"], p["pole_diameter_m"] / 2
        b = sc.body("pole", (-8.0, -0.3, 1.0), free=True)            # a rigid rod along its own x axis: the tip is its +x end
        sc.geom(b, "pole", type="capsule", fromto=(-L / 2 + r, 0, 0, L / 2 - r, 0, 0), size=(r,), mass=p["pole_mass_kg"],
                rgba=(0.9, 0.9, 0.95, 1), friction=POLE_FRICTION, priority=1, solref=(0.004, 1.0),
                solimp=(0.95, 0.99, 0.001), **POLE)
        sc.geom(b, "pole_tip", type="sphere", pos=(L / 2 - r, 0, 0), size=(r * 1.02,), mass=0.0001,
                rgba=(0.85, 0.15, 0.15, 1), contype="0", conaffinity="0")
        for side in SIDES:                               # the hands: the G1's Dex3-1 (rfo.realhand), no weld
            sc.real_hands[side] = "dex3"
        sc.camera("venue", (-6.5, -7.5, 3.2), (-0.5, 0.0, 1.3), fovy=58)
        sc.camera("box", (-3.4, -0.3, 1.5), (-0.5, 0.0, 0.2), fovy=50)

    def reset(self, w):
        p = self.p
        w.put("bar", (self.bar["x"], 0.0, self.bar["rest_z"]))
        r, d = w.robot, w.d                              # the right arm carrying (CARRY_ARM)
        a = w.L.ARMS.start + 7
        d.qpos[r.qadr[a:a + 7]] = CARRY_ARM
        r.arb.q_a[a:a + 7] = r.arb.q_b[a:a + 7] = CARRY_ARM
        f = w.L.ARMS.start + 1                           # the free left arm off the hip (FREE_ARM_ROLL)
        d.qpos[r.qadr[f]] = r.rest[f] + FREE_ARM_ROLL
        r.arb.q_a[f] = r.arb.q_b[f] = r.rest[f] + FREE_ARM_ROLL
        mujoco.mj_kinematics(w.m, d)
        c, R = w.grasp_frame("right")                    # the pole across the palm (the grasp frame's y), at its
        ax = R[:, 1] if R[0, 1] >= 0.0 else -R[:, 1]     # middle, its tip (+x of its body) forwards
        up = np.array([0.0, 0.0, 1.0]) - ax[2] * ax
        up /= np.linalg.norm(up)
        q = np.zeros(4)
        mujoco.mju_mat2Quat(q, np.c_[ax, np.cross(up, ax), up].ravel())
        w.put("pole", c, quat=q)
        w.close_on("right", "pole")

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
        self.weight = float(sum(m.body_mass[b] for b in w.robot.bodies)) * 9.81
        # support_s: time on the planted pole in the current flight; grip0: the upper hand's place on the pole at
        # lift-off (m from the tip); hand_bar_s: the hands' time on the bar; crossed: who has passed the bar's plane
        # grip: where each hand holds the pole now (m from the tip; None: not holding)
        # vx: the pelvis' forward speed at each physics step of the last runup_window_s (the run-up); lift_off: the
        # current flight's take-off (that run-up's mean speed, the pole's angle from vertical); load_s: time on the
        # loaded pole in the flight, hanging or not
        n = int(round(self.p["runup_window_s"] / m.opt.timestep))
        self.trackers = {"flights": Flights(ref, also_allowed=self.bar_mask | self.pole_mask),
                         "support_s": 0.0, "load_s": 0.0, "grip0": None, "grip": {"left": None, "right": None},
                         "hand_bar_s": 0.0, "vx": np.zeros(n), "vx_i": 0, "lift_off": None,
                         "crossed": [], "prev": None, "t_clear": None, "t_land": None, "bar_z0": None}

    def pole_angle_deg(self, w) -> float:
        """The pole's angle from vertical (degrees)."""
        ax = w.d.xmat[self.pole_id].reshape(3, 3)[:, 0]
        return math.degrees(math.acos(min(1.0, abs(float(ax[2])))))

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

    def pole_load(self, w) -> float:
        """The force the box takes from the pole now (N): the sum of the contacts' normal forces."""
        m, d = w.m, w.d
        f, out = np.zeros(6), 0.0
        pid = self.pole_id
        for i in range(d.ncon):
            c = d.contact[i]
            g1, g2 = int(c.geom1), int(c.geom2)
            if (m.geom_bodyid[g1] == pid and self.box_mask[g2]) or (m.geom_bodyid[g2] == pid and self.box_mask[g1]):
                mujoco.mj_contactForce(m, d, i, f)
                out += float(f[0])
        return out

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
        was_air = fl.air
        fl.update()
        if fl.air and not was_air:                       # lift-off: the run-up's speed and the pole's angle
            tr["lift_off"] = {"lift_off_s": round(ref.time, 4), "pole_deg": round(self.pole_angle_deg(w), 1),
                              "run_up_m_s": round(float(tr["vx"].mean()), 3)}
        tr["vx"][tr["vx_i"] % len(tr["vx"])] = float(w.d.qvel[w.robot.fv])    # (the free base's velocity: world
        tr["vx_i"] += 1                                                         # frame; a ring of the last steps)
        for s in SIDES:                                  # where each hand is on the pole now (a hand that slides
            tr["grip"][s] = (round(self.grip_from_tip(w, s), 4)      # up it climbs as one that lets go and closes
                             if w.held[s] == "pole" else None)        # higher: TR 28.2(c))
        grips = [tr["grip"][s] for s in SIDES if tr["grip"][s] is not None]
        planted = self.planted(w, ref)
        if planted:
            ref.stage("plant", grip_from_tip_m=grips)
        if not fl.air:
            tr["support_s"], tr["load_s"], tr["grip0"] = 0.0, 0.0, None
        else:
            if tr["grip0"] is None and grips:                # lift-off: where the upper hand is on the pole
                tr["grip0"] = max(grips)
            if planted and self.pole_load(w) >= p["min_pole_load"] * self.weight:
                tr["load_s"] = round(tr["load_s"] + dt, 6)
                lo = tr["lift_off"] or {"run_up_m_s": 0.0, "pole_deg": 0.0}
                palm = max([float(w.d.site_xpos[w.robot.palm[s]][2]) for s in SIDES if w.held[s] == "pole"] or [-9.0])
                if (palm > float(w.d.xpos[w.robot.pelvis][2]) and lo["run_up_m_s"] >= p["runup_min_m_s"]
                        and lo["pole_deg"] >= p["pole_min_deg"]):    # a hang, after a run-up, on a leaning pole
                    tr["support_s"] = round(tr["support_s"] + dt, 6)
                    if tr["support_s"] >= p["min_support_s"]:
                        ref.stage("take-off", support_s=tr["support_s"], **lo)
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
                lo = tr["lift_off"] or {}
                why = dict(support_s=tr["support_s"], loaded_s=tr["load_s"], **lo)
                if not fl.air or tr["load_s"] < p["min_support_s"]:
                    return ref.fail("cleared the bar without the pole planted in the box", **why)
                if lo.get("run_up_m_s", 0.0) < p["runup_min_m_s"]:
                    return ref.fail("cleared the bar without a run-up to the take-off", **why)
                if lo.get("pole_deg", 0.0) < p["pole_min_deg"]:
                    return ref.fail("cleared the bar from a pole near vertical at the take-off", **why)
                return ref.fail("cleared the bar pushing down on the pole, not hanging from it", **why)
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
