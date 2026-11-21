"""Basketball two-hand dunk on a lowered basket (FIBA): the ring at 2.39 m, below FIBA Mini-Basketball's 2.60 m,
set at the robot's measured reach, and the start 0.75 m from the point under the ring. The ball is held in the H1-2's
own Inspire five-finger hands (rfo.realhand), squeezed between the two open palms, by contact and
friction alone (no weld); the robot jumps, forces it down through the ring from above with both hands on it, and
lands on its feet. Official court, size-7 ball, full-size backboard and ring lowered by 0.66 m;
the Unitree H1-2."""
import math
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from rfo.referee import Crossing, HoopPass
from rfo.scene import HITTABLE, OFFICIAL, VISUAL, bounce_solref
from rfo.task import TaskBase

BALL = OFFICIAL["basketball"]            # size 7: 0.1195 m radius, 0.62 kg, rebound 0.85, drag and Magnus lift in air

# ---- the FIBA court (this block is the same in every basketball family; a task directory holds one module) ----
# FIBA Official Basketball Rules 2024, Art. 2 (the court: distances from the inner edge of the end line, lines 5 cm
# wide) and its appendix Basketball Equipment (backboard, ring). The ring's centre is 1.575 m from the end line and the
# backboard's face 1.20 m, so the centre is 0.375 m in front of the face and the ring's inner edge 0.150 m (the
# equipment appendix: 151 mm +- 2). Ring metal 16-20 mm: 18 mm. The ring's rebound: the equipment appendix asks for an
# energy absorption of 35 to 50 % of the impact energy: 42.5 % here, a restitution of sqrt(1 - 0.425) = 0.76 (measured
# on this ring with this ball: 0.76, with the contact's nominal value 0.81).
COURT = dict(length=28.0, width=15.0, line=0.05, ring_x=1.575, board_x=1.20, ft_line=5.80, key_half=2.45,
             ft_radius=1.80, three_radius=6.75, three_side=0.90, no_charge=1.25, net_length=0.42)
RING_RESTITUTION, RING_NOMINAL = math.sqrt(1.0 - 0.425), 0.81
WOOD, PAINT = (0.76, 0.60, 0.42, 1), (0.70, 0.30, 0.22, 1)


def _arc(sc, name, cx, cy, radius, a0, a1, n=32, sg=1):
    """A painted arc (5 cm wide) of `radius` round (cx, cy) from angle a0 to a1 (radians, from the basket's +x)."""
    for i in range(n):
        b0, b1 = a0 + (a1 - a0) * i / n, a0 + (a1 - a0) * (i + 1) / n
        sc.line(f"{name}{i}", (cx + sg * radius * math.cos(b0), cy + radius * math.sin(b0)),
                (cx + sg * radius * math.cos(b1), cy + radius * math.sin(b1)), width=COURT["line"])


