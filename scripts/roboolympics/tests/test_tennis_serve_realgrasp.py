"""tennis-serve-realgrasp (the ITF court, a free 0.30 kg racket held by friction in the H1-2's right Dex1-1 gripper,
the ball held by friction in the left one): the referee's test.

Two positives.
* REAL: the reference solution (oracles/tennis-serve-realgrasp/oracle.py) serves through the action rows only (LowCmd
  rows with the legs' gravity support, the grippers' closure commands): the left gripper opens while the robot stands
  at rest, the ball falls about 0.8 m, an underarm swing of the gripped racket meets it at about 4 m/s and sends it
  off at about 14 m/s over the net into the box; all physics, run twice for determinism.
* INJECTION (for the referee's details):
* real: the robot stands at rest behind the baseline, the racket held level with its strings up under the left
  gripper (two arm poses reached through `stand` rows, the racket held only by the jaws' friction), the left gripper
  opens (the closure command 0), the ball falls out of it and meets the strings 0.3 s later;
* injected: at that real string contact the ball's velocity is set to a serve's (20 m/s, 11 degrees up); its
  flight over the net and its landing in the box are real.

The let is played out with real grasping: a served ball is put on the net's top edge (a real net cord), the referee
asks for the serve again, the left gripper is brought round the spare ball in its cup, closes on it, lifts it out of
the cup by friction, brings it over the strings and lets it fall; the second serve counts; a second let fails.
Tees: a ball set on top of the spare ball, or back in the empty cup after a let, is not released (it touches
something), and a tossed ball that comes down on the spare or into the cup fails.

Negatives, each with its exact reason: holding the ball (time; the ball held in the left gripper the whole time is
no toss), opening the gripper and letting the ball drop, the racket dropped (the right gripper opened), the racket
held too lightly (it slips and turns out of the jaws), a ball tossed onto the gripper / forearm instead of the
strings and then sent over the net (no racket strike), a ball that bounces off the gripper onto the strings (not
clear of you), a ball that reaches the strings faster than the toss limit (thrown, or tossed too high), the still
racket's bunt (no speed added), releasing while walking or too soon, releasing from on the baseline / left of the
centre mark / right of the sideline, foot faults during the service motion, the ball caught again by the left
gripper (one toss), the ball carried over the net by hand, a double hit, a carry on the strings, a serve that touches
the server, a net post, the net (and drops), goes through the net, lands long, in the wrong box, a line ball in and a
ball just out, touching the spare ball before a let, the robot or the racket touching the net, a fall."""
import importlib.util
import os

import numpy as np

from rfo.testing import act, hold, make, move_robot, verdict
from rfo.tasks import tennis_serve_realgrasp as T

FAMILY = "tennis-serve-realgrasp"
R = T.BALL["radius"]
TH = T.FREE_RACKET["strings_half_thickness_m"]           # the strings' collision slab, each side of their plane
# arms (stand row order: shoulder pitch, roll, yaw, elbow pitch, roll, wrist pitch, yaw): the racket level with its
# strings up, the head's centre at (0.62, 0, 1.05); the left jaws' centre 0.35 m above it (numerical IK, scratch)
RIGHT = np.array([0.6376, -0.0257, 0.159, 0.323, 1.3233, 0.1514, 0.9561])
LEFT = np.array([-0.6945, -0.0965, -0.0524, 0.1866, -0.0153, 0.111, 0.0026])
SPARE = np.array([0.1855, 0.1754, 0.5038, 0.4025, -0.2713, -0.46, 0.4569])   # the left jaws round the spare ball in
NEAR = np.array([0.2877, -0.1054, 0.6245, 0.1938, -0.0973, -0.46, 0.3609])    # its cup, 9 cm short of it, 8 cm above
LIFT = np.array([0.2122, 0.0833, 0.6906, -0.0647, -0.1981, -0.0381, 0.3727])  # it (fingers level, pointing out-left)
V_IN, V_LONG, V_WRONG = (19.35, 3.384, 3.756), (23.381, 3.265, 4.323), (19.604, -1.522, 3.658)
V_SHORT = (13.488, 2.309, 2.959)
REST = "you were not standing at rest when you released the ball"
PLACE = "you did not stand in the server's position when you released the ball: "
OUT = "the serve landed outside the service box"
LOST = "the racket left your right hand"


