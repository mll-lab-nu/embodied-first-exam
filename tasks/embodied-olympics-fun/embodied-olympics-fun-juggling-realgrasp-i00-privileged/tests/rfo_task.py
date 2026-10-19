"""Keepie-uppie with a real drop: juggling, but nothing is welded to a hand: the size-5 football starts pressed between
the two open palms (only the arms' squeeze and friction hold it, it can slip out), and the drop is the hands' own
movement. Then keep it up for ten touches in a row with the feet, the legs or the head. Everything after the drop and
every referee number are juggling's; only the hold, the drop and the texts about them differ."""
import math
import xml.etree.ElementTree as ET

import numpy as np

import mujoco

from rfo.referee import Touch
from rfo.scene import OFFICIAL
from rfo.task import TaskBase

BALL = OFFICIAL["football"]
GRASS = (0.16, 0.50, 0.20, 1)
ARMS = {"left_upper_arm", "left_forearm", "left_hand", "right_upper_arm", "right_forearm", "right_hand"}
LEGAL = ("feet", "shins", "thighs", "head")
HANDS = {"left_hand", "right_hand"}


# ---- the ball between the palms ----
# The G1's hands are flat palm pads (4.4 x 8 x 10 cm boxes on the wrist mounts, the broad face on the mount's +x the
# palm; the rubber fist around each is only drawn). The start: both forearms forward at the height of the hips, turned
# so that the palms face each other across the body (the wrist rolls), the upper arms turned in until both palms touch
# the ball in front of the pelvis (HOLD: the joint angles where each palm's face touches the ball); the start command
# is SQUEEZE, the same pose with the palms' faces SQUEEZE_M further in, so that the shoulder servos press the ball
# between them: nothing else holds it. The arms have no gravity feed-forward: under that command the arms settle
# against the ball in about 2 s (measured offline: 2.5 s with the ball held at its start, then let go); the robot
# starts there, at rest (SETTLED: the pelvis' height and orientation, every joint), the ball where it then sits
# (BALL_AT: its centre in the right mount's frame). The drop is the hands' own movement: the palms parting (or the
# arms lowering, turning) until the ball falls free. Measured (tests/test_juggling_realgrasp.py): the squeeze presses
# about 6.6 N on each palm and holds the ball still for a whole episode (it creeps 3 to 4 mm in 60 s); with the
# command at HOLD (the palms only touching) the ball slips out at once.
HOLD = dict(right_shoulder_pitch=-0.0311, right_shoulder_roll=0.0369, right_shoulder_yaw=0.0479, right_elbow=0.2278,
            right_wrist_roll=1.5475, right_wrist_pitch=-0.0635, right_wrist_yaw=0.1964, left_shoulder_pitch=-0.0311,
            left_shoulder_roll=-0.0369, left_shoulder_yaw=-0.0479, left_elbow=0.2278, left_wrist_roll=-1.5475,
            left_wrist_pitch=-0.0635, left_wrist_yaw=-0.1964)
SQUEEZE = dict(right_shoulder_pitch=-0.0363, right_shoulder_roll=0.1002, right_shoulder_yaw=0.085, right_elbow=0.2431,
               right_wrist_roll=1.4958, right_wrist_pitch=-0.1162, right_wrist_yaw=0.2002,
               left_shoulder_pitch=-0.0363, left_shoulder_roll=-0.1002, left_shoulder_yaw=-0.085, left_elbow=0.2432,
               left_wrist_roll=-1.4958, left_wrist_pitch=-0.1162, left_wrist_yaw=-0.2002)
SQUEEZE_M = 0.02
SETTLED_Z_QUAT = (0.78495, 1.0, 9e-05, 0.00181, -0.00161)
SETTLED = (-0.1002, 0.01297, -0.00978, 0.29939, -0.20256, 0.05421, -0.1016, -0.01197, 0.00947, 0.29946, -0.20158,
           -0.05364, -0.00084, -0.00022, 0.01669, -0.03581, -0.03908, -0.06771, 0.25076, -1.49931, -0.13233, -0.19233,
           -0.03555, 0.05609, 0.06968, 0.25093, 1.49933, -0.13451, 0.19202)
