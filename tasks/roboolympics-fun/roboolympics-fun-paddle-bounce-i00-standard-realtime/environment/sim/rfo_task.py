"""Paddle bounce (table tennis ball control): a ball is dropped above the paddle on your right hand; keep it bouncing
on the blade, every bounce back up to the height it was dropped from.

The ball and its contact with the blade are the table-tennis-return family's: the official 40 mm, 2.7 g ball with
Google DeepMind's identified fluid coefficients and thin-shell inertia, RoboOlympics' ball-paddle contact pair
(roboolympics/sports/tabletennis/sim/scene/tt_scene.xml, Apache-2.0; the pair is hand-picked, not identified) and the
simulator options they were made with (elliptic friction cones, impratio 10).

Why the rule is "back up to the drop height" (measured on this model): a ball dropped from 0.305 m onto a still, rigid
blade comes back to 0.270 m and then keeps 87 to 95 % of its height at every bounce (the contact and the air take the
rest; a ball that falls further keeps less: 0.83 m from 1.18 m); on the blade held by the standing robot's arm the
first bounce keeps 86 %. A rule that only asks each bounce to rise 0.15 m above the blade is paid for by the drop: a
still blade gets 6 such bounces from 0.305 m, 10 from 0.5 m and 13 from 1.18 m, and a still blade that is lowered 2 cm
after every bounce gets 20 from 0.5 m (0.40 m of lowering in all). No passive rebound, on a still or a sinking blade,
reaches the height the ball fell from again; a bounce that does has been given energy by the blade."""
import xml.etree.ElementTree as ET

import math

import numpy as np

from rfo.referee import Touch
from rfo.scene import OFFICIAL
from rfo.task import TaskBase

BALL = OFFICIAL["tabletennis"]

# The paddle on the right wrist mount (+z along the forearm, away from the wrist; the blade's two faces look along the
# mount's +-x): a handle through the fist and RoboOlympics' blade, a 15 x 15 x 1.5 cm box; 0.05 + 0.09 = 0.14 kg.
PADDLE = dict(blade_m=0.15, thickness_m=0.015, blade_centre_m=0.175, mass_kg=0.14)
PADDLE_XML = (
    '<geom name="paddle_handle" type="capsule" fromto="0 0 0 0 0 0.10" size="0.014" mass="0.05" '
    'rgba="0.55 0.38 0.2 1" contype="4" conaffinity="0"/>'
    '<geom name="paddle_blade" type="box" pos="0 0 0.175" size="0.0075 0.075 0.075" mass="0.09" '
    'rgba="0.8 0.1 0.1 1" contype="4" conaffinity="0"/>')
BLADE_PAIR = dict(solref="-600000 -12", friction="0.8 0.8 0.005 0.0001 0.0001", solimp="0.98 0.99 0.001 0.5 2",
                  solreffriction="-0.0 -200.0")

EARLY = "the ball was touched before it was dropped"
OTHER = "the ball touched something of yours other than the paddle's blade"
FLOOR = "the ball touched the floor"
LOW = "the ball came back to the blade without having risen enough"
REST = "the ball rested on the blade"


