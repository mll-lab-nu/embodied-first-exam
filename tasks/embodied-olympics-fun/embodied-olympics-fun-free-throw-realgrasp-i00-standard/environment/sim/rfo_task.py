"""Basketball free throw with a real hold (FIBA): from behind the free-throw line, inside the semi-circle, shoot the
ball you hold pressed between your two bare palms (no grip: squeeze and friction alone) so that it enters the basket
from above. Official court, backboard, ring and size-7 ball; the Unitree H1-2."""
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

# ---- end of the court block ----


# ---- the two-palm hold at the start ----
# The H1-2's hands are the palm pads (4.4 x 8 x 10 cm boxes) on the wrist mounts; at rest their broad faces (the
# mounts' +x) look at each other across the body, 0.294 m apart, and the ball is 0.239 m across. The start: upper
# arms a little forward, forearms a little raised, upper arms turned in until both pads touch the ball in front of the
# chest (HOLD, the right arm; the left one mirrored); the hold targets (the start command) are SQUEEZE further in, so
# the shoulder servos press the ball: nothing else holds it. The arms have no gravity feed-forward, so under that
# command they sag to SETTLED (measured: tests/test_dunk_realgrasp.py, 3 s of the start command): the robot starts
# there, at rest, the ball where it then sits (BALL_OFFSET from the middle between the two pads). Rolling the upper
# arms in does not work near the body: their hulls meet the torso's at shoulder roll 0.15 rad.
# Measured (tests/test_dunk_realgrasp.py): the start command presses about 20 N on each palm (shoulder yaw 8 N m,
# roll 5 N m) and holds the ball for the whole episode and under an extra 3.6 g; with both arms up and the shoulder
# roll 0.12 rad (25 N m) past the touching pose the palms press about 40 N and hold an extra 1.1 g (1.6 g at the
# roll's 40 N m); one palm alone loses the ball within about 0.1 s.
HOLD = dict(shoulder_pitch=-0.20, shoulder_roll=0.0, shoulder_yaw=0.014, elbow_pitch=-0.30)
SQUEEZE = dict(shoulder_yaw=0.06, shoulder_roll=0.05)
SETTLED = dict(shoulder_pitch=-0.1708, shoulder_roll=0.0332, shoulder_yaw=0.0329, elbow_pitch=-0.2794,
               elbow_roll=-0.0025, wrist_pitch=0.0132, wrist_yaw=-0.0625)
BALL_OFFSET = (-0.0047, 0.0, -0.0065)
MIRROR = ("shoulder_roll", "shoulder_yaw", "elbow_roll", "wrist_yaw")      # the joints whose sign flips on the left
PAD_HALF, PAD_Z = 0.022, 0.05                  # the palm pad's half thickness and its centre along the forearm
# The palm-ball contact. With the ball's own contact (its rule-book rebound, 0.85, a lightly damped spring) a ball
# squeezed between two palms rattles and walks out of them in about a second, with pyramidal or elliptic friction
# cones alike; a palm rebound of 0.42 drops it in 6 s, 0.27 lets it creep 5 mm/s. The palm is the soft part of a hand
# and absorbs the ball: a critically damped contact (palm rebound 0.12, measured head-on at 3 m/s), with elliptic
# friction cones and impratio 100 for the whole world (as in the worlds with a real gripper, realhand.py), holds a
# still ball to 0.1 mm in 9 s. The floor, the ring and the backboard keep the ball's own contact (rebound 0.85).
PALM_SOLREF, PALM_SOLIMP, PALM_MU, PALM_REBOUND = "0.005 1", "0.99 0.999 0.001", 0.7, 0.12
CONE, IMPRATIO = "elliptic", 100.0


def _joint(w, name: str) -> int:
    return w.L.JOINTS.index(name + "_joint")


def pad_face(w, side: str) -> tuple[np.ndarray, np.ndarray]:
    """The centre of the pad's inner face (the mount's +x face) and its outward normal, in the world."""
    d, b = w.d, w.robot.mount[side]
    R = d.xmat[b].reshape(3, 3)
    return d.xpos[b] + R @ np.array([PAD_HALF, 0.0, PAD_Z]), R[:, 0].copy()


def ball_between_palms(w) -> None:
    """t = 0: both arms settled in the hold, the ball between the pads; the targets (the start command) are HOLD +
    SQUEEZE."""
    r, d = w.robot, w.d
    for side in ("right", "left"):
        for jn in SETTLED:
            s = -1.0 if side == "left" and jn in MIRROR else 1.0
            i = _joint(w, f"{side}_{jn}")
            d.qpos[r.qadr[i]] = s * SETTLED[jn]
            r.arb.q_a[i] = r.arb.q_b[i] = s * (HOLD.get(jn, 0.0) + SQUEEZE.get(jn, 0.0))
    mujoco.mj_kinematics(w.m, d)
    c = [f + BALL["radius"] * n for f, n in (pad_face(w, "right"), pad_face(w, "left"))]
    w.put("ball", (c[0] + c[1]) / 2 + np.array(BALL_OFFSET))
