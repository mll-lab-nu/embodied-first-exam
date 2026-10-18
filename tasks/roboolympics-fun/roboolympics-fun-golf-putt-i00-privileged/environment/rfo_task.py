"""Golf putt (v2, official setting): a 3 m putt on a flat green at stimp 10, into a real hole (108 mm across, 101.6 mm
deep, cut into the green: the ball physically drops in), with one stroke of a real putter (0.86 m, 0.5 kg, 3 degrees of
loft, 70 degrees of lie) that is fixed in the Unitree G1's right hand. The robot stands side-on to the putt, as a
golfer does: the ball in front of it, the hole to its left.

How the venue is built. The scene's floor plane cannot have a hole, so this module lowers it by the hole's depth (it is
then the bottom of the hole and the ground around the green) and lays the green on it as boxes whose tops are at
z = 0: four slabs around a square of 0.28 m, and inside that square 24 wedge boxes around the hole, each with one
vertical face on a side of a regular 24-gon. The polygon is inscribed in the official 108 mm circle (its corners are
on the circle, its flats 0.46 mm inside it), so the opening is nowhere wider than the official hole.

Measured in the simulator (tests/test_golf_putt.py asserts the first two):
- stimp: with the ball's rolling resistance GREEN_ROLL_M a ball that starts rolling at 1.83 m/s (the speed a USGA
  Stimpmeter releases it at) stops after 3.05 m (10 ft): stimp 10; its deceleration is 0.55 m/s^2;
- the hole takes a ball that rolls over its centre at up to about 1.5 m/s at the lip (a real hole: 1.63 m/s, the speed
  at which the ball falls its radius while it crosses), one 20 mm off the centre up to 1.4 m/s, 30 mm off up to
  1.1 m/s, 40 mm off only below 0.7 m/s; faster or wider balls lip out or jump it;
- a ball struck by the putter leaves without spin, skids, and rolls on at about 5/7 of its launch speed (as on a real
  green): a putt that dies at the hole needs a launch of about 2.6 m/s, a head speed of about 1.7 m/s;
- the G1 can address this ball with the unscaled putter (the reference solution does): the forearm forwards and down,
  the wrist's roll joint about 1.6 rad, the shaft about 5 degrees from vertical (the toe 10 degrees down); with the
  sole flat (the shaft 20 degrees from vertical) the hand would have to be where the arm does not reach.

The world uses elliptic friction cones (set in build): with MuJoCo's default pyramids a ball rolling at an angle to
the world's axes drifted off its line (by a quarter of the angle over 3 m).
"""
import math

import numpy as np

from rfo.referee import Touch
from rfo.scene import OFFICIAL, fmt, quat_z
from rfo.task import TaskBase

BALL = OFFICIAL["golf"]                 # R&A / USGA: at least 42.67 mm, at most 45.93 g
GREEN_ROLL_M = 0.00166                  # the ball's rolling resistance on the green (m): stimp 10, see the calibration
HOLE_SIDES = 24                         # the hole's polygon
CORE_HALF_M = 0.14                      # the square round the hole that the wedge boxes fill
WEDGE_LEN_M = 0.16
GREEN_RGBA = (0.33, 0.66, 0.33, 1)

# The putter (Equipment Rules, Part 2: a plain head, longer from heel to toe than from face to back, loft at most 10
# degrees, the shaft at least 10 degrees off the vertical in the address position). Lengths in m, masses in kg.
PUTTER = dict(grip_length_m=0.26, grip_radius_m=0.012, butt_above_fist_m=0.05, shaft_radius_m=0.0045,
              head_heel_toe_m=0.110, head_face_back_m=0.025, head_height_m=0.025, hosel_from_heel_m=0.015,
              grip_kg=0.05, shaft_kg=0.10, head_kg=0.35, lie_deg=70.0)


def _quat(cols) -> tuple:
    """The quaternion (w, x, y, z) of the rotation whose matrix has the three unit vectors `cols` as its columns."""
    import mujoco
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, np.array(cols, float).T.ravel())
    return tuple(float(x) for x in q)


