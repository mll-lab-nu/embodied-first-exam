"""Basketball dribble (FIBA): dribble the ball from the end line into the frontcourt, 14 m, without a dribbling or a
travelling violation. Official court and size-7 ball; the Unitree H1-2."""
import math

import mujoco
import numpy as np

from rfo.referee import Touch
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
# on this ring with this ball: 0.76, with the contact's nominal value 0.81; tests/test_free_throw.py).
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


def ball_in_hand(w, side: str = "right") -> None:
    """The ball against the end of the fist, gripped."""
    m, d = w.m, w.d
    mujoco.mj_kinematics(m, d)
    b = w.robot.mount[side]
    w.put("ball", d.xpos[b] + d.xmat[b].reshape(3, 3) @ np.array([0.0, 0.0, 0.105 + BALL["radius"]]))
    w.grab(side, "ball", event=False)
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


class Task(TaskBase):
    name = "basketball-dribble"
    title = "Basketball: dribble to the frontcourt"
    category = "basketball-and-rackets"
    robot = "unitree_h1"
    rulebook = ("FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix "
                "(size-7 ball), Art. 13 (how the ball is played), Art. 23 (out of bounds), Art. 24 (dribbling), "
                "Art. 25 (travelling), Art. 28.1.3 (when a dribbled ball is in the frontcourt)")
    deviations = [
        "Art. 3 (equipment): the hand holds the ball by a grip switched on and off, not by fingers; the ball is "
        "released when the grip is switched off, and after that release no grip takes it again.",
        "Art. 24.1.2 (the ball 'comes to rest' in a hand) is read as: a hand's touch of the ball that lasts longer "
        "than {hand_touch_max_s} s. A dribble that has ended cannot legally be started again (Art. 24.2), so a ball "
        "that comes to rest in a hand, or is touched by both hands at once, ends the attempt.",
        "Art. 13: every touch of the ball by a part of you other than a hand is a violation; intent (an accidental "
        "touch of a leg is legal in the rule book) cannot be judged.",
        "Art. 14 / 24 give no distance for 'control' of a dribbled ball: here the ball's centre must stay within "
        "{control_radius_m} m (horizontally) of your pelvis, so that a ball thrown ahead and walked after is not a "
        "dribble.",
        "Art. 28 (eight seconds to reach the frontcourt) is not applied: the attempt lasts at most {time_limit_s} s of robot time.",
    ]
    time_limit_s = 60.0
    start = (0.0, 0.0, 0.0)
    stages = ["dribble", "past the free-throw line", "in the frontcourt"]
    fall_z = FALL_Z
    params = dict(court_length_m=28.0, court_width_m=15.0, line_width_m=0.05, centre_line_m=14.0,
                  free_throw_line_m=5.80, start_from_end_line_m=0.50, start_from_basket_axis_m=2.50,
                  ring_height_m=3.05, ring_inner_diameter_m=0.45, ring_metal_m=0.018, ring_centre_to_board_m=0.375,
                  board_width_m=1.80, board_height_m=1.05, board_bottom_m=2.90,
                  hand_touch_max_s=0.30, touch_gap_s=0.03, step_gap_s=0.03, pivot_slide_m=0.20, control_radius_m=2.0)

    sentence = ("Dribble the basketball in your right hand from the end line across the centre line, 14 m up the "
                "court, without a dribbling or a travelling violation.")
    rules = ("A FIBA court, {court_length_m} m by {court_width_m} m inside its boundary lines (lines "
             "{line_width_m} m wide); the centre line's axis is {centre_line_m} m from the end line. The ball is a "
             "size-7 basketball (" + f"{2 * BALL['radius']:.3f} m across, {BALL['mass']:.2f} kg, it keeps "
             f"{BALL['bounce']:.2f} of its speed in a bounce on the floor" + "). It starts gripped in your right "
             "hand, and you stand still. Starting the dribble: the first foot you lift makes the other your pivot "
             "foot; the pivot foot, and before a foot is lifted either foot, may not slide more than "
             "{pivot_slide_m} m along the floor, and the pivot foot may not leave the floor before "
             "you have let go of the ball (a foot has left the floor when it has not touched it for {step_gap_s} s). "
             "The dribble: after the release you play the ball with one hand at a time, by touches that push it to "
             "the floor (thrown, tapped, rolled or bounced): between two touches by your hands the ball must have "
             "touched the floor; contacts of a hand less than {touch_gap_s} s apart are one touch; the release "
             "counts as the first touch (the releasing hand may stay on the ball for {touch_gap_s} s after the grip "
             "opens; the next touch by a hand needs a bounce on the floor first); no grip takes the ball again. There is no limit to your steps while the ball is not in a hand. You succeed at the "
             "first moment the ball touches the floor in the frontcourt (beyond the centre line's far edge, "
             "{centre_line_m} m plus half a line width from the end line) with both your feet in the frontcourt "
             "(every point where each foot last touched the floor is beyond that edge), after at least one touch "
             "of your dribble. You fail if you travel at the start; if a hand's touch lasts longer than "
             "{hand_touch_max_s} s (the ball has come to rest in the hand); if both hands touch the ball at the "
             "same time; if a hand touches the ball twice without the ball having touched the floor in between; if "
             "the ball touches any part of you other than a hand; if the ball's centre is ever more than "
             "{control_radius_m} m (horizontally) from your pelvis after the release; if the ball or any part of "
             "you touches the floor on or outside a boundary line (out of bounds); if you fall (a fall: your pelvis "
             f"lower than {FALL_Z} m above the floor, or any part of you other than your feet on the floor)" + "; or "
             "after {time_limit_s} s.")
    venue = ("You stand in the backcourt just inside the end line, facing up the court (+x): the end line's inner "
             "edge is {start_from_end_line_m} m behind your pelvis and the centre line {centre_line_m} m beyond that "
             "edge. The basket of this end is to your right: the court's long axis, with the backboard (its lower "
             "edge {board_bottom_m} m high, 1.2 m in from the end line) and the ring, is "
             "{start_from_basket_axis_m} m to your right; the side lines are {court_width_m} m apart, the nearer one "
             "5 m to your left. Painted on the floor: the boundary lines, the restricted area, the free-throw line "
             "({free_throw_line_m} m from the end line) and circle, the three-point line, the centre line and "
             "circle. The ball is against the end of your right fist. A ball is released when the hand's grip is "
             "switched off.")
    difficulty = ("The ball keeps 85 % of its speed in a bounce, so every touch has to push it down and forward again "
                  "to where the hand will be, with a rigid palm 8 cm wide, for 14 m, on a body whose walking gait "
                  "covers about 0.7 m/s, drifts in heading, and is disturbed by every push of the arm."
                  " The built-in walking gait steps on the spot even at a zero command, so while the ball is in your hand its steps are counted like any others.")

    def build(self, sc):
        p = self.p
        # the basket's axis is to the robot's right; the ring's centre is 1.575 m in from the end line
        hx = -p["start_from_end_line_m"] + COURT["ring_x"]
        self.axis_y = -p["start_from_basket_axis_m"]
        self.hoop = build_court(sc, hx, self.axis_y, p, flip=True)
        sc.ball("ball", "basketball", (0.6, -0.17, 1.13), grippable=True)
        sc.camera("venue", (5.0, 9.5, 5.5), (6.5, -1.0, 0.5), fovy=60)

    def reset(self, w):
        ball_in_hand(w)

    def referee_reset(self, w, ref):
        p = self.p
        self.ball = ref.geoms(body="ball")
        self.hand = {s: ref.part(f"{s}_hand") for s in ("left", "right")}
        self.hands = ref.part("hands")
        self.body = ref.part("robot") & ~self.hands
        self.robot = ref.part("robot")
        self.x_end = -p["start_from_end_line_m"]                               # the end line's inner edge
        self.x_ft = self.x_end + p["free_throw_line_m"]
        self.x_front = self.x_end + p["centre_line_m"] + p["line_width_m"] / 2    # the centre line's far edge
        self.y_lo, self.y_hi = self.axis_y - p["court_width_m"] / 2, self.axis_y + p["court_width_m"] / 2
        travel = Travel(w, ref, p["step_gap_s"], 2, p["pivot_slide_m"])
        travel.start("pivot")
        self.trackers = {"hand": Touch(ref, self.ball, self.hands, gap=p["touch_gap_s"]), "travel": travel,
                         "released": None, "floor_since_hand": False, "touches": 0, "foot_x": {}}

    def may_grip(self, w, side, name):
        return self.trackers.get("released") is None       # after the release the ball is only ever pushed

    def _out(self, pts) -> bool:
        return bool(len(pts)) and bool(np.any((pts[:, 0] <= self.x_end) | (pts[:, 1] <= self.y_lo)
                                              | (pts[:, 1] >= self.y_hi)))

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        bad = tr["travel"].update()
        for s in ("left", "right"):                        # where each foot last touched the floor (its rearmost point)
            pts = ref.contact_points(ref.part(f"{s}_foot"), ref.ground)
            if len(pts):
                tr["foot_x"][s] = round(float(np.min(pts[:, 0])), 4)
        if self._out(ref.contact_points(self.robot, ref.ground)):
            return ref.fail("out of bounds: you touched the floor on or outside a boundary line")
        if tr["released"] is None:
            if bad or tr["travel"].pivot_up:
                return ref.fail(bad or "travelling: the pivot foot left the floor before the ball was released")
            if w.holder("ball"):
                return
            tr["released"] = ref.time
            tr["travel"].stop()
        b = w.pos("ball")
        floor_pts = ref.contact_points(self.ball, ref.ground)
        if self._out(floor_pts):
            return ref.fail("out of bounds: the ball touched the floor on or outside a boundary line")
        if ref.touching(self.ball, self.body):
            return ref.fail("the ball touched a part of you other than a hand",
                            parts=sorted(ref.parts_touching(self.ball) - {"left_hand", "right_hand"}))
        pel = w.pelvis()
        gap = math.hypot(b[0] - pel[0], b[1] - pel[1])
        if gap > p["control_radius_m"]:
            return ref.fail("the ball got away: it was further from you than the control distance", distance_m=round(gap, 3))
        hand = tr["hand"]
        if ref.touching(self.ball, self.hand["left"]) and ref.touching(self.ball, self.hand["right"]):
            return ref.fail("both hands touched the ball at the same time")
        if hand.update():
            if hand.count > 1 or ref.time - tr["released"] > p["touch_gap_s"]:      # (not the releasing hand's own contact)
                if not tr["floor_since_hand"]:
                    return ref.fail("a hand touched the ball twice without the ball touching the floor in between")
                tr["touches"] += 1
                ref.metrics["dribbles"] = tr["touches"]
                ref.stage("dribble")
        if hand.active and ref.touching(self.ball, self.hands):
            tr["floor_since_hand"] = False
            if hand.duration > p["hand_touch_max_s"]:
                return ref.fail("the ball came to rest in a hand: a touch lasted too long", touch_s=round(hand.duration, 3))
        if len(floor_pts):
            if not ref.touching(self.ball, self.hands):
                tr["floor_since_hand"] = True
            bx = float(np.min(floor_pts[:, 0]))
            if bx > self.x_ft and tr["touches"] >= 1:
                ref.stage("past the free-throw line")
            fx = tr["foot_x"]
            if (bx > self.x_front and tr["touches"] >= 1 and len(fx) == 2 and min(fx.values()) > self.x_front
                    and ref.stage("in the frontcourt")):
                ref.succeed()

    def step(self, w, ref):
        ref.metrics["distance_m"] = round(float(w.pelvis()[0] - self.x_end), 3)
        ref.metrics["ball_height_m"] = round(float(w.pos("ball")[2]), 3)

    def privileged(self, w):
        tr = self.trackers
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(), "dribbles": tr["touches"],
                "released": tr["released"] is not None, "end_line_x": self.x_end, "frontcourt_x": self.x_front,
                "side_lines_y": [self.y_lo, self.y_hi]}