class Play:
    """A scripted server on a bare World: its arms' targets and its grippers' closure commands, held between calls."""

    def __init__(self, w, A):
        self.w, self.A = w, A
        self.new()

    def new(self):
        w = self.w
        w.reset()
        self.left, self.right = w.robot.rest[13:20].copy(), w.robot.rest[20:27].copy()
        self.gl, self.gr = 1.0, 1.0
        return self

    def row(self):
        q = self.w.robot.rest[12:27].copy()
        q[1:8], q[8:15] = self.left, self.right
        return np.r_[q, self.gl, self.gr]

    def keep(self, seconds=None, until=None, gl=None, gr=None):
        w = self.w
        self.gl = self.gl if gl is None else gl
        self.gr = self.gr if gr is None else gr
        n = None if seconds is None else int(round(seconds / w.CONTROL_DT))
        while not w.done and (n is None or n > 0) and not (until is not None and until()):
            act(w, self.A, "stand", self.row())
            n = None if n is None else n - 1

    def move(self, left=None, right=None, seconds=1.5):
        l0, r0 = self.left.copy(), self.right.copy()
        n = int(round(seconds / self.w.CONTROL_DT))
        for i in range(1, n + 1):
            if left is not None:
                self.left = l0 + (np.asarray(left) - l0) * i / n
            if right is not None:
                self.right = r0 + (np.asarray(right) - r0) * i / n
            self.keep(self.w.CONTROL_DT)

    def ready(self):
        """Racket level under the ball, at rest for 0.7 s."""
        self.move(LEFT, RIGHT)
        self.keep(0.7)
        return self

    def strike(self):
        """Real: the left gripper opens, the ball falls onto the strings."""
        w = self.w
        t0 = w.ref.time
        self.keep(until=lambda: w.task.trackers["phase"] == "served", gl=0.0)
        assert not w.done and w.ref.time - t0 > 0.2, (verdict(w), w.ref.time - t0)       # 0.3 m of free fall
        return self

    def shoot(self, v, ball="ball"):
        """The ball leaves the strings with the velocity v (set 3 cm clear of them, on the side it came from)."""
        w = self.w
        w.put(ball, w.pos(ball) + np.array([0.0, 0.0, 0.03]), vel=v)

    def serve(self, v, ball="ball"):
        self.ready().strike()
        self.shoot(v, ball)
        self.keep()
        return verdict(self.w)


def move(w, **kw):
    """move_robot with what the grippers hold: the racket always (w.held, read from contacts, can flicker for a few
    ms), the ball if it is held."""
    p0 = w.d.qpos[w.robot.fq:w.robot.fq + 3].copy()
    move_robot(w, **kw)
    dp = w.d.qpos[w.robot.fq:w.robot.fq + 3] - p0
    for name in {"racket"} | {n for n in w.held.values() if n}:
        qa, _ = w.free[name]
        w.d.qpos[qa:qa + 3] += dp


