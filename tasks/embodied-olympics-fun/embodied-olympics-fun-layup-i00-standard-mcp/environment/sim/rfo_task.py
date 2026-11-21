"""Basketball layup (FIBA): the ball starts held in the H1-2's own two Inspire hands (rfo.realhand: five fingers each;
contact and friction only, nothing welded), resting on the upturned right hand with the left hand on its side; with it
take at most two steps towards the basket, jump, let go of it in the air close to the ring, and it enters the basket
from above. Official court, backboard, ring and size-7 ball; the Unitree H1-2. The court, travelling and two-hand hold
blocks are copied byte-identically from basketball-dribble."""
import math
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from rfo.referee import Crossing, Flights, HoopPass
from rfo.scene import HITTABLE, OFFICIAL, VISUAL, bounce_solref
from rfo.task import TaskBase

BALL = OFFICIAL["basketball"]            # size 7: 0.1195 m radius, 0.62 kg, rebound 0.85, drag and Magnus lift in air
FALL_Z = 0.35

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


# ---- the two-hand hold at the start (the H1-2's Inspire hands) ----
# The ball is held as a player carries it before a play: resting on the upturned right hand, the fingers spread
# forwards under it and curled a little round it (closure HOLD_CLOSURE), the left hand on its left side, the palm on
# it. HOLD (each arm's joints, numeric inverse kinematics of both arms) puts the right palm under the ball and the left
# palm on its side, each 2 mm into the ball's surface (the palm's face is PALM_FACE from the hand's grasp centre on a
# ball this size); the start command keeps those arm targets and closures; nothing presses the ball but its weight and
# the hands' own drives.
HOLD = {"right": np.array([-0.4674, 0.2556, -0.335, 1.5041, 1.3391, -0.2658, 1.0833]),
        "left": np.array([-0.2102, 0.0481, -0.724, 0.4173, 0.0342, -0.47, 0.7949])}
HOLD_CLOSURE = {"right": 0.3, "left": 0.0}
PALM_FACE, PALM_PRESS = 0.0265, 0.002
# HOLD has the right upper arm 1.8 mm inside the torso's hull (the robot's self-collision, world.py): the right arm
# starts START_ROLL (shoulder roll) off the chest, its target stays HOLD, so the servo lays it against the chest (at
# most 0.02 mm deep; the ball as before).
START_ROLL = -0.02


def ball_in_hands(w) -> None:
    """t = 0: both arms in the hold, the ball on the upturned right palm (its centre PALM_FACE - PALM_PRESS less than a
    ball radius out of the palm, along the palm's normal), the closures set; the start command keeps them."""
    r, d = w.robot, w.d
    a = w.L.ARMS.start
    for i, side in enumerate(("left", "right")):
        d.qpos[r.qadr[a + 7 * i:a + 7 * i + 7]] = HOLD[side]
        r.arb.q_a[a + 7 * i:a + 7 * i + 7] = r.arb.q_b[a + 7 * i:a + 7 * i + 7] = HOLD[side]
        w.hands.cmd[side] = HOLD_CLOSURE[side]
    d.qpos[r.qadr[a + 8]] += START_ROLL                 # the right shoulder roll off the chest (START_ROLL)
    mujoco.mj_kinematics(w.m, d)
    c, R = w.grasp_frame("right")
    w.put("ball", c + R[:, 0] * (BALL["radius"] - PALM_FACE + PALM_PRESS))


# The palm-ball contact (an explicit pair with the H1-2 model's own collision hull of the Inspire hand base, the palm:
# PALM_GEOM). With the ball's own contact (its rule-book rebound, 0.85, a lightly damped spring) a ball on a palm
# rattles off it. The palm is the soft part of a hand and absorbs the ball: a critically damped contact (palm rebound
# 0.12, measured head-on at 3 m/s), with the elliptic friction cones and impratio 100 of every world with real hands
# (rfo.realhand). The fingers' and the thumb's rubber pads keep their own contact (rfo.realhand: friction 1.0, stiff,
# critically damped); the floor, the ring and the backboard keep the ball's own (rebound 0.85).
PALM_SOLREF, PALM_SOLIMP, PALM_MU, PALM_REBOUND = "0.005 1", "0.99 0.999 0.001", 0.7, 0.12
PALM_GEOM = "{side}_wrist_yaw_link_sc0"        # the hand base's hull in the H1-2 model (realhand.inspire_palm_geom)
# ---- end of the hold ----