class Task(TaskBase):
    name = "paddle-bounce"
    title = "Table tennis: keep the ball bouncing on the paddle"
    category = "basketball-and-rackets"
    robot = "unitree_g1"
    rulebook = ("ITTF Handbook 2024, The Laws of Table Tennis, for the equipment: 2.3 (the ball), 2.4 (the racket). "
                "Bouncing the ball on the racket is a ball-control drill, not an event with a rule book: the number of "
                "consecutive bounces asked for is this benchmark's line")
    deviations = [
        "2.4 (the racket): the blade is a rigid 15 cm square, 1.5 cm thick, 0.14 kg with its handle (legal: the Laws "
        "set no size, shape or weight); its covering is one contact law on both faces (RoboOlympics' ball-paddle pair, "
        "hand-picked, not identified), and it is fixed to the right hand, because the robot's fist cannot hold a handle",
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
                  hit_gain=0.98, drop_x_m=0.36, drop_y_m=-0.20, drop_z_m=1.20, drop_time_s=2.0, fall_height_m=0.35)

    sentence = ("Keep the table tennis ball that is dropped in front of you bouncing on the paddle in your right hand: "
                "{bounces} bounces in a row, each back up to the height the ball was dropped from.")
    rules = ("A table tennis racket (a rigid square blade 0.15 m wide and 0.015 m thick on a short handle, 0.14 kg) is "
             "fixed to your right hand. The official ball (40 mm, 2.7 g; it flies in air, with drag) hangs at rest, its "
             "centre {drop_z_m} m above the floor, until {drop_time_s} s after the start, and then falls. You succeed "
             "after {bounces} bounces in a row on the blade (either face; the faces need not alternate). A bounce is a "
             "touch of the blade after which, before the ball touches the blade again, the ball's centre rises at "
             "least {min_rise_m} m above the height at which it left the blade and reaches at least the height it was "
             "dropped from, {drop_z_m} m above the floor, and which the ball leaves with at least {hit_gain} of the "
             "speed it reached the blade with (both speeds taken at the height where the touch began). On a still "
             "blade every bounce is lower than the one before (the ball keeps about nine tenths of its height, 0.95 "
             "of its speed), so each bounce needs a hit of the blade; a rebound that rises enough but was not hit "
             "is not counted, and is not a fault. A touch is all contact of the ball with the blade from the first contact on, "
             "with breaks shorter than {touch_gap_s} s; a bounce's own contact lasts about a millisecond. You fail if "
             "the ball comes back to the blade after a touch without having risen that much; if a touch lasts longer "
             "than {max_touch_s} s from its first contact to its last (the ball rests, rolls or is carried on the "
             "blade); if the ball touches the floor or anything of yours other than the blade (the racket's handle, "
             "the hand and the arm included); if you touch the ball before it is dropped; if you fall; or after "
             "{time_limit_s} s. A fall is your pelvis lower than {fall_height_m} m above the floor, or any part of "
             "you other than your feet touching the floor (the racket on the floor is a fall).")
    venue = ("You stand on a level floor facing +x, the paddle hanging from your right hand, its handle in the fist "
             "and the blade beyond it (the blade's centre 0.175 m from the wrist). The ball hangs {drop_x_m} m ahead "
             "of your pelvis and {drop_y_m} m to your left (negative: to your right), its centre {drop_z_m} m above "
             "the floor, and is let go, with no speed and no spin, {drop_time_s} s after the start. There is no wind.")
    difficulty = ("Every bounce needs an upward hit of the right strength at the right instant, with the blade level "
                  "and under a 40 mm ball: a tilt of a degree sends the ball off the 15 cm blade within a few "
                  "bounces, and the arm that holds the blade gives way a little at every hit. It has to go right "
                  "twenty times in a row.")

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
        sc.hand_tools["right"] = PADDLE_XML
        sc.ball("ball", "tabletennis", (p["drop_x_m"], p["drop_y_m"], p["drop_z_m"]))
        # DeepMind's table-tennis physics (as in table_tennis_return.py): options, thin-shell inertia, the blade pair
        opt = sc.root.find("option")
        opt.set("cone", "elliptic")
        opt.set("impratio", "10")
        body = next(b for b in sc.wb.iter("body") if b.get("name") == "ball")
        i = 2.0 / 3.0 * BALL["mass"] * BALL["radius"] ** 2
        ET.SubElement(body, "inertial", pos="0 0 0", mass=repr(BALL["mass"]), diaginertia=f"{i:.6g} {i:.6g} {i:.6g}")
        ET.SubElement(sc.root.find("contact"), "pair", name="ball_paddle_blade", geom1="ball", geom2="paddle_blade",
                      **BLADE_PAIR)
        sc.camera("venue", (1.7, -1.8, 1.45), (0.2, -0.1, 0.9), fovy=42)

    def reset(self, w):
        p = self.p
        w.pin("ball", (p["drop_x_m"], p["drop_y_m"], p["drop_z_m"]))

    def referee_reset(self, w, ref):
        p = self.p
        self.ball = ref.geoms(body="ball")
        self.blade = ref.geoms(names=["paddle_blade"])
        self.handle = ref.geoms(names=["paddle_handle"])
        self.other = ref.robot_mask & ~self.blade
        self.trackers = {"blade": Touch(ref, self.ball, self.blade, gap=p["touch_gap_s"]), "dropped": False,
                         "left_z": None, "apex_z": None, "risen": True, "bounces": 0, "speed": 0.0, "v_in": 0.0, "z_in": 0.0}

    def before_step(self, w):
        p = self.p
        if not self.trackers["dropped"] and w.k >= int(round(p["drop_time_s"] / w.CONTROL_DT)):
            w.launch("ball", (p["drop_x_m"], p["drop_y_m"], p["drop_z_m"]), (0.0, 0.0, 0.0))
            self.trackers["dropped"] = True
            w.ref.event("drop")

    def substep(self, w, ref):
        tr, p = self.trackers, self.p
        if not tr["dropped"]:
            if ref.touching(self.ball, ref.robot_mask):
                ref.fail(EARLY, parts=sorted(ref.parts_touching(self.ball)))
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
        R = w.d.xmat[w.m.body("ball").id].reshape(3, 3)
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "ball_spin": (R @ w.d.qvel[va + 3:va + 6]).tolist(),
                "dropped": bool(self.trackers.get("dropped")), "drop_time_s": self.p["drop_time_s"],
                "blade_centre": w.d.geom_xpos[g].tolist(), "blade_normal": (n if n[2] >= 0 else -n).tolist(),
                "bounces": int(self.trackers.get("bounces", 0)), "paddle": PADDLE}