def oracle():
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("oracle", os.path.join(here, "..", "oracles", FAMILY, "oracle.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Shim:
    """What the reference solution uses of rcb_rfo.Session, on a test world."""

    def __init__(self, w, A):
        self.world, self.A = w, A

    @property
    def done(self):
        return self.world.done

    def step(self, typ, row):
        act(self.world, self.A, typ, row)
        return self.world.done


def strings(w):
    return w.d.geom_xpos[w.m.geom("racket_strings").id].copy()


def main():
    w, A = make(FAMILY)
    task, p = w.task, w.task.p
    nx, cy = p["net_x_m"], p["centre_y_m"]
    P = Play(w, A)
    assert (w.robot.name, task.robot) == ("unitree_h1", "unitree_h1") and task.rulebook and len(task.deviations) >= 5
    for text in (task.sentence, task.rules, task.venue, task.difficulty, *task.deviations):
        text.format(**p, time_limit_s=task.time_limit_s)                    # every number quoted is a parameter
    x0, x1, y0, y1 = task.box()
    assert abs(x1 - x0 - 6.40) < 1e-9 and abs(y1 - cy - 4.115) < 1e-9 and abs(y0 - (cy - 0.025)) < 1e-9
    rb = w.m.body("racket").id                                              # the racket: a free 0.30 kg body, balance
    assert abs(w.m.body_mass[rb] - 0.30) < 1e-9 and abs(w.m.body_ipos[rb][2] - 0.33) < 1e-9     # 0.33 m from the butt
    assert w.real_hands == {"left": "dex1", "right": "dex1"} and not w.welds
    assert w.held == {"left": "ball", "right": "racket"} and task.trackers["held"] == 0.0, w.held
    assert nx - T.HALF_LENGTH > 0.3 and cy - 0.025 > 0.3                    # behind the baseline, right of the mark

    # ---- nop, and the cheapest things
    hold(w, A)                                                              # both grippers stay closed: the ball
    v = verdict(w)                                                          # held the whole time is no toss
    assert v["failed"] == "time" and v["stages"] == [] and w.held == {"left": "ball", "right": "racket"}, (v, w.held)
    assert np.linalg.norm(w.pos("ball2") - [p["spare_x_m"], p["spare_y_m"], p["spare_z_m"]]) < 0.005
    P.new().keep(0.7); P.keep(gl=0.0)                                       # the left gripper opens: dropped
    assert verdict(w)["failed"] == "the tossed ball reached the ground unstruck" and verdict(w)["stages"] == ["toss"], verdict(w)
    P.new().keep(0.3); P.keep(gr=0.0)                                       # the right gripper opens: the racket falls
    v = verdict(w)
    assert v["failed"] == LOST and w.t < 0.5 and w.hands.opening("right") > 0.034, (v, w.t)
    P.new().keep(1.0, gr=0.62)                                              # jaws closed to 34 mm: no clamp, it slips out
    assert verdict(w)["failed"] == LOST and w.t < 0.5, verdict(w)
    P.new().ready().strike(); P.keep()                                      # the still racket: a bunt (all real)
    v = verdict(w)
    assert v["failed"] == "the racket did not speed the ball up" and v["stages"] == ["toss", "strike"], v

    # ---- the real serve: the reference solution (oracles/tennis-serve-realgrasp), all physics, through the rows
    orc = oracle()
    if orc.TECHNIQUE is not None:
        w.reset(); orc.solve(Shim(w, A))
        v = verdict(w)
        assert v["success"] and v["stages"] == ["toss", "strike", "over the net", "in"], v
        assert x0 < v["metrics"]["landing_x_m"] < x1 and y0 < v["metrics"]["landing_y_m"] < y1, v
        e = next(e for e in w.ref.events if e.get("stage") == "strike")
        assert e["speed_before_m_s"] <= p["toss_max_speed_m_s"] and v["metrics"]["strike_speed_m_s"] > 12.0, (e, v)
        assert w.ref.time - task.trackers["held"] <= p["racket_gap_s"]       # the racket still held (both jaws)
        assert [x["ev"] for x in w.ref.events].count("let") == 0
        sha = w.state_sha()
        w.reset(); orc.solve(Shim(w, A))
        assert w.state_sha() == sha                                         # deterministic

    # ---- the positive (injection, see the docstring)
    v = P.new().serve(V_IN)
    assert v["success"] and v["stages"] == ["toss", "strike", "over the net", "in"], v
    assert x0 < v["metrics"]["landing_x_m"] < x1 and y0 < v["metrics"]["landing_y_m"] < y1 and w.t < 5.0, (v, w.t)
    e = next(e for e in w.ref.events if e.get("stage") == "strike")
    assert e["strings"] and e["ball_height_m"] > 0.9 and 1.5 < e["speed_before_m_s"] < 3.5, e
    assert w.ref.time - task.trackers["held"] <= p["racket_gap_s"]
    sha = w.state_sha()
    P.new().serve(V_IN)
    assert w.state_sha() == sha                                             # the same run again: the same state

    # ---- Rule 16: at rest, in the server's position
    P.new()
    for _ in range(60):                                                     # walking
        act(w, A, "walk", np.r_[0.0, -0.3, 0.0, P.row()])
    for _ in range(30):
        act(w, A, "walk", np.r_[0.0, -0.3, 0.0, P.row()[:15], 0.0, 1.0])
    assert verdict(w)["failed"] == REST, verdict(w)
    P.new().keep(0.2); P.keep(gl=0.0)                                       # still, but not for long enough
    assert verdict(w)["failed"] == REST, verdict(w)
    for (x, y), why in (((0.45, 0.0), "a foot touched the baseline or the court"),
                        ((0.0, cy), "a foot touched the centre mark's extension"),
                        ((0.0, cy - T.HALF_WIDTH), "a foot touched the ground outside the sideline's extension")):
        P.new(); move(w, x=x, y=y); P.keep(0.8); P.keep(gl=0.0)
        assert verdict(w)["failed"] == PLACE + why, (x, y, verdict(w))
    P.new(); move(w, y=cy - 0.30); P.keep(0.8)    # close to the mark, but right of it:
    P.keep(until=lambda: w.ref.has("toss"), gl=0.0)                                 # legal
    assert w.ref.stages == ["toss"] and not w.done, verdict(w)

    # ---- Rule 18: the feet between the release and the strike (the ball is kept in the air by hand meanwhile)
    for (x, y), why in (((0.45, 0.0), "foot fault: a foot touched the baseline or the court"),
                        ((0.0, -0.40), "foot fault: you changed position by walking")):
        P.new().keep(0.7); P.keep(until=lambda: w.ref.has("toss"), gl=0.0)
        w.put("ball", (0.5, 0.2, 2.5), vel=(0.0, 0.0, 3.0)); P.keep(0.05)
        assert not w.done, verdict(w)
        move(w, x=x, y=y); P.keep(0.3)
        assert verdict(w)["failed"] == why, (x, y, verdict(w))
    P.new().ready().strike(); P.shoot(V_IN); P.keep(0.05)                   # after the strike the feet are free
    move(w, x=0.45); P.keep()
    assert verdict(w)["success"], verdict(w)

    # ---- the toss and the strike
    P.new().ready(); P.keep(until=lambda: w.ref.has("toss"), gl=0.0); P.keep(0.02)   # thrown down at the strings
    w.put("ball", strings(w) + [0.0, 0.0, TH + R + 0.05], vel=(0.0, 0.0, -6.0)); P.keep()   # (or tossed too high)
    v = verdict(w)
    assert v["failed"] == "the ball was thrown, not tossed" and w.ref.events[-1]["speed_before_m_s"] > 5.0, v
    P.new().ready(); P.keep(0.03, gl=0.0)                                   # struck out of the hand: the gripper opens,
    w.put("ball", strings(w) + [0.0, 0.0, TH + R + 0.01], vel=(0.0, 0.0, -2.0)); P.keep()   # the strings meet the
    assert verdict(w)["failed"] == "the racket struck the ball before it was clear of you", verdict(w)  # ball 40 ms later
    P.new().ready(); P.keep(until=lambda: w.ref.has("toss"), gl=0.0); P.keep(0.02)   # struck by the gripper and
    c, _ = w.jaw_frame("right")                                                       # sent off: no racket strike
    w.put("ball", c + [0.05, 0.0, 0.034 + R + 0.002], vel=(-1.0, 0.0, -1.0)); P.keep(0.01)
    w.put("ball", w.pos("ball") + [0.0, 0.0, 0.05], vel=V_IN); P.keep()
    assert verdict(w)["failed"] == "the ball passed the net without a racket strike", verdict(w)
    P.new().ready(); P.keep(until=lambda: w.ref.has("toss"), gl=0.0)       # carried over the net by hand
    w.put("ball", (nx - 0.3, cy + 1.0, 1.5), vel=(1.0, 0.0, 0.0)); P.keep()
    assert verdict(w)["failed"] == "the ball passed the net without a racket strike", verdict(w)
    P.new().ready(); P.keep(until=lambda: w.ref.has("toss"), gl=0.0)       # caught again by the left gripper (put
    c, _ = w.jaw_frame("left")                                              # back between its jaws, which close)
    w.put("ball", c); P.keep(0.2, gl=1.0)
    assert verdict(w)["failed"] == "the tossed ball was caught again (one toss per serve)", verdict(w)
    P.new().ready().strike(); P.shoot((0.0, 0.0, 4.0)); P.keep()            # real: popped up, it comes down on the strings again
    assert verdict(w)["failed"] == "the racket hit the ball twice", verdict(w)
    P.new().ready().strike()                                                # held on the strings: a carry
    while not w.done:
        w.put("ball", strings(w) + [0.0, 0.0, TH + R - 0.002])
        P.keep(w.CONTROL_DT)
    assert verdict(w)["failed"] == "the racket carried the ball", verdict(w)
    P.new().ready().strike(); w.put("ball", (0.6, 0.0, 1.3), vel=(-8.0, 0.0, 0.0)); P.keep()      # back at the chest
    assert verdict(w)["failed"] == "the served ball touched you", verdict(w)

    # ---- where the serve goes
    for vel, why in ((V_LONG, OUT), (V_WRONG, OUT), (V_SHORT, "the serve landed on your own side")):
        v = P.new().serve(vel)
        assert v["failed"] == why and "in" not in v["stages"], (vel, v)
    P.new().ready().strike()                                                # into the net: it stops there and drops
    w.put("ball", (nx - 1.0, cy + 2.0, 0.5), vel=(25.0, 0.0, 0.0)); P.keep()
    assert verdict(w)["failed"] == "the serve landed on your own side" and w.pos("ball")[0] < nx, verdict(w)
    P.new().ready().strike()                                                # onto a net post
    w.put("ball", (nx - 1.0, cy + T.POST_Y + T.POST_R + T.NET_HALF_THICK, 0.7), vel=(20.0, 0.0, 0.0)); P.keep()
    assert verdict(w)["failed"] == "the serve touched a net post", verdict(w)
    P.new().ready().strike()                                                # (a teleport through the net: the guard)
    w.put("ball", (nx - 0.02, cy + 1.0, 0.5)); P.keep(0.01)
    w.put("ball", (nx + 0.10, cy + 1.0, 0.5)); P.keep()
    assert verdict(w)["failed"] == "the serve did not pass over the net", verdict(w)
    for (bx, by), good in (((x1 - 0.02, y0 + 0.01), True), ((x1 + 0.02, cy + 1.0), False), ((x1 - 1.0, y0 - 0.03), False),
                           ((x1 - 1.0, y1 - 0.01), True), ((x1 - 1.0, y1 + 0.02), False)):
        P.new().ready().strike()                                            # Rule 12: on a line of the box is in; the
        w.put("ball", (nx + 2.0, cy + 2.0, 3.0)); P.keep(0.01)              # point under the centre decides
        w.put("ball", (bx, by, 0.3), vel=(0.0, 0.0, -5.0)); P.keep()
        v = verdict(w)
        assert v["success"] if good else v["failed"] == OUT, (bx, by, v)

    # ---- Rule 22: the let, replayed once with the spare ball, taken from its cup by the left gripper (real)
    def net_cord(ball):
        w.put(ball, (nx - 0.3, cy + 2.0, T.net_top(2.0) + 0.02), vel=(14.0, 0.0, 0.0))

    def take_spare():
        P.keep(0.0, gl=0.0); P.move(left=NEAR, seconds=0.8); P.keep(0.3)
        P.move(left=SPARE, seconds=0.6); P.keep(0.4, gl=1.0)
        P.move(left=LIFT, seconds=0.4); P.move(left=LEFT, seconds=1.0); P.keep(0.7)

    P.new().ready()                                                         # before a let the spare is not to be touched
    P.move(left=NEAR, seconds=0.8); P.move(left=SPARE, seconds=0.6); P.keep(0.3)
    assert verdict(w)["failed"] == "you touched the spare ball before a let", verdict(w)
    P.new().ready().strike(); net_cord("ball")
    P.keep(until=lambda: task.trackers["phase"] == "await")
    assert not w.done and w.ref.stages == ["toss", "strike", "over the net"], verdict(w)
    assert [e["ev"] for e in w.ref.events].count("let") == 1 and task.trackers["ball"] == "ball2"
    assert x0 < w.pos("ball")[0] < x1, w.pos("ball")                        # (the let's ball did land in the box)
    take_spare()
    assert w.held["left"] == "ball2" and task.trackers["phase"] == "hold", (w.held, task.trackers["phase"])
    assert np.hypot(*(w.pos("ball2")[:2] - strings(w)[:2])) < 0.09, (w.pos("ball2"), strings(w))   # over the strings
    P.strike(); P.shoot(V_IN, "ball2"); P.keep()
    v = verdict(w)
    assert v["success"] and v["metrics"]["lets"] == 1 and x0 < v["metrics"]["landing_x_m"] < x1, v
    P.new().ready().strike(); net_cord("ball")                              # the second serve a net cord too
    P.keep(until=lambda: task.trackers["phase"] == "await")
    take_spare(); P.strike(); net_cord("ball2"); P.keep()
    assert verdict(w)["failed"] == "a second let", verdict(w)

    # ---- tees: a ball resting on something is not released, and a tossed ball may touch nothing but you and the racket
    TEE = "the tossed ball touched something other than you or the racket"
    top = np.array([p["spare_x_m"], p["spare_y_m"], p["spare_z_m"] + 2 * R + 0.001])
    cup = np.array([p["spare_x_m"], p["spare_y_m"], p["spare_z_m"] + 0.0007])   # (where the ball rests in it)
    P.new().keep(0.7); P.keep(0.02, gl=0.0)                                 # the first serve's ball set on top of the
    w.put("ball", top); P.keep(0.12)                                        # spare ball: not released while it rests
    assert not w.ref.has("toss") and not w.done and np.linalg.norm(w.pos("ball") - top) < 0.01, (verdict(w), w.pos("ball"))
    P.keep()
    assert verdict(w)["failed"] in (TEE, "the tossed ball reached the ground unstruck"), verdict(w)
    P.new().ready(); P.keep(until=lambda: w.ref.has("toss"), gl=0.0)       # a tossed ball that comes down on the spare
    w.put("ball", top + [0.0, 0.0, 0.01], vel=(0.0, 0.0, -1.0)); P.keep()
    assert verdict(w)["failed"] == TEE, verdict(w)
    P.new().ready().strike(); net_cord("ball")                              # after a let: the spare taken out of its
    P.keep(until=lambda: task.trackers["phase"] == "await")                 # cup, the gripper opens and the ball is set
    take_spare(); P.keep(0.01, gl=0.0)                                      # back in the empty cup: not released
    w.put("ball2", cup); P.keep(0.3)
    assert task.trackers["phase"] == "hold" and not w.done and np.linalg.norm(w.pos("ball2") - cup) < 0.005, \
        (verdict(w), task.trackers["phase"], w.pos("ball2"))
    P.new().ready().strike(); net_cord("ball")                              # ... and a replayed toss that drops into
    P.keep(until=lambda: task.trackers["phase"] == "await")                 # the empty cup
    take_spare(); P.keep(until=lambda: task.trackers["phase"] == "toss", gl=0.0)
    w.put("ball2", cup + [0.0, 0.0, 0.02]); P.keep()
    assert verdict(w)["failed"] == TEE, verdict(w)

    # ---- the robot
    P.new().keep(0.2); move(w, x=nx - 0.10, y=cy); P.keep(0.5)    # at the net
    assert verdict(w)["failed"] == "you or the racket touched the net", verdict(w)
    P.new().keep(0.2); move(w, z=0.30); P.keep(0.5)  # on the ground
    assert verdict(w)["failed"] in ("fell", LOST), verdict(w)
    print(f"PASS {FAMILY}")


if __name__ == "__main__":
    main()
