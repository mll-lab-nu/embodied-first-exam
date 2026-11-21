"""Basketball free throw (FIBA): from behind the free-throw line, inside the semi-circle, shoot the
ball you hold in your two hands (the H1-2's own Inspire five-finger hands: contact and friction alone, no weld) so that
it enters the basket from above. Official court, backboard, ring and size-7 ball; the Unitree H1-2."""
import math

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
    name = "free-throw"
    title = "Basketball: free throw"
    category = "basketball-and-rackets"
    robot = "unitree_h1"
    rulebook = ("FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix "
                "(backboard, ring, size-7 ball), Art. 13 (how the ball is played: with the hands), Art. 14 (control: "
                "a player holds a live ball), Art. 16 (goal; a ball that passes through the basket from below is a "
                "violation), Art. 43 (free throws)")
    deviations = [
        "the player's hands: the H1-2's own Inspire hands (five fingers, six drives: four fingers, the thumb's "
        "flexion and rotation; the core's fingertip forces, 20 N, the thumb 30 N: twice the device's), closed by one command per hand; they hold the "
        "ball by contact and friction only (nothing is welded), a hand smaller than a player's (its span about 0.2 m "
        "against the ball's 0.24 m). Any shooting style is allowed; the ball is released when no hand touches it "
        "any more.",
        "Art. 13.1.2 (the ball is played with the hands only) is read strictly: until the shot is through, the ball "
        "may touch no part of you but your hands (fingers, thumb, palm and wrist); holding it against the trunk, the "
        "arms or a leg is not a hold of this task.",
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

    sentence = ("Shoot a free throw: from behind the free-throw line, shoot the basketball you hold in your two "
                "hands so that it enters the basket from above.")
    rules = ("The official basket: a rigid ring of {ring_inner_diameter_m} m inner diameter ({ring_metal_m} m metal), "
             "its top edge {ring_height_m} m above the floor, its centre {ring_centre_to_board_m} m in front of a "
             "backboard {board_width_m} m wide and {board_height_m} m high whose lower edge is {board_bottom_m} m "
             "above the floor. The ball is a size-7 basketball (" + f"{2 * BALL['radius']:.3f} m across, "
             f"{BALL['mass']:.2f} kg, it keeps {BALL['bounce']:.2f} of its speed in a bounce on the floor" + "); it "
             "flies in air (drag and spin lift). Your hands are five-finger hands that hold things only by contact and "
             "friction: the ball starts in them, between your two open palms, your arms pressing it, and is at your disposal at the start; it can slip out. A hand is its fingers, thumb, palm and "
             "wrist; a hand is on the ball while "
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
             "The ball is in your hands in front of your chest, its centre 1.13 m above the floor and 0.39 m "
             "ahead of your pelvis: both hands open (grip values 0, the fingers straight), your palms on its two "
             "sides (on these hands it bears on the two thumbs, which lie a little proud of the palms); the start command turns your shoulders a little further in than "
             "your arms stand (the difference is the squeeze that holds the ball). A grip value is that hand's closure "
             "command (0 open, 1 every finger and thumb drive closing; a finger stops on what it touches). The "
             "ball is a free body: `held` in your state says which hand holds it (its fingers and its thumb or palm "
             "on it; the open-hand squeeze at the start touches no finger, so `held` is empty there).")
    difficulty = ("The 0.62 kg ball has to leave the hands at about 8 m/s on a steep arc to reach a ring 3.05 m high "
                  "and more than 4 m away, with a margin of a few centimetres in air that slows it; the hands, "
                  "smaller than the ball, have to push it and open in time, and both have to leave it at the same "
                  "instant without spinning it off line. The arms' fastest swing gives less than that, and the body "
                  "only stands by an open-loop stance.")

    def build(self, sc):
        p = self.p
        hx = p["start_behind_line_m"] + p["line_to_ring_m"]
        self.hoop = build_court(sc, hx, 0.0, p)
        sc.ball("ball", "basketball", (0.42, 0.0, 1.28))         # nothing grippable: held by the hands' contact
        for side in ("left", "right"):                           # the H1-2's own Inspire hands (rfo.realhand)
            sc.real_hands[side] = "inspire"
        sc.camera("venue", (-2.6, -3.6, 2.6), (hx * 0.55, 0.0, 1.7), fovy=55)

    def reset(self, w):
        ball_in_hands(w)

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
