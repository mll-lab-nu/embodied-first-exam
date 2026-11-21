"""Rope skipping (the one-minute rope skipping test of the Chinese National Student Physical Fitness Standard): the
robot turns a beaded rope by its two handles, held in its own Dex3-1 hands (rfo.realhand, "dex3": a thumb, an index
and a middle finger, contact and friction only), and jumps it, forwards, both feet together."""
import math
import xml.etree.ElementTree as ET

import numpy as np

import mujoco

from rfo.task import TaskBase
# A rigid rope handle (plastic)'s contact with the robot, the venue's fixtures and the other props (the ground keeps
# its own: rfo/world.py GROUND_SOLMIX): the stiff contact of the core's shells (rfo/world.py SHELL_CONTACT: solref
# 0.004 s, solimp 0.99 0.999 0.0005, from Embodied Olympics' weightlifting fix, a rigid prop on the robot's aluminium) with
# a solmix that wins over a default-contact geom; a ball (priority 1) keeps its own bounce. With MuJoCo's default soft
# contact (solref 0.02 1, solimp 0.9 0.95) it sank 58 mm into the floor (stress test).
from rfo.world import SHELL_CONTACT as RIGID  # noqa: E402

SIDES = ("left", "right")
FLOOR = (0.80, 0.62, 0.40, 1)           # a sports hall's wooden floor (looks.py dresses it as wood)
ROPE_RGBA = ((0.85, 0.15, 0.15, 1), (0.95, 0.95, 0.95, 1))     # beads alternate in two colours
HANDLE_RGBA = (0.10, 0.25, 0.75, 1)
HANDLE_ALONG_FINGERS_M = -0.01  # the handle's axis this far from the hand's grasp centre towards the wrist (a search
#                                 over placements: where the closed fingers and thumb hold it)
ROPE_SELF_COLLISION = True      # the rope's segments collide with each other (a rope that crosses itself does not
#                                 pass through; not a segment with its tied neighbours, which it overlaps at the pivot)


def _qmul(a, b):
    out = np.zeros(4)
    mujoco.mju_mulQuat(out, np.asarray(a, float), np.asarray(b, float))
    return out