# ---- end of the hold ----


class Task(TaskBase):
    name = "free-throw-realgrasp"
    title = "Basketball: free throw, real hold"
    category = "basketball-and-rackets"
    robot = "unitree_h1"
    rulebook = ("FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix "
                "(backboard, ring, size-7 ball), Art. 13 (how the ball is played: with the hands), Art. 14 (control: "
                "a player holds a live ball), Art. 16 (goal; a ball that passes through the basket from below is a "
                "violation), Art. 43 (free throws)")
    deviations = [
        "Art. 3 (equipment): the hands are flat rubber palm pads without fingers; the ball is held only by pressing it "
        "between the two palms (friction), and it slips or drops when the arms do not press hard enough. Any "
        "shooting style is allowed (a two-handed set or push shot, an underhand two-handed shot); the ball is "
        "released when no hand touches it any more.",
        "Art. 3 (equipment, the hand): the palm is modelled as the soft part of a hand: it absorbs the ball (a ball "
        "thrown at a still palm keeps "
        f"{PALM_REBOUND:.2f} of its speed) instead of bouncing it like the floor ({BALL['bounce']:.2f}); with the "
        "ball's own floor rebound on the palms a squeezed ball rattles out of them within about a second. The floor, "
        "the ring and the backboard keep the ball's rule-book rebound.",
        "Art. 13.1.2 (the ball is played with the hands only) is read strictly: until the shot is through, the ball "
        "may touch no part of you but your hands (palm pads and wrists); holding it against the trunk, the arms or "
        "a leg is not a hold of this task.",
        "Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not "
        "slow the ball. A goal is judged at the ring: the ball's centre down through the ring's plane and on to one "
        "ball diameter below it.",
        "Art. 43.2.3: the ball is at your disposal at the start of the episode; there is no referee, no opponent and "
        "no rebound: one throw, and touching the ball after the release ends the attempt.",
    ]
    time_limit_s = 12.0
    start = (0.0, 0.0, 0.0)
    stages = ["release", "through the ring"]

    @property
    def fall_z(self) -> float:                    # (the referee's fall line: the parameter)
        return float(self.p["fall_z_m"])
    params = dict(ring_height_m=3.05, ring_inner_diameter_m=0.45, ring_metal_m=0.018, ring_centre_to_board_m=0.375,
                  board_width_m=1.80, board_height_m=1.05, board_bottom_m=2.90, line_to_ring_m=4.225,
                  semicircle_radius_m=1.80, start_behind_line_m=0.35, release_limit_s=5.0, retouch_grace_s=0.05,
                  touch_gap_s=0.03, fall_z_m=0.35)

    sentence = ("Shoot a free throw: from behind the free-throw line, shoot the basketball you hold pressed between "
                "your two palms so that it enters the basket from above.")
    rules = ("The official basket: a rigid ring of {ring_inner_diameter_m} m inner diameter ({ring_metal_m} m metal), "
             "its top edge {ring_height_m} m above the floor, its centre {ring_centre_to_board_m} m in front of a "
             "backboard {board_width_m} m wide and {board_height_m} m high whose lower edge is {board_bottom_m} m "
             "above the floor. The ball is a size-7 basketball (" + f"{2 * BALL['radius']:.3f} m across, "
             f"{BALL['mass']:.2f} kg, it keeps {BALL['bounce']:.2f} of its speed in a bounce on the floor" + "); it "
             "flies in air (drag and spin lift). Your hands have no fingers and no grip: the ball starts pressed "
             "between your two flat palms and is at your disposal at the start; only the force of your arms and "
             "friction hold it, and it can slip out. A hand is the palm pad and the wrist; a hand is on the ball while "
             "it touches the ball, gaps shorter than {touch_gap_s} s included; the ball is in your hands while at "
             "least one hand is on it. The release is the moment the ball is no longer in your hands (no hand on it); "
             "the ball can be released only once: a ball that slips or drops out of your hands is released too. The "
             "free-throw line's edge nearest to you is {line_to_ring_m} m from the point under the ring's centre; the "
             "free-throw semi-circle has a radius of {semicircle_radius_m} m round the middle of that edge. You "
             "succeed when, after the release, the ball's centre goes down through the ring's plane inside the ring "
             "and on down to one ball diameter below it. You fail if the ball has not been released within "
             "{release_limit_s} s; if, before the release, the ball touches any part of you other than your hands; "
             "if, before the ball has touched the ring or entered the basket, any part of you touches the floor on or "
             "beyond the free-throw line's near edge or outside the semi-circle; if any part of you touches the ball "
             "more than {retouch_grace_s} s after the release (it cannot be taken again); if the ball touches the "
             "floor before it is through the ring; if the ball's centre comes up through the ring from below; if you "
             "fall before the ball is through (a fall: your pelvis lower than {fall_z_m} m above the floor, or any "
             "part of you other than your feet on the floor); or after {time_limit_s} s.")
    venue = ("A FIBA court. You stand inside the free-throw semi-circle facing the basket (+x), your pelvis "
             "{start_behind_line_m} m behind the free-throw line's near edge and on the line through the ring's "
             "centre; the point under the ring's centre is {line_to_ring_m} m beyond that edge. Painted on the floor: "
             "the restricted area, the free-throw line and circle, the three-point line, the no-charge semi-circle. "
             "The ball is pressed between your two palms in front of your chest, its centre about 1.3 m above the "
             "floor and 0.45 m ahead of your pelvis: your upper arms are a little forward, your forearms a little "
             "raised and turned in so that the palms squeeze it; the start command keeps that squeeze (the joint "
             "table's start angles are a little further in than the arms stand: the difference is the squeeze). Your "
             "hands have no grip: the grip columns of the action rows do nothing in this task.")
    difficulty = ("The 0.62 kg ball has to leave the hands at about 8 m/s on a steep arc to reach a ring 3.05 m high "
                  "and more than 4 m away, with a margin of a few centimetres in air that slows it; the hands can "
                  "only squeeze it from the sides, so all of that speed has to be carried by the friction of two flat "
                  "palms, and both have to leave it at the same instant without spinning it off line. The arms' "
                  "fastest swing gives less than that, and the body only stands by an open-loop stance.")

    def build(self, sc):
        p = self.p
        hx = p["start_behind_line_m"] + p["line_to_ring_m"]
        self.hoop = build_court(sc, hx, 0.0, p)
        sc.ball("ball", "basketball", (0.42, 0.0, 1.28))         # no grip: the ball is not grippable
        opt = sc.root.find("option")
        opt.set("cone", CONE)
        opt.set("impratio", f"{IMPRATIO:g}")
        for side in ("left", "right"):
            ET.SubElement(sc.root.find("contact"), "pair", name=f"palm_ball_{side}", geom1="ball",
                          geom2=f"{side}_palm_pad", condim="6",
                          friction=f"{PALM_MU} {PALM_MU} 0.003 {BALL['roll']} {BALL['roll']}", solref=PALM_SOLREF,
                          solimp=PALM_SOLIMP)
        sc.camera("venue", (-2.6, -3.6, 2.6), (hx * 0.55, 0.0, 1.7), fovy=55)

    def reset(self, w):
        ball_between_palms(w)

    def referee_reset(self, w, ref):
        h = self.hoop
        self.ball = ref.geoms(body="ball")
        self.hands = {s: ref.part(f"{s}_hand") for s in ("left", "right")}
        self.robot = ref.part("robot")
        self.body = self.robot & ~ref.part("hands")
        self.ring = ref.geoms(prefix="hoop_rim") | ref.geoms(names=["hoop_plate"])
        self.trackers = {"hoop": HoopPass((h["x"], h["y"], h["z"]), h["inner_radius"], BALL["radius"]),
                         "up": Crossing((0, 0, 1), h["z"], direction=1), "touch": {"left": 0.0, "right": 0.0},
                         "released": None, "live": True}

    def on_ball(self, ref) -> dict:
        """Which hands are on the ball now (touching it, gaps shorter than touch_gap_s included)."""
        t = self.trackers["touch"]
        return {s: t[s] is not None and ref.time - t[s] <= self.p["touch_gap_s"] + 1e-9 for s in ("left", "right")}

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
            for s in ("left", "right"):
                if ref.touching(self.hands[s], self.ball):
                    tr["touch"][s] = round(ref.time, 4)
            if ref.touching(self.ball, self.body):
                return ref.fail("the ball touched a part of you other than your hands",
                                parts=sorted(ref.parts_touching(self.ball) - {"left_hand", "right_hand"}))
            if any(self.on_ball(ref).values()):
                if ref.touching(self.ball, ref.ground):
                    return ref.fail("the ball touched the floor")
                return
            tr["released"] = round(ref.time, 4)
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
                "hands_on_ball": self.on_ball(w.ref), "released": self.trackers["released"] is not None}