def build_court(sc, hx: float, hy: float, p: dict, flip: bool = False) -> dict:
    """The FIBA court from one end line to 6 m beyond the centre line, the ring's centre above (hx, hy). The basket
    is towards +x and the court runs towards -x (flip: the other way round). Painted: the boundary lines, the
    restricted area, the free-throw line and circle, the three-point line, the no-charge semi-circle, the centre line
    and circle. Built: the backboard, the ring with its plate, a net and a support (the last two visual only)."""
    C, lw = COURT, COURT["line"]
    sg = -1 if flip else 1
    X = lambda d: hx + sg * d                              # noqa: E731 -- d: from the ring's centre towards the end line
    de = C["ring_x"]                                       # the end line's inner edge
    hw = C["width"] / 2
    sc.box("court", (X(de - 9.0), hy, 0.0002), (11.0, hw + 2.0, 0.0002), rgba=WOOD)
    sc.box("restricted_area", (X(de - C["ft_line"] / 2), hy, 0.0005), (C["ft_line"] / 2, C["key_half"], 0.0002), rgba=PAINT)
    sc.line("end_line", (X(de + lw / 2), hy - hw - lw), (X(de + lw / 2), hy + hw + lw), width=lw)
    for s, tag in ((1, "L"), (-1, "R")):
        sc.line(f"side_line{tag}", (X(de), hy + s * (hw + lw / 2)), (X(de - 20.0), hy + s * (hw + lw / 2)), width=lw)
        sc.line(f"key_line{tag}", (X(de), hy + s * (C["key_half"] - lw / 2)),
                (X(de - C["ft_line"]), hy + s * (C["key_half"] - lw / 2)), width=lw)
        ys = hw - C["three_side"] - lw / 2                 # the three-point line's straight part, then its arc
        da = -math.sqrt(C["three_radius"] ** 2 - (hw - C["three_side"]) ** 2)
        sc.line(f"three_line{tag}", (X(de), hy + s * ys), (X(da), hy + s * ys), width=lw)
        sc.line(f"no_charge_line{tag}", (X(0.0), hy + s * (C["no_charge"] + lw / 2)),
                (X(0.375), hy + s * (C["no_charge"] + lw / 2)), width=lw)
    a = math.asin((hw - C["three_side"]) / C["three_radius"])
    _arc(sc, "three_arc", hx, hy, C["three_radius"] - lw / 2, math.pi - a, math.pi + a, n=48, sg=sg)
    _arc(sc, "no_charge_arc", hx, hy, C["no_charge"] + lw / 2, math.pi / 2, 3 * math.pi / 2, n=20, sg=sg)
    df = de - C["ft_line"]                                 # the free-throw line's edge farthest from the end line
    sc.line("free_throw_line", (X(df + lw / 2), hy - 1.80), (X(df + lw / 2), hy + 1.80), width=lw)
    _arc(sc, "free_throw_circle", X(df), hy, C["ft_radius"] - lw / 2, 0.0, 2 * math.pi, n=40, sg=sg)
    sc.line("centre_line", (X(de - 14.0), hy - hw - lw), (X(de - 14.0), hy + hw + lw), width=lw)
    _arc(sc, "centre_circle", X(de - 14.0), hy, C["ft_radius"] - lw / 2, 0.0, 2 * math.pi, n=40, sg=sg)
    # ---- the basket (the body's +x is towards the end line)
    g = sc.body("hoop", (hx, hy, 0.0), quat=(0.0, 0.0, 0.0, 1.0) if flip else None)
    R = p["ring_inner_diameter_m"] / 2 + p["ring_metal_m"] / 2          # the ring's centre line
    zc = p["ring_height_m"] - p["ring_metal_m"] / 2                      # the ring's top edge is at ring_height_m
    orange = (0.95, 0.35, 0.05, 1)
    ring = dict(HITTABLE, priority=2, solref=bounce_solref(RING_NOMINAL), solimp="0.95 0.99 0.001", condim=3,
                friction=(0.6, 0.005, 0.0001))
    n = 24
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        sc.geom(g, f"hoop_rim{i}", type="capsule", fromto=(R * math.cos(a0), R * math.sin(a0), zc, R * math.cos(a1),
                                                          R * math.sin(a1), zc), size=(p["ring_metal_m"] / 2,),
                rgba=orange, **ring)
    bx = p["ring_centre_to_board_m"]                                     # the backboard's face, from the ring's centre
    sc.geom(g, "hoop_plate", type="box", pos=((R + bx) / 2, 0, zc - 0.004), size=((bx - R) / 2, 0.06, 0.005),
            rgba=orange, **ring)
    bw, bh, bz = p["board_width_m"] / 2, p["board_height_m"] / 2, p["board_bottom_m"]
    sc.geom(g, "hoop_board", type="box", pos=(bx + 0.02, 0, bz + bh), size=(0.02, bw, bh), rgba=(0.92, 0.95, 0.98, 0.45),
            **HITTABLE)
    for nm, y, z, sy, sz in (("top", 0, bz + 2 * bh - 0.025, bw, 0.025), ("bottom", 0, bz + 0.025, bw, 0.025),
                             ("left", bw - 0.025, bz + bh, 0.025, bh), ("right", -bw + 0.025, bz + bh, 0.025, bh),
                             ("sq_top", 0, bz + 0.575, 0.295, 0.025), ("sq_bottom", 0, bz + 0.125, 0.295, 0.025),
                             ("sq_left", 0.27, bz + 0.35, 0.025, 0.225), ("sq_right", -0.27, bz + 0.35, 0.025, 0.225)):
        sc.geom(g, f"hoop_mark_{nm}", type="box", pos=(bx - 0.001, y, z), size=(0.001, sy, sz), rgba=(1, 1, 1, 1), **VISUAL)
    for i in range(12):                                                  # the net: visual only (a declared deviation)
        a0 = 2 * math.pi * i / 12
        for s in (-1, 1):
            a1 = a0 + s * math.pi / 12
            sc.geom(g, f"hoop_net{i}{'ab'[s > 0]}", type="capsule",
                    fromto=(R * math.cos(a0), R * math.sin(a0), zc - 0.01, 0.15 * math.cos(a1), 0.15 * math.sin(a1),
                            zc - C["net_length"]), size=(0.003,), rgba=(1, 1, 1, 0.8), **VISUAL)
    sx = C["ring_x"] + 2.0                                               # the support: 2 m behind the end line, visual
    sc.geom(g, "hoop_support", type="box", pos=(sx, 0, 1.6), size=(0.12, 0.12, 1.6), rgba=(0.2, 0.22, 0.3, 1), **VISUAL)
    sc.geom(g, "hoop_arm", type="box", pos=((bx + 0.04 + sx) / 2, 0, 3.3), size=((sx - bx - 0.04) / 2, 0.06, 0.08),
            rgba=(0.2, 0.22, 0.3, 1), **VISUAL)
    return dict(x=hx, y=hy, z=p["ring_height_m"], inner_radius=p["ring_inner_diameter_m"] / 2, end_line_x=X(de),
                free_throw_line_x=X(df), board_face_x=X(bx))

