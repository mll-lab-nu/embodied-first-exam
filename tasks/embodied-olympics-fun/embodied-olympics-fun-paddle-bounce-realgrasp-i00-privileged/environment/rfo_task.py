"""Paddle bounce with a real grip (table tennis ball control): paddle-bounce's drill, a ball dropped above the paddle in
your right hand kept bouncing on the blade, every bounce back up to the height it was dropped from; but the paddle is
not part of the hand. It is a free 0.14 kg table tennis racket held only by the friction of the right hand's
two-finger gripper (Unitree Dex1-1): it can slip, turn in the jaws and be dropped.

Everything else is paddle-bounce's (copied: a task directory holds one module): the official 40 mm, 2.7 g ball with
Google DeepMind's identified fluid coefficients and thin-shell inertia, RoboOlympics' ball-blade contact pair
(roboolympics/sports/tabletennis/sim/scene/tt_scene.xml, Apache-2.0; hand-picked, not identified), the same blade (a
rigid 15 x 15 x 1.5 cm box, 0.09 kg), the drop, the counting rule and every number.

The paddle (FREE_PADDLE; the block is shared, byte for byte, with table-tennis-return-realgrasp): paddle-bounce's
blade and handle mass on a straight handle of a real racket's size, 100 mm long, 32 mm wide and 25 mm thick (ITTF
Law 2.4 sets no size, shape or weight for the blade or the handle; a common "straight" handle is 100 x 30-34 x 23-26 mm),
as a free body. Its blade's centre is 0.175 m from the butt, as on paddle-bounce's paddle from the wrist.

The hand: the core's Dex1-1 (rfo.realhand: 90 mm stroke, 80 mm jaws, 5-120 N), the paddle held by contact and friction
only, no weld. The handle lies along the jaws (the longest patch the gripper has: 75 mm of the 80 mm pads on the
handle), its two broad faces against the pads, so the blade's faces look along the closing axis as on paddle-bounce's
fixed paddle; the butt 5 mm from the gripper's body; the closure command 1 (120 N). The blade is then 0.068 m further
from the wrist than paddle-bounce's (its centre 0.243 m from the wrist mount, not 0.175): the gripper's body and jaws
are that long.

Measured with this module (tests/test_paddle_bounce_realgrasp.py asserts them): at 120 N, the paddle held level on the
standing robot's arm turns less than 0.1 degree and moves less than 0.2 mm in the jaws in 1.4 s, and it does not move
hanging from the hand at rest; eased to a clamp of 0.6 N it slides 5 cm down the jaws under its own weight, and at
0.3 N it slides out and falls. The two-jaw contact breaks for at most 2 ms in the reference solution's 20 bounces.

Why the rule is "back up to the drop height": see paddle-bounce (no passive rebound reaches the height the ball fell
from; a bounce that does has been given energy by the blade). Measured again on this module: a ball dropped from
1.20 m onto the still, level blade held in the gripper (its centre 0.87 m up) rises 0.25 m above it, to 1.15 m:
below the drop height, so the first passive rebound already fails.

The simulator's options: paddle-bounce sets DeepMind's elliptic cones with impratio 10; a world with a real hand needs
impratio 100 (realhand.IMPRATIO: with 10 a clamped handle creeps under a steady torque), and this module leaves it at
100 (it is the real-hand worlds' setting for every contact; the ball-blade pair was hand-picked, not identified).
"""
import xml.etree.ElementTree as ET

import math

import mujoco
import numpy as np

from rfo.referee import Touch
from rfo.scene import HITTABLE, OFFICIAL
from rfo.task import TaskBase

BALL = OFFICIAL["tabletennis"]

# ------------------------------------------------------------------------------- the free paddle (ITTF Law 2.4)
# A free body "paddle" in its own frame: the butt at the origin, +z along the handle to the blade's far edge, the
# blade's faces look along the body's +-x (the handle's thickness is along x, its width along y). Shared, identically,
# by paddle-bounce-realgrasp and table-tennis-return-realgrasp.
FREE_PADDLE = dict(blade_m=0.15, blade_thickness_m=0.015, blade_kg=0.09, blade_centre_from_butt_m=0.175,
                   handle_length_m=0.10, handle_width_m=0.032, handle_thickness_m=0.025, handle_kg=0.05, mass_kg=0.14,
                   handle_friction=0.8)


