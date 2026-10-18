"""Basketball catch and shoot (FIBA): a chest pass comes to you at the top of the key; catch it and shoot from there:
the ball enters the basket from above. Official court, backboard, ring and size-7 ball; the Unitree H1-2."""
import math

import mujoco
import numpy as np

from rfo.referee import Crossing, HoopPass
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
    name = "catch-and-shoot"
    title = "Basketball: catch and shoot"
    category = "basketball-and-rackets"
    robot = "unitree_h1"
    rulebook = ("FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix "
                "(backboard, ring, size-7 ball), Art. 13 (how the ball is played), Art. 16 (goal), Art. 25 "
                "(travelling)")
    deviations = [
        "Art. 3 (equipment): the hand holds the ball by a grip switched on and off, not by fingers: the grip takes "
        "the ball when its surface is within 3.5 cm of the palm and it moves at most 6 m/s relative to the hand; the "
        "ball is released when the grip is switched off.",
        "Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not "
        "slow the ball. A goal is judged at the ring: the ball's centre down through the ring's plane and on to one "
        "ball diameter below it.",
        "The pass is thrown by a machine, not a team-mate: always the same chest pass, at a fixed time.",
        "Art. 13: a touch of the ball by a leg or a foot is always taken as deliberate (a violation); intent cannot "
        "be judged.",
        "Art. 25.2.1: a ball caught with a foot off the floor is judged by the two-step rule without the pivoting "
        "it allows after a stop: after two steps no foot may touch the floor again while the ball is held.",
        "One attempt, no opponent, no rebound: a pass that is not caught on the fly, and touching the ball after the "
        "shot's release, end the attempt.",
    ]
    time_limit_s = 15.0
    start = (0.0, 0.0, 0.0)
    stages = ["catch", "release", "through the ring"]
    fall_z = FALL_Z
    # The pass: a chest pass of pass_speed_m_s from pass_distance_m away (the left wing, on the three-point line),
    # released pass_from_z_m high at pass_time_s and aimed at the point pass_to_x_m ahead of the robot's pelvis,
    # pass_to_z_m high: (pass_vx, pass_vy, pass_vz) is that pass (found by shooting it in this air; the test checks
    # that the ball passes within 2 cm of the point).
    params = dict(ring_height_m=3.05, ring_inner_diameter_m=0.45, ring_metal_m=0.018, ring_centre_to_board_m=0.375,
                  board_width_m=1.80, board_height_m=1.05, board_bottom_m=2.90, spot_to_ring_m=5.8,
                  pass_time_s=2.0, pass_speed_m_s=8.0, pass_distance_m=5.0, pass_from_x_m=1.05, pass_from_y_m=4.96,
                  pass_from_z_m=1.25, pass_to_x_m=0.40, pass_to_z_m=1.25, pass_vx=-0.9143, pass_vy=-6.9768, pass_vz=3.8063,
                  max_steps=2, step_gap_s=0.03, pivot_slide_m=0.20, retouch_grace_s=0.05)

    sentence = ("Catch and shoot: catch the chest pass that comes to you from the left wing, then shoot from where "
                "you stand so that the ball enters the basket from above.")
    rules = ("The official basket: a rigid ring of {ring_inner_diameter_m} m inner diameter ({ring_metal_m} m metal), "
             "its top edge {ring_height_m} m above the floor, its centre {ring_centre_to_board_m} m in front of a "
             "backboard {board_width_m} m wide and {board_height_m} m high whose lower edge is {board_bottom_m} m "
             "above the floor. The ball is a size-7 basketball (" + f"{2 * BALL['radius']:.3f} m across, "
             f"{BALL['mass']:.2f} kg, it keeps {BALL['bounce']:.2f} of its speed in a bounce on the floor" + "); it "
             "flies in air (drag and spin lift). It is passed to you {pass_time_s} s after the start: a chest pass "
             "of {pass_speed_m_s} m/s from {pass_distance_m} m away. In order: you catch the ball (a hand's grip "
             "takes it) before it has touched the floor; you let go of it (the shot); its centre goes down through "
             "the ring's plane inside the ring and on down to one ball diameter below it, which is the success. "
             "Travelling, from the catch to the shot's release: if both your feet are on the floor at the catch, the "
             "first foot you lift makes the other your pivot foot; the pivot foot, and before a foot is lifted "
             "either foot, may not slide more than {pivot_slide_m} m along the floor (in the steps case below: any "
             "foot that is on the floor, from where it stood or was put down), and once it has left the floor no foot may touch the floor again before the ball "
             "has left your hand. If a foot is off the floor at the catch, you may take at most {max_steps} steps "
             "(a step: a foot touching the floor after it has been off it for at least {step_gap_s} s; both feet "
             "landing within {step_gap_s} s of each other are one step; not the same foot twice in a row), and after "
             "them no foot may touch the floor again before the release. You fail if anything of you touches the "
             "ball before it is passed; if the passed ball touches the floor, or one of your legs or feet, before "
             "you have caught it; if you travel; if any part of you touches the ball more than {retouch_grace_s} s "
             "after the shot's release (it cannot be gripped again); if the ball touches the floor before it is "
             "through the ring; if the ball's centre comes up through the ring from below; if you fall before the "
             f"ball is through (a fall: your pelvis lower than {FALL_Z} m above the floor, or any part of you other "
             "than your feet on the floor)" + "; or after {time_limit_s} s.")
    venue = ("A FIBA court. You stand at the top of the key facing the basket (+x): the point under the ring's "
             "centre is {spot_to_ring_m} m ahead of your pelvis (inside the three-point line; the free-throw line is "
             "1.575 m ahead of you). The passer stands on the left wing: the ball waits {pass_from_x_m} m ahead of "
             "you and {pass_from_y_m} m to your left, {pass_from_z_m} m above the floor. The pass is aimed at the "
             "point {pass_to_x_m} m straight ahead of where your pelvis starts, {pass_to_z_m} m above the floor: it "
             "leaves on an upward arc (28 degrees) and is there 0.76 s later, moving at about 7.2 m/s to your right "
             "and downwards. A hand's closed grip takes the ball when the ball's surface comes within 3.5 cm of "
             "the palm and the ball moves at most 6 m/s relative to the hand; a ball is released when the grip is "
             "switched off.")
    difficulty = ("The pass arrives faster than the grip can take it: the hand has to be on the ball's path and "
                  "moving with it. Then a 0.62 kg ball must leave that hand at about 9 m/s on a steep arc towards a "
                  "ring 5.8 m away, from a body that may not take a step."
                  " The built-in walking gait steps on the spot even at a zero command, so while the ball is in your hand its steps are counted like any others.")

    def build(self, sc):
        p = self.p
        hx = p["spot_to_ring_m"]
        self.hoop = build_court(sc, hx, 0.0, p)
        sc.ball("ball", "basketball", self._from(), grippable=True)
        sc.box("passer", (p["pass_from_x_m"] + 0.05, p["pass_from_y_m"] + 0.30, 0.85), (0.12, 0.10, 0.85),
               rgba=(0.25, 0.3, 0.55, 1))
        sc.camera("venue", (-3.4, -4.2, 2.8), (2.4, 0.8, 1.6), fovy=58)

    def _from(self):
        p = self.p
        return (p["pass_from_x_m"], p["pass_from_y_m"], p["pass_from_z_m"])

    def reset(self, w):
        w.pin("ball", self._from())

    def referee_reset(self, w, ref):
        p, h = self.p, self.hoop
        self.ball = ref.geoms(body="ball")
        self.robot = ref.part("robot")
        self.legs = ref.part("legs")
        self.trackers = {"hoop": HoopPass((h["x"], h["y"], h["z"]), h["inner_radius"], BALL["radius"]),
                         "up": Crossing((0, 0, 1), h["z"], direction=1),
                         "travel": Travel(w, ref, p["step_gap_s"], int(p["max_steps"]), p["pivot_slide_m"]),
                         "passed": False, "caught": None, "released": None}

    def before_step(self, w):
        p, tr = self.p, self.trackers
        if not tr["passed"] and w.t >= p["pass_time_s"] - 1e-9:
            tr["passed"] = True
            w.launch("ball", self._from(), (p["pass_vx"], p["pass_vy"], p["pass_vz"]))
            w.ref.event("pass")

    def may_grip(self, w, side, name):
        tr = self.trackers
        return bool(tr.get("passed")) and tr.get("caught") is None      # the pass, once; no second grip

    def substep(self, w, ref):
        tr, p, h = self.trackers, self.p, self.hoop
        bad = tr["travel"].update()
        if not tr["passed"]:
            if ref.touching(self.ball, self.robot):
                ref.fail("the ball was touched before the pass", parts=sorted(ref.parts_touching(self.ball)))
            return
        held = bool(w.holder("ball"))
        b = w.pos("ball")
        if tr["caught"] is None:
            if held:
                tr["caught"] = ref.time
                tr["travel"].start()
                ref.stage("catch", feet=tr["travel"].mode)
            elif ref.touching(self.ball, ref.ground):
                ref.fail("the pass was not caught: the ball touched the floor")
            elif ref.touching(self.ball, self.legs):
                ref.fail("the ball touched a leg or a foot", parts=sorted(ref.parts_touching(self.ball)))
            return
        was_in = tr["hoop"].entered
        ev = tr["hoop"].update(b)
        x = tr["up"].update(b)
        if x is not None and not was_in and math.hypot(x[0] - h["x"], x[1] - h["y"]) < h["inner_radius"]:
            return ref.fail("the ball came up through the ring from below")
        if tr["released"] is None:
            if bad:
                return ref.fail(bad)
            if held:
                return
            tr["released"] = ref.time
            bad = tr["travel"].stop()
            if bad:
                return ref.fail(bad)
            ref.stage("release")
            return
        if ref.time - tr["released"] > p["retouch_grace_s"] and ref.touching(self.ball, self.robot):
            ref.fail("the ball was touched again after the release", parts=sorted(ref.parts_touching(self.ball)))
        elif ref.touching(self.ball, ref.ground):
            ref.fail("the ball touched the floor")
        elif ev == "through":
            if ref.stage("through the ring"):
                ref.succeed()

    def step(self, w, ref):
        ref.metrics["ball_height_m"] = round(float(w.pos("ball")[2]), 3)

    def privileged(self, w):
        tr = self.trackers
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(), "hoop": self.hoop,
                "passed": bool(tr["passed"]), "pass_time_s": self.p["pass_time_s"], "caught": tr["caught"] is not None}