def putter_frame(lie_deg: float, loft_deg: float) -> dict:
    """The putter's directions in the wrist mount's frame (+z along the forearm away from the wrist, x the palm's
    normal): the shaft runs from the fist along -y (at right angles to the forearm, as a fist holds a hammer); the
    head's heel-to-toe line h makes the lie angle with the shaft, its toe on the side the forearm points to; n is the
    sole's normal (up when the sole is flat on the green); the face looks along f = +x, tilted up by the loft."""
    L, l = math.radians(lie_deg), math.radians(loft_deg)
    s = np.array([0.0, -1.0, 0.0])
    u = np.array([0.0, 0.0, 1.0])
    h = math.cos(L) * s + math.sin(L) * u
    n = -math.sin(L) * s + math.cos(L) * u
    f = np.array([1.0, 0.0, 0.0])
    return dict(s=s, h=h, n=n, f=f, f_loft=math.cos(l) * f + math.sin(l) * n, n_loft=-math.sin(l) * f + math.cos(l) * n)


def putter(length: float, loft_deg: float, mass: float) -> str:
    """The putter as MJCF in the wrist mount's frame: grip, shaft, head and a face plate that carries the loft. Its
    length is measured as the Rules do, along the shaft's axis from the butt to the sole."""
    P, F = PUTTER, putter_frame(PUTTER["lie_deg"], loft_deg)
    k = mass / (P["grip_kg"] + P["shaft_kg"] + P["head_kg"])      # the three parts in their proportions
    hh = P["head_height_m"] / 2
    fist = np.array([0.0, 0.0, 0.05])                        # the middle of the fist
    butt = fist - F["s"] * P["butt_above_fist_m"]
    grip_end = butt + F["s"] * P["grip_length_m"]
    hosel = butt + F["s"] * (length - hh / math.sin(math.radians(P["lie_deg"])))     # the axis meets the head's mid-plane
    head = hosel + F["h"] * (P["head_heel_toe_m"] / 2 - P["hosel_from_heel_m"])
    face = head + F["f"] * (P["head_face_back_m"] / 2 + 0.002)
    col = 'contype="4" conaffinity="0"'
    return (
        f'<geom name="putter_grip" type="capsule" fromto="{fmt(butt)} {fmt(grip_end)}" size="{P["grip_radius_m"]}" '
        f'mass="{k * P["grip_kg"]:.6g}" rgba="0.1 0.1 0.1 1" {col}/>'
        f'<geom name="putter_shaft" type="capsule" fromto="{fmt(grip_end)} {fmt(hosel)}" size="{P["shaft_radius_m"]}" '
        f'mass="{k * P["shaft_kg"]:.6g}" rgba="0.75 0.75 0.78 1" {col}/>'
        f'<geom name="putter_head" type="box" pos="{fmt(head)}" quat="{fmt(_quat([F["h"], F["f"], F["n"]]))}" '
        f'size="{P["head_heel_toe_m"] / 2} {P["head_face_back_m"] / 2} {hh}" mass="{k * (P["head_kg"] - 0.02):.6g}" '
        f'rgba="0.15 0.15 0.18 1" {col}/>'
        f'<geom name="putter_face" type="box" pos="{fmt(face)}" '
        f'quat="{fmt(_quat([F["h"], F["f_loft"], F["n_loft"]]))}" size="{P["head_heel_toe_m"] / 2} 0.0015 {hh}" '
        f'mass="{k * 0.02:.6g}" rgba="0.8 0.8 0.82 1" {col}/>')


