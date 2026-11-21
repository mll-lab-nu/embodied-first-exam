"""Basketball: a dribble between the legs, then a dunk (FIBA). From the top of the key the ball,
held in the H1-2's own Inspire five-finger hands (rfo.realhand; contact and friction only, no weld), is dribbled; one bounce of the dribble passes between the legs;
the dribble ends with the ball gathered in both hands; at most two steps; the ball is forced down through the ring
from above with the hands on it; land on the feet. Official court, backboard and size-7 ball; the ring lowered to
2.39 m (below FIBA Mini-Basketball's 2.60 m: the robot's measured reach); the Unitree H1-2."""
import math
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from rfo.referee import Crossing, HoopPass, Touch
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


# ---- the leg gate ----
# "Between the legs" is judged on the robot's own geometry: the gate is the triangle whose corners are the two feet
# (the sole sites) and the crotch (the point midway between the two hip joints), cut off at the height of the lower
# knee joint (a dribble between the legs is a low bounce; and above the knees the H1-2's collision legs, capsules of
# 2 cm radius on the thighs, are much thinner than its real thighs, while below them the shins' collision hulls and
# the real shins agree within about 2 cm). A bounce of the dribble goes between
# the legs when the ball's centre passes through that gate from one side of its plane to the other, no hand
# touching the ball, the ball itself moving through the plane, in the direction of the pass, at cross_speed_min_m_s or
# more (its own velocity, not one relative to the robot: a robot that walks, turns or rocks over a ball lying or
# bouncing in place moves the plane, not the ball), and the ball is on the other side of the gate when a hand touches
# it next (a ball that comes back, or goes round a leg, does not count). The plane's normal keeps its orientation from
# one physics step to the next (a cross product would flip when a swinging sole passes the line from the other sole to
# the crotch); while the triangle is thinner than gate_min_area_m2 (a sole on that line) no pass is counted, and a pass
# is the ball's centre changing sides within one ball radius of the plane (not the plane swinging past it). With the
# H1-2's feet at the stance (0.38 m apart, the soles' inner edges 0.28 m) a 0.239 m ball fits between the feet with
# about 2 cm to spare on each side (the real shins' inner faces, 0.25 m apart, leave about 0.5 cm); any touch of a
# leg is a violation of the dribble.
def gate(w) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The leg gate's triangle now: left foot, right foot, crotch."""
    d, r = w.d, w.robot
    hips = [d.xpos[w.m.body(f"{s}_hip_pitch_link").id] for s in ("left", "right")]
    return (d.site_xpos[r.foot_site["left"]].copy(), d.site_xpos[r.foot_site["right"]].copy(), (hips[0] + hips[1]) / 2)


def knee_height(w) -> float:
    """The height of the lower knee joint: the gate's top."""
    return float(min(w.d.xpos[w.m.body(f"{s}_knee_link").id][2] for s in ("left", "right")))


def gate_normal(L, R, C) -> tuple[np.ndarray, float]:
    """The unit normal of the triangle's plane (its orientation is the caller's business) and the triangle's area."""
    n = np.cross(R - L, C - L)
    a = float(np.linalg.norm(n))
    return n / (a + 1e-12), a / 2


def in_triangle(x, L, R, C) -> bool:
    """x (a point in the triangle's plane) inside the triangle L R C."""
    v0, v1, v2 = R - L, C - L, x - L
    d00, d01, d11, d20, d21 = v0 @ v0, v0 @ v1, v1 @ v1, v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    if den <= 1e-12:
        return False
    v = (d11 * d20 - d01 * d21) / den
    u = (d00 * d21 - d01 * d20) / den
    return v >= 0.0 and u >= 0.0 and u + v <= 1.0
# ---- end of the leg gate ----