def _quat_from_x(x, prev_R=None):
    """A frame whose x axis is x (unit), turned as little as possible from prev_R (parallel transport)."""
    x = np.asarray(x, float) / np.linalg.norm(x)
    if prev_R is None:
        ref = np.array([0.0, 0.0, 1.0]) if abs(x[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    else:
        ref = prev_R[:, 2]
        if abs(ref @ x) > 0.95:
            ref = prev_R[:, 1]
    y = np.cross(ref, x)
    y /= np.linalg.norm(y)
    z = np.cross(x, y)
    R = np.c_[x, y, z]
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, R.ravel())
    return q, R


def _chord_walk(dense: np.ndarray, n: int, l: float) -> tuple[np.ndarray, float]:
    """n + 1 points starting at dense[0], each l from the previous one, walking along the polyline `dense`; and how
    far (arc length) the last point is past the polyline's end (negative: short of it)."""
    seg = np.linalg.norm(np.diff(dense, axis=0), axis=1)
    cum = np.r_[0.0, np.cumsum(seg)]
    pts = [dense[0].copy()]
    j, pos = 0, 0.0
    for _ in range(n):
        P = pts[-1]
        while j < len(dense) - 1 and np.linalg.norm(dense[j + 1] - P) < l:
            j += 1
        if j >= len(dense) - 1:                      # past the end: straight on along the last direction
            d = dense[-1] - dense[-2]
            b = d / np.linalg.norm(d)
            f = dense[-1] - P
            B, C = 2 * (f @ b), f @ f - l * l
            s = (-B + math.sqrt(max(B * B - 4 * C, 0.0))) / 2
            pts.append(dense[-1] + s * b)
            pos = cum[-1] + s
            continue
        a, b = dense[j], dense[j + 1] - dense[j]
        f = a - P
        A, B, C = b @ b, 2 * (f @ b), f @ f - l * l
        s = (-B + math.sqrt(max(B * B - 4 * A * C, 0.0))) / (2 * A)
        pts.append(a + s * b)
        pos = cum[j] + s * seg[j]
    return np.array(pts), pos - cum[-1]


class Task(TaskBase):
    name = "jump-rope"
    title = "Rope skipping (one minute)"
    category = "track-and-jumps"
    robot = "unitree_g1"
    rulebook = ("The Chinese National Student Physical Fitness Standard (国家学生体质健康标准, 2014 revision, Ministry "
                "of Education 教体艺〔2014〕5号), one-minute rope skipping (1分钟跳绳): the rope turned forwards, a "
                "two-foot jump (正摇双脚跳); each turn of the rope round the body that passes under the feet counts one; "
                "a miss (the rope caught on the body) does not stop the clock, the skipper starts the rope again; the "
                "result is the count in one minute. The family's success line is the standard's pass mark (60 points) "
                "for first-grade boys: {count} jumps in one minute")
    deviations = [
        "Equipment: the standard names no rope. The rope here is a 7 ft ({rope_length_m} m between the swivels) "
        "beaded school rope, the length that skipping-rope sizing charts give a skipper shorter than 1.45 m "
        "(4 ft 9 in): {n_seg} rigid segments of two 38 mm low-density polyethylene beads each (9.5 mm across, "
        "Kanga's deluxe beaded rope), {rope_mass_kg} kg in all (a 7 ft segmented rope weighs 0.2 lb). Neighbouring "
        "segments are tied by stiff pivots that stretch by a few millimetres under load (the cord); the rope "
        "feels the air's drag and collides with itself, the floor and the robot. Its two plastic handles are "
        "{handle_length_m} m long and {handle_mass_kg} kg each, "
        "with the rope on a swivel at their far ends.",
        "Hands: the robot's hands are its own Unitree Dex3-1 three-finger hands (1.37 N m back-driven per finger "
        "joint, at the device's torques). Each handle lies across the palm, the fingers and the thumb closed round "
        "it, held only by their contact and friction, so it can slip out or be dropped.",
        "Judging: a judge's eye is replaced by geometry, checked at every 1 ms physics step. The rope passes under a "
        "foot when its point at that foot's sideways position crosses, from front to back, the upright plane "
        "across the robot's heading through the foot, lower than the foot's lowest point (plus the rope's "
        "thickness). It passes over the head when its point at the head's sideways position crosses the upright "
        "plane through the head from back to front, higher than the top of the head. Three numbers the standard "
        "leaves to the judge's eye: the rope must move backwards at {min_rope_speed_m_s} m/s or more as it passes "
        "(a turning rope, not a hop over a still one), under the second foot within {pass_window_s} s of the first, "
        "and both feet must leave the floor within {two_foot_window_s} s of each other (a two-foot jump).",
        "Timing: the minute runs from t = 0, with the robot standing, a handle in each hand and the rope on the "
        "floor behind its heels. The attempt ends with success once the robot has landed on its feet after the "
        "{count}th jump and stood still for {stand_s} s (the families' land-and-stand rule), without waiting for "
        "the end of the minute.",
    ]
    time_limit_s = 60.0
    start = (0.0, 0.0, 0.0)
    stages = [f"jump {i + 1}" for i in range(17)] + ["stand"]
    params = dict(count=17, rope_length_m=2.13, rope_mass_kg=0.10, n_seg=28, rope_radius_m=0.00475,
                  rope_twist_inertia=2e-6, rope_tie_solref_s=0.004, rope_solref_s=0.004, rope_friction=0.4,
                  handle_length_m=0.15, handle_radius_m=0.014, handle_mass_kg=0.04, handle_inside_m=0.05, closure=1.0,
                  rope_drag_cd=1.2, rope_behind_m=0.25, two_foot_window_s=0.10, pass_window_s=0.15, min_rope_speed_m_s=1.0,
                  release_s=0.05, stand_s=1.0, fall_z_m=0.35)

    sentence = ("Skip rope: turn the rope forwards with both hands, over your head and under your feet, and jump it "
                "with both feet together, {count} times within one minute.")
    rules = ("You hold a skipping rope by its two handles, one in each of your three-finger hands. Turn it forwards: "
             "over your head from back to front, then down in front of you and under your feet from front to back. "
             "A jump counts when the rope, after passing over your head, passes under both feet while nothing of you "
             "touches the floor, and your take-off was two-footed: both feet left the floor within "
             "{two_foot_window_s} s of each other. The rope passes over your head when its point straight above "
             "your head crosses the upright plane through your head, from back to front, higher than the top of "
             "your head. It passes under a foot when its point at that foot's sideways position crosses the upright "
             "plane through that foot, across your heading, from front to back, lower than the bottom of the foot "
             "plus the rope's thickness, while it moves backwards over the floor at {min_rope_speed_m_s} m/s or more (the "
             "rope turning, not you hopping forwards over a still rope). It must pass under the second foot within "
             "{pass_window_s} s of the first. "
             "Each turn of the rope counts at most once. Extra hops between turns are allowed but do not count. "
             "A miss does not end the attempt: if the rope stops on your body, passes under the feet while a foot "
             "or anything else of you touches the floor, passes under only one foot, turns backwards, or comes "
             "under your feet without first going over your head, that turn does not count, and the rope must go "
             "over your head again before the next jump. After your {count}th counted jump you must land on your "
             "feet (the first thing of you to touch the floor) and then stand for {stand_s} s without a break: only "
             "your feet on the floor, your torso within about 20 degrees of vertical, your pelvis slower than "
             "0.35 m/s; then you succeed. You fail if you let go of a handle (a handle out of its hand for more than "
             "{release_s} s: not touching that hand's fingers and its thumb or palm; or a handle touching the floor), if the last landing is not on your feet, if "
             "you fall (your pelvis lower than {fall_z_m} m, or any part of you other than your feet on the floor), "
             "or after {time_limit_s} s.")
    venue = ("You stand facing +x on the level wooden floor of a sports hall. In each hand you hold a handle "
             "({handle_length_m} m long, 0.028 m thick) across the palm, the fingers closed round it, its far end "
             "about 0.07 m beyond the index finger's side, where the rope is attached on a swivel. The rope is {rope_length_m} m long and {rope_mass_kg} kg, "
             "made of plastic beads 9.5 mm thick. It hangs from each handle straight down to the floor and lies on "
             "the floor behind your heels in a bow whose middle is about {rope_behind_m} m behind your pelvis or "
             "further. Nothing else is near you.")
    difficulty = ("Every jump needs two skills at once. The arms must keep a light, floppy rope turning at a steady "
                  "speed through hands that hold it only by friction. The legs must make a two-footed hop, about "
                  "0.1 m high and timed to within a tenth of a second, to the rope coming under the feet. Then the "
                  "robot must land and do it again {count} times without falling. Neither built-in gait can hop, "
                  "and a rope that stops on a shin or a toe has to be started again from behind.")

    def __init__(self):
        super().__init__()
        self._stages()

    def configure(self, params):
        super().configure(params)
        self._stages()

    def _stages(self):
        self.stages = [f"jump {i + 1}" for i in range(int(self.p["count"]))] + ["stand"]
        self.fall_z = self.p["fall_z_m"]

    # ------------------------------------------------------------------ the venue
    def seg_len(self) -> float:
        return self.p["rope_length_m"] / int(self.p["n_seg"])

    def build(self, sc):
        p = self.p
        sc.box("hall", (0.0, 0.0, 0.0003), (4.0, 4.0, 0.0003), rgba=FLOOR)
        hl, hr, hm = p["handle_length_m"], p["handle_radius_m"], p["handle_mass_kg"]
        N, l, r = int(p["n_seg"]), self.seg_len(), p["rope_radius_m"]
        mseg = p["rope_mass_kg"] / N
        for s in SIDES:                               # the G1's Dex3-1 hands: the handles are held by friction
            sc.real_hands[s] = "dex3"
        # qpos0 is only a reference (reset() places everything): the handles high above the floor, side by side
        for s, y in (("left", 0.6), ("right", -0.6)):
            b = sc.body(f"handle_{s}", (0.0, y, 1.8), free=True)
            sc.geom(b, f"handle_{s}", type="cylinder", size=(hr, hl / 2), mass=hm,
                    rgba=HANDLE_RGBA, contype="1", conaffinity="13", condim="4", friction=(0.8, 0.005, 0.0001),
                    **RIGID)
            ET.SubElement(b, "site", name=f"swivel_{s}", pos=f"0 0 {hl / 2:.6g}", size="0.004", group="4")
        # the rope: N segments, each a free body; neighbours, and the two ends to the handles' swivels, are tied by
        # `connect` constraints (the beads' pivots on the cord, the swivel bearings). A chain of ball joints instead
        # makes MuJoCo factor one deep tree densely (slow) and blows up when the rope snaps taut (an inextensible
        # chain); the connects' slight compliance is the cord's stretch.
        i_bend = mseg * (l * l / 12 + r * r / 4)
        rope = dict(contype="2", conaffinity="15" if ROPE_SELF_COLLISION else "13", condim="3", priority="3",
                    friction=f"{p['rope_friction']:g} 0.005 0.0001", solref=f"{p['rope_solref_s']:g} 1",
                    solimp="0.9 0.95 0.001", fluidshape="ellipsoid", fluidcoef=(p["rope_drag_cd"] / 2, 0.25, 1.5, 0, 0))
        eq = sc.root.find("equality")
        for i in range(N):
            bd = sc.body(f"rope{i}", (0.0, 0.5 - i * l, 2.0), free=True)
            ET.SubElement(bd, "inertial", pos=f"{l / 2:.6g} 0 0", mass=f"{mseg:.6g}",
                          diaginertia=f"{min(p['rope_twist_inertia'], 1.9 * i_bend):.6g} {i_bend:.6g} {i_bend:.6g}")
            sc.geom(bd, f"rope{i}", type="capsule", fromto=(0, 0, 0, l, 0, 0), size=(r,), rgba=ROPE_RGBA[i % 2],
                    **rope)
            ET.SubElement(bd, "site", name=f"rope{i}", pos="0 0 0", size="0.002", group="4")
            ET.SubElement(bd, "site", name=f"rope{i}_end", pos=f"{l:.6g} 0 0", size="0.002", group="4")
            ET.SubElement(eq, "connect", name=f"rope_tie{i}", site1=f"rope{i}",
                          site2="swivel_left" if i == 0 else f"rope{i - 1}_end", solref=f"{p['rope_tie_solref_s']:g} 1")
        ET.SubElement(eq, "connect", name="rope_tie_end", site1=f"rope{N - 1}_end", site2="swivel_right",
                      solref=f"{p['rope_tie_solref_s']:g} 1")
        ex = sc.root.find("contact")                  # the rope does not rub on its own handles
        for s in SIDES:
            for i in range(N):
                ET.SubElement(ex, "exclude", body1=f"handle_{s}", body2=f"rope{i}")
        for i in range(N - 1):                        # nor a segment on its tied neighbours (self-collision: the rest)
            ET.SubElement(ex, "exclude", body1=f"rope{i}", body2=f"rope{i + 1}")
        sc.camera("venue", (2.6, -2.2, 1.3), (0.0, 0.0, 0.65), fovy=50)
        sc.camera("side", (0.0, -3.2, 0.8), (0.0, 0.0, 0.7), fovy=45)

    # ------------------------------------------------------------------ t = 0
    def handle_in_hand(self, w, side):
        """(position, quaternion) of a handle in the hand at t = 0: across the palm (its axis the hand's grasp frame's
        y through the grasp centre), its inner end handle_inside_m beyond the grasp centre on the middle finger's
        side, the swivel end beyond the index finger's side (the grasp frame's y points to the middle finger on the
        left hand, to the index finger on the right)."""
        c, R = w.grasp_frame(side)
        c = c + R[:, 2] * HANDLE_ALONG_FINGERS_M
        ax = R[:, 1] * (-1.0 if side == "left" else 1.0)
        centre = c + ax * (self.p["handle_length_m"] / 2 - self.p["handle_inside_m"])
        q, _ = _quat_from_x(ax)                                 # a frame with x = the handle's axis ...
        q = _qmul(q, np.array([math.cos(math.pi / 4), 0, math.sin(math.pi / 4), 0]))   # ... its z the axis
        return centre, q

    def rope_path(self, S, E, back_x: float):
        """The rope at rest from the left swivel S to the right one E: straight down from S to the floor, along the
        floor round behind the heels (a bow reaching back to back_x and beyond as its length needs), up to E.
        Returns the N + 1 nodes."""
        p = self.p
        N, l, r = int(p["n_seg"]), self.seg_len(), p["rope_radius_m"]

        def dense(bulge):
            A = np.array([S[0], S[1], r])
            B = np.array([E[0], E[1], r])
            u = np.linspace(0, 1, 600)
            leg1 = S[None, :] + (A - S)[None, :] * u[:, None]
            depth = (A[0] - back_x) + bulge
            floor = np.c_[A[0] + (B[0] - A[0]) * u - depth * np.sin(np.pi * u), A[1] + (B[1] - A[1]) * u,
                          np.full_like(u, r)]
            leg2 = B[None, :] + (E - B)[None, :] * u[:, None]
            return np.r_[leg1, floor[1:], leg2[1:]]

        def over(bulge):
            return _chord_walk(dense(bulge), N, l)

        lo, hi = -0.2, 2.0                      # over() falls as the path gets longer (a deeper bow)
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if over(mid)[1] > 0 else (lo, mid)
        pts, _ = over((lo + hi) / 2)
        pts = pts[:-1]
        return np.r_[pts, E[None, :]]

    def reset(self, w):
        m, d = w.m, w.d
        mujoco.mj_kinematics(m, d)
        hl = self.p["handle_length_m"]
        sw = {}
        for s in SIDES:
            c, q = self.handle_in_hand(w, s)
            w.put(f"handle_{s}", c, q)
            R = np.zeros(9)
            mujoco.mju_quat2Mat(R, q)
            sw[s] = c + R.reshape(3, 3)[:, 2] * hl / 2
        self._place_rope(w, sw)
        self.grasp = {s: w.close_on(s, f"handle_{s}", closure=self.p["closure"]) for s in SIDES}
        mujoco.mj_kinematics(m, d)                     # the grasps have settled: the rope again from the swivels
        self._place_rope(w, {s: d.site_xpos[m.site(f"swivel_{s}").id].copy() for s in SIDES})
        mujoco.mj_kinematics(m, d)

    def _place_rope(self, w, sw):
        m, d = w.m, w.d
        pts = self.rope_path(sw["left"], sw["right"], w.pelvis()[0] - self.p["rope_behind_m"])
        Rp = None
        for i in range(int(self.p["n_seg"])):
            Q, Rp = _quat_from_x(pts[i + 1] - pts[i], Rp)
            w.put(f"rope{i}", pts[i], Q)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        m = w.m
        N = int(self.p["n_seg"])
        self._seg_ids = np.array([m.body(f"rope{i}").id for i in range(N)])
        self._seg_vadr = np.array([w.free[f"rope{i}"][1] for i in range(N)])
        col = (m.geom_contype != 0) | (m.geom_conaffinity != 0)
        self._foot_g = {s: np.flatnonzero(ref.part(f"{s}_foot") & col) for s in SIDES}
        self._head_g = np.flatnonzero(ref.part("head") & col)
        self._robot = ref.part("robot")
        self._feet = {s: ref.part(f"{s}_foot") for s in SIDES}
        self._handles = {s: ref.geoms(names=[f"handle_{s}"]) for s in SIDES}
        self.fall_z = self.p["fall_z_m"]
        self.trackers = {
            "count": 0,
            "state": "over",            # what the rope must do next: "over" the head, then "under" the feet
            "prev": {"left": None, "right": None, "head": None},   # signed distance of the rope's point past the plane
            "under": {},                # the feet the rope has passed under since its last pass over the head
            "on_ground": {"left": 0.0, "right": 0.0},              # when each foot last touched the ground
            "unheld": {"left": None, "right": None},               # since when a handle has not been in its hand
            "turns": 0.0, "angle": None, "landing": False, "landed": False,
        }

    # geometry -------------------------------------------------------------
    def rope_points(self, w) -> np.ndarray:
        """The rope's N + 1 nodes (world), from the left swivel to the right one."""
        d = w.d
        ids = self._seg_ids
        P = d.xpos[ids]
        X = d.xmat[ids].reshape(-1, 3, 3)[:, :, 0]
        return np.r_[P, (P[-1] + X[-1] * self.seg_len())[None, :]]

    def _span(self, w, g, axis) -> tuple[float, float]:
        """(min, max) of geoms g along a unit vector (their oriented bounding boxes)."""
        m, d = w.m, w.d
        R = d.geom_xmat[g].reshape(-1, 3, 3)
        c = d.geom_xpos[g] + np.einsum("gij,gj->gi", R, m.geom_aabb[g, :3])
        half = np.sum(np.abs(np.einsum("i,gij->gj", axis, R)) * m.geom_aabb[g, 3:], axis=1)
        p = c @ axis
        return float(np.min(p - half)), float(np.max(p + half))

    def frame(self, w):
        """The robot's heading frame: origin (the pelvis over the floor), forward and left unit vectors."""
        x, y, _, yaw = w.pelvis()
        return np.array([x, y, 0.0]), np.array([math.cos(yaw), math.sin(yaw), 0.0]), \
            np.array([-math.sin(yaw), math.cos(yaw), 0.0])

    @staticmethod
    def rope_at(P, o, fwd, left, y):
        """The rope's point at the sideways position y (heading frame): (forward, height, segment i, fraction f) by
        interpolation on the segment i (nodes i, i + 1) that crosses y nearest the rope's middle; None if no part of
        the rope is there."""
        u = (P - o) @ left - y
        s = u[:-1] * u[1:]
        idx = np.flatnonzero(s <= 0)
        if not len(idx):
            return None
        i = int(idx[np.argmin(np.abs(idx + 0.5 - (len(P) - 1) / 2))])
        f = u[i] / (u[i] - u[i + 1]) if u[i] != u[i + 1] else 0.5
        q = P[i] + f * (P[i + 1] - P[i])
        return float((q - o) @ fwd), float(q[2]), i, float(f)

    def node_velocities(self, w) -> np.ndarray:
        """The rope's N + 1 nodes' velocities (world): each segment's start is its free body's origin, whose linear
        velocity is the free joint's; the last node is the last segment's far end."""
        d = w.d
        V = d.qvel[self._seg_vadr[:, None] + np.arange(3)[None, :]]
        b = self._seg_ids[-1]
        x = d.xmat[b].reshape(3, 3)[:, 0] * self.seg_len()
        om = d.qvel[self._seg_vadr[-1] + 3:self._seg_vadr[-1] + 6]          # (the free joint's local angular velocity)
        om_w = d.xmat[b].reshape(3, 3) @ om
        return np.r_[V, (V[-1] + np.cross(om_w, x))[None, :]]

    def landmarks(self, w):
        """The planes the rope must pass: for each foot (forward position, sideways position, its lowest point) and
        the head (forward position, sideways position, its top), in the heading frame."""
        o, fwd, left = self.frame(w)
        up = np.array([0.0, 0.0, 1.0])
        out = {}
        for s in SIDES:
            g = self._foot_g[s]
            f0, f1 = self._span(w, g, fwd)
            l0, l1 = self._span(w, g, left)
            out[s] = ((f0 + f1) / 2 - o @ fwd, (l0 + l1) / 2 - o @ left, self._span(w, g, up)[0])
        g = self._head_g
        f0, f1 = self._span(w, g, fwd)
        l0, l1 = self._span(w, g, left)
        out["head"] = ((f0 + f1) / 2 - o @ fwd, (l0 + l1) / 2 - o @ left, self._span(w, g, up)[1])
        return (o, fwd, left), out

    # the rules ------------------------------------------------------------
    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        t = ref.time
        ground = ref.ground
        for s in SIDES:
            if ref.touching(self._feet[s], ground):
                tr["on_ground"][s] = t
        airborne = not ref.touching(self._robot, ground)
        for s in SIDES:                                  # a handle out of its hand (or on the ground)
            if ref.touching(self._handles[s], ground):
                return ref.fail("let go of a handle", hand=s, why="the handle touched the ground")
            if w.held[s] == f"handle_{s}":
                tr["unheld"][s] = None
            elif tr["unheld"][s] is None:
                tr["unheld"][s] = t
            elif t - tr["unheld"][s] >= p["release_s"]:
                return ref.fail("let go of a handle", hand=s)
        if tr["landing"]:                               # the qualifying jump has been counted: its landing
            if not tr["landed"] and not airborne:
                parts = ref.parts_touching(ground)
                if parts <= {"left_foot", "right_foot"}:
                    tr["landed"] = True                  # (then the stand: step())
                else:
                    ref.fail("the landing was not on the feet", parts=sorted(parts))
            return
        (o, fwd, left), lm = self.landmarks(w)
        P = self.rope_points(w)
        V = None
        for key in ("left", "right", "head"):
            fx, fy, fz = lm[key]
            q = self.rope_at(P, o, fwd, left, fy)
            prev = tr["prev"][key]
            cur = None if q is None else q[0] - fx
            tr["prev"][key] = cur
            if q is None or prev is None or (prev >= 0) == (cur >= 0):
                continue
            if V is None:
                V = self.node_velocities(w)
            i, f = q[2], q[3]                           # the rope's own speed forwards over the floor: the
            speed = float(((1 - f) * V[i] + f * V[i + 1]) @ fwd)    # material point's velocity (not the frame's)
            back_to_front = cur >= 0
            z = q[1]
            if key == "head":
                if back_to_front and z > fz:            # over the head, forwards
                    if tr["state"] == "under" and tr["under"]:
                        self._miss(ref, "the rope did not pass under both feet", feet=sorted(tr["under"]))
                    tr["state"], tr["under"] = "under", {}
                elif not back_to_front and z > fz and tr["state"] == "under":
                    self._miss(ref, "the rope turned back over the head")
                    tr["state"], tr["under"] = "over", {}
                continue
            if z >= fz + 2 * p["rope_radius_m"]:         # not under this foot (beside it, or at the leg)
                continue
            if back_to_front:
                self._miss(ref, "the rope passed under the feet backwards", foot=key)
                tr["state"], tr["under"] = "over", {}
                continue
            if tr["state"] != "under":
                self._miss(ref, "the rope passed under the feet without going over the head first", foot=key)
                continue
            tr["under"][key] = {"t": round(t, 4), "airborne": airborne, "rope_below_m": round(fz - z, 4),
                                "rope_speed_m_s": round(-speed, 3)}
            if len(tr["under"]) == 2:
                self._judge(w, ref)
        if tr["state"] == "under" and len(tr["under"]) == 1:
            t0 = next(iter(tr["under"].values()))["t"]
            if t - t0 > p["pass_window_s"]:
                self._miss(ref, "the rope did not pass under both feet", feet=sorted(tr["under"]))
                tr["state"], tr["under"] = "over", {}

    def _miss(self, ref, why, **kw):
        ref.event("no count", why=why, **kw)
        self.trackers["last_miss"] = why

    def _judge(self, w, ref):
        tr, p = self.trackers, self.p
        u = tr["under"]
        tr["state"], tr["under"] = "over", {}
        if not all(v["airborne"] for v in u.values()):
            return self._miss(ref, "a foot or another part of the robot was on the ground as the rope passed")
        if min(v["rope_speed_m_s"] for v in u.values()) < p["min_rope_speed_m_s"]:
            return self._miss(ref, "the rope was not turning under the feet (a jump over a still rope)",
                              speeds=[v["rope_speed_m_s"] for v in u.values()])
        lag = abs(tr["on_ground"]["left"] - tr["on_ground"]["right"])
        if lag > p["two_foot_window_s"]:
            return self._miss(ref, "not a two-foot take-off", lag_s=round(lag, 3))
        tr["count"] += 1
        ref.metrics["count"] = tr["count"]
        ref.stage(f"jump {tr['count']}", passes=u)
        if tr["count"] >= int(p["count"]):
            tr["landing"] = True

    def step(self, w, ref):
        tr = self.trackers
        P = self.rope_points(w)                         # the rope's revolutions (reported): its middle's angle
        a, b = P[0], P[-1]                               # around the line between the swivels
        ax = b - a
        n = np.linalg.norm(ax)
        if n > 1e-6:
            ax = ax / n
            mid = P[len(P) // 2] - a
            r = mid - (mid @ ax) * ax
            e1 = np.array([0.0, 0.0, 1.0]) - ax[2] * ax
            e1 /= max(np.linalg.norm(e1), 1e-9)
            e2 = np.cross(ax, e1)
            ang = math.atan2(float(r @ e2), float(r @ e1))
            if tr["angle"] is not None:
                da = (ang - tr["angle"] + math.pi) % (2 * math.pi) - math.pi
                tr["turns"] = round(tr["turns"] - da / (2 * math.pi), 6)    # forwards > 0
            tr["angle"] = round(ang, 9)
        ref.metrics["count"] = tr["count"]
        ref.metrics["rope_turns"] = round(tr["turns"], 3)
        if tr["landed"] and ref.hold("stand", ref.standing(), self.p["stand_s"]):    # land and stand
            if ref.stage("stand"):
                ref.succeed()

    def privileged(self, w):
        tr = self.trackers
        P = self.rope_points(w)
        return {"pelvis": w.pelvis().tolist(), "rope_nodes": P.round(4).tolist(),
                "handles": {s: w.pos(f"handle_{s}").round(4).tolist() for s in SIDES},
                "held": {s: w.held[s] == f"handle_{s}" for s in SIDES}, "count": tr["count"],
                "waiting_for": tr["state"], "rope_turns": tr["turns"]}
