"""Skateboard ollie, stationary: a rider stands on a real skateboard at rest on flat ground (a free deck with
kicktails, two steering trucks, four wheels on axles; nothing holds the feet to it) and ollies: the back foot snaps the
tail against the ground, the front foot drags the board up, the whole board rises clear of the ground, and the robot
lands on it with all four wheels down and stands still on it.

Sources of the board's numbers: Element Section 7.5 deck (31.5 x 7.5 in, wheelbase 14.0 in); a maple deck of 3 lb
(maple decks 3-4.5 lb, parcelpath.com); Independent 129 Stage 11 truck, 367 g (evo.com; 331 g at skatedeluxe), 7.625 in
axle, about 55 mm high; Spitfire Formula Four 52 mm 99A wheels, 240 g the set (skatedeluxe) plus two 12 g bearings
each; the trucks' pivot axis at 63 degrees and the bushings' tilt stiffness of 100 N m/rad (Varszegi and Takacs,
"Downhill motion of the skater-skateboard system", Periodica Polytechnica Mech. Eng. 60(1), 2016, Table 1); the
tail-ground impact with a coefficient of restitution of 0.8 (Heinen, Brockie, ten Broek, van der Kruk, Moore,
"Maximizing ollie height by optimizing control strategy and skateboard geometry using direct collocation", Sports
Engineering 2023); wood on concrete, friction 0.6 (Engineering ToolBox); a hard (99A) urethane wheel on smooth
concrete: rolling resistance 0.02 (non-pneumatic wheels on concrete 0.020, Dickey, RESNA 2018; hard 95A urethane
casters 0.025-0.035), sliding friction 0.7; grip tape on a shoe sole, friction 1.0."""
import math
import xml.etree.ElementTree as ET

import numpy as np

from rfo.scene import STANDABLE, VISUAL, bounce_solref
from rfo.task import TaskBase
# A rigid truck hanger (aluminium)'s contact with the robot, the venue's fixtures and the other props (the ground
# keeps its own: rfo/world.py GROUND_SOLMIX): the stiff contact of the core's shells (rfo/world.py SHELL_CONTACT:
# solref 0.004 s, solimp 0.99 0.999 0.0005, from Embodied Olympics' weightlifting fix, a rigid prop on the robot's
# aluminium) with a solmix that wins over a default-contact geom; a ball (priority 1) keeps its own bounce. With
# MuJoCo's default soft contact (solref 0.02 1, solimp 0.9 0.95) it sank 50 mm (a wheel through the palm pad: the
# trucks did not accept the robot's hulls and pads, conaffinity 1; now 1 | 4, the strike boxes still pass as on a
# standable deck) (stress test).
from rfo.world import SHELL_CONTACT as RIGID  # noqa: E402

ROBOT_START = (0.0, 0.0, -math.pi / 2)