class Task(TaskBase):
    name = "dunk-between-legs"
    title = "Basketball: between-the-legs dribble and dunk"
    category = "basketball-and-rackets"
    robot = "unitree_h1"
    rulebook = ("FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix "
                "(backboard, ring, size-7 ball), Art. 13 (how the ball is played), Art. 14 (control: a player holds "
                "a live ball), Art. 15 (a dunk: the ball forced downwards into the basket with one or both hands), "
                "Art. 16 (goal; a ball that passes through the basket from below is a violation), Art. 23 (out of "
                "bounds), Art. 24 (dribbling: its start, its end, no second dribble), Art. 25 (travelling, 25.2.1.2: "
                "two steps upon completion of a dribble), Art. 26 (three seconds), Art. 36 (technical foul: hanging "
                "on the ring); FIBA Mini-Basketball Rules (the ring at 2.60 m)")
    deviations = [
        "Basketball Equipment (basket): the basket is lowered: the ring's top edge is {ring_height_m} m above the "
        "floor, below FIBA Mini-Basketball's 2.60 m (FIBA's own ring: 3.05 m), set at the robot's measured own-motor "
        "reach (H1-2 with H2-class leg actuators), at the edge of the robot's reach, and the pass between the legs is the harder part; the "
        "full-size backboard keeps its size and its height relative to the ring (lower edge {board_bottom_m} m). "
        "The ball stays the size-7 ball.",
        "Art. 3 (equipment, the hands): the hands are the H1-2's own Inspire five-finger hands (six drives: four "
        "fingers, the thumb's flexion and rotation), closed by one command per hand; the ball is held by the hands' "
        "contact and friction alone (the open palms pressed on its sides by the arms) and "
        "slips or drops when they do not hold it. It is dribbled by pushing it with a hand (the palm and the "
        "fingers).",
        "Art. 24.1.2 (the ball 'comes to rest' in a hand) is read as: a touch of one hand that lasts longer than "
        "{hand_touch_max_s} s. The dribble ends when both hands touch the ball at the same time (the gather); a "
        "dribble ended by a ball at rest in one hand ends the attempt (no dribble can be started again, Art. 24.2).",
        "Art. 13: during the dribble every touch of the ball by a part of you other than a hand is a violation; intent "
        "(an accidental touch of a leg is legal in the rule book) cannot be judged.",
        "The rule book has no 'between the legs': this task's definition (the leg gate: the triangle of your two "
        "feet and your crotch below your knees, crossed by the ball's centre during a bounce, no "
        "hand on it, the ball moving through it at "
        "{cross_speed_min_m_s} m/s or more, and the ball on the other side at the next touch) is "
        "this task's own requirement.",
        "Art. 15 defines a dunk only as forcing the ball downwards into the basket with one or both hands: here, at "
        "the moment its centre enters the ring, both hands are on the ball, or a hand is on it whose latest contact "
        "is at least {from_above_m} m above its centre (a hand pressing it from above).",
        "Art. 14 / 24 give no distance for 'control' of a dribbled ball: here the ball's centre must stay within "
        "{control_radius_m} m (horizontally) of your pelvis while it is dribbled.",
        "Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not "
        "slow the ball. The ball is through the basket when its centre has gone down through the ring's plane inside "
        "the ring and on to one ball diameter below it.",
        "Art. 26 (three seconds) is not applied: the attempt is a single action without opponents (as in the other "
        "basketball families, which start in or next to the restricted area).",
        "Art. 36: hanging on the ring is judged by time: the robot may touch the basket (ring, its plate, the "
        "backboard) for at most {basket_touch_s} s in all.",
        "The landing (on the feet, standing {stand_s} s) is this task's own requirement; the rule book asks nothing "
        "of a player after a goal.",
    ]
    time_limit_s = 40.0
    start = (0.0, 0.0, 0.0)
    stages = ["dribble", "between the legs", "gather", "dunk", "stand"]

    @property
    def fall_z(self) -> float:                    # (the referee's fall line: the parameter)
        return float(self.p["fall_z_m"])
    params = dict(ring_height_m=2.39, ring_inner_diameter_m=0.45, ring_metal_m=0.018, ring_centre_to_board_m=0.375,
                  board_width_m=1.80, board_height_m=1.05, board_bottom_m=2.24, court_width_m=15.0, line_width_m=0.05,
                  free_throw_line_m=5.80, start_to_ring_m=4.425, start_behind_free_throw_line_m=0.20,
                  touch_gap_s=0.03, hand_touch_max_s=0.30, from_above_m=0.06, cross_speed_min_m_s=1.0,
                  gate_min_area_m2=0.02, fall_z_m=FALL_Z,
                  control_radius_m=2.0,
                  basket_touch_s=0.30, max_steps=2, step_gap_s=0.03, foot_slide_m=0.20, stand_s=1.0,
                  stand_speed_m_s=0.35, stand_upright_cos=0.94)

    sentence = ("From the top of the key, with the basketball held in your two hands, dribble it, make one "
                "of its bounces pass between your legs, gather it in both hands, and with at most two steps dunk it: "
                "force it down through the ring from above with your hands on it, then land on your feet.")
    rules = ("A FIBA court ({court_width_m} m wide inside its side lines, lines {line_width_m} m wide); the official "
             "basket: a rigid ring of {ring_inner_diameter_m} m inner diameter ({ring_metal_m} m metal), its top edge "
             "{ring_height_m} m above the floor, its centre {ring_centre_to_board_m} m in front of a backboard "
             "{board_width_m} m wide and {board_height_m} m high whose lower edge is {board_bottom_m} m above the "
             "floor. The ball is a size-7 basketball (" + f"{2 * BALL['radius']:.3f} m across, {BALL['mass']:.2f} kg, "
             f"it keeps {BALL['bounce']:.2f} of its speed in a bounce on the floor" + "). Your hands are five-finger "
             "hands: the ball starts held between them, the palms pressed on its sides and the hands open, "
             "and only the hands' contact and friction hold it; it can slip out. A hand is the palm, the fingers and "
             "the wrist; a hand is on the ball while it touches the ball, gaps shorter than {touch_gap_s} s included; the ball is in your hands while at least "
             "one hand is on it. "
             "Starting the dribble: you stand still with the ball in your hands; the first foot you lift makes the "
             "other your pivot foot; the pivot foot, and before a foot is lifted either foot, may not slide more than "
             "{foot_slide_m} m along the floor, and the pivot foot may not leave the floor before the ball has left "
             "your hands (a foot has left the floor when it has not touched it for {step_gap_s} s). The ball may not "
             "touch the floor while it is in your hands. The dribble starts when the ball has left your hands and "
             "touched the floor. "
             "The dribble: you play the ball by touches of one hand at a time that push it to the floor: between two "
             "touches by your hands the ball must have touched the floor (the ball leaving your hands at the start "
             "counts as a touch); contacts of your hands less than {touch_gap_s} s apart are one touch; a touch of "
             "one hand may last at most {hand_touch_max_s} s (longer: the ball has come to rest in the hand); the "
             "ball may touch no part of you but your hands; its centre must stay within {control_radius_m} m "
             "(horizontally) of your pelvis; there is no limit to your steps. "
             "Between the legs: the leg gate is the triangle whose corners are the soles of your two feet (each "
             "foot's sole point) and your crotch (the point midway between your two hip joints), wherever your legs "
             "are, up to the height of your lower knee joint, while the triangle's area is at least "
             "{gate_min_area_m2} m2 "
             "(a thinner one, with a sole on the line from the other sole to the crotch, is no gate). A bounce goes "
             "between your legs when, between two touches of your hands, the ball touches the floor, its centre "
             "passes through the leg gate from one side of the gate's plane to the other while no hand touches it, "
             "the ball itself (not you) moving through that plane in the direction of the pass at "
             "{cross_speed_min_m_s} m/s or more, this is the last time its centre passes the gate's "
             "plane before the next touch, "
             "and at that next touch the ball is on the other side of the plane from where it was at the touch "
             "before. At least one bounce of your dribble must go between your legs. "
             "The gather: the dribble ends when both your hands are on the ball at the same moment; it must end so, "
             "and only after a bounce between your legs. From then on the ball must stay in your hands until its "
             "centre has gone down into the ring, and it may not touch the floor (a second dribble). Travelling: "
             "after the gather you may take at most {max_steps} steps with the ball in your hands. A step is a foot "
             "touching the floor after it has been off it for at least {step_gap_s} s; both feet landing within "
             "{step_gap_s} s of each other are one step; the same foot may not touch down twice in a row; a foot on "
             "the floor may not slide more than {foot_slide_m} m from where it stood or was put down; after that no "
             "foot may touch the floor again until the ball is through the ring. "
             "The dunk: the ball's centre goes down through the ring's plane inside the ring while both your hands "
             "are on the ball, or while a hand is on it whose latest contact with it is at least {from_above_m} m "
             "above the ball's centre (pressing it down from above), and on down to one ball diameter below the "
             "ring (in the hands, or let "
             "go once its centre is inside the ring). A ball whose centre comes up through the ring from below is a "
             "violation. Hanging on the ring: you may touch the basket (the ring, its plate, the backboard) with any "
             "part of you for at most {basket_touch_s} s in all. After the dunk let go of the ball (no hand on it) "
             "and stand: for {stand_s} s without a break only your feet touch the ground, your torso is upright (the "
             "cosine of its tilt at least {stand_upright_cos}) and your pelvis moves slower than {stand_speed_m_s} "
             "m/s. Then you have succeeded. You fail if you travel; if the ball touches the floor while in your hands "
             "before the dribble, or goes through the ring before it; if during the dribble a hand "
             "touches the ball twice without the ball touching the "
             "floor in between, a touch of one hand lasts too long, the ball touches a part of you other than a "
             "hand, or the ball gets further from you than the control distance; if you gather the ball before a "
             "bounce between your legs; if after the gather the ball leaves your hands before its centre has entered "
             "the ring or touches the floor; if the ball goes through the ring after an entry at which neither both "
             "hands nor a hand from above were on it (a shot, a tip from below or the side, a drop); if, let go "
             "inside the ring, it touches the floor without having gone through; if the ball comes up through the "
             "ring from below; if the ball or any part of you touches the floor on or outside a boundary line (the "
             "end line or a side line); if you hang on the ring; if you fall at any time (a fall: your pelvis lower "
             "than {fall_z_m} m above the floor, or any part of you other than your feet on the floor); or after "
             "{time_limit_s} s.")
    venue = ("A FIBA court. You stand at the top of the key facing the basket (+x): the point under the ring's centre "
             "is {start_to_ring_m} m ahead of your pelvis, the backboard's face {ring_centre_to_board_m} m beyond it, "
             "the end line's inner edge 1.575 m beyond that point. The free-throw line (the top of the restricted "
             "area; its edge on your side {free_throw_line_m} m from the end line) is "
             "{start_behind_free_throw_line_m} m ahead of your pelvis, just in front of your toes; the side lines are "
             "{court_width_m} m apart, 7.5 m to each side of "
             "you. The ring's top edge is {ring_height_m} m above the floor. Painted on the floor: the boundary "
             "lines, the restricted area, the free-throw line and circle, the three-point line, the no-charge "
             "semi-circle, the centre line and circle. The ball is held between your two hands in front of your "
             "chest, its centre 1.13 m above the floor and 0.39 m ahead of your pelvis: the hands open (grip values 0, "
             "the fingers straight), the palms on its two sides (on these hands it bears on the two thumbs, which "
             "lie a little proud of the palms), and the arms pressing the palms in (the start command's shoulder roll and yaw are a little further in than the arms stand: "
             "the difference is the squeeze). A grip value is that hand's closure command (0 open, 1 every finger "
             "and thumb joint closing towards its closed angle; a finger stops on what it touches).")
    difficulty = ("Every touch of the dribble has to push the ball down with a hand, and one bounce has to go "
                  "through the narrow gap between the robot's own feet and come out where a hand can meet it, without "
                  "touching a leg; then both hands have to catch the moving ball and hold it, with only the hands' "
                  "contact and friction holding it. After at most two steps the 67 kg body has to rise about 0.4 m "
                  "with the ball held overhead and bring it down into a ring only 0.21 m wider than the ball, and "
                  "land; the robot has a walking gait (which steps on the spot even at a zero command) and nothing "
                  "that jumps or lands.")

    def build(self, sc):
        p = self.p
        hx = p["start_to_ring_m"]
        self.hoop = build_court(sc, hx, 0.0, p)
        sc.ball("ball", "basketball", (0.42, 0.0, 1.28))         # not grippable: the hands hold it by contact
        for side in ("left", "right"):
            sc.real_hands[side] = "inspire"
        sc.camera("venue", (1.2, -6.0, 2.0), (2.2, 0.0, 1.3), fovy=60)

    def reset(self, w):
        ball_in_hands(w)

    def referee_reset(self, w, ref):
        p, h = self.p, self.hoop
        self.ball = ref.geoms(body="ball")
        self.hand = {s: ref.part(f"{s}_hand") for s in ("left", "right")}
        self.hands = ref.part("hands")
        self.robot = ref.part("robot")
        self.body = self.robot & ~self.hands
        self.basket = ref.geoms(prefix="hoop_rim") | ref.geoms(names=["hoop_plate", "hoop_board"])
        self.x_end = h["end_line_x"]                                            # the end line's inner edge
        self.y_half = p["court_width_m"] / 2
        travel = Travel(w, ref, p["step_gap_s"], int(p["max_steps"]), p["foot_slide_m"])
        travel.start("pivot")
        self.trackers = {"phase": "hold", "travel": travel,
                         "hand": Touch(ref, self.ball, self.hands, gap=p["touch_gap_s"]),
                         "touch": {"left": 0.0, "right": 0.0}, "top": {"left": False, "right": False},
                         "released": None, "floor_since_hand": False, "touches": 0, "side0": None, "gate_s": None,
                         "gate_b": None, "gate_n": None, "cross": None, "between": 0, "gathered": None,
                         "hoop": HoopPass((h["x"], h["y"], h["z"]), h["inner_radius"], BALL["radius"]),
                         "up": Crossing((0, 0, 1), h["z"], direction=1), "entry_hands": None, "let_go": None,
                         "dunked": None, "basket_ph": 0}

    def on_ball(self, ref) -> dict:
        """Which hands are on the ball now (touching it, gaps shorter than touch_gap_s included)."""
        t = self.trackers["touch"]
        return {s: t[s] is not None and ref.time - t[s] <= self.p["touch_gap_s"] + 1e-9 for s in ("left", "right")}

    def _off_axis(self, b) -> float:
        return math.hypot(b[0] - self.hoop["x"], b[1] - self.hoop["y"])

    def _out(self, pts) -> bool:
        return bool(len(pts)) and bool(np.any((pts[:, 0] >= self.x_end) | (np.abs(pts[:, 1]) >= self.y_half)))

    def _gate(self, w, b):
        """(signed distance of the ball's centre to the gate's plane, the gate's corners, its normal, whether the
        triangle is a gate). The normal keeps the orientation it had at the last step (first: towards the robot's
        back, or its left when the plane is along its heading); a thin triangle keeps the last normal."""
        tr = self.trackers
        L, R, C = gate(w)
        n, area = gate_normal(L, R, C)
        ok = area >= self.p["gate_min_area_m2"]
        prev = tr.get("gate_n")
        if not ok and prev is not None:
            n = np.asarray(prev, float)
        elif prev is not None:
            n = n if float(n @ np.asarray(prev, float)) >= 0 else -n
        else:
            yaw = float(w.pelvis()[3])
            ref_dir = np.array([-math.cos(yaw), -math.sin(yaw), 0.0])
            if abs(float(n @ ref_dir)) < 0.3:
                ref_dir = np.array([-math.sin(yaw), math.cos(yaw), 0.0])
            n = n if float(n @ ref_dir) >= 0 else -n
        if ok or prev is None:
            tr["gate_n"] = [round(float(v), 12) for v in n]
        return float(n @ (b - L)), (L, R, C), n, ok

    def substep(self, w, ref):
        tr, h, p = self.trackers, self.hoop, self.p
        b = w.pos("ball")
        now = {s: ref.touching(self.hand[s], self.ball) for s in ("left", "right")}
        for s in ("left", "right"):
            if now[s]:
                tr["touch"][s] = round(ref.time, 4)
                pts = ref.contact_points(self.hand[s], self.ball)
                tr["top"][s] = bool(len(pts)) and bool(float(np.max(pts[:, 2])) >= b[2] + p["from_above_m"])
        on = self.on_ball(ref)
        touching = now["left"] or now["right"]
        if ref.touching(self.robot, self.basket):
            tr["basket_ph"] += 1
            if tr["basket_ph"] * w.PHYS_DT > p["basket_touch_s"] + 1e-9:
                return ref.fail("hanging on the ring: the basket touched for more than the time allowed",
                                parts=sorted(ref.parts_touching(self.basket)))
        bad = tr["travel"].update()
        phase = tr["phase"]
        if phase == "dunked":
            if tr["let_go"] is None and not any(on.values()):
                tr["let_go"] = round(ref.time, 4)
            return
        if self._out(ref.contact_points(self.robot, ref.ground)):
            return ref.fail("out of bounds: you touched the floor on or outside a boundary line")
        floor_pts = ref.contact_points(self.ball, ref.ground)
        if self._out(floor_pts):
            return ref.fail("out of bounds: the ball touched the floor on or outside a boundary line")
        was_in = tr["hoop"].entered
        ev = tr["hoop"].update(b)
        x = tr["up"].update(b)
        if x is not None and not was_in and self._off_axis(x) < h["inner_radius"]:
            return ref.fail("the ball came up through the ring from below")
        if phase == "hold":
            if ev == "through":
                return ref.fail("the ball went through the ring before the dribble")
            if bad or tr["travel"].pivot_up:
                return ref.fail(bad or "travelling: the pivot foot left the floor before the ball left the hands")
            if len(floor_pts):
                return ref.fail("the ball touched the floor while in your hands")
            if not any(on.values()):
                tr["phase"], tr["released"] = "dribble", round(ref.time, 4)
                bad = tr["travel"].stop()
                if bad:
                    return ref.fail(bad, steps=tr["travel"].steps)
                s, _, _, _ = self._gate(w, b)
                tr["side0"], tr["gate_s"], tr["cross"] = s >= 0, s, None
                tr["gate_b"] = [round(float(v), 9) for v in b]
            return
        if phase == "dribble":
            return self._dribble(w, ref, b, now, touching, floor_pts, ev)
        # phase "held": gathered, on the way to the dunk
        if bad:
            return ref.fail(bad, steps=tr["travel"].steps)
        hands_ok = (on["left"] and on["right"]) or any(on[s] and tr["top"][s] for s in ("left", "right"))
        if ev == "enter":
            tr["entry_hands"] = {"on": sorted(s for s in ("left", "right") if on[s]),
                                 "from_above": sorted(s for s in ("left", "right") if on[s] and tr["top"][s]),
                                 "ok": hands_ok}
        elif ev == "through":
            if not (tr["entry_hands"] or {}).get("ok"):
                return ref.fail("the ball went through the ring without both hands or a hand from above on it at "
                                "the entry", hands=tr["entry_hands"])
            tr["phase"], tr["dunked"] = "dunked", round(ref.time, 4)
            bad = tr["travel"].stop()
            if bad:
                return ref.fail(bad, steps=tr["travel"].steps)
            ref.stage("dunk")
            return
        if tr["let_go"] is None and not any(on.values()):
            tr["let_go"] = round(ref.time, 4)
            if not tr["hoop"].entered:
                return ref.fail("the ball left your hands after the gather, before the dunk")
        if len(floor_pts):
            if tr["let_go"] is not None:
                return ref.fail("the ball did not go through the ring")
            return ref.fail("double dribble: the ball touched the floor after the gather")

    def _dribble(self, w, ref, b, now, touching, floor_pts, ev):
        tr, p = self.trackers, self.p
        if ev == "through":
            return ref.fail("the ball went through the ring without a hand on it (a shot, not a dunk)")
        if ref.touching(self.ball, self.body):
            return ref.fail("the ball touched a part of you other than a hand",
                            parts=sorted(ref.parts_touching(self.ball) - {"left_hand", "right_hand"}))
        pel = w.pelvis()
        gap = math.hypot(b[0] - pel[0], b[1] - pel[1])
        if gap > p["control_radius_m"]:
            return ref.fail("the ball got away: it was further from you than the control distance",
                            distance_m=round(gap, 3))
        s, (L, R, C), n, ok = self._gate(w, b)
        s_prev, tr["gate_s"] = tr["gate_s"], s
        q_prev, tr["gate_b"] = tr["gate_b"], [round(float(v), 9) for v in b]
        crossed = (s_prev is not None and q_prev is not None and (s_prev < 0) != (s < 0)
                   and abs(s_prev) <= BALL["radius"] and abs(s) <= BALL["radius"])
        if crossed and touching:
            tr["cross"] = None                    # a crossing with a hand on the ball is carried, not bounced
        elif crossed:
            f = s_prev / (s_prev - s) if s_prev != s else 1.0
            q = np.asarray(q_prev, float)         # the ball's centre a physics step ago
            xc = q + (b - q) * f
            xc = xc - n * float(n @ (xc - L))     # (onto the plane)
            v_ball = float(n @ w.vel("ball")) * (1.0 if s > s_prev else -1.0)   # the ball's own, in the pass' way
            tr["cross"] = {"t": round(ref.time, 4),
                           "inside": ok and bool(in_triangle(xc, L, R, C)) and float(xc[2]) <= knee_height(w),
                           "speed": round(v_ball, 3), "z": round(float(xc[2]), 3)}
        hand = tr["hand"]
        if hand.update():
            if not tr["floor_since_hand"]:
                return ref.fail("a hand touched the ball twice without the ball touching the floor in between")
            tr["touches"] += 1
            ref.metrics["dribbles"] = tr["touches"]
            c = tr["cross"]
            if (c is not None and c["inside"] and c["speed"] >= p["cross_speed_min_m_s"]
                    and tr["side0"] is not None and (s >= 0) != tr["side0"]):
                tr["between"] += 1
                ref.metrics["between_the_legs"] = tr["between"]
                ref.stage("between the legs", cross=c)
            tr["cross"] = None
        if touching:
            tr["floor_since_hand"] = False
            tr["side0"] = s >= 0
            if now["left"] and now["right"]:      # the gather: the dribble ends with the ball in both hands
                if not ref.has("between the legs"):
                    return ref.fail("the dribble ended before a bounce between the legs")
                tr["phase"], tr["gathered"] = "held", round(ref.time, 4)
                tr["travel"].start("steps")
                ref.stage("gather")
                return
            if hand.duration > p["hand_touch_max_s"]:
                return ref.fail("the ball came to rest in a hand: a touch lasted too long",
                                touch_s=round(hand.duration, 3))
        if len(floor_pts) and not touching:
            tr["floor_since_hand"] = True
            ref.stage("dribble")

    def step(self, w, ref):
        tr, p = self.trackers, self.p
        ref.metrics["ball_height_m"] = round(float(w.pos("ball")[2]), 3)
        ref.metrics["basket_touch_s"] = round(tr["basket_ph"] * w.PHYS_DT, 3)
        ok = (ref.has("dunk") and tr["let_go"] is not None
              and ref.standing(max_speed=p["stand_speed_m_s"], min_upright=p["stand_upright_cos"]))
        if ref.hold("stand", ok, p["stand_s"]):
            if ref.stage("stand"):
                ref.succeed()

    def privileged(self, w):
        tr = self.trackers
        L, R, C = gate(w)
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(), "hoop": self.hoop,
                "phase": tr["phase"], "hands_on_ball": self.on_ball(w.ref),
                "leg_gate": {"left_foot": L.tolist(), "right_foot": R.tolist(), "crotch": C.tolist(),
                             "top_z": knee_height(w)}, "last_gate_crossing": tr["cross"],
                "dribbles": tr["touches"], "between_the_legs": tr["between"], "steps": len(tr["travel"].steps),
                "dunked": tr["dunked"] is not None, "basket_touch_s": round(tr["basket_ph"] * w.PHYS_DT, 3)}
