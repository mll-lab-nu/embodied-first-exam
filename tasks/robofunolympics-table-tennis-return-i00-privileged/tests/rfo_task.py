"""Table tennis: return a legal service (ITTF Laws 2.5-2.7, 2.10) on the official table, with the paddle on the right
hand.

The ball, the table and the net are Google DeepMind's system-identified model as RoboOlympics uses it
(roboolympics/sports/tabletennis/sim/scene/tt_scene.xml, from competitive_robot_table_tennis, Apache-2.0): the ball's
fluid coefficients and thin-shell inertia, the identified ball-table contact pair, a rigid net, and the simulator
options the pair was identified and the serve library was made with (1 ms, implicitfast, elliptic friction cones with
impratio 10: with MuJoCo's default pyramidal cones the same service bounces 13 cm further on the receiver's court).
The ball-paddle pair is RoboOlympics' (hand-picked, not identified). The service is one entry of RoboOlympics' serve
library (sim/serve_library.json: 279 services a Franka on a rail made under the real robot's limits, each judged legal
by Laws 2.6.1-2.6.4), stored as the ball's state at the server's strike."""
import xml.etree.ElementTree as ET

import numpy as np

from rfo.referee import Touch
from rfo.scene import OFFICIAL
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


# The paddle on the right wrist mount (+z along the forearm, away from the wrist; the blade's two faces look along the
# mount's +-x): a handle through the fist and RoboOlympics' blade, a 15 x 15 x 1.5 cm box; 0.05 + 0.09 = 0.14 kg.
PADDLE = dict(blade_m=0.15, thickness_m=0.015, blade_centre_m=0.175, mass_kg=0.14)
PADDLE_XML = (
    '<geom name="paddle_handle" type="capsule" fromto="0 0 0 0 0 0.10" size="0.014" mass="0.05" '
    'rgba="0.55 0.38 0.2 1" contype="4" conaffinity="0"/>'
    '<geom name="paddle_blade" type="box" pos="0 0 0.175" size="0.0075 0.075 0.075" mass="0.09" '
    'rgba="0.8 0.1 0.1 1" contype="4" conaffinity="0"/>')
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
BODY = "the ball touched something of yours other than the racket's blade or the racket hand"
TWICE = "the ball was struck twice"
DOUBLE_BOUNCE = "the ball bounced twice on your court"
OWN_COURT = "the return touched your own court"
SIDE = "the return hit the side of the table"
FLOOR = "the ball touched the floor"
BAD_SERVICE = "the service was not a legal service"


def tt_physics(sc, ball: str = "ball"):
    """DeepMind's table-tennis physics in this scene: the simulator options, the ball's thin-shell inertia, and the
    explicit contact pairs of the ball with the geoms of PAIRS that exist."""
    opt = sc.root.find("option")
    opt.set("cone", "elliptic")
    opt.set("impratio", "10")
    body = next(b for b in sc.wb.iter("body") if b.get("name") == ball)
    i = 2.0 / 3.0 * BALL["mass"] * BALL["radius"] ** 2          # 7.2e-7 kg m^2, as in DeepMind's model
    ET.SubElement(body, "inertial", pos="0 0 0", mass=repr(BALL["mass"]), diaginertia=f"{i:.6g} {i:.6g} {i:.6g}")
    names = {g.get("name") for g in sc.root.iter("geom")} | {
        n for frag in sc.hand_tools.values() for n in ("paddle_blade",) if n in frag}
    for geom, kw in PAIRS:
        if geom in names:
            ET.SubElement(sc.root.find("contact"), "pair", name=f"{ball}_{geom}", geom1=ball, geom2=geom, **kw)


