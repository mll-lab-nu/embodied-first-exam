"""Table tennis: return a legal service with a real grip (ITTF Laws 2.5-2.7, 2.10): table-tennis-return's task, the
library service returned after its bounce on your court onto the opponent's court; but the paddle is not part of the
hand. It is a free 0.14 kg racket held only by the friction of the right hand's two-finger gripper (Unitree Dex1-1): it
can slip, turn in the jaws when it meets the ball, and be dropped.

Everything else is table-tennis-return's (copied: a task directory holds one module): the table, the net, the ball,
the service (entry 221 of RoboOlympics' serve library), the contact pairs, every number. What changed:
* the paddle (FREE_PADDLE; the block is shared, byte for byte, with paddle-bounce-realgrasp): table-tennis-return's
  blade (a rigid 15 x 15 x 1.5 cm box, 0.09 kg) on a straight handle of a real racket's size, 100 mm long, 32 mm wide
  and 25 mm thick, 0.14 kg in all, as a free body;
* the hand: the core's Dex1-1 (rfo.realhand: 90 mm stroke, 80 mm jaws, 5-120 N); the handle lies along the jaws (75 mm
  of the 80 mm pads on it), its broad faces against the pads, so the blade's faces look along the closing axis as on
  table-tennis-return's fixed paddle; the butt 5 mm from the gripper's body; the closure command 1 (120 N). The
  blade's centre is then 0.243 m from the wrist mount, not 0.175. "In the hand" = the handle touches both jaws; a
  break of at most out_of_hand_s (0.05 s) is not a release;
* the racket hand (Law 2.5.5, the hand carrying the racket) is the right gripper: striking with it below the wrist is
  legal (Law 2.5.7) as on table-tennis-return; the paddle may touch nothing of the robot but that gripper;
* the simulator's options: DeepMind's pair was identified with impratio 10; a world with a real hand needs impratio 100
  (realhand.IMPRATIO: with 10 a clamped handle creeps under a steady torque), and this module leaves it at 100.
  Measured: the library service still bounces on the server's court 0.433 m beyond the net and on the receiver's
  0.332 m before it (the library's 0.431 and 0.334 m; the test asserts them to 5 mm, as table-tennis-return's does).

From table-tennis-return's docstring:

The ball, the table and the net are Google DeepMind's system-identified model as RoboOlympics uses it
(roboolympics/sports/tabletennis/sim/scene/tt_scene.xml, from competitive_robot_table_tennis, Apache-2.0): the ball's
fluid coefficients and thin-shell inertia, the identified ball-table contact pair, a rigid net, and the simulator
options the pair was identified and the serve library was made with (1 ms, implicitfast, elliptic friction cones with
impratio 10: with MuJoCo's default pyramidal cones the same service bounces 13 cm further on the receiver's court).
The ball-paddle pair is RoboOlympics' (hand-picked, not identified). The service is one entry of RoboOlympics' serve
library (sim/serve_library.json: 279 services a Franka on a rail made under the real robot's limits, each judged legal
by Laws 2.6.1-2.6.4), stored as the ball's state at the server's strike."""
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from rfo.referee import Touch
from rfo.scene import HITTABLE, OFFICIAL
from rfo.task import TaskBase

BALL = OFFICIAL["tabletennis"]

# The service of instance seed 0: entry number int.from_bytes(sha256(b"robofunolympics/table-tennis-return/seed=0")
# .digest()[:8], "big") % 279 = 221 of the library's "serves" list (id "lab0121"; the list is ordered by difficulty for
# the receiver, 0 the easiest, so 221 is in the hardest quarter: a short service whose second bounce is still on the
# receiver's court). The library's frame (table top z = 0, the net the plane y = 0, the server at y > 0) is turned into
# the venue's: x = net_x + y_lib, y = -x_lib, z = table height + z_lib; velocity and spin (rad/s, world axes) likewise.
SERVE_LIB = dict(index=221, id="lab0121", pos=(0.199863, 1.418919, 0.139714), vel=(-0.353897, -2.769383, 1.627944),
                 spin=(10.47295, -1.07876, 0.16247))


def _venue(v):
    return (v[1], -v[0], v[2])


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


HAND = "right"                     # the racket hand
BUTT_FROM_JAW_CENTRE_M = 0.035     # the butt 5 mm out from the gripper's housing: the handle along the 80 mm jaws