# ---- end of the court block ----


# ---- Art. 25, travelling (this block is the same in layup, dunk, catch-and-shoot and basketball-dribble) ----
class Foot:
    """One foot and the floor: lifted once it has not touched the ground for `gap` seconds, a touchdown at its next
    contact. update() once per physics step returns "lift", "down" or None. The robot starts standing."""

    def __init__(self, ref, side: str, gap: float):
        self.ref, self.sel, self.gap = ref, ref.part(f"{side}_foot"), gap
        self.down, self.t_last = True, None        # (t_last None: no contact seen yet; the model settles onto the
        #                                             floor in the first milliseconds, which is not a lift)

    def update(self) -> str | None:
        ref = self.ref
        if ref.touching(self.sel, ref.ground):
            self.t_last = ref.time
            if not self.down:
                self.down = True
                return "down"
        elif self.down and self.t_last is not None and ref.time - self.t_last >= self.gap:
            self.down = False
            return "lift"
        return None

    def state(self) -> list:
        return [self.down, self.t_last]


class Travel:
    """FIBA Art. 25.2.1 while a hand holds the ball. Mode "pivot" (the ball gained while standing on both feet): the
    first foot lifted makes the other the pivot foot; once the pivot foot has left the floor no foot may come back to
    it before the ball is released, and the pivot foot may not slide. Mode "steps" (the ball gained while moving): at
    most `max_steps` touchdowns, never the same foot twice in a row (two feet landing within `gap` seconds are one
    step). A foot that stays on the floor may not slide more than `slide` from where it stood or was put down (in
    "pivot" mode: both feet until one is lifted, then the pivot foot), so a shuffle without a lift is travelling too.
    update() once per physics step returns the violation, or None."""

    def __init__(self, w, ref, gap: float, max_steps: int = 2, slide: float = 0.20):
        self.w, self.ref, self.gap, self.max_steps, self.slide = w, ref, gap, max_steps, slide
        self.feet = {s: Foot(ref, s, gap) for s in ("left", "right")}
        self.mode = None                  # None: the ball is not held
        self.pivot, self.pivot_xy, self.pivot_up = None, None, False
        self.steps: list = []             # [time, "left" | "right" | "both"]
        self.anchor: dict = {"left": None, "right": None}       # where a foot on the floor stood or was put down

    def start(self, mode: str | None = None) -> None:
        """The ball is in the hand from now: "pivot" if both feet are on the floor, else "steps" (or as given)."""
        both = all(f.down for f in self.feet.values())
        self.mode = mode or ("pivot" if both else "steps")
        self.pivot, self.pivot_xy, self.pivot_up, self.steps = None, None, False, []
        self.anchor = {s: (self._xy(s) if f.down else None) for s, f in self.feet.items()}

    def stop(self) -> str | None:
        """The ball has left the hand. Returns a violation the last step made, if any."""
        bad = self._same_foot(final=True) if self.mode == "steps" else None
        self.mode = None
        return bad

    def _xy(self, side: str) -> list:
        return [round(float(x), 4) for x in self.w.d.site_xpos[self.w.robot.foot_site[side]][:2]]

    def _same_foot(self, final: bool = False) -> str | None:
        st = self.steps
        if len(st) >= 2 and st[-1][1] == st[-2][1] and (final or self.ref.time - st[-1][0] > self.gap):
            return "travelling: the same foot touched the floor twice in a row"
        return None

    def update(self) -> str | None:
        ev = {s: f.update() for s, f in self.feet.items()}
        if self.mode is None:
            return None
        t = self.ref.time
        for s in ("left", "right"):                       # a foot on the floor stays where it is
            if ev[s] == "down":
                self.anchor[s] = self._xy(s)
            elif ev[s] == "lift":
                self.anchor[s] = None
            elif self.anchor[s] is not None and (self.mode == "steps" or self.pivot is None):
                x, y = self._xy(s)
                if math.hypot(x - self.anchor[s][0], y - self.anchor[s][1]) > self.slide:
                    return "travelling: a foot slid along the floor"
        if self.mode == "pivot":
            for s, o in (("left", "right"), ("right", "left")):
                if ev[s] == "lift":
                    if self.pivot is None:
                        self.pivot, self.pivot_xy = o, self._xy(o)
                    elif s == self.pivot:
                        self.pivot_up = True
                elif ev[s] == "down" and self.pivot_up:
                    return "travelling: a foot came back to the floor after the pivot foot had left it"
            if self.pivot is not None and not self.pivot_up:
                x, y = self._xy(self.pivot)
                if math.hypot(x - self.pivot_xy[0], y - self.pivot_xy[1]) > self.slide:
                    return "travelling: the pivot foot moved"
            return None
        for s in ("left", "right"):
            if ev[s] == "down":
                st = self.steps
                if st and t - st[-1][0] <= self.gap and st[-1][1] not in (s, "both"):
                    st[-1][1] = "both"
                else:
                    st.append([round(t, 4), s])
                    if len(st) > self.max_steps:
                        return "travelling: a third step with the ball in the hand"
        return self._same_foot()

    def state(self) -> list:
        return [self.mode, self.pivot, self.pivot_xy, self.pivot_up, self.steps, self.anchor,
                [self.feet[s].state() for s in ("left", "right")]]