class Task(TaskBase):
    name = "table-tennis-return"
    title = "Table tennis: return a service"
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
        "2.4 (the racket): the blade is a rigid 15 cm square, 1.5 cm thick, 0.14 kg with its handle (legal: the Laws "
        "set no size, shape or weight); its covering is one contact law on both faces (RoboOlympics' ball-paddle pair, "
        "hand-picked, not identified), and it is fixed to the right hand, because the robot's fist cannot hold a handle",
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
        strike_window_s=0.05, bounce_gap_s=0.02, fall_height_m=0.35)

    sentence = ("Return the service: after the table tennis ball has bounced once on your court, strike it with the "
                "paddle on your right hand so that it touches the opponent's court.")
    rules = ("The table is the official one: {table_length_m} m long, {table_width_m} m wide, its playing surface "
             "{table_height_m} m above the floor, with a net {net_height_m} m high across its middle that reaches "
             "{net_overhang_m} m beyond each side line. Your court is the half of the playing surface on your side of "
             "the net, the opponent's court the other half; the top edges belong to the playing surface, the sides of "
             "the table top do not (a ball that touches the table with its centre below the level of the playing "
             "surface has hit the side). The ball is the official one (40 mm, 2.7 g) and flies in air: drag and the "
             "lift of its spin act on it. A racket (a rigid square blade 0.15 m wide, 0.015 m thick, 0.14 kg with its "
             "handle) is fixed to your right hand, the racket hand; your left hand is the free hand. The service is "
             "struck {serve_time_s} s after the start: a legal service, so the ball bounces first on the server's "
             "court, passes the net and bounces on your court. Then you must make a good return (Law 2.7): strike the "
             "ball, after that one bounce on your court, with the blade or with the racket hand below the wrist, so "
             "that it touches the opponent's court, directly or after touching the net; it may pass over or around the "
             "net. You succeed at the moment the ball touches the opponent's court after your strike. All contacts of "
             "the blade or the racket hand with the ball within {strike_window_s} s of the first are one strike. You "
             "fail if you touch the ball before the service, or before it has bounced on your court (obstruction); if "
             "the ball bounces a second time on your court before you strike it (ball contacts with the table less "
             "than {bounce_gap_s} s apart are one bounce); if anything of yours other than the blade or the racket "
             "hand touches the ball (the racket's handle, an arm, the body); if the blade or the racket hand touches "
             "the ball again later than {strike_window_s} s after the first contact (struck twice, or carried); if "
             "after your strike the ball touches your own court, the side of the table or the floor before the "
             "opponent's court; if the ball touches the floor at any time; if any part of you or the racket touches "
             "the net; if your free hand touches the playing surface while the ball is in play (from the service on); "
             "if you fall; or after {time_limit_s} s. Anything else of you, the racket included, may touch the table. "
             "A fall is your pelvis lower than {fall_height_m} m above the floor, or any part of you other than your "
             "feet touching the floor (the racket on the floor is a fall).")
    venue = ("You stand at your end of the table facing it (+x), on its centre line, your pelvis {table_near_x_m} m "
             "behind your end line; the net is 1.37 m beyond the end line and the server's end line 2.74 m. The ball "
             "waits at rest where the server strikes it: {serve_x_m} m ahead of your pelvis, {serve_y_m} m to your "
             "left (negative: to your right) and {serve_z_m} m above the floor, just behind the server's end line. The "
             "service is one of a library of legal robot services: they leave the server's racket at 2.2 to 4.5 m/s "
             "with up to 34 rad/s of spin and bounce on your court between 0.2 and 0.8 s after the strike; short "
             "services bounce a second time on your court if you do not strike them. The paddle hangs from your right "
             "hand, its handle in the fist and the blade beyond it, the blade's centre 0.175 m from the wrist.")
    difficulty = ("The served ball is over your court for a few tenths of a second, low above a table that is as high "
                  "as your hips, and may have to be met far inside the end line: the blade, a rigid extension of a "
                  "0.5 m arm, has to be there at the right instant and angle while the body leans over the table "
                  "without touching the net. The return must clear a 15 cm net and still come down on a court 1.37 m "
                  "long, off a ball that carries spin.")

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
        sc.hand_tools["right"] = PADDLE_XML
        tt_physics(sc)
        sc.camera("venue", (x0 - 1.3, -2.6, 1.75), (x0 + 1.1, 0.0, 0.75), fovy=50)

    def _serve(self):
        p = self.p
        return ((p["serve_x_m"], p["serve_y_m"], p["serve_z_m"]), (p["serve_vx"], p["serve_vy"], p["serve_vz"]),
                (p["serve_wx"], p["serve_wy"], p["serve_wz"]))

    def reset(self, w):
        w.pin("ball", self._serve()[0])

    def referee_reset(self, w, ref):
        p = self.p
        self.ball = ref.geoms(body="ball")
        self.blade = ref.geoms(names=["paddle_blade"])
        self.striker = self.blade | ref.part("right_hand")
        self.other = ref.robot_mask & ~self.striker
        self.free_hand = ref.part("left_hand")
        self.table = ref.geoms(names=["table"])
        self.netg = ref.geoms(names=["net"])
        self.trackers = {"served": False, "table": Touch(ref, self.ball, self.table, gap=p["bounce_gap_s"]),
                         "server_bounce": False, "strike_t": None, "net_touch": False}

    def before_step(self, w):
        tr = self.trackers
        if not tr["served"] and w.t >= self.p["serve_time_s"] - 1e-9:
            tr["served"] = True
            pos, vel, spin = self._serve()
            w.launch("ball", pos, vel, angvel=spin)            # (the ball's frame is the world's at the launch)
            w.ref.event("service")

    def substep(self, w, ref):
        p, tr = self.p, self.trackers
        if ref.touching(ref.robot_mask, self.netg):
            return ref.fail(NET, parts=sorted(ref.parts_touching(self.netg)))
        if not tr["served"]:
            if ref.touching(self.ball, ref.robot_mask):
                ref.fail(EARLY, parts=sorted(ref.parts_touching(self.ball)))
            return
        top = p["table_height_m"]
        pts = ref.contact_points(self.free_hand, self.table)
        if len(pts) and float(np.max(pts[:, 2])) >= top - 0.002:
            return ref.fail(FREE_HAND)
        b = w.pos("ball")
        # ---- the ball and the robot
        if ref.touching(self.ball, ref.robot_mask):
            if not ref.has("bounce"):
                return ref.fail(OBSTRUCTION, parts=sorted(ref.parts_touching(self.ball)))
            if ref.touching(self.ball, self.other):
                return ref.fail(BODY, parts=sorted(ref.parts_touching(self.ball)),
                                handle=ref.touching(self.ball, ref.geoms(names=["paddle_handle"])))
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
                "serve_time_s": p["serve_time_s"], "paddle": PADDLE, "blade_centre": w.d.geom_xpos[g].tolist(),
                "blade_normal": w.d.geom_xmat[g].reshape(3, 3)[:, 0].tolist(),
                "table": {"near_x": p["table_near_x_m"], "net_x": self.net_x, "far_x": p["table_near_x_m"] + p["table_length_m"],
                          "half_width": p["table_width_m"] / 2, "top": p["table_height_m"],
                          "net_top": p["table_height_m"] + p["net_height_m"]}}