# DeepMind's identified ball-table pair, the net as their scene has it (the ball's undamped 1e5 N/m spring on a rigid
# box), RoboOlympics' ball-paddle pair
PAIRS = (("table", dict(solref="-1000000 -17", friction="0.1 0.1 0.005 0.0001 0.0001", solimp="0.98 0.99 0.001 0.5 2",
                        solreffriction="-0.0 -200.0")),
         ("net", dict(solref="-100000 0", friction="1 1 0.005 0.0001 0.0001")),
         ("paddle_blade", dict(solref="-600000 -12", friction="0.8 0.8 0.005 0.0001 0.0001",
                               solimp="0.98 0.99 0.001 0.5 2", solreffriction="-0.0 -200.0")))

EARLY = "the ball was touched before the service"
NET = "you touched the net assembly"
FREE_HAND = "your free hand touched the playing surface"
OBSTRUCTION = "obstruction: the ball was touched before it bounced on your court"
BODY = "the ball touched something other than the racket's blade or the racket hand"
TWICE = "the ball was struck twice"
DOUBLE_BOUNCE = "the ball bounced twice on your court"
OWN_COURT = "the return touched your own court"
SIDE = "the return hit the side of the table"
FLOOR = "the ball touched the floor"
BAD_SERVICE = "the service was not a legal service"
LEFT_HAND = "the paddle left your hand"
HELD_ELSE = "the paddle touched a part of you other than your right hand"
PADDLE_FLOOR = "the paddle touched the floor"


def tt_physics(sc, ball: str = "ball"):
    """DeepMind's table-tennis physics in this scene: the simulator options (elliptic cones; impratio is left to the
    real hand's 100, see the docstring), the ball's thin-shell inertia, and the explicit contact pairs of the ball with
    the geoms of PAIRS that exist."""
    opt = sc.root.find("option")
    opt.set("cone", "elliptic")
    body = next(b for b in sc.wb.iter("body") if b.get("name") == ball)
    i = 2.0 / 3.0 * BALL["mass"] * BALL["radius"] ** 2          # 7.2e-7 kg m^2, as in DeepMind's model
    ET.SubElement(body, "inertial", pos="0 0 0", mass=repr(BALL["mass"]), diaginertia=f"{i:.6g} {i:.6g} {i:.6g}")
    names = {g.get("name") for g in sc.root.iter("geom")}
    for geom, kw in PAIRS:
        if geom in names:
            ET.SubElement(sc.root.find("contact"), "pair", name=f"{ball}_{geom}", geom1=ball, geom2=geom, **kw)