class Task(TaskBase):
    name = "layup"
    title = "Basketball: layup"
    category = "basketball-and-rackets"
    robot = "unitree_h1"
    rulebook = ("FIBA Official Basketball Rules 2024: Art. 2 (court, no-charge semi-circle), Art. 3 and the Basketball "
                "Equipment appendix (backboard, ring, size-7 ball), Art. 13 (how the ball is played), Art. 14 (control: "
                "a player holds a live ball), Art. 16 (goal), Art. 25 (travelling)")
    deviations = [
        "the player's hands: the H1-2's own Inspire five-finger hands (six drives each: four fingers, the thumb's "
        "flexion and rotation; fingertip forces 20 N, the thumb 30 N), each closed by one command; the ball is held "
        "in the two hands by contact and friction alone (nothing is welded) and can slip or drop; it is let go when no "
        "hand has been on it for {touch_gap_s} s.",
        "Art. 3 (equipment, the hand): the palm is modelled as the soft part of a hand: it absorbs the ball (a ball "
        "thrown at a still palm keeps "
        f"{PALM_REBOUND:.2f} of its speed) instead of bouncing it like the floor ({BALL['bounce']:.2f}); with the "
        "ball's own rebound a ball on a palm rattles off it. The fingers' rubber pads absorb it too (critically "
        "damped); the floor, the ring and the backboard keep the ball's rule-book rebound.",
        "Art. 13: while the ball is in your hands it may touch no part of you but the hands (no ball held against the "
        "chest or between the forearms); intent cannot be judged.",
        "Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not "
        "slow the ball. A goal is judged at the ring: the ball's centre down through the ring's plane and on to one "
        "ball diameter below it.",
        "Art. 25.2.1: you start standing with the ball in the hands and are judged as a player who has just ended a "
        "dribble while moving: two steps are allowed (a standing player would have a pivot foot instead), since no "
        "dribble precedes the layup here. After the two steps no foot may touch the floor again while the ball is "
        "held: pivoting after a stop is not offered.",
        "The layup itself is not defined by the rule book: here it is a shot let go in the air (after a real "
        "take-off) with the ball inside the no-charge semi-circle's radius of the ring ({layup_radius_m} m, "
        "Art. 2.4.7); a shot from further out or from the floor is not a layup.",
        "One attempt, no opponent, no rebound, no dribble: the ball leaving the hands is the shot, and touching it "
        "after that ends the attempt.",
    ]
    time_limit_s = 15.0
    start = (0.0, 0.0, 0.0)
    stages = ["approach", "release in the air", "through the ring"]
    fall_z = FALL_Z
    params = dict(ring_height_m=3.05, ring_inner_diameter_m=0.45, ring_metal_m=0.018, ring_centre_to_board_m=0.375,
                  board_width_m=1.80, board_height_m=1.05, board_bottom_m=2.90, start_to_ring_m=3.0,
                  layup_radius_m=1.25, max_steps=2, step_gap_s=0.03, foot_slide_m=0.20, air_min_s=0.05,
                  takeoff_speed_m_s=0.5, retouch_grace_s=0.05, touch_gap_s=0.03)

    sentence = ("Make a layup: with the basketball held in your two hands take at most two steps towards the "
                "basket, jump, and let go of the ball in the air close to the ring so that it enters the basket from "
                "above.")
    rules = ("The official basket: a rigid ring of {ring_inner_diameter_m} m inner diameter ({ring_metal_m} m metal), "
             "its top edge {ring_height_m} m above the floor, its centre {ring_centre_to_board_m} m in front of a "
             "backboard {board_width_m} m wide and {board_height_m} m high whose lower edge is {board_bottom_m} m "
             "above the floor. The ball is a size-7 basketball (" + f"{2 * BALL['radius']:.3f} m across, "
             f"{BALL['mass']:.2f} kg, it keeps {BALL['bounce']:.2f} of its speed in a bounce on the floor" + "); it "
             "flies in air (drag and spin lift). Your hands are five-finger hands, each closed by its grip value (0 "
             "open, 1 closed); they hold the ball only by contact and friction: it starts resting on your upturned "
             "right hand, the fingers curled a little round it, your left hand on its side, and it can slip or drop. "
             "A hand is the palm, the fingers, the thumb and the wrist; a hand is on the ball while it touches the "
             "ball, gaps shorter than "
             "{touch_gap_s} s included; the ball is in your hands while at least one hand is on it, and you let go of "
             "it at the last touch of a hand after which no hand has been on it for {touch_gap_s} s. While the ball is "
             "in your hands it may touch no part of you but your hands, and it may not touch the floor. Travelling: "
             "while the ball is in your hands you may take at most {max_steps} steps. A step is a foot touching the "
             "floor after it has been off it for at least {step_gap_s} s; both feet landing within {step_gap_s} s of "
             "each other are one step; the same foot may not touch down twice in a row, and a foot on the floor may "
             "not slide more than {foot_slide_m} m from where it stood or was put down (a shuffle is travelling). "
             "After that no foot may touch the floor again until you have let go of the ball. The release: at the "
             "moment you let go you must be in the air: nothing of you has touched anything but the ball for at least "
             "{air_min_s} s, after a take-off at which your pelvis was moving upwards at {takeoff_speed_m_s} m/s or "
             "more; and the ball's centre must be within {layup_radius_m} m (horizontally) of the ring's centre, the "
             "radius of the no-charge semi-circle painted under the basket. You succeed when, after that release, the "
             "ball's centre goes down through the ring's plane inside the ring and on down to one ball diameter below "
             "it (off the backboard or not). You fail if you travel; if the ball touches the floor or a part of you "
             "other than a hand while it is in your hands; if you let go of the ball (on purpose or because it "
             "slipped) with something of you on the floor, without a take-off, or further from the ring; if any part "
             "of you touches the ball more than {retouch_grace_s} s after you let go of it (no catching it again); if "
             "the ball touches the floor before it is through the ring; if the ball's centre comes up through the "
             "ring from below; if you fall before the ball is through (a fall: your pelvis lower than "
             f"{FALL_Z} m above the floor, or any part of you other than your feet on the floor)" + "; or after "
             "{time_limit_s} s.")
    venue = ("A FIBA court. You stand in the restricted area facing the basket (+x); the point under the ring's "
             "centre is {start_to_ring_m} m ahead of your pelvis, the backboard's face {ring_centre_to_board_m} m "
             "beyond it. Painted on the floor: the restricted area, the free-throw line and circle behind you, and "
             "the no-charge semi-circle ({layup_radius_m} m round the point under the ring, open towards the end "
             "line). The ball rests on your upturned right hand in front of your chest, its centre about 1.1 m above "
             "the floor, 0.39 m ahead of your pelvis and 0.06 m to its right; the right hand's fingers point forwards "
             "under it, curled a little round it (grip value 0.3), the left hand's palm is on its left side, open "
             "(grip value 0); the start command keeps that hold. A grip value is that hand's closure command: 0 opens "
             "the fingers, 1 closes every finger and the thumb until they meet something.")
    difficulty = ("Two steps and a jump have to carry a 67 kg body almost two metres while the hands keep the ball "
                  "through every footfall, and the release comes in the air, about a metre below a ring that is "
                  "0.21 m wider than the ball: the hands have to let it go with the speed of the arms' own push, "
                  "since a hand does not bounce it. The robot has a walking gait and nothing that "
                  "jumps or lands; the built-in walking gait steps on the spot even at a zero command, so while the "
                  "ball is in your hands its steps are counted like any others.")

    def build(self, sc):
        p = self.p
        hx = p["start_to_ring_m"]
        self.hoop = build_court(sc, hx, 0.0, p)
        sc.ball("ball", "basketball", (0.42, 0.0, 1.28))         # nothing is grippable: the hands hold it
        sc.real_hands["left"] = sc.real_hands["right"] = "inspire"   # the H1-2's own hands (rfo.realhand)
        for side in ("left", "right"):
            ET.SubElement(sc.root.find("contact"), "pair", name=f"palm_ball_{side}", geom1="ball",
                          geom2=PALM_GEOM.format(side=side), condim="6",
                          friction=f"{PALM_MU} {PALM_MU} 0.003 {BALL['roll']} {BALL['roll']}", solref=PALM_SOLREF,
                          solimp=PALM_SOLIMP)
        sc.camera("venue", (hx - 3.4, -4.6, 2.6), (hx - 0.8, 0.0, 1.7), fovy=55)

    def reset(self, w):
        ball_in_hands(w)

    def referee_reset(self, w, ref):
        p, h = self.p, self.hoop
        self.ball = ref.geoms(body="ball")
        self.hand = {s: ref.part(f"{s}_hand") for s in ("left", "right")}
        self.robot = ref.part("robot")
        self.body = self.robot & ~ref.part("hands")
        travel = Travel(w, ref, p["step_gap_s"], int(p["max_steps"]), p["foot_slide_m"])
        travel.start("steps")
        self.trackers = {"hoop": HoopPass((h["x"], h["y"], h["z"]), h["inner_radius"], BALL["radius"]),
                         "up": Crossing((0, 0, 1), h["z"], direction=1),
                         "flights": Flights(ref, min_air=p["air_min_s"], also_allowed=self.ball),
                         "travel": travel, "takeoff_vz": None, "touch": {"left": 0.0, "right": 0.0}, "last": None,
                         "released": None}

    def on_ball(self, ref) -> dict:
        """Which hands are on the ball now (touching it, gaps shorter than touch_gap_s included)."""
        t = self.trackers["touch"]
        return {s: t[s] is not None and ref.time - t[s] <= self.p["touch_gap_s"] + 1e-9 for s in ("left", "right")}

    def _off_axis(self, b) -> float:
        return math.hypot(b[0] - self.hoop["x"], b[1] - self.hoop["y"])

    def substep(self, w, ref):
        tr, p, h = self.trackers, self.p, self.hoop
        fl = tr["flights"]
        was_air = fl.air
        fl.update()
        if fl.air and not was_air and tr["released"] is None:
            tr["takeoff_vz"] = round(float(w.d.qvel[w.robot.fv + 2]), 4)
        bad = tr["travel"].update()
        b = w.pos("ball")
        was_in = tr["hoop"].entered
        ev = tr["hoop"].update(b)
        x = tr["up"].update(b)
        if x is not None and not was_in and self._off_axis(x) < h["inner_radius"]:
            return ref.fail("the ball came up through the ring from below")
        if tr["released"] is None:
            now = [s for s in ("left", "right") if ref.touching(self.hand[s], self.ball)]
            for s in now:
                tr["touch"][s] = round(ref.time, 4)
            if now:                                   # the state at the latest touch: the release, if it is the last
                air = fl.air and fl.cur is not None
                tr["last"] = {"t": round(ref.time, 4), "ball": [round(float(v), 4) for v in b],
                              "air_s": round(ref.time - fl.cur["t0"], 4) if air else None,
                              "takeoff_vz": tr["takeoff_vz"] if air else None}
            if bad:
                return ref.fail(bad, steps=tr["travel"].steps)
            if ref.touching(self.ball, self.body):
                return ref.fail("the ball touched a part of you other than a hand while in your hands",
                                parts=sorted(ref.parts_touching(self.ball) - {"left_hand", "right_hand"}))
            if ref.touching(self.ball, ref.ground):
                return ref.fail("the ball touched the floor while in your hands")
            if any(self.on_ball(ref).values()):
                if self._off_axis(b) <= p["layup_radius_m"]:
                    ref.stage("approach")
                return
            last = tr["last"]
            if last is None:                          # (no hand has touched it since the start: it left them now)
                air = fl.air and fl.cur is not None
                last = {"t": round(ref.time, 4), "ball": [round(float(v), 4) for v in b],
                        "air_s": round(ref.time - fl.cur["t0"], 4) if air else None,
                        "takeoff_vz": tr["takeoff_vz"] if air else None}
            tr["released"] = last["t"]
            bad = tr["travel"].stop()
            if bad:
                return ref.fail(bad)
            d = self._off_axis(last["ball"])
            if last["air_s"] is None or last["air_s"] < p["air_min_s"]:
                return ref.fail("the ball was let go with the robot not in the air", air_s=last["air_s"])
            if last["takeoff_vz"] is None or last["takeoff_vz"] < p["takeoff_speed_m_s"]:
                return ref.fail("the ball was let go in the air without a take-off", takeoff_vz=last["takeoff_vz"])
            if d > p["layup_radius_m"]:
                return ref.fail("the ball was let go too far from the ring", ball_to_ring_m=round(d, 3))
            ref.stage("approach")
            ref.stage("release in the air", ball_height_m=round(float(last["ball"][2]), 3),
                      ball_to_ring_m=round(d, 3), air_s=last["air_s"], takeoff_speed_m_s=last["takeoff_vz"])
            if ev == "through" and ref.stage("through the ring"):
                ref.succeed()
            return
        if ref.time - tr["released"] > p["retouch_grace_s"] and ref.touching(self.ball, self.robot):
            ref.fail("the ball was touched again after the release", parts=sorted(ref.parts_touching(self.ball)))
        elif ref.touching(self.ball, ref.ground):
            ref.fail("the ball touched the floor")
        elif ev == "through":
            if ref.stage("through the ring"):
                ref.succeed()

    def step(self, w, ref):
        ref.metrics["pelvis_to_ring_m"] = round(self._off_axis(w.pelvis()), 3)
        ref.metrics["ball_height_m"] = round(float(w.pos("ball")[2]), 3)
        ref.metrics["steps"] = len(self.trackers["travel"].steps)

    def privileged(self, w):
        tr = self.trackers
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(), "hoop": self.hoop,
                "hands_on_ball": self.on_ball(w.ref), "steps": len(tr["travel"].steps),
                "airborne": bool(tr["flights"].air), "released": tr["released"] is not None}
