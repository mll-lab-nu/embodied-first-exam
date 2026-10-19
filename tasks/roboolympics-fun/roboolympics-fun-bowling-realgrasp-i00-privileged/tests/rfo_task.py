"""Ten-pin bowling with a real hold (USBC): from the approach, deliver the ball down the official lane without fouling
and knock down all ten pins with it: a strike. No grip and no finger holes: the 6 lb ball is held only by pressing it
between the two bare palms (contact and friction), a two-handed delivery. Lane, gutters, pin deck, pins and oil
pattern from RoboOlympics' bowling simulator (as in the family bowling); the Unitree H1-2."""
import math
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from rfo.scene import OFFICIAL, STANDABLE, VISUAL
from rfo.task import TaskBase

BALL = OFFICIAL["bowling"]                    # 8.5 in across, 6 lb: a legal house ball (USBC sets only a 16 lb maximum)
# ---- copied from RoboOlympics sports/bowling/sim/bowling.py (MIT): USBC dimensions, metres / kilograms
IN = 0.0254
N_BOARDS = 39
ROW_DX_FACTOR = math.sqrt(3) / 2
PIT_X = 19.157                                # 62 ft 10 3/16 in from the foul line: the end of the pin deck
KICK_BEFORE_HEAD_PIN = 0.45                   # the kickbacks (side walls) start this far before the head pin
PIN_COM_Z = 0.147                             # 5 13/16 in (USBC: 5 11/16 to 5 15/16)
# the pin's profile (USBC specification): height (in) -> diameter (in)
PIN_PROFILE = [(0.0, 2.03), (0.375, 2.5), (0.75, 2.828), (1.5, 3.4), (2.25, 3.906), (3.375, 4.51), (4.5, 4.766),
               (5.875, 4.563), (7.25, 3.927), (8.625, 2.828), (9.375, 2.237), (10.0, 1.797), (10.875, 1.87),
               (11.75, 2.2), (12.5, 2.38), (13.5, 2.2), (14.25, 1.75), (14.75, 1.1), (15.0, 0.0)]
CONTACT = "0.004 0.35"                        # solref of lane, deck and pins: RoboOlympics' damping ratio (the pins' rebound) and
#                                               its time constant of four physics steps (0.002 s at its 0.5 ms; 1 ms here)
DECK_MU, PIN_MU, GUTTER_MU = 0.2, 0.3, 0.2    # pin on the deck; pin on pin and on the ball; gutters and walls
TAPER_D0, TAPER_D1, N_RAMP = 6, 16, 6         # boards from the centre where the oil shortens / reaches its outside length
# ---- the pin as stacked primitives that follow the profile (heights in inches): (type, z0, z1, radius)
PIN_PARTS = [("cylinder", 0.0, 0.5, 1.015), ("cylinder", 0.5, 1.4, 1.5), ("capsule", 3.9, 5.0, 2.383),
             ("capsule", 6.1, 7.5, 1.72), ("capsule", 9.5, 11.0, 0.90), ("capsule", 12.35, 13.85, 1.15)]
LANE_Z = 0.10                                 # the lane's surface above the building's floor (the pit is that deep)
WOOD = (0.84, 0.67, 0.46, 1)


def pin_inertia(mass: float, height: float):
    """Principal moments about the centre of mass of the solid of revolution with the pin's profile, scaled to the
    pin's mass (RoboOlympics' pin_inertia)."""
    zs = np.linspace(0, height, 2001)
    r = np.interp(zs, [h * IN for h, _ in PIN_PROFILE], [d * IN / 2 for _, d in PIN_PROFILE])
    dm = math.pi * r ** 2 * (zs[1] - zs[0])
    s = mass / dm.sum()
    return float((dm * (r ** 2 / 4 + (zs - PIN_COM_Z) ** 2)).sum() * s), float((0.5 * dm * r ** 2).sum() * s)


