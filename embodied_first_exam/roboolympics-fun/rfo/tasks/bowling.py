"""Ten-pin bowling (USBC): from the approach, deliver the ball down the official lane without fouling and knock down
all ten pins with it: a strike. Lane, gutters, pin deck, pins and oil pattern from RoboOlympics' bowling simulator; a
6 lb ball; the Unitree H1-2."""
import math

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


def set_arm(w, **angles) -> None:
    """Put arm joints (names without "_joint") at angles for t = 0, and their held targets with them."""
    r, d = w.robot, w.d
    for name, v in angles.items():
        i = w.L.JOINTS.index(name + "_joint")
        d.qpos[r.qadr[i]] = v
        r.arb.q_a[i] = r.arb.q_b[i] = v
    mujoco.mj_kinematics(w.m, d)


class Task(TaskBase):
    name = "bowling"
    title = "Ten-pin bowling: a strike"
    category = "throwing-catching-striking"
    robot = "unitree_h1"
    rulebook = ("USBC Playing Rules 2024-2025 and USBC Equipment Specifications: the lane (60 ft from the foul line "
                "to the head pin, 41.5 in wide, gutters, pin deck), the pins (15 in, 3 lb 6 oz, 12 in apart), the "
                "ball (at most 8.595 in and 16 lb); the playing rules on a strike, a legal delivery, the foul (Rule "
                "5) and legal and illegal pinfall")
    deviations = [
        "Equipment (ball): the hand holds the ball by a grip switched on and off, which stands for the finger holes "
        "(the ball hangs from the end of the hand); a uniform ball, no weight block; it is released when the grip is "
        "switched off.",
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
    start = (-0.60, 0.30, 0.0)
    stages = ["delivery", "pins", "strike"]
    fall_z = LANE_Z + 0.50
    params = dict(lane_length_m=18.288, lane_width_m=1.0541, gutter_width_m=0.235, gutter_depth_m=0.047,
                  approach_length_m=4.572, pin_spacing_m=0.3048, pin_height_m=0.381, pin_mass_kg=1.53,
                  ball_mass_kg=BALL["mass"], ball_diameter_m=2 * BALL["radius"], oil_length_m=13.5, mu_oil=0.040,
                  mu_dry=0.20, pin_down_tilt_deg=20.0, settle_s=5.0, retouch_grace_s=0.20, fall_pelvis_m=0.50)

    sentence = ("Bowl a strike: from behind the foul line, deliver the ball that hangs from your right hand down the "
                "lane so that all ten pins are knocked down.")
    rules = ("The lane is {lane_width_m} m wide and runs {lane_length_m} m from the foul line to the head pin's spot, "
             "with a gutter {gutter_width_m} m wide and {gutter_depth_m} m deep on each side; behind the foul line "
             "the approach, level with the lane, is {approach_length_m} m long. Ten pins ({pin_height_m} m tall, "
             "{pin_mass_kg} kg each) stand in the triangle of four rows, {pin_spacing_m} m apart, its point towards "
             "you. The ball ({ball_diameter_m} m across, {ball_mass_kg} kg) hangs from your right hand. The lane is "
             "oiled (friction {mu_oil}) for the first {oil_length_m} m in its middle, less far on its outside boards, "
             "and dry (friction {mu_dry}) beyond. A delivery: you let go of the ball (once: it cannot be gripped "
             "again) and it crosses the foul line. It is a foul if any part of you touches the lane, a gutter or "
             "anything else on or beyond the foul line, at any time. Pins count only if the ball reaches them on the "
             "lane: a ball that touches a gutter before it has touched a pin knocks down nothing. A pin is down when "
             "it is tilted more than {pin_down_tilt_deg} degrees or is no longer on the lane's surface; the pins are "
             "counted {settle_s} s after the ball first touches one. You succeed with a strike: all ten pins down. "
             "You fail on a foul; on a gutter ball; if fewer than ten pins are down at the count; if any part of you "
             "touches the ball after the release (your right arm may still brush it during the first "
             "{retouch_grace_s} s); if you fall before the count (your pelvis lower than {fall_pelvis_m} m above the "
             "approach, or any part of you other than your feet on the approach or the floor); or after "
             "{time_limit_s} s.")
    venue = ("You stand on the approach facing the pins (+x), your pelvis 0.60 m behind the foul line and 0.30 m to "
             "the left of the lane's centre line; your right arm hangs straight down, a little away from the leg, the "
             "ball under its hand about 0.07 m to the right of the centre line. The approach and the lane are "
             f"{LANE_Z:g} m above the building's floor, which surrounds the approach. " + "The head pin is "
             "{lane_length_m} m beyond the foul line on the centre line. The ball is released when the hand's grip is "
             "switched off.")
    difficulty = ("A strike needs the ball in the pocket beside the head pin, a few centimetres wide, after 18 m of "
                  "lane on which it slides on the oil and grips on the dry boards; a 6 lb ball is deflected by the "
                  "pins more than a heavy one, so it must also arrive fast. Nothing but the release aims it, and the "
                  "body may not cross the foul line.")

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
        sc.ball("ball", "bowling", (-0.6, 0.0, H + 0.6), grippable=True, mass=p["ball_mass_kg"],
                radius=p["ball_diameter_m"] / 2)
        sc.camera("venue", (-3.2, -2.6, 2.3), (4.0, 0.0, 0.2), fovy=55)
        sc.camera("pins", (head - 2.6, -1.3, 1.4), (head + 0.4, 0.0, 0.25), fovy=45)

    def reset(self, w):
        d, H = w.d, LANE_Z
        d.qpos[w.robot.fq + 2] += H                           # the robot stands on the approach
        for i, (x, y) in enumerate(self.spots):
            w.put(f"pin{i + 1}", (x, y, H))
        set_arm(w, right_elbow_pitch=1.57, right_shoulder_roll=-0.22)
        b = w.robot.mount["right"]
        w.put("ball", d.xpos[b] + d.xmat[b].reshape(3, 3) @ np.array([0.0, 0.0, 0.105 + self.p["ball_diameter_m"] / 2]))
        w.grab("right", "ball", event=False)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        self.ball = ref.geoms(body="ball")
        self.robot = ref.part("robot")
        self.arm = ref.part("right_arm")
        self.not_arm = self.robot & ~self.arm
        self.pins = ref.geoms(prefix="pin")
        self.gutters = ref.geoms(names=["gutterL", "gutterR"])
        self.pin_ids = [w.m.body(f"pin{i + 1}").id for i in range(10)]
        self.trackers = {"released": None, "t_pins": None, "down": 0, "v_before": [0.0, 0.0, 0.0]}

    def may_grip(self, w, side, name):
        return False                                          # held from t = 0; once let go it cannot be gripped again

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
        held = bool(w.holder("ball"))
        if tr["released"] is None:
            if not held:
                tr["released"] = ref.time
                ref.metrics["release_speed_m_s"] = round(float(np.linalg.norm(w.vel("ball"))), 2)
            return
        if (ref.touching(self.ball, self.not_arm)
                or (ref.time - tr["released"] > p["retouch_grace_s"] and ref.touching(self.ball, self.arm))):
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
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(), "held": bool(w.holder("ball")),
                "pins": [w.d.xpos[b].tolist() for b in self.pin_ids], "pins_down": self.pins_down(w),
                "lane_surface_z": LANE_Z}