# ---- end of the travelling block ----

# ---- the two-hand hold (the H1-2's own Inspire hands, rfo.realhand "inspire"; the same in free-throw,
# catch-and-shoot, dunk and dunk-between-legs) ----
# A two-handed hold as for a chest pass or a two-handed set shot, the hands open (the fingers straight): the palms on
# the ball's two sides, the fingers up and forwards beside it, and the arms pressing the palms in: the start command
# (hold_targets) turns the shoulders SQUEEZE_RAD further in (roll and yaw) than TOUCH_LEFT / TOUCH_RIGHT, the pose in
# which the palms just clear the ball, so the shoulder servos squeeze it; nothing else holds it but the hands' contact
# and friction. On the Inspire the open thumb lies a little proud of the palm, so the ball bears on the two thumbs'
# proximal and middle links (measured with the core of 10-22, H2-class arms, self-collision on: about 57 N normal per
# hand, half the friction used, the elbows 8.6 cm off the torso; with the fingers closed over the ball it rests on
# the thumbs alone, about 8 cm lower). HOLD_LEFT / HOLD_RIGHT: where the arms stand under that squeeze with the
# ball's centre at BALL_AT (ahead of and above the pelvis' start): the settled hold, measured, so the start is at
# rest. The arms' 7 joints: shoulder pitch, roll, yaw, elbow pitch, roll, wrist pitch, yaw.
BALL_AT = (0.39, 0.0, 1.13)
TOUCH_LEFT = (-0.43, 0.3529, -1.0318, 0.4546, 0.2074, -0.44, 1.24)
TOUCH_RIGHT = (-0.4301, -0.3529, 1.0321, 0.4546, -0.2073, -0.44, -1.24)
HOLD_LEFT = (-0.3867, 0.3303, -1.0768, 0.5032, 0.1042, -0.4638, 1.2792)
HOLD_RIGHT = (-0.3867, -0.3303, 1.0768, 0.5032, -0.1042, -0.4638, -1.2792)
SQUEEZE_RAD = 0.10