# ---- the two-palm hold: the palm-ball contact block of dunk-realgrasp, copied unchanged (its comment included: it
# speaks of the basketball; here the bowling ball's own contact, rebound 0.10, stays on the lane, the gutters and the
# pins; the pair's XML in build() is dunk-realgrasp's too) ----
PAD_HALF, PAD_Z = 0.022, 0.05                  # the palm pad's half thickness and its centre along the forearm
# The palm-ball contact. With the ball's own contact (its rule-book rebound, 0.85, a lightly damped spring) a ball
# squeezed between two palms rattles and walks out of them in about a second, with pyramidal or elliptic friction
# cones alike; a palm rebound of 0.42 drops it in 6 s, 0.27 lets it creep 5 mm/s. The palm is the soft part of a hand
# and absorbs the ball: a critically damped contact (palm rebound 0.12, measured head-on at 3 m/s), with elliptic
# friction cones and impratio 100 for the whole world (as in the worlds with a real gripper, realhand.py), holds a
# still ball to 0.1 mm in 9 s. The floor, the ring and the backboard keep the ball's own contact (rebound 0.85).
PALM_SOLREF, PALM_SOLIMP, PALM_MU, PALM_REBOUND = "0.005 1", "0.99 0.999 0.001", 0.7, 0.12
CONE, IMPRATIO = "elliptic", 100.0

# ---- end of the copied block ----


def pad_face(w, side: str) -> tuple[np.ndarray, np.ndarray]:
    """The centre of the pad's inner face (the mount's +x face) and its outward normal, in the world."""
    d, b = w.d, w.robot.mount[side]
    R = d.xmat[b].reshape(3, 3)
    return d.xpos[b] + R @ np.array([PAD_HALF, 0.0, PAD_Z]), R[:, 0].copy()



# ---- the hold at the start (this family's: a 2.72 kg ball, 0.218 m across, in front of the hips) ----
# The two-handed stance: upper arms a little back, forearms forward and down, turned in (shoulder yaw) until both pads
# touch the ball in front of the hips (HOLD, the right arm; the left one mirrored); the hold targets (the start
# command) are SQUEEZE further in, so the shoulder servos press the ball: nothing else holds it. The arms have no
# gravity feed-forward, so under that command they sag to SETTLED (measured: 4 s of the start command, twice): the
# robot starts there, the ball where it then sits (BALL_OFFSET from the middle between the two pads).
# Measured (tests/test_bowling_realgrasp.py; the PNG/MP4 script of the family's report): the start command presses
# about 45 N on each palm (a still ball needs 19 N at the palms' friction 0.7) and holds the ball for the whole
# 40 s episode, and under an extra 1.6 g; without the squeeze (the arms at the touching pose) the ball slips out of
# the palms within 0.2 s. Held higher, at the waist or the chest (0.3 to 0.45 m ahead of the pelvis), the 2.7 kg ball
# tips the H1-2's open-loop stance over within 3 to 12 s; here (0.19 m ahead) the body leans and sways (pelvis pitch
# 0 to 4 degrees) and turns about 0.27 rad on its feet during the first 4 s, then stands for the whole episode.
HOLD = dict(shoulder_pitch=0.30, shoulder_roll=0.0, shoulder_yaw=0.2320, elbow_pitch=0.40)
SQUEEZE = dict(shoulder_yaw=0.25, shoulder_roll=0.10)
SETTLED = dict(shoulder_pitch=0.3128, shoulder_roll=0.0111, shoulder_yaw=0.2240, elbow_pitch=0.4361,
               elbow_roll=-0.0140, wrist_pitch=0.0487, wrist_yaw=-0.1577)
BALL_OFFSET = (-0.0078, -0.0001, 0.0009)
MIRROR = ("shoulder_roll", "shoulder_yaw", "elbow_roll", "wrist_yaw")      # the joints whose sign flips on the left

def _joint(w, name: str) -> int:
    return w.L.JOINTS.index(name + "_joint")