class Task(TaskBase):
    name = "golf-putt"
    title = "Golf: a 3 m putt"
    category = "basketball-and-rackets"
    robot = "unitree_g1"
    rulebook = ("The Rules of Golf (R&A / USGA, 2023): Definitions \"Hole\", \"Holed\", \"Stroke\", \"Line of Play\"; "
                "Rules 8.1b, 9.4, 10.1a, 10.1c, 11.1, 13.2, 13.3a; the Equipment Rules (2023), Part 2 (clubs) and Part 4 (the ball); "
                "the USGA Stimpmeter instructions for the green's speed")
    deviations = [
        "Definition \"Hole\": the opening is a regular {hole_sides}-sided polygon inscribed in the {hole_diameter_m} m "
        "circle (flats 0.5 mm inside it, never wider than the official hole) with rigid vertical walls (the liner is "
        "only drawn), because the simulator has no cylindrical cavity",
        "Rule 13.2: there is no flagstick (as when the player has it removed)",
        "Rule 10.1 and the Equipment Rules on the grip: the putter is fixed rigidly to the right wrist of a robot "
        "that has no fingers, its grip at right angles to the forearm (as a fist holds a hammer), and is played with "
        "one arm; the club itself is not scaled to the 1.32 m robot",
        "Rule 10.1a (a fair strike; an accidental double hit is one stroke): the referee needs numbers: every contact "
        "of the head with the ball must fall within {stroke_window_s} s of the first, and the contacts together may "
        "last at most {max_contact_s} s (the simulated impact of a clean putt lasts 0.012 s, a real one "
        "0.0005 s: the ball's contact is softer than a real ball's so that the simulator's 1 ms step resolves it)",
        "Rules 9.4, 11.1 and 3.3 (penalty strokes, replaying, counting strokes): a single attempt: anything that would "
        "cost a penalty or need a second stroke ends it as a failure",
        "Rule 13.3a (waiting for a ball that overhangs the hole): a ball that has been at rest for {rest_s} s is final",
        "the green: perfectly flat and uniform, no grain, no wind; its speed (stimp {stimp_ft}) is the ball's rolling "
        "resistance, calibrated so that a ball rolling at 1.83 m/s stops after 3.05 m",
    ]
    time_limit_s = 30.0
    start = (0.0, 0.0, 0.0)
    stages = ["stroke", "holed"]
    legal_ground = ("left_foot", "right_foot", "right_tool")        # the putter may be grounded (Rule 8.1b)
    params = dict(hole_diameter_m=0.108, hole_depth_m=0.1016, hole_sides=HOLE_SIDES, putt_distance_m=3.0, stimp_ft=10,
                  roll_resistance_m=GREEN_ROLL_M,
                  ball_x_m=0.44, ball_y_m=-0.12, putter_length_m=0.86, putter_mass_kg=0.50, putter_loft_deg=3.0,
                  green_behind_m=1.5, green_beyond_m=3.0, green_half_width_m=2.0,
                  max_contact_s=0.03, stroke_window_s=0.2, rest_move_m=0.001, rest_s=1.0, fall_height_m=0.35)

    def __init__(self):
        super().__init__()
        self.fall_z = self.p["fall_height_m"]

    def configure(self, params):
        super().configure(params)
        self.fall_z = self.p["fall_height_m"]

    sentence = ("Hole the {putt_distance_m} m putt: with one stroke of the putter in your right hand, roll the golf "
                "ball that lies on the green into the hole.")
    rules = ("The ball (42.67 mm, 45.9 g) lies at rest on a flat green of stimp {stimp_ft} (a ball that starts rolling "
             "at 1.83 m/s stops after 3.05 m). The hole is cut into the green {putt_distance_m} m from the ball: "
             "{hole_diameter_m} m across and {hole_depth_m} m deep, with no flagstick in it. A putter ("
             "{putter_length_m} m long, {putter_mass_kg} kg, {putter_loft_deg} degrees of loft) is fixed in your right "
             "hand. You succeed when the ball is holed with one stroke: after the stroke it comes to rest (its "
             "centre moves less than {rest_move_m} m in {rest_s} s) inside the hole with the whole ball below the "
             "surface of the green. A stroke is a fair strike of the ball with the putter's head (any side of the head): the first "
             "contact of the head with the ball starts it, every further contact must come within {stroke_window_s} s "
             "of the first (an accidental double hit is still one stroke), and all the contacts together may last at "
             "most {max_contact_s} s. You fail if the contacts last longer (the ball was pushed, scraped or scooped), "
             "if the head touches the ball again later (a second stroke), if anything else of you ever touches the "
             "ball (the putter's shaft or grip, a foot, a leg, a hand), if at the moment of the stroke your feet touch "
             "the green on both sides of the line of play (the straight line through the ball's spot and the hole's "
             "centre, extended behind the ball) or on that line, if the ball comes to rest anywhere but in the hole "
             "(on the lip and on the green beyond the hole included), if the ball leaves the green, if you fall (your "
             "pelvis lower than {fall_height_m} m above the green, or any part of you other than your feet touching "
             "the ground; the putter may touch the green), or after {time_limit_s} s.")
    venue = ("You stand on the green facing +x, side-on to the putt as a golfer does. The ball lies {ball_x_m} m ahead "
             "of your pelvis and {ball_y_m} m to your left (negative: to your right); the hole's centre is "
             "{putt_distance_m} m from the ball in the +y direction (to your left), so the line of play runs across "
             "in front of your feet. The green is level and extends {green_behind_m} m behind the ball (to your "
             "right), {green_beyond_m} m beyond the hole and {green_half_width_m} m to each side of the line of play; "
             "around it the ground is {hole_depth_m} m lower. The putter is a blade putter: its grip is held in your "
             "right fist at right angles to the forearm, the butt 0.05 m above the fist and the shaft leaving the fist "
             "on the other side, so with your arm at rest it points away from your right side, about level with your "
             "hand. The head (0.110 m from heel to toe, 0.025 m from face to back, 0.025 m high, 0.35 kg) sits at "
             "the shaft's end at a lie of 70 degrees, its toe on the side your forearm points to; its face looks at "
             "right angles to both the shaft and the forearm: to your left when the forearm points forwards and the "
             "shaft down. There is no wind.")
    difficulty = ("The hole is two and a half ball widths across and three metres away: the ball must start within "
                  "about one degree of the line and at a speed between the one that just reaches the hole and the one "
                  "that jumps it, and there is no second stroke. The club is an adult's, long and heavy for this "
                  "robot's wrist, and it has to be brought from where it starts to an address beside the ball first.")

    # ------------------------------------------------------------------ the venue
    def hole(self) -> np.ndarray:
        p = self.p
        return np.array([p["ball_x_m"], p["ball_y_m"] + p["putt_distance_m"]])      # the line of play is +y

    def build(self, sc):
        p = self.p
        hx, hy = self.hole()
        D, R, N = p["hole_depth_m"], p["hole_diameter_m"] / 2, int(p["hole_sides"])
        # elliptic friction cones: with MuJoCo's default pyramids the rolling resistance is not the same in every
        # direction, and a ball that rolls at an angle to the world's axes drifts off its line
        sc.root.find("option").set("cone", "elliptic")
        # the floor plane, lowered: the bottom of the hole and the ground around the green
        next(g for g in sc.wb.iter("geom") if g.get("name") == "floor").set("pos", fmt((0, 0, -D)))
        x0, x1 = hx - p["green_half_width_m"], hx + p["green_half_width_m"]
        y0, y1 = p["ball_y_m"] - p["green_behind_m"], hy + p["green_beyond_m"]
        c = CORE_HALF_M

        def slab(name, xa, xb, ya, yb):
            sc.box(name, ((xa + xb) / 2, (ya + yb) / 2, -D / 2), ((xb - xa) / 2, (yb - ya) / 2, D / 2), rgba=GREEN_RGBA,
                   solid="stand", friction=(1.0, 0.005, 0.0001))
            sc.ground.append(name)

        slab("green_near", x0, x1, y0, hy - c)               # the robot, and the ball's roll up to 0.14 m before the hole
        slab("green_far", x0, x1, hy + c, y1)
        slab("green_right", hx + c, x1, hy - c, hy + c)
        slab("green_left", x0, hx - c, hy - c, hy + c)
        a = R * math.cos(math.pi / N)                        # the polygon's flats (its corners are on the circle)
        w = (a + WEDGE_LEN_M) * math.tan(math.pi / N) + 0.002
        for i in range(N):
            th = 2 * math.pi * (i + 0.5) / N
            rc = a + WEDGE_LEN_M / 2
            name = f"green_hole{i}"
            sc.box(name, (hx + rc * math.cos(th), hy + rc * math.sin(th), -D / 2), (WEDGE_LEN_M / 2, w, D / 2),
                   rgba=GREEN_RGBA, solid="stand", friction=(1.0, 0.005, 0.0001), quat=quat_z(th))
            sc.ground.append(name)
            # the cup's liner, visual only: white, from 25 mm below the surface down (the Rules' depth for a liner)
            sc.box(f"hole_liner{i}", (hx + (a - 0.0004) * math.cos(th), hy + (a - 0.0004) * math.sin(th), -(D + 0.025) / 2),
                   (0.0003, a * math.tan(math.pi / N), (D - 0.025) / 2), rgba=(0.93, 0.93, 0.93, 1), quat=quat_z(th))
        sc.disc("hole_bottom", (hx, hy), R, rgba=(0.05, 0.05, 0.05, 1), z=-D + 0.0006)
        sc.hand_tools["right"] = putter(p["putter_length_m"], p["putter_loft_deg"], p["putter_mass_kg"])
        sc.ball("ball", "golf", (p["ball_x_m"], p["ball_y_m"], BALL["radius"]), roll=p["roll_resistance_m"])
        sc.camera("venue", (3.0, -2.2, 1.9), (0.3, 1.1, 0.3), fovy=55)
        sc.camera("hole", (hx + 0.45, hy - 0.55, 0.40), (hx, hy, -0.03), fovy=40)

    def reset(self, w):
        w.put("ball", (self.p["ball_x_m"], self.p["ball_y_m"], BALL["radius"]))

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        self.ball = ref.geoms(body="ball")
        self.head = ref.geoms(names=["putter_head", "putter_face"])
        self.other = ref.part("robot") & ~self.head
        self.floor = ref.geoms(names=["floor"])
        self.feet = ref.part("feet")
        # first / last: the stroke's first and latest contact (s); contact_s: how long the head has been on the ball
        # still_at / still_since: where and since when the ball has not moved (the rest condition)
        self.trackers = {"first": None, "last": None, "contact_s": 0.0, "hits": Touch(ref, self.ball, self.head, gap=0.005),
                         "still_at": None, "still_since": None}

    def _off_hole(self, b) -> float:
        return float(np.hypot(*(np.asarray(b[:2]) - self.hole())))

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        if ref.touching(self.ball, self.other):
            return ref.fail("the ball was touched by something other than the putter's head",
                            parts=sorted(ref.parts_touching(self.ball)))
        tr["hits"].update()
        if ref.touching(self.ball, self.head):
            if tr["first"] is None:
                tr["first"] = ref.time
                pts = ref.contact_points(self.feet, ref.ground)
                side = pts[:, 0] - p["ball_x_m"] if len(pts) else np.zeros(0)
                if len(side) and float(side.min()) <= 0.0 <= float(side.max()):
                    return ref.fail("the stance was astride or on the line of play")
                ref.stage("stroke")
            elif ref.time - tr["first"] > p["stroke_window_s"]:
                return ref.fail("a second stroke", after_s=round(ref.time - tr["first"], 3))
            tr["last"] = ref.time
            tr["contact_s"] = round(tr["contact_s"] + w.PHYS_DT, 6)
            if tr["contact_s"] > p["max_contact_s"] + 1e-9:
                return ref.fail("the ball was pushed, not struck", contact_s=tr["contact_s"])
        b = w.pos("ball")
        if ref.touching(self.ball, self.floor) and self._off_hole(b) > p["hole_diameter_m"] / 2:
            ref.fail("the ball left the green")

    def step(self, w, ref):
        tr, p = self.trackers, self.p
        b = w.pos("ball")
        off = self._off_hole(b)
        speed = float(np.linalg.norm(w.vel("ball")))
        ref.metrics["ball_to_hole_m"] = round(off, 3)
        ref.metrics["ball_speed_m_s"] = round(speed, 3)
        ref.metrics["head_contact_s"] = tr["contact_s"]
        ref.metrics["head_hits"] = tr["hits"].count
        if tr["first"] is None:
            return
        if (tr["still_at"] is None or ref.touching(self.ball, self.head)
                or float(np.linalg.norm(b - np.array(tr["still_at"]))) > p["rest_move_m"]):
            tr["still_at"], tr["still_since"] = [float(x) for x in b], w.t
        elif w.t - tr["still_since"] >= p["rest_s"] - 1e-9:
            if off < p["hole_diameter_m"] / 2 and b[2] + BALL["radius"] < 0.0:
                if ref.stage("holed"):
                    ref.succeed()
            else:
                ref.fail("the ball came to rest outside the hole", ball_to_hole_m=round(off, 3))

    def privileged(self, w):
        m, d = w.m, w.d
        g = m.geom("putter_face").id
        Rf = d.geom_xmat[g].reshape(3, 3)
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(), "hole": self.hole().tolist(),
                "hole_depth_m": self.p["hole_depth_m"], "putter_face": d.geom_xpos[g].tolist(),
                "putter_face_normal": Rf[:, 1].tolist(), "putter_heel_to_toe": Rf[:, 0].tolist(),
                "putter_sole_normal": Rf[:, 2].tolist(), "stroke_made": self.trackers["first"] is not None}