def hold_targets(side: str) -> np.ndarray:
    """The squeezing targets of an arm: the touching pose with the shoulder's roll and yaw SQUEEZE_RAD further in."""
    q = np.array(TOUCH_RIGHT if side == "right" else TOUCH_LEFT, float)
    s = 1.0 if side == "right" else -1.0
    q[1] += s * SQUEEZE_RAD
    q[2] += s * SQUEEZE_RAD
    return q


def ball_in_hands(w, arms_only: bool = False) -> None:
    """The arms in the settled hold, the start command the squeezing targets, the hands open, and, unless arms_only,
    the ball between the palms where the squeeze holds it."""
    r, d = w.robot, w.d
    a = w.L.ARMS.start
    for idx, side in ((slice(a, a + 7), "left"), (slice(a + 7, a + 14), "right")):
        d.qpos[r.qadr[idx]] = HOLD_LEFT if side == "left" else HOLD_RIGHT
        r.arb.q_a[idx] = r.arb.q_b[idx] = hold_targets(side)
    mujoco.mj_kinematics(w.m, d)
    if arms_only:
        return
    w.put("ball", BALL_AT)
    mujoco.mj_forward(w.m, d)
# ---- end of the hold ----


class Task(TaskBase):
    name = "dunk"
    title = "Basketball: two-hand dunk, lowered ring"
    category = "basketball-and-rackets"
    robot = "unitree_h1"
    rulebook = ("FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix "
                "(backboard, ring, size-7 ball), Art. 14 (control: a player holds a live ball), Art. 15 (a dunk: the "
                "ball forced downwards into the basket with one or both hands; here both), Art. 16 (goal; a ball that "
                "passes through the basket from below is a violation), Art. 25 (travelling), Art. 36 (technical foul: "
                "hanging on the ring); FIBA Mini-Basketball Rules (the ring at 2.60 m)")
    deviations = [
        "Basketball Equipment (basket): the basket is lowered: the ring's top edge is {ring_height_m} m above the "
        "floor, below FIBA Mini-Basketball's 2.60 m (FIBA's own ring: 3.05 m), set at the robot's measured own-motor "
        "reach (H1-2 with H2-class leg actuators), at the edge of the robot's reach; the "
        "full-size backboard keeps its size and its height relative to the ring (lower edge {board_bottom_m} m). "
        "The ball stays the size-7 ball.",
        "Art. 3 (equipment, the hands): the hands are the H1-2's own Inspire five-finger hands (six drives: four "
        "fingers, the thumb's flexion and rotation), closed by one command per hand; the ball is held by the hands' "
        "contact and friction alone (the open palms pressed on its sides by the arms) and "
        "slips or drops when they do not hold it.",
        "Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not "
        "slow the ball. The ball is through the basket when its centre has gone down through the ring's plane inside "
        "the ring and on to one ball diameter below it.",
        "Art. 25.2.1: you start standing with the ball in the hands and are judged as a player who has just ended a "
        "dribble while moving: two steps are allowed (a standing player would have a pivot foot instead). After the "
        "two steps no foot may touch the floor again while the ball is held: pivoting after a stop is not offered.",
        "Art. 24 (dribble): there is no dribble in this task; the ball stays in the hands from the start until the "
        "dunk, and a ball that touches the floor before the dunk ends the attempt.",
        "Art. 36: hanging on the ring is judged by time: the robot may touch the basket (ring, its plate, the "
        "backboard) for at most {basket_touch_s} s in all.",
        "The landing (on the feet, standing {stand_s} s) is this task's own requirement; the rule book asks nothing "
        "of a player after a goal.",
    ]
    time_limit_s = 15.0
    start = (0.0, 0.0, 0.0)
    stages = ["dunk", "stand"]
    fall_z = 0.35                       # (set from params in build)
    params = dict(ring_height_m=2.39, ring_inner_diameter_m=0.45, ring_metal_m=0.018, ring_centre_to_board_m=0.375,
                  board_width_m=1.80, board_height_m=1.05, board_bottom_m=2.24, start_to_ring_m=0.75,
                  touch_gap_s=0.03, basket_touch_s=0.30, max_steps=2, step_gap_s=0.03, foot_slide_m=0.20, stand_s=1.0,
                  stand_speed_m_s=0.35, stand_upright_cos=0.94, fall_z_m=0.35)

    sentence = ("Dunk the basketball with both hands: holding it in your two hands, jump, force it down through the "
                "ring from above with both hands on it, and land on your feet.")
    rules = ("The basket (official size, lowered): a rigid ring of {ring_inner_diameter_m} m inner diameter "
             "({ring_metal_m} m metal), "
             "its top edge {ring_height_m} m above the floor, its centre {ring_centre_to_board_m} m in front of a "
             "backboard {board_width_m} m wide and {board_height_m} m high whose lower edge is {board_bottom_m} m "
             "above the floor. The ball is a size-7 basketball (" + f"{2 * BALL['radius']:.3f} m across, "
             f"{BALL['mass']:.2f} kg, it keeps {BALL['bounce']:.2f} of its speed in a bounce on the floor" + "). Your "
             "hands are five-finger hands; the ball starts held between them, the palms pressed on its sides and the "
             "hands open, and only the hands' contact and friction hold it; it can slip out. A hand is "
             "on the ball while it touches the ball, gaps shorter than {touch_gap_s} s included (a hand is the palm, "
             "the fingers and the wrist); the ball is in your hands while at least one hand is on it. The ball must stay in your hands from the start until its "
             "centre has gone down into the ring: no dribble, no throw, no drop. The dunk: the ball's centre goes down "
             "through the ring's plane inside the ring while both hands are on the ball, and on down to one ball "
             "diameter below the ring (in the hands, or let go once its centre is inside the ring). The ball may not "
             "pass up through the ring first: a ball whose centre comes up through the ring from below is a "
             "violation. Travelling: while the ball is in your hands you may take at most {max_steps} steps. A step is "
             "a foot touching the floor after it has been off it for at least {step_gap_s} s; both feet landing "
             "within {step_gap_s} s of each other are one step; the same foot may not touch down twice in a row; a "
             "foot on the floor may not slide more than {foot_slide_m} m from where it stood or was put down; after "
             "that no foot may touch the floor again until the ball is through the ring. Hanging on the ring: you may "
             "touch the basket (the ring, its plate, the backboard) with any part of you for at most "
             "{basket_touch_s} s in all. After the dunk let go of the ball (no hand on it) and stand: for {stand_s} s "
             "without a break only "
             "your feet touch the ground, your torso is upright (the cosine of its tilt at least {stand_upright_cos}) "
             "and your pelvis moves slower than {stand_speed_m_s} m/s. Then you have succeeded. You fail if the ball "
             "leaves your hands before its centre has entered the ring; if the ball touches the floor before the "
             "dunk; if the ball goes through the ring after an entry at which not both hands were on it (a one-hand "
             "dunk, a tip, a shot or a drop); if, let go inside the ring, it touches the floor without having gone "
             "through; if the ball comes up through the ring from below; if you travel; if you hang on the ring; if "
             "you fall at any time (a fall: your pelvis lower than {fall_z_m} m above the floor, or any part of you "
             "other than your feet on the floor); or after "
             "{time_limit_s} s.")
    venue = ("A FIBA court. You stand under the basket's front, facing it (+x), inside the no-charge semi-circle: the "
             "point under the ring's centre is {start_to_ring_m} m ahead of your pelvis, the backboard's face "
             "{ring_centre_to_board_m} m beyond it. The ring's top edge is {ring_height_m} m above the floor. The ball "
             "is held between your two hands in front of your chest, its centre 1.13 m above the floor and 0.39 m "
             "ahead of your pelvis: the hands open (grip values 0, the fingers straight), the palms on its two sides "
             "(on these hands it bears on the two thumbs, which lie a little proud of the palms), and the arms "
             "pressing the palms in (the start command's shoulder roll and yaw are a little further in than the arms "
             "stand: the difference is the squeeze). A grip value is that "
             "hand's closure command (0 open, 1 every finger and thumb joint closing towards its closed angle; a "
             "finger stops on what it touches).")
    difficulty = ("With both arms up and the ball held between the hands its centre is about 2.19 m above the "
                  "floor; the ring is at 2.39 m, so the whole 67 kg body has to rise about 0.4 m (the ball's centre to "
                  "about 2.53 m) while the hands keep the ball through the jump's accelerations, and the hands, wrists and forearms have to go "
                  "into a ring only 0.21 m wider than the ball, then the robot has to come down on its feet. The robot "
                  "has a walking gait and nothing that jumps or lands; the built-in walking gait steps on the spot "
                  "even at a zero command, so while the ball is in your hands its steps are counted like any others.")

    def build(self, sc):
        p = self.p
        self.fall_z = p["fall_z_m"]
        hx = p["start_to_ring_m"]
        self.hoop = build_court(sc, hx, 0.0, p)
        sc.ball("ball", "basketball", (0.42, 0.0, 1.28))         # not grippable: the hands hold it by contact
        for side in ("left", "right"):
            sc.real_hands[side] = "inspire"
        sc.camera("venue", (hx - 3.2, -4.4, 2.6), (hx - 0.3, 0.0, 1.8), fovy=55)

    def reset(self, w):
        ball_in_hands(w)

    def referee_reset(self, w, ref):
        p, h = self.p, self.hoop
        self.ball = ref.geoms(body="ball")
        self.hands = {s: ref.part(f"{s}_hand") for s in ("left", "right")}
        self.robot = ref.part("robot")
        self.basket = ref.geoms(prefix="hoop_rim") | ref.geoms(names=["hoop_plate", "hoop_board"])
        travel = Travel(w, ref, p["step_gap_s"], int(p["max_steps"]), p["foot_slide_m"])
        travel.start("steps")
        self.trackers = {"hoop": HoopPass((h["x"], h["y"], h["z"]), h["inner_radius"], BALL["radius"]),
                         "up": Crossing((0, 0, 1), h["z"], direction=1), "travel": travel,
                         "touch": {"left": 0.0, "right": 0.0}, "entry_hands": None, "released": None,
                         "dunked": None, "basket_ph": 0}

    def on_ball(self, ref) -> dict:
        """Which hands are on the ball now (touching it, gaps shorter than touch_gap_s included)."""
        t = self.trackers["touch"]
        return {s: t[s] is not None and ref.time - t[s] <= self.p["touch_gap_s"] + 1e-9 for s in ("left", "right")}

    def _off_axis(self, b) -> float:
        return math.hypot(b[0] - self.hoop["x"], b[1] - self.hoop["y"])

    def substep(self, w, ref):
        tr, h, p = self.trackers, self.hoop, self.p
        for s in ("left", "right"):
            if ref.touching(self.hands[s], self.ball):
                tr["touch"][s] = round(ref.time, 4)
        on = self.on_ball(ref)
        if ref.touching(self.robot, self.basket):
            tr["basket_ph"] += 1
            if tr["basket_ph"] * w.PHYS_DT > p["basket_touch_s"] + 1e-9:
                return ref.fail("hanging on the ring: the basket touched for more than the time allowed",
                                parts=sorted(ref.parts_touching(self.basket)))
        bad = tr["travel"].update()
        if tr["dunked"] is not None:
            if tr["released"] is None and not any(on.values()):
                tr["released"] = round(ref.time, 4)
            return
        if bad:
            return ref.fail(bad, steps=tr["travel"].steps)
        b = w.pos("ball")
        was_in = tr["hoop"].entered
        ev = tr["hoop"].update(b)
        x = tr["up"].update(b)
        if x is not None and not was_in and self._off_axis(x) < h["inner_radius"]:
            return ref.fail("the ball came up through the ring from below")
        if ev == "enter":
            tr["entry_hands"] = sorted(s for s in ("left", "right") if on[s])
        elif ev == "through":
            if tr["entry_hands"] != ["left", "right"]:
                return ref.fail("the ball went through the ring without both hands on it at the entry",
                                hands=tr["entry_hands"])
            tr["dunked"] = round(ref.time, 4)
            bad = tr["travel"].stop()
            if bad:
                return ref.fail(bad, steps=tr["travel"].steps)
            ref.stage("dunk")
            return
        if tr["released"] is None and not any(on.values()):
            tr["released"] = round(ref.time, 4)
            if not tr["hoop"].entered:
                return ref.fail("the ball left the hands before the dunk")
        if ref.touching(self.ball, ref.ground):
            if tr["released"] is not None:
                return ref.fail("the ball did not go through the ring")
            return ref.fail("the ball touched the floor before the dunk")

    def step(self, w, ref):
        tr, p = self.trackers, self.p
        ref.metrics["ball_height_m"] = round(float(w.pos("ball")[2]), 3)
        ref.metrics["basket_touch_s"] = round(tr["basket_ph"] * w.PHYS_DT, 3)
        ok = (ref.has("dunk") and tr["released"] is not None
              and ref.standing(max_speed=p["stand_speed_m_s"], min_upright=p["stand_upright_cos"]))
        if ref.hold("stand", ok, p["stand_s"]):
            if ref.stage("stand"):
                ref.succeed()

    def privileged(self, w):
        tr = self.trackers
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(), "hoop": self.hoop,
                "hands_on_ball": self.on_ball(w.ref), "steps": len(tr["travel"].steps),
                "dunked": tr["dunked"] is not None, "basket_touch_s": round(tr["basket_ph"] * w.PHYS_DT, 3)}