BALL_AT = (0.13141, 0.02532, 0.04381)
PAD_HALF, PAD_Z = 0.022, 0.05                  # the palm pad's half thickness and its centre along the forearm
# The palm-ball contact below (the comment and the numbers) is dunk-realgrasp's, copied byte-identically; its numbers
# were measured there with the size-7 basketball.
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


def palm_face(w, side: str) -> tuple[np.ndarray, np.ndarray]:
    """The centre of the pad's palm face (the mount's +x face) and its outward normal, in the world."""
    d, b = w.d, w.robot.mount[side]
    R = d.xmat[b].reshape(3, 3)
    return d.xpos[b] + R @ np.array([PAD_HALF, 0.0, PAD_Z]), R[:, 0].copy()


def palm_contact(sc, ball: str, roll: float) -> None:
    """The palm-ball pairs (both palms) and the world's friction cones, as in dunk-realgrasp."""
    opt = sc.root.find("option")
    opt.set("cone", CONE)
    opt.set("impratio", f"{IMPRATIO:g}")
    for side in ("left", "right"):
        ET.SubElement(sc.root.find("contact"), "pair", name=f"palm_ball_{side}", geom1=ball,
                      geom2=f"{side}_palm_pad", condim="6",
                      friction=f"{PALM_MU} {PALM_MU} 0.003 {roll} {roll}", solref=PALM_SOLREF,
                      solimp=PALM_SOLIMP)


def ball_between_palms(w) -> None:
    """t = 0: the robot settled under its start command (both arms' is SQUEEZE, the other joints' their rest), the
    ball between the palms."""
    r, d = w.robot, w.d
    for jn, v in SQUEEZE.items():
        i = _joint(w, jn)
        r.arb.q_a[i] = r.arb.q_b[i] = v
    d.qpos[r.fq + 2:r.fq + 7] = SETTLED_Z_QUAT
    d.qpos[r.qadr] = SETTLED
    mujoco.mj_kinematics(w.m, d)
    b = r.mount["right"]
    w.put("ball", d.xpos[b] + d.xmat[b].reshape(3, 3) @ np.array(BALL_AT))
# ---- end of the palms ----