def build_free_paddle(sc, pos, quat=(1, 0, 0, 0), name="paddle"):
    """The paddle as a free body at pos/quat (its butt). Geoms <name>_handle (a box) and <name>_blade (a box), both
    colliding like a prop (HITTABLE): with the jaws, the robot, the floor, the table, the net, the ball."""
    P = FREE_PADDLE
    b = sc.body(name, pos, quat=quat, free=True)
    L = P["handle_length_m"]
    sc.geom(b, f"{name}_handle", type="box", pos=(0, 0, L / 2),
            size=(P["handle_thickness_m"] / 2, P["handle_width_m"] / 2, L / 2), mass=P["handle_kg"],
            rgba=(0.55, 0.38, 0.2, 1), friction=(P["handle_friction"], 0.005, 0.0001), **HITTABLE)
    B = P["blade_m"] / 2
    sc.geom(b, f"{name}_blade", type="box", pos=(0, 0, P["blade_centre_from_butt_m"]),
            size=(P["blade_thickness_m"] / 2, B, B), mass=P["blade_kg"], rgba=(0.8, 0.1, 0.1, 1), **HITTABLE)
    return b
# ------------------------------------------------------------------------------- (end of the shared paddle)


BLADE_PAIR = dict(solref="-600000 -12", friction="0.8 0.8 0.005 0.0001 0.0001", solimp="0.98 0.99 0.001 0.5 2",
                  solreffriction="-0.0 -200.0")
SIDE = "right"
BUTT_FROM_JAW_CENTRE_M = 0.035     # the butt 5 mm out from the gripper's housing: the handle along the 80 mm jaws

EARLY = "the ball was touched before it was dropped"
OTHER = "the ball touched something other than the paddle's blade"
FLOOR = "the ball touched the floor"
LOW = "the ball came back to the blade without having risen enough"
REST = "the ball rested on the blade"
LEFT_HAND = "the paddle left your hand"
HELD_ELSE = "the paddle touched a part of you other than your right hand"
PADDLE_FLOOR = "the paddle touched the floor"