def ball_between_palms(w, settled=None, targets=None) -> None:
    """t = 0: both arms at SETTLED (mirrored on the left), the ball between the pads; the targets (the start command)
    are HOLD + SQUEEZE."""
    r, d = w.robot, w.d
    settled = SETTLED if settled is None else settled
    if targets is None:
        targets = {jn: HOLD.get(jn, 0.0) + SQUEEZE.get(jn, 0.0) for jn in set(HOLD) | set(SQUEEZE) | set(settled)}
    for side in ("right", "left"):
        for jn in set(settled) | set(targets):
            s = -1.0 if side == "left" and jn in MIRROR else 1.0
            i = _joint(w, f"{side}_{jn}")
            d.qpos[r.qadr[i]] = s * settled.get(jn, targets.get(jn, 0.0))
            r.arb.q_a[i] = r.arb.q_b[i] = s * targets.get(jn, 0.0)
    mujoco.mj_kinematics(w.m, d)
    c = [f + BALL["radius"] * n for f, n in (pad_face(w, "right"), pad_face(w, "left"))]
    w.put("ball", (c[0] + c[1]) / 2 + np.array(BALL_OFFSET))


class Task(TaskBase):
    name = "bowling-realgrasp"
    title = "Ten-pin bowling: a strike, real hold"
    category = "throwing-catching-striking"
    robot = "unitree_h1"
    rulebook = ("USBC Playing Rules 2024-2025 and USBC Equipment Specifications: the lane (60 ft from the foul line "
                "to the head pin, 41.5 in wide, gutters, pin deck), the pins (15 in, 3 lb 6 oz, 12 in apart), the "
                "ball (at most 8.595 in and 16 lb); the playing rules on a strike, a legal delivery, the foul (Rule "
                "5) and legal and illegal pinfall. The rules do not say how the ball is held or with how many hands: "
                "a two-handed delivery is legal")
    deviations = [
        "Equipment (ball) and the hands: the hands are flat rubber palm pads without fingers and the ball has no "
        "finger holes (a uniform ball, no weight block). Nothing grips it: it is held only by pressing it between "
        "the palms (contact and friction), a two-handed hold, and it slips or drops when the arms do not press hard "
        "enough. It is released when it has touched no part of you for {release_s} s.",
        "Equipment (the hand): the palm-ball contact is the soft part of a hand, as in dunk-realgrasp: it absorbs the "
        "ball (a ball thrown at a still palm keeps " + f"{PALM_REBOUND:.2f}" + " of its speed; friction "
        f"{PALM_MU:g}" + "); the world has elliptic friction cones and an impedance ratio of " + f"{IMPRATIO:g}" + " "
        "(MuJoCo settings that make a squeezed ball stay put; they apply to every contact, the lane's and the pins' "
        "too). The lane, the gutters and the pins keep their own contact parameters.",
        "Equipment (pins): each pin is six stacked cylinders and capsules that follow the official profile, with the "
        "official mass, centre of gravity and the profile's moments of inertia.",
        "Lane condition: RoboOlympics' house pattern as friction zones (oil, friction {mu_oil}, for {oil_length_m} m "
        "in the middle of the lane and 3 m shorter on the outside boards; a 1.2 m transition; then dry boards, "
        "friction {mu_dry}); the values are RoboOlympics' assumptions after Frohlich (2004), not a measured lane.",
        "Pinfall and the pin count: a pin is down when it is tilted more than {pin_down_tilt_deg} degrees or is off "
        "the lane's surface (RoboOlympics' rule: a pin leaning on a wall counts as down); the count is taken "
        "{settle_s} s after the ball first touches a pin. No pinsetter, no sweep; the pit is " + f"{LANE_Z:g} m deep.",
        "Rule 5: the foul is judged at any time, not only during or after the delivery; a fall also ends the attempt "
        "as a failure, as in every task of this benchmark.",
        "One ball: the task is the first ball of a frame.",
    ]
    time_limit_s = 40.0
    start = (-0.60, 0.0, 0.0)
    stages = ["delivery", "pins", "strike"]
    fall_z = LANE_Z + 0.50
    params = dict(lane_length_m=18.288, lane_width_m=1.0541, gutter_width_m=0.235, gutter_depth_m=0.047,
                  approach_length_m=4.572, pin_spacing_m=0.3048, pin_height_m=0.381, pin_mass_kg=1.53,
                  ball_mass_kg=BALL["mass"], ball_diameter_m=2 * BALL["radius"], oil_length_m=13.5, mu_oil=0.040,
                  mu_dry=0.20, pin_down_tilt_deg=20.0, settle_s=5.0, release_s=0.05, fall_pelvis_m=0.50)

    sentence = ("Bowl a strike: from behind the foul line, deliver the ball you hold pressed between your two palms "
                "down the lane so that all ten pins are knocked down.")
    rules = ("The lane is {lane_width_m} m wide and runs {lane_length_m} m from the foul line to the head pin's spot, "
             "with a gutter {gutter_width_m} m wide and {gutter_depth_m} m deep on each side; behind the foul line "
             "the approach, level with the lane, is {approach_length_m} m long. Ten pins ({pin_height_m} m tall, "
             "{pin_mass_kg} kg each) stand in the triangle of four rows, {pin_spacing_m} m apart, its point towards "
             "you. The ball ({ball_diameter_m} m across, {ball_mass_kg} kg, no finger holes) starts pressed between "
             "your two palms. Your hands have no fingers and no grip: only the force of your arms and friction hold "
             "the ball, and it can slip out. Until the release the ball may touch no part of you but your hands (the "
             "palm pads and the wrists; either or both). The release: the ball has touched no part of you for "
             "{release_s} s (it is released at its last touch); after that no part of you may touch it again. The "
             "lane is oiled (friction {mu_oil}) for the first {oil_length_m} m in its middle, less far on its "
             "outside boards, and dry (friction {mu_dry}) beyond. A delivery: the released ball crosses the foul "
             "line. It is a foul if any part of you touches the lane, a gutter or anything else on or beyond the foul "
             "line, at any time. Pins count only if the ball reaches them on the lane: a ball that touches a gutter "
             "before it has touched a pin knocks down nothing. A pin is down when it is tilted more than "
             "{pin_down_tilt_deg} degrees or is no longer on the lane's surface; the pins are counted {settle_s} s "
             "after the ball first touches one. You succeed with a strike: all ten pins down. You fail on a foul; on "
             "a gutter ball; if fewer than ten pins are down at the count; if the ball touches a part of you other "
             "than a hand before the release; if any part of you touches the ball after the release; if you fall "
             "before the count (your pelvis lower than {fall_pelvis_m} m above the approach, or any part of you "
             "other than your feet on the approach or the floor); or after {time_limit_s} s.")
    venue = ("You stand on the approach facing the pins (+x), your pelvis 0.60 m behind the foul line on the lane's "
             "centre line. The ball is pressed between your two palms in front of your hips, its centre about "
             "0.82 m above the approach and 0.19 m ahead of your pelvis: your upper arms are a little back, your "
             "forearms point forwards and down and are turned in so that the palms squeeze it; the start command "
             "keeps that squeeze (the joint table's start angles are a little further in than the arms stand: the "
             "difference is the squeeze). Under the ball's weight your standing body leans forwards a little and "
             "sways. "
             "The approach and the lane are " + f"{LANE_Z:g} m above the building's floor, which surrounds the "
             "approach. " + "The head pin is {lane_length_m} m beyond the foul line on the centre line. Your hands "
             "have no grip: the grip columns of the action rows do nothing in this task.")
    difficulty = ("A strike needs the ball in the pocket beside the head pin, a few centimetres wide, after 18 m of "
                  "lane on which it slides on the oil and grips on the dry boards; a 6 lb ball is deflected by the "
                  "pins more than a heavy one, so it must also arrive fast. The 2.7 kg ball is held only by the "
                  "squeeze of two fingerless palms, which the swing's speed and the ball's weight pull apart, both "
                  "hands have to let go of it at the same moment without steering it off its line, and the body may "
                  "not cross the foul line.")

    # ------------------------------------------------------------------ the venue
    def pin_spots(self):
        p = self.p
        out = []
        for row in range(4):
            for k in range(row + 1):
                out.append((p["lane_length_m"] + row * p["pin_spacing_m"] * ROW_DX_FACTOR,
                            (row / 2 - k) * p["pin_spacing_m"]))
        return out

    def _oil_len(self, d: int) -> float:
        t = min(1.0, max(0.0, (d - TAPER_D0) / (TAPER_D1 - TAPER_D0)))
        return self.p["oil_length_m"] - 3.0 * t * t * (3 - 2 * t)

    def build(self, sc):
        p = self.p
        self.fall_z = LANE_Z + p["fall_pelvis_m"]
        H, hw, GW = LANE_Z, p["lane_width_m"] / 2, p["gutter_width_m"]
        head = p["lane_length_m"]
        kick_y, kick_x0 = hw + GW, head - KICK_BEFORE_HEAD_PIN
        opt = sc.root.find("option")
        opt.append(sc.root.makeelement("flag", dict(multiccd="enable")))    # feet on the approach, pins on the deck
        surf = dict(solref=CONTACT, solimp="0.95 0.99 0.001", condim=3, priority=3, **STANDABLE)
        wb = sc.wb
        # the approach: as wide as the lane and its gutters, level with the lane
        sc.platform("approach", (-p["approach_length_m"] / 2, 0.0), (p["approach_length_m"] / 2, kick_y + 0.08, H / 2),
                    rgba=(0.80, 0.64, 0.44, 1), ground=True)
        sc.geom(wb, "foul_line", type="box", pos=(0.0, 0, H + 0.0006), size=(0.005, hw, 0.0005), rgba=(0.1, 0.1, 0.1, 1), **VISUAL)
        # the lane: strips of boards with the same oil length, each cut along x into oil, transition and dry zones
        bw = p["lane_width_m"] / N_BOARDS
        strips = []
        for j in range(N_BOARDS):
            y0, y1 = -hw + j * bw, -hw + (j + 1) * bw
            L0 = round(self._oil_len(abs(j + 1 - 20)), 4)
            if strips and strips[-1][2] == L0:
                strips[-1] = (strips[-1][0], y1, L0)
            else:
                strips.append((y0, y1, L0))
        ramp = 1.2
        self.lane_names = []
        for i, (y0, y1, L0) in enumerate(strips):
            segs = [(0.0, L0, p["mu_oil"])]
            for k in range(N_RAMP):
                f = (k + 0.5) / N_RAMP
                segs.append((L0 + k * ramp / N_RAMP, L0 + (k + 1) * ramp / N_RAMP, p["mu_oil"] + f * (p["mu_dry"] - p["mu_oil"])))
            segs.append((L0 + ramp, head - 0.3, p["mu_dry"]))
            for k, (a, b, mu) in enumerate(segs):
                shade = 1.0 - 0.35 * (mu - p["mu_oil"]) / max(p["mu_dry"] - p["mu_oil"], 1e-9) * 0.4
                sc.geom(wb, f"lane{i}_{k}", type="box", pos=((a + b) / 2, (y0 + y1) / 2, H / 2), size=((b - a) / 2, (y1 - y0) / 2, H / 2),
                        friction=(mu, 0.005, 0.0001), rgba=(WOOD[0] * shade, WOOD[1] * shade, WOOD[2] * shade, 1), **surf)
                self.lane_names.append(f"lane{i}_{k}")
        sc.geom(wb, "deck", type="box", pos=((head - 0.3 + PIT_X) / 2, 0, H / 2), size=((PIT_X - head + 0.3) / 2, hw, H / 2),
                friction=(DECK_MU, 0.005, 0.0001), rgba=(0.90, 0.78, 0.60, 1), **surf)
        self.lane_names.append("deck")
        grey, dark = (0.55, 0.56, 0.60, 1), (0.12, 0.14, 0.20, 1)
        gz = H - p["gutter_depth_m"]
        for s, tag in ((1, "L"), (-1, "R")):
            sc.geom(wb, f"gutter{tag}", type="box", pos=(PIT_X / 2, s * (hw + GW / 2), gz / 2), size=(PIT_X / 2, GW / 2, gz / 2),
                    friction=(GUTTER_MU, 0.005, 0.0001), rgba=grey, **surf)
            sc.geom(wb, f"cap{tag}", type="box", pos=(kick_x0 / 2, s * (kick_y + 0.04), (H + 0.04) / 2),
                    size=(kick_x0 / 2, 0.04, (H + 0.04) / 2), rgba=grey, **surf)
            sc.geom(wb, f"kick{tag}", type="box", pos=((kick_x0 + PIT_X + 0.95) / 2, s * (kick_y + 0.02), (H + 1.0) / 2),
                    size=((PIT_X + 0.95 - kick_x0) / 2, 0.02, (H + 1.0) / 2), friction=(GUTTER_MU, 0.005, 0.0001),
                    rgba=dark if s < 0 else (0.12, 0.14, 0.20, 0.35), **surf)
        sc.geom(wb, "cushion", type="box", pos=(PIT_X + 0.92, 0, (H + 1.0) / 2), size=(0.02, kick_y, (H + 1.0) / 2),
                rgba=(0.08, 0.08, 0.10, 1), solref="0.02 1", priority=3, condim=3, **STANDABLE)
        # the pins
        self.spots = self.pin_spots()
        ixx, izz = pin_inertia(p["pin_mass_kg"], p["pin_height_m"])
        white = (0.97, 0.97, 0.95, 1)
        pin = dict(friction=(PIN_MU, 0.005, 0.0001), solref=CONTACT, solimp="0.95 0.99 0.001", condim=3, priority=2,
                   mass=0, rgba=white, contype=1, conaffinity=13)
        for i, (x, y) in enumerate(self.spots):
            b = sc.body(f"pin{i + 1}", (x, y, H), free=True)
            b.insert(1, b.makeelement("inertial", dict(pos=f"0 0 {PIN_COM_Z}", mass=f"{p['pin_mass_kg']!r}",
                                                        diaginertia=f"{ixx:.6e} {ixx:.6e} {izz:.6e}")))
            for k, (typ, z0, z1, r) in enumerate(PIN_PARTS):
                sc.geom(b, f"pin{i + 1}_{k}", type=typ, fromto=(0, 0, z0 * IN, 0, 0, z1 * IN), size=(r * IN,), **pin)
            sc.geom(b, f"pin{i + 1}_band", type="cylinder", fromto=(0, 0, 10.0 * IN, 0, 0, 10.5 * IN), size=(0.93 * IN,),
                    rgba=(0.8, 0.05, 0.05, 1), mass=0, **VISUAL)
        sc.ball("ball", "bowling", (-0.15, 0.0, H + 1.2), mass=p["ball_mass_kg"],      # no grip: not grippable
                radius=p["ball_diameter_m"] / 2)
        opt.set("cone", CONE)                                               # the two-palm hold (dunk-realgrasp)
        opt.set("impratio", f"{IMPRATIO:g}")
        for side in ("left", "right"):
            ET.SubElement(sc.root.find("contact"), "pair", name=f"palm_ball_{side}", geom1="ball",
                          geom2=f"{side}_palm_pad", condim="6",
                          friction=f"{PALM_MU} {PALM_MU} 0.003 {BALL['roll']} {BALL['roll']}", solref=PALM_SOLREF,
                          solimp=PALM_SOLIMP)
        sc.camera("venue", (-3.2, -2.6, 2.3), (4.0, 0.0, 0.2), fovy=55)
        sc.camera("pins", (head - 2.6, -1.3, 1.4), (head + 0.4, 0.0, 0.25), fovy=45)

    def reset(self, w):
        d, H = w.d, LANE_Z
        d.qpos[w.robot.fq + 2] += H                           # the robot stands on the approach
        for i, (x, y) in enumerate(self.spots):
            w.put(f"pin{i + 1}", (x, y, H))
        ball_between_palms(w)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        self.ball = ref.geoms(body="ball")
        self.robot = ref.part("robot")
        self.hands = ref.part("hands")
        self.not_hands = self.robot & ~self.hands
        self.pins = ref.geoms(prefix="pin")
        self.gutters = ref.geoms(names=["gutterL", "gutterR"])
        self.pin_ids = [w.m.body(f"pin{i + 1}").id for i in range(10)]
        self.trackers = {"released": None, "last_touch": 0.0, "t_pins": None, "down": 0, "v_before": [0.0, 0.0, 0.0]}

    def may_grip(self, w, side, name):
        return False                                          # nothing is grippable: no grip exists in this task

    def pins_down(self, w) -> list[bool]:
        """RoboOlympics' pin-down rule: tilted more than the limit, or off the lane's surface."""
        p = self.p
        out = []
        for b in self.pin_ids:
            up = float(w.d.xmat[b].reshape(3, 3)[2, 2])
            x, y, z = w.d.xpos[b]
            tilt = math.degrees(math.acos(max(-1.0, min(1.0, up))))
            on_lane = abs(y) <= p["lane_width_m"] / 2 and 0.0 <= x <= PIT_X and z > LANE_Z - 0.01
            out.append(tilt > p["pin_down_tilt_deg"] or not on_lane)
        return out

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        pts = ref.contact_points(self.robot, ~self.robot & ~self.ball)
        if len(pts) and float(pts[:, 0].max()) >= 0.0:
            return ref.fail("foul: touched the lane on or beyond the foul line",
                            parts=sorted(ref.parts_touching(~self.robot & ~self.ball)))
        if tr["t_pins"] is not None:
            return
        if tr["released"] is None:
            if ref.touching(self.ball, self.not_hands):
                return ref.fail("the ball touched a part other than the hands before the release",
                                parts=sorted(ref.parts_touching(self.ball) - {"left_hand", "right_hand"}))
            if ref.touching(self.ball, self.hands):
                tr["last_touch"] = round(ref.time, 4)
                return
            if ref.time - tr["last_touch"] < p["release_s"] - 1e-9:
                return
            tr["released"] = tr["last_touch"]
            ref.metrics["release_speed_m_s"] = round(float(np.linalg.norm(w.vel("ball"))), 2)
        if ref.touching(self.ball, self.robot):
            return ref.fail("the ball was touched after the release", parts=sorted(ref.parts_touching(self.ball)))
        x, y, _ = w.pos("ball")
        if not ref.has("delivery") and x > 0.0:
            ref.stage("delivery", y=round(float(y), 3))
        if ref.touching(self.ball, self.gutters):
            return ref.fail("a gutter ball", x=round(float(x), 2))
        if not ref.touching(self.ball, self.pins):
            tr["v_before"] = [float(c) for c in w.vel("ball")]
        elif ref.has("delivery"):
            tr["t_pins"] = ref.time
            v = tr["v_before"]                                # the ball's velocity just before it touched a pin
            ref.metrics["entry_speed_m_s"] = round(float(np.linalg.norm(v)), 2)
            ref.metrics["entry_y_m"] = round(float(y), 3)
            ref.metrics["entry_angle_deg"] = round(math.degrees(math.atan2(float(v[1]), float(v[0]))), 2)
            ref.stage("pins")

    def step(self, w, ref):
        tr, p = self.trackers, self.p
        down = self.pins_down(w)
        tr["down"] = int(sum(down))
        ref.metrics["pins_down"] = tr["down"]
        if tr["t_pins"] is not None and ref.time - tr["t_pins"] >= p["settle_s"] - 1e-9:
            if tr["down"] == 10:
                if ref.stage("strike"):
                    ref.succeed()
            else:
                ref.fail("not a strike", pins_down=tr["down"], standing=[i + 1 for i, d in enumerate(down) if not d])

    def privileged(self, w):
        tr = self.trackers
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "hands_on_ball": bool(w.ref.touching(self.ball, self.hands)), "released": tr["released"] is not None,
                "pins": [w.d.xpos[b].tolist() for b in self.pin_ids], "pins_down": self.pins_down(w),
                "lane_surface_z": LANE_Z}