class Task(TaskBase):
    name = "juggling-realgrasp"
    title = "Football: keepie-uppie, real drop"
    category = "football-and-volleyball"
    robot = "unitree_g1"
    rulebook = ("Keepie-uppie (ball juggling), the football skill: the ball is dropped from the hands and kept in the "
                "air with the feet, the legs and the head, each touch counted, the count ending when the ball touches "
                "the ground or a hand; it is a skill test, not an event of the Laws, and the family's standard is 10 "
                "consecutive touches. IFAB Laws of the Game 2025/26 for the ball (Law 2: size 5, 68-70 cm round, "
                "410-450 g) and for handling (Law 12: the hand or the arm)")
    deviations = [
        "A counter's eye is replaced by numbers: contacts less than {touch_gap_s} s apart are one touch, a touch may "
        "last at most {carry_s} s, and it counts when the ball's centre has then risen at least {rise_m} m (one ball "
        "diameter) above where it was when the touch began, before anything touches it again; a ball that rolls or "
        "rests on a leg is not a touch.",
        "A touch is a strike: so that a ball that merely bounces on a still limb or head is not juggling, every "
        "touch after the first must send the ball off with at least {touch_gain} of the speed it arrived with (a "
        "still limb returns about 0.85); a touch that does not is not counted, and is not a fault.",
        "Only the feet, the legs (shin and thigh) and the head count and may touch the ball; the chest and the "
        "shoulders, which a human juggler may use, are not allowed, because the robot's trunk is one rigid shell.",
        "The ball starts pressed between the robot's two open palms in front of its hips (the robot has flat palm "
        "pads, no fingers and no grip): only the arms' squeeze and friction hold it, and it slips out when they "
        "press too little. The drop is the hands' own movement (the palms parting); a referee's eye for 'the "
        "ball has left the hand' is replaced by a number: the ball touches no part of the robot for {hold_gap_s} s, "
        "and the drop is the end of its last contact. Before the drop only the hands may touch the ball (a ball held "
        "against the body, an arm or a leg is not in the hand). The palm absorbs the ball as a hand does (the "
        "palm-ball contact of dunk-realgrasp: a ball thrown at a still palm keeps " + f"{PALM_REBOUND:.2f}" + " of its "
        "speed); every other contact keeps the ball's rule-book rebound. No wind.",
    ]
    time_limit_s = 30.0
    start = (0.0, 0.0, 0.0)
    stages = [f"touch {i + 1}" for i in range(10)]
    fall_z = 0.35
    legal_ground = ("left_foot", "right_foot")
    params = dict(touches=10, rise_m=0.22, carry_s=0.15, touch_gap_s=0.05, hold_gap_s=0.03, release_grace_s=0.15,
                  touch_gain=0.95, fall_z_m=0.35)

    sentence = ("Juggle the football: drop it from between your palms and keep it in the air for ten touches in a "
                "row with your feet, legs or head, without it touching the ground or a hand again.")
    rules = ("A size-5 football (0.22 m across, 0.43 kg, in air) starts pressed between your two open palms; your "
             "hands have no fingers and no grip (the grip columns of the action rows do nothing in this task): only "
             "the squeeze of your arms and friction hold the ball, and it slips out when they press too little. "
             "Until the drop only your hands (the palm pads and the wrists) may touch the ball. The drop: the ball "
             "has touched no part of you for {hold_gap_s} s; it is the end of the ball's last contact with a hand. A "
             "hand or an arm may still be in contact with the ball for {release_grace_s} s after the drop (the ball "
             "leaving the hand); after that a hand or an arm on the ball is a handball. From the drop on, a touch is "
             "a contact of the ball with a foot, a shin, a thigh or your head (contacts less than {touch_gap_s} s "
             "apart are one touch); it counts when the ball's centre has then risen at least {rise_m} m above the "
             "height it had when the touch began, before anything touches it again, and, for every touch after the "
             "first, when the ball leaves the touch with at least {touch_gain} of the speed it had when the touch "
             "began (both taken at the height where the touch began; a ball that only bounces on a still limb leaves "
             "slower: such a touch is not counted, and is not a fault). You succeed at the moment the tenth touch "
             "counts. You fail if the ball touches the ground (before the drop too), if a part of you other than the "
             "hands touches it before the drop, if a hand or an arm touches it later than {release_grace_s} s after "
             "the drop, if your trunk (chest, shoulders, pelvis) touches it, if one touch lasts longer than "
             "{carry_s} s (the ball resting or balanced on you), if the ball is touched again before it has risen "
             "{rise_m} m, if you fall (your pelvis lower than {fall_z_m} m above the ground, or any part of you "
             "other than the feet on the ground; standing on one foot is not a fall), or after {time_limit_s} s.")
    venue = ("You stand on level grass. Your upper arms hang, your forearms point forward and are turned so that the "
             "palms face each other; the ball is pressed between them, its centre about 0.85 m above the ground and "
             "0.33 m ahead of your pelvis. The start command keeps that squeeze (the joint table's start angles are "
             "where the arms stand with the ball between the palms; the command is a little further in: the "
             "difference is the squeeze).")
    difficulty = ("Each touch is an upward strike by a leg or the head, timed to a falling 0.43 kg ball and aimed so "
                  "that the ball comes down within reach again, ten times in a row; the robot has to stand on one "
                  "leg to use a foot or a thigh, which neither built-in gait does, and a ball that merely bounces on "
                  "a still limb loses a quarter of its height each time and wanders off.")

    def __init__(self):
        super().__init__()
        self.stages = [f"touch {i + 1}" for i in range(int(self.p["touches"]))]

    def configure(self, params):
        super().configure(params)
        self.stages = [f"touch {i + 1}" for i in range(int(self.p["touches"]))]
        self.fall_z = self.p["fall_z_m"]

    def build(self, sc):
        sc.box("pitch", (0.0, 0, 0.0003), (6.0, 6.0, 0.0003), rgba=GRASS)
        sc.ball("ball", "football", (0.3, -0.3, 1.0))           # no grip: the ball is not grippable
        palm_contact(sc, "ball", BALL["roll"])
        sc.camera("venue", (2.6, -2.6, 1.5), (0.0, -0.1, 0.8), fovy=50)

    def reset(self, w):
        ball_between_palms(w)

    def referee_reset(self, w, ref):
        self.ball = ref.geoms(body="ball")
        self.legal = ref.part(*LEGAL)
        self.arms = ref.part("arms")
        self.trunk = ref.robot_mask & ~self.legal & ~self.arms
        self.trackers = {"touch": Touch(ref, self.ball, self.legal, gap=self.p["touch_gap_s"]), "dropped": None,
                         "last_on": 0.0,
                         "count": 0, "pending": False, "z_touch": 0.0, "apex": 0.0, "speed": 0.0, "v_in": 0.0,
                         "v_out": None, "first": True}

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        if tr["dropped"] is None:                            # the ball on the hand(s): nothing but contact holds it
            if ref.touching(self.ball, ref.ground):
                return ref.fail("the ball touched the ground", touches=0)
            if ref.touching(self.ball, ref.robot_mask):
                parts = ref.parts_touching(self.ball)
                if not parts <= HANDS:
                    return ref.fail("the ball was held with a part other than the hands", parts=sorted(parts))
                tr["last_on"] = ref.time
            elif ref.time - tr["last_on"] >= p["hold_gap_s"] - 1e-9:
                # clear of every hand for hold_gap_s: the ball has left the hand at the end of its last contact
                tr["dropped"] = tr["last_on"]
                ref.event("drop", at=round(tr["last_on"], 3), speed=round(float(np.linalg.norm(w.vel("ball"))), 2))
            return
        since = ref.time - tr["dropped"]
        if ref.touching(self.ball, ref.ground):
            return ref.fail("the ball touched the ground", touches=tr["count"])
        if ref.touching(self.ball, self.arms) and since > p["release_grace_s"]:
            return ref.fail("handball", parts=sorted(ref.parts_touching(self.ball) & ARMS), touches=tr["count"])
        if ref.touching(self.ball, self.trunk):
            return ref.fail("the ball was touched by the trunk", parts=sorted(ref.parts_touching(self.ball)),
                            touches=tr["count"])
        touch = tr["touch"]
        z = float(w.pos("ball")[2])
        speed, tr["speed"] = tr["speed"], float(np.linalg.norm(w.vel("ball")))     # speed: one physics step ago
        if touch.update():                                 # a new touch
            if tr["pending"]:
                return ref.fail("the ball was touched again before it had risen enough",
                                rise_m=round(tr["apex"] - tr["z_touch"], 3), touches=tr["count"])
            tr["pending"], tr["z_touch"], tr["apex"], tr["v_in"], tr["v_out"] = True, z, z, speed, None
        if touch.active and touch.duration > p["carry_s"]:
            return ref.fail("the ball was carried", touch_s=round(touch.duration, 3), touches=tr["count"])
        if tr["pending"]:
            tr["apex"] = max(tr["apex"], z)
            if not ref.touching(self.ball, self.legal) and z - tr["z_touch"] >= p["rise_m"]:
                tr["pending"] = False
                # the speed the ball left the touch with, at the touch's height (from its energy now: free flight)
                tr["v_out"] = math.sqrt(max(0.0, tr["speed"] ** 2 + 2 * 9.81 * (z - tr["z_touch"])))
                struck = tr["first"] or tr["v_out"] >= p["touch_gain"] * tr["v_in"]
                tr["first"] = False
                if not struck:                             # a passive bounce: no touch of the count
                    ref.event("bounce", speed_in=round(tr["v_in"], 2), speed_out=round(tr["v_out"], 2))
                    return
                tr["count"] += 1
                if ref.stage(f"touch {tr['count']}", touch_s=round(touch.duration, 3)) and tr["count"] >= p["touches"]:
                    ref.succeed()

    def step(self, w, ref):
        tr = self.trackers
        ref.metrics["touches"] = tr["count"]
        ref.metrics["ball_height_m"] = round(float(w.pos("ball")[2]), 3)

    def privileged(self, w):
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "dropped": self.trackers.get("dropped") is not None, "touches": int(self.trackers.get("count", 0))}