class Task(TaskBase):
    name = "skateboard-ollie"
    title = "Skateboard ollie"
    category = "parkour-apparatus-balance"
    robot = "unitree_g1"
    rulebook = ("World Skate, Skateboarding Technical Commission, Street & Park Competition Rules (update of April "
                "2025): Technical Specifications of Materials, Skateboard (a deck with four wheels attached by trucks; "
                "it cannot be physically attached to the skater's feet); the Runs + Tricks format (single tricks, "
                "one attempt each); Makes versus Bails (the Head Judge decides whether a trick is landed)")
    deviations = [
        "Runs + Tricks format: one trick, a stationary ollie on flat ground (the board at rest at the start, no "
        "obstacle), the whole board rising at least {clear_m} m above the ground, instead of an ollie at speed onto "
        "or over a street course's obstacle: {clear_m} m is this benchmark's round number (the "
        "robot's measured pops lift the board higher), and the stationary form is the one this robot "
        "can attempt without a push-off on one leg, which it has no balance for",
        "Makes versus Bails: the Head Judge's call is replaced by fixed criteria (a make: the board leaves the "
        "ground with a foot on it and rises clear by {clear_m} m, all four wheels come down with both feet on the "
        "deck, and the robot stands still on the board for {stand_s} s; World Skate judges an ollie made when the "
        "rider lands on the board); the judges' score (difficulty, execution, style) is not given",
        "the skateboard is rigid bodies: the deck is three boxes (no concave, no flex), the wheels cylinders, the "
        "truck a hinge about its pivot axis with a linear torsion spring for the bushings and a hard stop at "
        "{tilt_limit_deg} degrees of deck tilt (the bushings' progressive stiffening is not modelled)",
        "the robot is the size of a child (1.32 m), so the deck is a 7.5 in board, the width skate shops give for "
        "that height, instead of an adult's 8 to 8.5 in",
    ]
    time_limit_s = 8.0
    start = ROBOT_START
    stages = ["pop", "clear", "landed", "stand"]
    fall_rule = True                 # any part of the robot on the ground (a foot too) is a bail
    legal_ground = ()
    fall_z = 0.30
    params = dict(
        deck_length_m=0.80, deck_width_m=0.19, deck_thickness_m=0.0115, deck_mass_kg=1.36, kick_deg=18.0,
        kick_start_m=0.225, wheelbase_m=0.356, truck_height_m=0.055, axle_width_m=0.194, truck_mass_kg=0.367,
        wheel_radius_m=0.026, wheel_width_m=0.032, wheel_mass_kg=0.084, wheel_crr=0.02, wheel_friction=0.7,
        deck_ground_friction=0.6, tail_restitution=0.8,
        grip_friction=1.0, pivot_deg=63.0, bushing_nm_rad=100.0, tilt_limit_deg=12.0,
        board_offset_m=0.11, clear_m=0.05, stand_s=1.0, still_speed_m_s=0.35, wheel_gap_m=0.005, contact_gap_s=0.05, foot_off_s=0.2, min_upright=0.8,
        fall_z_m=0.30,
    )

    sentence = ("Ollie the skateboard from a standstill: pop the tail and lift the board with your feet until all of "
                "it is at least 5 cm off the ground, then land on it and stand still on it for a second.")
    rules = ("The skateboard: a {deck_length_m} m deck, {deck_width_m} m wide, with a kicktail and a nose turned "
             "up {kick_deg} degrees, on two trucks {wheelbase_m} m apart with four {wheel_radius_m} m-radius wheels; "
             "the trucks steer when the deck tilts (pivot axis {pivot_deg} degrees, {bushing_nm_rad} N m/rad of "
             "bushing stiffness, a stop at {tilt_limit_deg} degrees of tilt). Nothing holds your feet to it: grip "
             "tape (friction {grip_friction}) only. The attempt, in this order: (1) pop: the board leaves the ground "
             "(no part of it touching anything but you) with a foot on its deck as it leaves; (2) clear: in the "
             "same flight of the board, every part of it (deck, trucks, wheels) is at least {clear_m} m above the "
             "ground; (3) landed: then all four wheels on the ground (each within {wheel_gap_m} m of it) with both feet on "
             "the deck; (4) stand: for {stand_s} s without a break, both feet on the deck (contact breaks of at "
             "most {contact_gap_s} s), all four wheels on the ground, your torso within "
             "about 37 degrees of upright (the cosine of its tilt at least {min_upright}) and your pelvis slower than "
             "{still_speed_m_s} m/s. You succeed at (4). A pop that does not clear may be followed by another. You "
             "fail if any part of you other than the feet and shins touches the board (an ollie is done without "
             "hands), if any part of you, a foot included, touches the ground or your pelvis drops below {fall_z_m} m "
             "(a bail), if the board touches the ground upside down, after the landing if a foot stays off the deck "
             "for more than {foot_off_s} s or your torso tilts beyond that limit, and at {time_limit_s} s.")
    venue = ("A level concrete plaza. You stand across the board, which is at rest on the ground, facing -y, left "
             "foot towards the nose: the board's long axis points along +x, its nose at +x. Your feet are in your "
             "standing stance, 0.24 m apart, the left one about the middle of the deck, the right one at the tail's "
             "bend; the board's centre is {board_offset_m} m ahead (in x) of your pelvis.")
    difficulty = ("The ollie is a timed whole-body skill on a free board: the tail has to be snapped down with the "
                  "front foot unloaded, the front foot has to drag the rising board up and level it while the robot "
                  "is in the air, and the robot has to land on a narrow deck that rolls and steers when it tilts. "
                  "Even standing still, the board is unstable under a rigid rider (its trucks tilt and steer), so the "
                  "ankles have to balance it before and after the trick.")

    # ------------------------------------------------------------------ the board
    def build(self, sc):
        p = self.p
        T, hw, ks = p["deck_thickness_m"], p["deck_width_m"] / 2, p["kick_start_m"]
        th = math.radians(p["kick_deg"])
        kl = p["deck_length_m"] / 2 - ks                     # the kick's length along its surface
        r = p["wheel_radius_m"]
        za = -T / 2 - p["truck_height_m"]                    # the axles below the deck's middle plane
        self.deck_z = r - za                                 # the deck's middle plane above the ground
        self.deck_top = self.deck_z + T / 2
        x0, y0, _ = self.start
        self.board0 = (x0 + p["board_offset_m"], y0 - 0.009, self.deck_z)
        b = sc.body("board", self.board0, free=True)
        lin = p["deck_mass_kg"] / p["deck_length_m"]
        # the deck's maple against the robot's body is rigid (RIGID's solref and solimp; priority 1: it wins over the
        # hulls); a solmix of 1e-6 leaves the soles' contact on it as it was (the G1's soles have the same priority:
        # their own parameters govern); the deck's tail strike on the ground is the explicit pairs below
        deck = dict(friction=(p["grip_friction"], 0.005, 0.0001), priority=1, condim=3, solref=RIGID["solref"],
                    solimp=RIGID["solimp"], solmix="1e-06", **STANDABLE)
        sc.geom(b, "deck_mid", type="box", size=(ks, hw, T / 2), mass=lin * 2 * ks, rgba=(0.12, 0.12, 0.13, 1), **deck)
        for s, tag in ((-1, "tail"), (1, "nose")):
            cx = s * (ks + kl / 2 * math.cos(th))
            cz = kl / 2 * math.sin(th)
            q = (math.cos(-s * th / 2), 0.0, math.sin(-s * th / 2), 0.0)
            sc.geom(b, f"deck_{tag}", type="box", pos=(cx, 0, cz), quat=q, size=(kl / 2, hw, T / 2), mass=lin * kl,
                    rgba=(0.12, 0.12, 0.13, 1), **deck)
        lam = math.radians(p["pivot_deg"])
        k_h = p["bushing_nm_rad"] / 2 * math.cos(lam) ** 2
        th_max = math.radians(p["tilt_limit_deg"]) / math.cos(lam)
        wb = p["wheelbase_m"] / 2
        yw = p["axle_width_m"] / 2 - p["wheel_width_m"] / 2
        mu_r = p["wheel_crr"] * r
        base_m = 0.35 * p["truck_mass_kg"]
        for s, tag in ((1, "front"), (-1, "rear")):
            sc.geom(b, f"base_{tag}", type="box", pos=(s * wb, 0, -T / 2 - 0.012), size=(0.03, 0.03, 0.012),
                    mass=base_m, rgba=(0.7, 0.7, 0.72, 1), **VISUAL)
            h = ET.SubElement(b, "body", name=f"hanger_{tag}", pos=f"{s * wb:.6g} 0 {za:.6g}")
            ET.SubElement(h, "joint", name=f"truck_{tag}", type="hinge",
                          axis=f"{s * math.cos(lam):.6g} 0 {math.sin(lam):.6g}", stiffness=f"{k_h:.6g}",
                          damping="0.2", range=f"{-th_max:.6g} {th_max:.6g}", armature="0.0001")
            sc.geom(h, f"hanger_{tag}", type="capsule", fromto=(0, -yw + 0.01, 0.006, 0, yw - 0.01, 0.006), size=(0.011,),
                    mass=(1 - 0.35) * p["truck_mass_kg"], rgba=(0.7, 0.7, 0.72, 1), contype=1, conaffinity=5, **RIGID)
            for sy, side in ((1, "l"), (-1, "r")):
                wbody = ET.SubElement(h, "body", name=f"wheel_{tag}_{side}", pos=f"0 {sy * yw:.6g} 0")
                ET.SubElement(wbody, "joint", name=f"wheel_{tag}_{side}", type="hinge", axis="0 1 0", damping="0",
                              armature="0")
                sc.geom(wbody, f"wheel_{tag}_{side}", type="cylinder",
                        fromto=(0, -p["wheel_width_m"] / 2, 0, 0, p["wheel_width_m"] / 2, 0), size=(r,),
                        mass=p["wheel_mass_kg"], rgba=(0.95, 0.93, 0.85, 1), condim=6, priority=2,
                        friction=(p["wheel_friction"], 0.001, mu_r), contype=1, conaffinity=5)
        # the deck meets the ground (a tail strike) as wood on concrete: explicit pairs with that contact
        con = sc.root.find("contact")
        ET.SubElement(con, "exclude", body1="world", body2="board")
        for g in ("deck_mid", "deck_tail", "deck_nose"):
            ET.SubElement(con, "pair", geom1=g, geom2="floor", condim="3", friction=f"{p['deck_ground_friction']:g} {p['deck_ground_friction']:g} 0.005 0.0001 0.0001",
                          solref=bounce_solref(p["tail_restitution"]), solimp="0.95 0.99 0.001")
        sc.box("plaza", (x0, y0, 0.0003), (6.0, 4.0, 0.0003), rgba=(0.55, 0.55, 0.53, 1))
        sc.camera("venue", (x0 + 0.1, y0 - 3.0, 1.0), (x0 + 0.1, y0, 0.45), fovy=50)

    def reset(self, w):
        import mujoco
        p = self.p
        r = w.robot
        mujoco.mj_kinematics(w.m, w.d)
        soles = [g for g in range(w.m.ngeom) if "ankle_roll_link_sc" in w.m.geom(g).name]
        low = min(float(w.d.geom_xpos[g][2] - w.m.geom_size[g][0]) for g in soles)
        w.d.qpos[r.fq + 2] += self.deck_top + 0.001 - low   # the robot stands on the deck
        w.put("board", self.board0)

    def referee_reset(self, w, ref):
        self.board_g = ref.geoms(body="board")              # deck, trucks, wheels
        self.deck_g = ref.geoms(prefix="deck_")
        self.wheel_ids = [w.m.geom(f"wheel_{n}").id for n in ("front_l", "front_r", "rear_l", "rear_r")]
        self.floor = ref.geoms(names=["floor"])
        self.robot = ref.part("robot")
        self.feet = ref.part("feet")
        self.lfoot, self.rfoot = ref.part("left_foot"), ref.part("right_foot")
        self.not_feet = self.robot & ~ref.part("feet", "shins")      # the legs below the knees may brush it
        # air: the board touches nothing but the robot now; popped: this flight began with a foot on the deck;
        # max_clear_m: the board's lowest point's best height in a popped flight; off: per foot, seconds off the deck
        # since the landing
        self.trackers = {"air": False, "popped": False, "max_clear_m": 0.0, "off": [0.0, 0.0]}

    def _wheels_down(self, w) -> bool:
        """All four wheels on the ground: each wheel's lowest point within wheel_gap_m of it."""
        m, d = w.m, w.d
        for g in self.wheel_ids:
            R = d.geom_xmat[g].reshape(3, 3)
            az = abs(float(R[2, 2]))
            low = d.geom_xpos[g][2] - az * m.geom_size[g][1] - m.geom_size[g][0] * math.sqrt(max(0.0, 1 - az * az))
            if low > self.p["wheel_gap_m"]:
                return False
        return True

    def _deck_up(self, w) -> float:
        return float(w.d.xmat[w.m.body("board").id][8])

    def _board_low(self, w) -> float:
        """The lowest point of the board's collision geometry (deck boxes, hangers, wheels) above the ground."""
        m, d = w.m, w.d
        lo = 9.0
        for g in self.low_geoms:
            R = d.geom_xmat[g].reshape(3, 3)
            c, sz = d.geom_xpos[g], m.geom_size[g]
            if m.geom_type[g] == 6:                         # box
                lo = min(lo, c[2] - float(np.abs(R[2]) @ sz))
            else:                                           # cylinder / capsule along the local z
                az = abs(float(R[2, 2]))
                rad = sz[0]
                lo = min(lo, c[2] - az * sz[1] - rad * math.sqrt(max(0.0, 1 - az * az)))
        return lo

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        if not hasattr(self, "low_geoms"):
            self.low_geoms = [int(g) for g in np.flatnonzero(self.board_g) if w.m.geom_contype[g]]
        if ref.touching(self.not_feet, self.board_g):
            return ref.fail("touched the board with a hand, an arm or the body",
                            parts=sorted(ref.parts_touching(self.board_g) - {"left_foot", "right_foot", "left_shin",
                                                                            "right_shin"}))
        on_floor = ref.touching(self.board_g, self.floor)
        if on_floor and self._deck_up(w) < 0.5:
            return ref.fail("the board turned over")
        airborne = not on_floor and not ref.touching(self.board_g, ~self.robot & ~self.board_g)
        if airborne and not tr["air"]:                       # the board has just left the ground
            tr["popped"] = bool(ref.touching(self.feet, self.deck_g))
            if tr["popped"] and not ref.has("pop"):
                ref.stage("pop", x=round(float(w.pos("board")[0]), 3))
        if not airborne:
            tr["popped"] = False
        tr["air"] = bool(airborne)
        if airborne and tr["popped"]:
            low = self._board_low(w)
            if low > tr["max_clear_m"]:
                tr["max_clear_m"] = round(low, 4)
                ref.metrics["board_clearance_m"] = tr["max_clear_m"]
            if low >= p["clear_m"] and not ref.has("clear"):
                ref.stage("clear", height_m=round(low, 4))
        if ref.has("clear") and not ref.has("landed"):
            if self._wheels_down(w) and ref.touching(self.lfoot, self.deck_g) and ref.touching(self.rfoot, self.deck_g):
                ref.stage("landed")

    def step(self, w, ref):
        p, tr = self.p, self.trackers
        if ref.failed or not ref.has("landed"):
            return
        for i, foot in enumerate((self.lfoot, self.rfoot)):
            tr["off"][i] = 0.0 if ref.touching(foot, self.deck_g) else round(tr["off"][i] + w.CONTROL_DT, 4)
            if tr["off"][i] > p["foot_off_s"]:
                return ref.fail("a foot left the board after the landing", foot=("left", "right")[i])
        if w.upright() < p["min_upright"]:
            return ref.fail("fell on the board", upright=round(w.upright(), 3))
        v = float(np.linalg.norm(w.d.qvel[w.robot.fv:w.robot.fv + 3]))
        still = (max(tr["off"]) <= p["contact_gap_s"] and self._wheels_down(w) and v <= p["still_speed_m_s"])
        if ref.hold("stand", still, p["stand_s"]) and ref.stage("stand"):
            ref.succeed()

    def board_state(self, w):
        d, m = w.d, w.m
        b = m.body("board").id
        R = d.xmat[b].reshape(3, 3)
        roll = math.atan2(float(R[2, 1]), float(R[2, 2]))
        pitch = math.asin(max(-1.0, min(1.0, -float(R[2, 0]))))
        yaw = math.atan2(float(R[1, 0]), float(R[0, 0]))
        return dict(pos=d.xpos[b].tolist(), vel=w.vel("board").tolist(), roll=roll, pitch=pitch, yaw=yaw)

    def privileged(self, w):
        return {"board": self.board_state(w), "pelvis": w.pelvis().tolist(),
                "board_low_m": self._board_low(w) if hasattr(self, "low_geoms") else None}