class Task(TaskBase):
    name = "paddle-bounce-realgrasp"
    title = "Table tennis: keep the ball bouncing on a paddle held by a real grip"
    category = "basketball-and-rackets"
    robot = "unitree_g1"
    rulebook = ("ITTF Handbook 2024, The Laws of Table Tennis, for the equipment: 2.3 (the ball), 2.4 (the racket), "
                "2.5.5 (the racket hand: the hand carrying the racket). Bouncing the ball on the racket is a "
                "ball-control drill, not an event with a rule book: the number of consecutive bounces asked for is "
                "this benchmark's line")
    deviations = [
        "2.4 (the racket): the blade is a rigid 15 cm square, 1.5 cm thick, on a straight handle {handle_length_m} m "
        "long, {handle_width_m} m wide and {handle_thickness_m} m thick, {paddle_mass_kg} kg in all (legal: the Laws "
        "set no size, shape or weight); its covering is one contact law on both faces (RoboOlympics' ball-paddle pair, "
        "hand-picked, not identified)",
        "2.5.5 (the hand carrying the racket): the hand is a two-finger gripper, Unitree's Dex1-1 (90 mm stroke, 80 mm "
        "jaws, at most 120 N); the handle lies along its jaws and the paddle is held by their friction alone, as a "
        "hand holds it; \"in the hand\" is defined by contact: the handle touches both of the gripper's jaws, and a "
        "break of up to {out_of_hand_s} s is not a release",
        "the start: nobody hands the robot a ball; it hangs at rest in front of the robot and is let go at "
        "{drop_time_s} s",
        "a bounce is a hit: so that the rebounds of one strong hit off a still blade are not counted, the ball must "
        "leave a counted bounce with at least {hit_gain} of the speed it reached the blade with (both taken at the "
        "height of the touch; a still blade returns about 0.95); a bounce that does not is not counted, and is not "
        "a fault",
    ]
    time_limit_s = 20.0
    start = (0.0, 0.0, 0.0)
    stages = [f"bounce {i + 1}" for i in range(20)]            # one per bounce of params["bounces"]
    params = dict(bounces=20, min_rise_m=0.15, max_touch_s=0.02, touch_gap_s=0.02,
                  hit_gain=0.98, drop_x_m=0.36, drop_y_m=-0.20, drop_z_m=1.20, drop_time_s=2.0, fall_height_m=0.35,
                  paddle_mass_kg=FREE_PADDLE["mass_kg"], handle_length_m=FREE_PADDLE["handle_length_m"],
                  handle_width_m=FREE_PADDLE["handle_width_m"], handle_thickness_m=FREE_PADDLE["handle_thickness_m"],
                  blade_centre_m=FREE_PADDLE["blade_centre_from_butt_m"], out_of_hand_s=0.05)

    sentence = ("Keep the table tennis ball that is dropped in front of you bouncing on the paddle held in your right "
                "hand's gripper: {bounces} bounces in a row, each back up to the height the ball was dropped from, "
                "without letting go of the paddle.")
    rules = ("A table tennis racket (a rigid square blade 0.15 m wide and 0.015 m thick on a straight handle "
             "{handle_length_m} m long, {handle_width_m} m wide and {handle_thickness_m} m thick; {paddle_mass_kg} kg; "
             "the blade's centre {blade_centre_m} m from the butt) is a separate body; at the start its handle is "
             "closed in your right hand's two-finger gripper, which holds it by friction only: it can slip, turn in "
             "the gripper and fall. The paddle is in your hand while its handle touches both of the gripper's jaws; "
             "it has left your hand when for more than {out_of_hand_s} s the handle has not touched both jaws. The "
             "paddle may touch nothing of you but your right hand (the gripper's jaws and body). The official ball "
             "(40 mm, 2.7 g; it flies in air, with drag) hangs at rest, its centre {drop_z_m} m above the floor, until "
             "{drop_time_s} s after the start, and then falls. You succeed after {bounces} bounces in a row on the "
             "blade (either face; the faces need not alternate). A bounce is a touch of the blade after which, before "
             "the ball touches the blade again, the ball's centre rises at least {min_rise_m} m above the height at "
             "which it left the blade and reaches at least the height it was dropped from, {drop_z_m} m above the "
             "floor, and which the ball leaves with at least {hit_gain} of the speed it reached the blade with (both "
             "speeds taken at the height where the touch began). On a still blade every bounce is lower than the one "
             "before (the ball keeps about nine tenths of its height, 0.95 of its speed), so each bounce needs a hit "
             "of the blade; a rebound that rises enough but was not hit is not counted, and is not a fault. A touch "
             "is all contact of the ball with the blade from the first contact on, with breaks shorter than "
             "{touch_gap_s} s; a bounce's own contact lasts about a millisecond. You fail if the paddle leaves your "
             "hand at any time (dropped, thrown or slipped out of the gripper); if the paddle touches any part of you "
             "other than your right hand; if the ball comes back to the blade after a touch without having risen that "
             "much; if a touch lasts longer than {max_touch_s} s from its first contact to its last (the ball rests, "
             "rolls or is carried on the blade); if the ball touches the floor or anything other than the blade (the "
             "paddle's handle, the gripper, your arm or body included); if you or the paddle touch the ball before it "
             "is dropped; if you fall; or after {time_limit_s} s. A fall is your pelvis lower than {fall_height_m} m "
             "above the floor, or any part of you other than your feet touching the floor; the paddle touching the "
             "floor is a fall too.")
    venue = ("You stand on a level floor facing +x. The paddle's handle is closed in your right gripper along its two "
             "fingers, the butt just short of the gripper's body and the rest of the handle reaching beyond the "
             "fingertips; the blade's faces look the way the jaws close (your palm's side and the back of your hand), "
             "and the paddle points ahead along your forearm, the blade's centre about 0.24 m beyond your wrist. The "
             "ball hangs {drop_x_m} m ahead of your pelvis and {drop_y_m} m to your left (negative: to your right), "
             "its centre {drop_z_m} m above the floor, and is let go, with no speed and no spin, {drop_time_s} s "
             "after the start. There is no wind.")
    difficulty = ("Every bounce needs an upward hit of the right strength at the right instant, with the blade level "
                  "and under a 40 mm ball: a tilt of a degree sends the ball off the 15 cm blade within a few "
                  "bounces, and the arm that holds the blade gives way a little at every hit. The paddle sits in a "
                  "two-finger gripper, so the blade is where the jaws hold it, not where the arm was told to put "
                  "it, and it has to go right twenty times in a row.")

    def __init__(self):
        super().__init__()
        self._set_stages()

    def configure(self, params):
        super().configure(params)
        self._set_stages()

    def _set_stages(self):
        self.stages = [f"bounce {i + 1}" for i in range(int(self.p["bounces"]))]
        self.fall_z = float(self.p["fall_height_m"])

    def build(self, sc):
        p = self.p
        sc.box("mat", (0.3, 0, 0.0003), (1.5, 1.5, 0.0003), rgba=(0.45, 0.25, 0.25, 1))
        sc.real_hands[SIDE] = "dex1"
        sc.ball("ball", "tabletennis", (p["drop_x_m"], p["drop_y_m"], p["drop_z_m"]))
        build_free_paddle(sc, pos=(0.5, -0.6, 0.05))
        # DeepMind's table-tennis physics (as in paddle_bounce.py): elliptic cones, thin-shell inertia, the blade
        # pair; impratio is left to the real hand's 100 (see the docstring)
        opt = sc.root.find("option")
        opt.set("cone", "elliptic")
        body = next(b for b in sc.wb.iter("body") if b.get("name") == "ball")
        i = 2.0 / 3.0 * BALL["mass"] * BALL["radius"] ** 2
        ET.SubElement(body, "inertial", pos="0 0 0", mass=repr(BALL["mass"]), diaginertia=f"{i:.6g} {i:.6g} {i:.6g}")
        ET.SubElement(sc.root.find("contact"), "pair", name="ball_paddle_blade", geom1="ball", geom2="paddle_blade",
                      **BLADE_PAIR)
        sc.camera("venue", (1.7, -1.8, 1.45), (0.2, -0.1, 0.9), fovy=42)

    def reset(self, w):
        """The paddle's handle along the right gripper's fingers (its axis the fingers' axis, the blade's normal the
        closing axis), the butt BUTT_FROM_JAW_CENTRE_M before the jaws' centre; then the jaws close on it (the full
        command: 120 N) and the grasp settles."""
        p = self.p
        w.pin("ball", (p["drop_x_m"], p["drop_y_m"], p["drop_z_m"]))
        c, R = w.jaw_frame(SIDE)
        q = np.zeros(4)
        mujoco.mju_mat2Quat(q, R.ravel())
        w.put("paddle", c - BUTT_FROM_JAW_CENTRE_M * R[:, 2], quat=q)
        self.grasp = w.close_on(SIDE, "paddle")

    def referee_reset(self, w, ref):
        p = self.p
        self.ball = ref.geoms(body="ball")
        self.blade = ref.geoms(names=["paddle_blade"])
        self.handle = ref.geoms(names=["paddle_handle"])
        self.paddle = self.blade | self.handle
        self.other = ref.robot_mask | self.handle
        self.right_hand = ref.part(f"{SIDE}_hand")
        self.jaws = (ref.geoms(body=f"{SIDE}_hand_jaw_a"), ref.geoms(body=f"{SIDE}_hand_jaw_b"))
        self.trackers = {"blade": Touch(ref, self.ball, self.blade, gap=p["touch_gap_s"]), "dropped": False,
                         "left_z": None, "apex_z": None, "risen": True, "bounces": 0, "speed": 0.0, "v_in": 0.0,
                         "z_in": 0.0, "both_jaws_t": 0.0}

    def before_step(self, w):
        p = self.p
        if not self.trackers["dropped"] and w.k >= int(round(p["drop_time_s"] / w.CONTROL_DT)):
            w.launch("ball", (p["drop_x_m"], p["drop_y_m"], p["drop_z_m"]), (0.0, 0.0, 0.0))
            self.trackers["dropped"] = True
            w.ref.event("drop")

    def in_hand(self, ref) -> bool:
        return ref.touching(self.handle, self.jaws[0]) and ref.touching(self.handle, self.jaws[1])

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        if self.in_hand(ref):
            tr["both_jaws_t"] = round(ref.time, 4)
        else:
            gap = round(ref.time - tr["both_jaws_t"], 4)
            if gap > ref.metrics.get("grip_break_max_s", 0.0):
                ref.metrics["grip_break_max_s"] = gap       # (reported: the longest break of the two-jaw contact)
            if gap > p["out_of_hand_s"] + 1e-9:
                return ref.fail(LEFT_HAND, out_s=gap)
        if ref.touching(self.paddle, ref.robot_mask & ~self.right_hand):
            return ref.fail(HELD_ELSE, parts=sorted(ref.parts_touching(self.paddle) - {f"{SIDE}_hand"}))
        if ref.touching(self.paddle, ref.ground):
            return ref.fail(PADDLE_FLOOR)
        if not tr["dropped"]:
            if ref.touching(self.ball, self.other | self.blade):
                ref.fail(EARLY, parts=sorted(ref.parts_touching(self.ball)),
                         paddle=ref.touching(self.ball, self.paddle))
            return
        if ref.touching(self.ball, self.other):
            return ref.fail(OTHER, parts=sorted(ref.parts_touching(self.ball)),
                            handle=ref.touching(self.ball, self.handle))
        if ref.touching(self.ball, ref.ground):
            return ref.fail(FLOOR)
        t = tr["blade"]
        z = float(w.pos("ball")[2])
        speed, tr["speed"] = tr["speed"], float(np.linalg.norm(w.vel("ball")))     # speed: one physics step ago
        if t.update():
            if not tr["risen"]:
                return ref.fail(LOW, rise_m=round(tr["apex_z"] - tr["left_z"], 3), apex_m=round(tr["apex_z"], 3))
            tr["risen"], tr["v_in"], tr["z_in"] = False, speed, z
        if ref.touching(self.ball, self.blade):
            tr["left_z"] = tr["apex_z"] = z
            if t.duration > p["max_touch_s"]:
                return ref.fail(REST, touch_s=round(t.duration, 3))
        elif t.count and not tr["risen"]:
            tr["apex_z"] = max(tr["apex_z"], z)
            if z - tr["left_z"] >= p["min_rise_m"] and z >= p["drop_z_m"]:
                tr["risen"] = True
                # the speed the ball left the blade with, at the touch's height (from its energy now: free flight)
                v_out = math.sqrt(max(0.0, tr["speed"] ** 2 + 2 * 9.81 * (z - tr["z_in"])))
                if v_out < p["hit_gain"] * tr["v_in"]:     # a rebound, not a hit: not counted
                    ref.event("rebound", speed_in=round(tr["v_in"], 3), speed_out=round(v_out, 3))
                    return
                tr["bounces"] += 1
                n = tr["bounces"]
                ref.metrics["bounces"] = n
                if ref.stage(f"bounce {n}", left_z=round(tr["left_z"], 3)) and n >= int(p["bounces"]):
                    ref.succeed()

    def step(self, w, ref):
        ref.metrics["ball_height_m"] = round(float(w.pos("ball")[2]), 3)

    def privileged(self, w):
        g = w.m.geom("paddle_blade").id
        n = np.asarray(w.d.geom_xmat[g]).reshape(3, 3)[:, 0]         # the blade's normal; reported as the face looking up
        _, va = w.free["ball"]
        _, pv = w.free["paddle"]
        R = w.d.xmat[w.m.body("ball").id].reshape(3, 3)
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "ball_spin": (R @ w.d.qvel[va + 3:va + 6]).tolist(),
                "dropped": bool(self.trackers.get("dropped")), "drop_time_s": self.p["drop_time_s"],
                "blade_centre": w.d.geom_xpos[g].tolist(), "blade_normal": (n if n[2] >= 0 else -n).tolist(),
                "paddle_pos": w.pos("paddle").tolist(), "paddle_quat": w.d.xquat[w.m.body("paddle").id].tolist(),
                "paddle_velocity": w.d.qvel[pv:pv + 3].tolist(), "paddle_angvel": w.d.qvel[pv + 3:pv + 6].tolist(),
                "paddle_in_hand_t": self.trackers.get("both_jaws_t", 0.0),
                "bounces": int(self.trackers.get("bounces", 0)), "paddle": FREE_PADDLE}