class Task(TaskBase):
    name = "table-tennis-return-realgrasp"
    title = "Table tennis: return a service, paddle held by a real grip"
    category = "basketball-and-rackets"
    robot = "unitree_g1"
    rulebook = ("ITTF Handbook 2024, The Laws of Table Tennis: 2.1 (the table), 2.2 (the net assembly), 2.3 (the ball), "
                "2.4 (the racket), 2.5 (definitions: struck, obstruction, racket hand, free hand), 2.6 (the service), "
                "2.7 (the return), 2.10 (a point)")
    deviations = [
        "2.6.1-2.6.3 (the service): there is no server and no toss: the ball waits at the server's strike point and is "
        "launched at {serve_time_s} s with the position, velocity and spin it has at the strike of a legal service of "
        "RoboOlympics' serve library (a service a Franka arm made under its real limits; entry {serve_index}, the "
        "draw of this instance's seed, not chosen for being returnable), because the task is one return, not a match",
        "2.1.3 (the table's bounce): the playing surface is Google DeepMind's system-identified table, on which a ball "
        "dropped from 30 cm rebounds 26 cm, not the Law's about 23 cm; it is the only identified model of the ball's "
        "bounce with spin there is",
        "2.2 (the net): the net is a rigid wall 1 cm thick, {net_height_m} m high, reaching {net_overhang_m} m beyond "
        "each side line, without separate posts or a cord (DeepMind's model); a soft net is not simulated",
        "2.4 (the racket): the blade is a rigid 15 cm square, 1.5 cm thick, on a straight handle {handle_length_m} m "
        "long, {handle_width_m} m wide and {handle_thickness_m} m thick, {paddle_mass_kg} kg in all (legal: the Laws "
        "set no size, shape or weight); its covering is one contact law on both faces (RoboOlympics' ball-paddle pair, "
        "hand-picked, not identified)",
        "2.5.5 (the racket hand, the hand carrying the racket): the hand is a two-finger gripper, Unitree's Dex1-1 "
        "(90 mm stroke, 80 mm jaws, at most 120 N); the handle lies along its jaws and the racket is held by their "
        "friction alone, as a hand holds it; \"carrying\" is defined by contact: the handle touches both of the "
        "gripper's jaws, and a break of up to {out_of_hand_s} s is not a release; the racket may touch nothing of the "
        "player but the racket hand (the Laws do not forbid a second hand on the racket; here it would make the free "
        "hand a second racket hand)",
        "2.10.1.7 (deliberately striking the ball twice): intent cannot be judged: every contact of the blade or the "
        "racket hand within {strike_window_s} s of the first is the same strike, a later one is a second strike",
        "2.10.1.8 (moving the playing surface): the table is fixed and this is not judged: a competition table weighs "
        "three times the robot and more, and the robot's push on it is limited by the grip of its own feet",
        "2.5.8 and 2.10.1 (the ball touching the player): any touch of the ball by anything but the blade or the "
        "racket hand loses the point, also after the ball has bounced on the robot's court (stricter than the Laws, "
        "which then only require that the return be struck)",
    ]
    time_limit_s = 8.0
    start = (0.0, 0.0, 0.0)
    stages = ["bounce", "strike", "opponent's court"]
    params = dict(
        table_length_m=2.74, table_width_m=1.525, table_height_m=0.76, net_height_m=0.1525, net_overhang_m=0.1525,
        table_near_x_m=0.50,
        serve_time_s=3.0, serve_index=SERVE_LIB["index"],
        serve_x_m=round(0.50 + 1.37 + SERVE_LIB["pos"][1], 6), serve_y_m=-SERVE_LIB["pos"][0],
        serve_z_m=round(0.76 + SERVE_LIB["pos"][2], 6),
        serve_vx=_venue(SERVE_LIB["vel"])[0], serve_vy=_venue(SERVE_LIB["vel"])[1], serve_vz=_venue(SERVE_LIB["vel"])[2],
        serve_wx=_venue(SERVE_LIB["spin"])[0], serve_wy=_venue(SERVE_LIB["spin"])[1], serve_wz=_venue(SERVE_LIB["spin"])[2],
        strike_window_s=0.05, bounce_gap_s=0.02, fall_height_m=0.35,
        paddle_mass_kg=FREE_PADDLE["mass_kg"], handle_length_m=FREE_PADDLE["handle_length_m"],
        handle_width_m=FREE_PADDLE["handle_width_m"], handle_thickness_m=FREE_PADDLE["handle_thickness_m"],
        blade_centre_m=FREE_PADDLE["blade_centre_from_butt_m"], out_of_hand_s=0.05)

    sentence = ("Return the service: after the table tennis ball has bounced once on your court, strike it with the "
                "paddle held in your right hand's gripper so that it touches the opponent's court, without letting go "
                "of the paddle.")
    rules = ("The table is the official one: {table_length_m} m long, {table_width_m} m wide, its playing surface "
             "{table_height_m} m above the floor, with a net {net_height_m} m high across its middle that reaches "
             "{net_overhang_m} m beyond each side line. Your court is the half of the playing surface on your side of "
             "the net, the opponent's court the other half; the top edges belong to the playing surface, the sides of "
             "the table top do not (a ball that touches the table with its centre below the level of the playing "
             "surface has hit the side). The ball is the official one (40 mm, 2.7 g) and flies in air: drag and the "
             "lift of its spin act on it. The racket is a separate body: a rigid square blade 0.15 m wide and 0.015 m "
             "thick on a straight handle {handle_length_m} m long, {handle_width_m} m wide and {handle_thickness_m} m "
             "thick, {paddle_mass_kg} kg in all, the blade's centre {blade_centre_m} m from the butt. At the start its "
             "handle is closed in your right hand's two-finger gripper, which holds it by friction only: it can slip, "
             "turn in the gripper and fall. Your right hand (the gripper's jaws and body) is the racket hand, your "
             "left hand the free hand. The racket is in your hand while its handle touches both of the gripper's "
             "jaws; it has left your hand when for more than {out_of_hand_s} s the handle has not touched both jaws. The service is "
             "struck {serve_time_s} s after the start: a legal service, so the ball bounces first on the server's "
             "court, passes the net and bounces on your court. Then you must make a good return (Law 2.7): strike the "
             "ball, after that one bounce on your court, with the blade of the racket in your hand or with the racket "
             "hand below the wrist (the gripper), so "
             "that it touches the opponent's court, directly or after touching the net; it may pass over or around the "
             "net. You succeed at the moment the ball touches the opponent's court after your strike. All contacts of "
             "the blade or the racket hand with the ball within {strike_window_s} s of the first are one strike. You "
             "fail if the racket leaves your hand at any time (dropped, thrown or slipped out of the gripper); if the "
             "racket touches any part of you other than the racket hand; if you or the racket touch the ball before "
             "the service, or before it has bounced on your court (obstruction); if "
             "the ball bounces a second time on your court before you strike it (ball contacts with the table less "
             "than {bounce_gap_s} s apart are one bounce); if anything other than the blade or the racket hand "
             "touches the ball (the racket's handle, an arm, the body); if the blade or the racket hand touches "
             "the ball again later than {strike_window_s} s after the first contact (struck twice, or carried); if "
             "after your strike the ball touches your own court, the side of the table or the floor before the "
             "opponent's court; if the ball touches the floor at any time; if any part of you or the racket touches "
             "the net; if the racket touches the floor; if your free hand touches the playing surface while the ball is in play (from the service on); "
             "if you fall; or after {time_limit_s} s. Anything else of you, the racket included, may touch the table. "
             "A fall is your pelvis lower than {fall_height_m} m above the floor, or any part of you other than your "
             "feet touching the floor.")
    venue = ("You stand at your end of the table facing it (+x), on its centre line, your pelvis {table_near_x_m} m "
             "behind your end line; the net is 1.37 m beyond the end line and the server's end line 2.74 m. The ball "
             "waits at rest where the server strikes it: {serve_x_m} m ahead of your pelvis, {serve_y_m} m to your "
             "left (negative: to your right) and {serve_z_m} m above the floor, just behind the server's end line. The "
             "service is one of a library of legal robot services: they leave the server's racket at 2.2 to 4.5 m/s "
             "with up to 34 rad/s of spin and bounce on your court between 0.2 and 0.8 s after the strike; short "
             "services bounce a second time on your court if you do not strike them. The paddle's handle is closed in your "
             "right gripper along its two fingers, the butt just short of the gripper's body and the rest of the handle "
             "reaching beyond the fingertips; the blade's faces look the way the jaws close (your palm's side and the "
             "back of your hand), and the paddle points ahead along your forearm, the blade's centre about 0.24 m "
             "beyond your wrist.")
    difficulty = ("The served ball is over your court for a few tenths of a second, low above a table that is as high "
                  "as your hips, and may have to be met far inside the end line: the blade, a rigid extension of a "
                  "0.5 m arm, has to be there at the right instant and angle while the body leans over the table "
                  "without touching the net. The return must clear a 15 cm net and still come down on a court 1.37 m "
                  "long, off a ball that carries spin. The paddle sits in a two-finger gripper: the blade is where the "
                  "jaws hold it, and a fast stroke must not fling it out of the hand.")

    def __init__(self):
        super().__init__()
        self.fall_z = float(self.p["fall_height_m"])

    def configure(self, params):
        super().configure(params)
        self.fall_z = float(self.p["fall_height_m"])

    def build(self, sc):
        p = self.p
        h, x0, L, hw = p["table_height_m"], p["table_near_x_m"], p["table_length_m"], p["table_width_m"] / 2
        self.net_x = x0 + L / 2
        sc.box("hall", (x0 + L / 2, 0, 0.0003), (L / 2 + 2.5, 3.0, 0.0003), rgba=(0.45, 0.25, 0.25, 1))
        # the table top (DeepMind's: one box 4 cm thick) and the net, a rigid box hw + overhang to each side
        sc.box("table", (self.net_x, 0, h - 0.02), (L / 2, hw, 0.02), rgba=(0.10, 0.25, 0.55, 1), solid="hit")
        sc.box("net", (self.net_x, 0, h + p["net_height_m"] / 2),
               (0.005, hw + p["net_overhang_m"], p["net_height_m"] / 2), rgba=(1, 1, 1, 0.5), solid="hit")
        for i, (lx, ly) in enumerate(((0.27, 0.6), (0.27, -0.6), (L - 0.27, 0.6), (L - 0.27, -0.6))):
            sc.box(f"table_leg{i}", (x0 + lx, ly, (h - 0.04) / 2), (0.03, 0.03, (h - 0.04) / 2),
                   rgba=(0.2, 0.2, 0.22, 1), solid="hit")
        for i, y in enumerate((-hw + 0.01, hw - 0.01)):          # side lines and end lines 2 cm, the centre line 3 mm
            sc.box(f"table_side_line{i}", (self.net_x, y, h + 0.0003), (L / 2, 0.01, 0.0003))
        for i, x in enumerate((x0 + 0.01, x0 + L - 0.01)):
            sc.box(f"table_end_line{i}", (x, 0, h + 0.0003), (0.01, hw, 0.0003))
        sc.box("table_centre_line", (self.net_x, 0, h + 0.0003), (L / 2, 0.0015, 0.0003))
        sc.ball("ball", "tabletennis", (p["serve_x_m"], p["serve_y_m"], p["serve_z_m"]))
        build_free_paddle(sc, pos=(x0 - 1.0, -1.5, 0.05))
        sc.real_hands[HAND] = "dex1"
        tt_physics(sc)
        sc.camera("venue", (x0 - 1.3, -2.6, 1.75), (x0 + 1.1, 0.0, 0.75), fovy=50)

    def _serve(self):
        p = self.p
        return ((p["serve_x_m"], p["serve_y_m"], p["serve_z_m"]), (p["serve_vx"], p["serve_vy"], p["serve_vz"]),
                (p["serve_wx"], p["serve_wy"], p["serve_wz"]))

    def reset(self, w):
        """The paddle's handle along the right gripper's fingers (its axis the fingers' axis, the blade's normal the
        closing axis), the butt BUTT_FROM_JAW_CENTRE_M before the jaws' centre; then the jaws close on it (the full
        command: 120 N) and the grasp settles."""
        w.pin("ball", self._serve()[0])
        c, R = w.jaw_frame(HAND)
        q = np.zeros(4)
        mujoco.mju_mat2Quat(q, R.ravel())
        w.put("paddle", c - BUTT_FROM_JAW_CENTRE_M * R[:, 2], quat=q)
        self.grasp = w.close_on(HAND, "paddle")

    def referee_reset(self, w, ref):
        p = self.p
        self.ball = ref.geoms(body="ball")
        self.blade = ref.geoms(names=["paddle_blade"])
        self.handle = ref.geoms(names=["paddle_handle"])
        self.paddle = self.blade | self.handle
        self.racket_hand = ref.part(f"{HAND}_hand")
        self.striker = self.blade | self.racket_hand
        self.other = (ref.robot_mask & ~self.striker) | self.handle
        self.jaws = (ref.geoms(body=f"{HAND}_hand_jaw_a"), ref.geoms(body=f"{HAND}_hand_jaw_b"))
        self.free_hand = ref.part("left_hand")
        self.table = ref.geoms(names=["table"])
        self.netg = ref.geoms(names=["net"])
        self.trackers = {"served": False, "table": Touch(ref, self.ball, self.table, gap=p["bounce_gap_s"]),
                         "server_bounce": False, "strike_t": None, "net_touch": False, "both_jaws_t": 0.0}

    def before_step(self, w):
        tr = self.trackers
        if not tr["served"] and w.t >= self.p["serve_time_s"] - 1e-9:
            tr["served"] = True
            pos, vel, spin = self._serve()
            w.launch("ball", pos, vel, angvel=spin)            # (the ball's frame is the world's at the launch)
            w.ref.event("service")

    def in_hand(self, ref) -> bool:
        return ref.touching(self.handle, self.jaws[0]) and ref.touching(self.handle, self.jaws[1])

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        if self.in_hand(ref):
            tr["both_jaws_t"] = round(ref.time, 4)
        else:
            gap = round(ref.time - tr["both_jaws_t"], 4)
            if gap > ref.metrics.get("grip_break_max_s", 0.0):
                ref.metrics["grip_break_max_s"] = gap       # (reported: the longest break of the two-jaw contact)
            if gap > p["out_of_hand_s"] + 1e-9:
                return ref.fail(LEFT_HAND, out_s=gap)
        if ref.touching(self.paddle, ref.robot_mask & ~self.racket_hand):
            return ref.fail(HELD_ELSE, parts=sorted(ref.parts_touching(self.paddle) - {f"{HAND}_hand"}))
        if ref.touching(ref.robot_mask | self.paddle, self.netg):
            return ref.fail(NET, parts=sorted(ref.parts_touching(self.netg)), racket=ref.touching(self.paddle, self.netg))
        if ref.touching(self.paddle, ref.ground):
            return ref.fail(PADDLE_FLOOR)
        if not tr["served"]:
            if ref.touching(self.ball, ref.robot_mask | self.paddle):
                ref.fail(EARLY, parts=sorted(ref.parts_touching(self.ball)), racket=ref.touching(self.ball, self.paddle))
            return
        top = p["table_height_m"]
        pts = ref.contact_points(self.free_hand, self.table)
        if len(pts) and float(np.max(pts[:, 2])) >= top - 0.002:
            return ref.fail(FREE_HAND)
        b = w.pos("ball")
        # ---- the ball and the robot
        if ref.touching(self.ball, ref.robot_mask | self.paddle):
            if not ref.has("bounce"):
                return ref.fail(OBSTRUCTION, parts=sorted(ref.parts_touching(self.ball)),
                                racket=ref.touching(self.ball, self.paddle))
            if ref.touching(self.ball, self.other):
                return ref.fail(BODY, parts=sorted(ref.parts_touching(self.ball)),
                                handle=ref.touching(self.ball, self.handle))
            if tr["strike_t"] is None:
                tr["strike_t"] = ref.time
                tr["table"].rearm()                           # a contact with the table that begins now is a new one
                ref.stage("strike", x=round(float(b[0]), 3), y=round(float(b[1]), 3), z=round(float(b[2]), 3),
                          with_hand=not ref.touching(self.ball, self.blade))
            elif ref.time - tr["strike_t"] > p["strike_window_s"]:
                return ref.fail(TWICE, after_s=round(ref.time - tr["strike_t"], 3))
        # ---- the ball and the net, the floor, the table
        if ref.touching(self.ball, self.netg):
            if not tr["net_touch"]:
                ref.event("net touch", struck=tr["strike_t"] is not None)
            tr["net_touch"] = True
            if not ref.has("bounce"):                         # a service that touches the net is a let (2.9.1.1)
                return ref.fail(BAD_SERVICE, why="it touched the net")
        if ref.touching(self.ball, ref.ground):
            return ref.fail(FLOOR, struck=tr["strike_t"] is not None)
        if tr["table"].update():
            own, on_top = b[0] < self.net_x, b[2] >= top
            where = dict(x=round(float(b[0]), 3), y=round(float(b[1]), 3))
            if tr["strike_t"] is None:
                if not tr["server_bounce"]:
                    if own or not on_top:
                        return ref.fail(BAD_SERVICE, why="it did not bounce on the server's court first", **where)
                    tr["server_bounce"] = True
                    ref.event("bounce on the server's court", **where)
                elif not own or not on_top:
                    return ref.fail(BAD_SERVICE, why="it did not bounce on your court second", **where)
                elif not ref.stage("bounce", **where):
                    return ref.fail(DOUBLE_BOUNCE, **where)
            elif own:
                return ref.fail(OWN_COURT, **where)
            elif not on_top:
                return ref.fail(SIDE, **where)
            else:
                ref.metrics["landing_x_m"], ref.metrics["landing_y_m"] = where["x"], where["y"]
                ref.metrics["net_touch"] = float(tr["net_touch"])
                if ref.stage("opponent's court", **where):
                    ref.succeed()

    def privileged(self, w):
        p = self.p
        _, va = w.free["ball"]
        g = w.m.geom("paddle_blade").id
        R = w.d.xmat[w.m.body("ball").id].reshape(3, 3)
        return {"ball": w.pos("ball").tolist(), "ball_velocity": w.vel("ball").tolist(),
                "ball_spin": (R @ w.d.qvel[va + 3:va + 6]).tolist(), "served": bool(self.trackers["served"]),
                "serve_time_s": p["serve_time_s"], "paddle": FREE_PADDLE, "blade_centre": w.d.geom_xpos[g].tolist(),
                "paddle_pos": w.pos("paddle").tolist(), "paddle_quat": w.d.xquat[w.m.body("paddle").id].tolist(),
                "paddle_in_hand_t": self.trackers["both_jaws_t"],
                "blade_normal": w.d.geom_xmat[g].reshape(3, 3)[:, 0].tolist(),
                "table": {"near_x": p["table_near_x_m"], "net_x": self.net_x, "far_x": p["table_near_x_m"] + p["table_length_m"],
                          "half_width": p["table_width_m"] / 2, "top": p["table_height_m"],
                          "net_top": p["table_height_m"] + p["net_height_m"]}}
