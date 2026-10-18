"""Basketball free throw (FIBA): from behind the free-throw line, inside the semi-circle, throw the ball you hold so
that it enters the basket from above. Official court, backboard, ring and size-7 ball; the Unitree H1-2."""
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


class Task(TaskBase):
    name = "free-throw"
    title = "Basketball: free throw"
    category = "basketball-and-rackets"
    robot = "unitree_h1"
    rulebook = ("FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix "
                "(backboard, ring, size-7 ball), Art. 16 (goal), Art. 43 (free throws)")
    deviations = [
        "Art. 3 (equipment): the hand holds the ball by a grip switched on and off, not by fingers; the ball is "
        "released when the grip is switched off.",
        "Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not "
        "slow the ball. A goal is judged at the ring: the ball's centre down through the ring's plane and on to one "
        "ball diameter below it.",
        "Art. 43.2.3: the ball is at your disposal at the start of the episode; there is no referee, no opponent and "
        "no rebound: one throw, and touching the ball after the release ends the attempt.",
    ]
    time_limit_s = 12.0
    start = (0.0, 0.0, 0.0)
    stages = ["release", "through the ring"]
    fall_z = FALL_Z
    params = dict(ring_height_m=3.05, ring_inner_diameter_m=0.45, ring_metal_m=0.018, ring_centre_to_board_m=0.375,
                  board_width_m=1.80, board_height_m=1.05, board_bottom_m=2.90, line_to_ring_m=4.225,
                  semicircle_radius_m=1.80, start_behind_line_m=0.35, release_limit_s=5.0, retouch_grace_s=0.05)

    sentence = ("Shoot a free throw: from behind the free-throw line, throw the basketball in your right hand so that "
                "it enters the basket from above.")
    rules = ("The official basket: a rigid ring of {ring_inner_diameter_m} m inner diameter ({ring_metal_m} m metal), "
             "its top edge {ring_height_m} m above the floor, its centre {ring_centre_to_board_m} m in front of a "
             "backboard {board_width_m} m wide and {board_height_m} m high whose lower edge is {board_bottom_m} m "
             "above the floor. The ball is a size-7 basketball (" + f"{2 * BALL['radius']:.3f} m across, "
             f"{BALL['mass']:.2f} kg, it keeps {BALL['bounce']:.2f} of its speed in a bounce on the floor" + "); it "
             "flies in air (drag and spin lift). It starts gripped in your right hand and is at your disposal at the "
             "start. The free-throw line's edge nearest to you is {line_to_ring_m} m from the point under the ring's "
             "centre; the free-throw semi-circle has a radius of {semicircle_radius_m} m round the middle of that "
             "edge. You succeed when, after you have let go of the ball, its centre goes down through the ring's "
             "plane inside the ring and on down to one ball diameter below it. You fail if you have not let go of the "
             "ball within {release_limit_s} s; if, before the ball has touched the ring or entered the basket, any "
             "part of you touches the floor on or beyond the free-throw line's near edge or outside the semi-circle; "
             "if any part of you touches the ball more than {retouch_grace_s} s after you let go of it (it cannot be "
             "gripped again); if the ball touches the floor before it is through the ring; if the ball's centre comes "
             "up through the ring from below; if you fall before the ball is through (a fall: your pelvis lower than "
             f"{FALL_Z} m above the floor, or any part of you other than your feet on the floor)" + "; or after "
             "{time_limit_s} s.")
    venue = ("A FIBA court. You stand inside the free-throw semi-circle facing the basket (+x), your pelvis "
             "{start_behind_line_m} m behind the free-throw line's near edge and on the line through the ring's "
             "centre; the point under the ring's centre is {line_to_ring_m} m beyond that edge. Painted on the floor: "
             "the restricted area, the free-throw line and circle, the three-point line, the no-charge semi-circle. "
             "The ball is against the end of your right fist. A ball is released when the hand's grip is switched off.")
    difficulty = ("From a hand about a metre above the floor the 0.62 kg ball needs to leave at about 8 m/s on a steep "
                  "arc to reach a ring 3.05 m high and more than 4 m away, with a margin of a few centimetres in air "
                  "that slows it, and within five seconds. A straight-arm swing at the shoulder's speed limit gives "
                  "less than that, and the body only stands by an open-loop stance.")

    def build(self, sc):
        p = self.p
        hx = p["start_behind_line_m"] + p["line_to_ring_m"]
        self.hoop = build_court(sc, hx, 0.0, p)
        sc.ball("ball", "basketball", (0.6, -0.17, 1.13), grippable=True)
        sc.camera("venue", (-2.6, -3.6, 2.6), (hx * 0.55, 0.0, 1.7), fovy=55)

    def reset(self, w):
        ball_in_hand(w)

    def referee_reset(self, w, ref):
        p, h = self.p, self.hoop
        self.ball = ref.geoms(body="ball")
        self.robot = ref.part("robot")
        self.ring = ref.geoms(prefix="hoop_rim") | ref.geoms(names=["hoop_plate"])
        centre = (h["x"], h["y"], h["z"])
        self.trackers = {"hoop": HoopPass(centre, h["inner_radius"], BALL["radius"]),
                         "up": Crossing((0, 0, 1), h["z"], direction=1), "released": None, "live": True}

    def may_grip(self, w, side, name):
        return self.trackers.get("released") is None      # one throw: the ball cannot be gripped again

    def _position(self, w, ref) -> str | None:
        """Art. 43.2.3: behind the line and inside the semi-circle, by the points where the robot touches the floor."""
        p, h = self.p, self.hoop
        pts = ref.contact_points(self.robot, ref.ground)
        if not len(pts):
            return None
        xf = h["free_throw_line_x"]
        if float(np.max(pts[:, 0])) >= xf:
            return "touched the free-throw line or the floor beyond it"
        if float(np.max(np.hypot(pts[:, 0] - xf, pts[:, 1] - h["y"]))) > p["semicircle_radius_m"]:
            return "left the free-throw semi-circle"
        return None

    def substep(self, w, ref):
        tr, p, h = self.trackers, self.p, self.hoop
        if tr["live"]:                                    # until the ball has touched the ring or entered the basket
            bad = self._position(w, ref)
            if bad:
                return ref.fail(bad)
        if tr["released"] is None:
            if w.holder("ball"):
                return
            tr["released"] = ref.time
            ref.stage("release")
        b = w.pos("ball")
        was_in = tr["hoop"].entered
        ev = tr["hoop"].update(b)
        x = tr["up"].update(b)
        if ev == "enter" or ref.touching(self.ball, self.ring):
            tr["live"] = False
        if x is not None and not was_in and math.hypot(x[0] - h["x"], x[1] - h["y"]) < h["inner_radius"]:
            return ref.fail("the ball came up through the ring from below")
        if ref.time - tr["released"] > p["retouch_grace_s"] and ref.touching(self.ball, self.robot):
            ref.fail("the ball was touched again after the release", parts=sorted(ref.parts_touching(self.ball)))
        elif ref.touching(self.ball, ref.ground):
            ref.fail("the ball touched the floor")
        elif ev == "through":
            if ref.stage("through the ring"):
                ref.succeed()

    def step(self, w, ref):
        tr, p = self.trackers, self.p
        if tr["released"] is None and w.t > p["release_limit_s"] + 1e-9:
            ref.fail("the ball was not released within the time allowed")
        ref.metrics["ball_height_m"] = round(float(w.pos("ball")[2]), 3)

    def privileged(self, w):
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(), "hoop": self.hoop,
                "released": self.trackers["released"] is not None}
