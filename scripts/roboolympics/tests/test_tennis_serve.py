"""tennis-serve (v2, the ITF court, the 0.30 kg racket on the H1-2): the referee's test. No real solution exists yet
(measured: a torso-driven swing that leaves the robot standing moves the racket head at 9.6 m/s and sends a still
ball off at 13.8 m/s, and the slowest legal serve needs 12 m/s at 26 to 44 degrees; but no controller yet tosses the
ball into that swing and aims it), so the positive is an INJECTION:

* real: the robot stands at rest behind the baseline with the racket held level under its left hand (two arm poses
  reached through `stand` rows), lets go of the ball, the ball falls 0.3 m and meets the strings 0.23 s later;
* injected: at that real string contact the ball's velocity is set to a serve's (20 m/s, 11 degrees up; the still
  racket alone sends the ball off at 1 m/s: the third test); its flight over the net and its landing in the box are
  real.

The let is played out: a served ball is put on the net's top edge (a real net cord: it touches the tape, goes over
and lands in the box), the referee asks for the serve again, the left hand really takes the spare ball from its cup
(the grip), and the second serve counts; a second let fails.

Negatives, each with its exact reason: holding the ball (time), dropping it, the still racket's bunt and a ball
thrown past the racket that only touches it (neither speeds the ball up), releasing while
walking, releasing from on the baseline / left of the centre mark / right of the sideline, a foot fault during the
service motion (onto the baseline; a change of position), a strike out of the hand, a ball thrown over the net by
hand, a double hit (real: the ball left to bounce on the racket), a carry, a serve that touches the server, a net
post, the net (and drops), goes through the net (a teleport: the referee's guard), lands long, in the wrong box,
a line ball in and a ball just out, the robot touching the net, a fall; the ball cannot be gripped again after the
toss, and the spare cannot be taken before a let."""
import numpy as np

from rfo.testing import act, hold, make, move_robot, verdict
from rfo.tasks import tennis_serve as T

FAMILY = "tennis-serve"
R = T.BALL["radius"]
# the left hand holds the ball out in front, the right arm holds the racket level 0.3 m under it (strings down / up)
LEFT = np.array([-0.47, 0.185, 0.233, -0.041, -0.027, -0.022, 0.163])
RIGHT = np.array([-0.027, -0.62, 0.325, -0.332, -0.66, -0.47, 0.382])
SPARE = np.array([-0.013, 0.183, 1.266, 0.292, 0.548, -0.222, -0.213])     # the left palm on the spare ball in its cup
NEAR = np.array([-0.013, 0.60, 1.266, 0.292, 0.548, -0.222, -0.213])       # ... and beside it, on the way there
V_IN, V_LONG, V_WRONG = (19.35, 3.384, 3.756), (23.381, 3.265, 4.323), (19.604, -1.522, 3.658)
V_SHORT = (13.488, 2.309, 2.959)
REST = "you were not standing at rest when you released the ball"
PLACE = "you did not stand in the server's position when you released the ball: "
OUT = "the serve landed outside the service box"


class Play:
    """A scripted server on a bare World: its arms' targets and its left grip, held between calls."""

    def __init__(self, w, A):
        self.w, self.A = w, A
        self.new()

    def new(self):
        w = self.w
        w.reset()
        self.left, self.right, self.grip = w.robot.rest[13:20].copy(), w.robot.rest[20:27].copy(), 1.0
        return self

    def row(self):
        q = self.w.robot.rest[12:27].copy()
        q[1:8], q[8:15] = self.left, self.right
        return np.r_[q, self.grip, 0.0]

    def keep(self, seconds=None, until=None, grip=None):
        w = self.w
        self.grip = self.grip if grip is None else grip
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
        """Racket under the ball, at rest for 0.7 s."""
        self.move(LEFT, RIGHT)
        self.keep(0.7)
        return self

    def toss(self):
        self.keep(self.w.CONTROL_DT, grip=0.0)

    def strike(self):
        """Real: the release, the fall onto the strings."""
        w = self.w
        self.toss()
        t0 = w.ref.time
        self.keep(until=lambda: w.task.trackers["phase"] == "served")
        assert not w.done and w.ref.time - t0 > 0.15, (verdict(w), w.ref.time - t0)       # 0.3 m of free fall
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
    assert abs(w.m.body_mass[w.robot.mount["right"]] - 0.30) < 1e-6        # the racket: 0.30 kg on the hand
    assert nx - T.HALF_LENGTH > 0.3 and cy - 0.025 > 0.3                    # the server starts behind the baseline, right of the mark

    # ---- nop, and the cheapest things
    hold(w, A)                                                              # the ball stays in the hand
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)
    assert np.linalg.norm(w.pos("ball2") - [p["spare_x_m"], p["spare_y_m"], p["spare_z_m"]]) < 0.005     # the spare rests in its cup
    P.new().keep(0.7); P.keep(grip=0.0)                                     # dropped
    assert verdict(w)["failed"] == "the tossed ball reached the ground unstruck" and verdict(w)["stages"] == ["toss"], verdict(w)
    P.new().ready().strike(); P.keep()                                      # the still racket: a bunt (all real):
    v = verdict(w)                                                          # the ball leaves slower than it came
    assert v["failed"] == "the racket did not speed the ball up" and v["stages"] == ["toss", "strike"], v
    assert 0.3 < v["metrics"]["strike_speed_m_s"] < 2.4, v
    P.new().ready(); P.toss()                                               # thrown at 20 m/s by the hand past the
    P.keep(0.12)                                                            # racket, which only touches it on the
    w.put("ball", w.d.geom_xpos[w.m.geom("racket_head").id] + [-0.3, 0.0, 0.0125 + R - 0.004], vel=V_IN)   # way: no serve
    P.keep()
    v = verdict(w)
    assert v["failed"] == "the ball was thrown, not tossed" and w.ref.events[-1]["speed_before_m_s"] > 12.0, v
    w2, A2 = make(FAMILY, toss_max_speed_m_s=99.0)                          # (without the toss's speed limit the
    P2 = Play(w2, A2); P2.new().ready(); P2.toss(); P2.keep(0.12)           # second rule says no: no speed added)
    w2.put("ball", w2.d.geom_xpos[w2.m.geom("racket_head").id] + [-0.3, 0.0, 0.0125 + R - 0.004], vel=V_IN)
    P2.keep()
    v = verdict(w2)
    assert v["failed"] == "the racket did not speed the ball up" and v["metrics"]["strike_speed_m_s"] > 12.0, v
    w2.close()

    # ---- the positive (injection, see the docstring)
    v = P.new().serve(V_IN)
    assert v["success"] and v["stages"] == ["toss", "strike", "over the net", "in"], v
    assert x0 < v["metrics"]["landing_x_m"] < x1 and y0 < v["metrics"]["landing_y_m"] < y1 and w.t < 5.0, (v, w.t)
    e = next(e for e in w.ref.events if e.get("stage") == "strike")
    assert e["ball_height_m"] > 0.9, e
    sha = w.state_sha()
    P.new().serve(V_IN)
    assert w.state_sha() == sha                                             # the same run again: the same state

    # ---- Rule 16: at rest, in the server's position
    P.new()
    for _ in range(60):                                                     # walking
        act(w, A, "walk", np.r_[0.0, -0.3, 0.0, P.row()[:15], 1.0, 0.0])
    act(w, A, "walk", np.r_[0.0, -0.3, 0.0, P.row()[:15], 0.0, 0.0])
    assert verdict(w)["failed"] == REST, verdict(w)
    P.new().keep(0.3); P.toss()                                             # still, but not for long enough
    assert verdict(w)["failed"] == REST, verdict(w)
    for (x, y), why in (((0.45, 0.0), "a foot touched the baseline or the court"),
                        ((0.0, cy), "a foot touched the centre mark's extension"),
                        ((0.0, cy - T.HALF_WIDTH), "a foot touched the ground outside the sideline's extension")):
        P.new(); move_robot(w, x=x, y=y, held=True); P.keep(0.8); P.toss()
        assert verdict(w)["failed"] == PLACE + why, (x, y, verdict(w))
    P.new(); move_robot(w, y=cy - 0.30, held=True); P.keep(0.8); P.toss()              # close to the mark, but right of it: legal
    assert w.ref.stages == ["toss"] and not w.done, verdict(w)

    # ---- Rule 18: the feet between the release and the strike (the ball is kept in the air by hand meanwhile)
    for (x, y), why in (((0.45, 0.0), "foot fault: a foot touched the baseline or the court"),
                        ((0.0, -0.40), "foot fault: you changed position by walking")):
        P.new().keep(0.7); P.toss()
        w.put("ball", (0.5, 0.2, 2.5), vel=(0.0, 0.0, 3.0)); P.keep(0.05)
        assert not w.done, verdict(w)
        move_robot(w, x=x, y=y, held=True); P.keep(0.3)
        assert verdict(w)["failed"] == why, (x, y, verdict(w))
    P.new().ready().strike(); P.shoot(V_IN); P.keep(0.05)                   # after the strike the feet are free
    move_robot(w, x=0.45, held=True); P.keep()
    assert verdict(w)["success"], verdict(w)

    # ---- the toss and the strike
    P.new().ready(); P.toss()                                               # struck out of the hand: the ball put on
    g = w.m.geom("racket_head").id                                          # the strings 10 ms after the release
    w.put("ball", w.d.geom_xpos[g] + [0.0, 0.0, 0.0125 + R + 0.01], vel=(0.0, 0.0, -3.0)); P.keep()
    assert verdict(w)["failed"] == "the racket struck the ball before it was clear of you", verdict(w)
    P.new().ready(); P.toss(); w.put("ball", w.pos("ball"), vel=V_IN); P.keep()      # thrown over the net by hand
    assert verdict(w)["failed"] == "the ball passed the net without a racket strike", verdict(w)
    P.new().ready().strike(); P.shoot((0.0, 0.0, 4.0)); P.keep()            # real: popped up, it comes down on the strings again
    assert verdict(w)["failed"] == "the racket hit the ball twice", verdict(w)
    P.new().ready().strike()                                                # held on the strings: a carry
    while not w.done:
        w.put("ball", w.d.geom_xpos[g] + [0.0, 0.0, 0.0125 + R - 0.002])
        P.keep(w.CONTROL_DT)
    assert verdict(w)["failed"] == "the racket carried the ball", verdict(w)
    P.new().ready().strike(); w.put("ball", (0.6, 0.0, 1.3), vel=(-8.0, 0.0, 0.0)); P.keep()      # back at the chest
    assert verdict(w)["failed"] == "the served ball touched you", verdict(w)
    P.new().ready().strike(); P.keep(0.02)                                  # the toss cannot be taken back: no grip
    w.put("ball", w.d.site_xpos[w.robot.palm["left"]] + w.d.xmat[w.robot.mount["left"]].reshape(3, 3)[:, 0] * (0.026 + R))
    P.keep(0.03, grip=1.0)
    assert w.held["left"] is None, w.held

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
        w.put("ball", (nx + 2.0, cy + 2.0, 3.0)); P.keep(0.01)              # point under the centre decides (carried
        w.put("ball", (bx, by, 0.3), vel=(0.0, 0.0, -5.0)); P.keep()        # over the net by hand, thrown down there)
        v = verdict(w)
        assert v["success"] if good else v["failed"] == OUT, (bx, by, v)

    # ---- Rule 22: the let, replayed once with the spare ball
    def net_cord(ball):
        w.put(ball, (nx - 0.3, cy + 2.0, T.net_top(2.0) + 0.02), vel=(14.0, 0.0, 0.0))

    P.new().ready()
    P.move(left=NEAR, seconds=0.8); P.move(left=SPARE, seconds=0.5); P.keep(0.2)   # before a let the spare cannot be
    assert w.held["left"] == "ball"                                                # taken (the hand holds the ball)
    P.new().ready().strike(); net_cord("ball")
    P.keep(until=lambda: task.trackers["phase"] == "await")
    assert not w.done and w.ref.stages == ["toss", "strike", "over the net"], verdict(w)
    assert [e["ev"] for e in w.ref.events].count("let") == 1 and task.trackers["ball"] == "ball2"
    assert x0 < w.pos("ball")[0] < x1, w.pos("ball")                        # (the let's ball did land in the box)
    P.move(left=NEAR, seconds=0.8); P.move(left=SPARE, seconds=0.5)         # the hand goes to the cup, open, ...
    assert w.held["left"] is None and not w.done
    P.keep(0.1, grip=1.0)                                                   # ... and the grip takes the spare (real)
    assert w.held["left"] == "ball2" and task.trackers["phase"] == "hold", (w.held, task.trackers["phase"])
    P.move(left=NEAR, seconds=0.5); P.move(left=LEFT, seconds=1.0); P.keep(0.7)
    g2 = w.d.geom_xpos[g]
    assert np.hypot(*(w.pos("ball2")[:2] - g2[:2])) < 0.09, (w.pos("ball2"), g2)   # over the strings again
    t0 = w.ref.time
    P.toss(); P.keep(until=lambda: task.trackers["phase"] == "served")
    assert not w.done and w.ref.time - t0 > 0.15, verdict(w)
    P.shoot(V_IN, "ball2"); P.keep()
    v = verdict(w)
    assert v["success"] and v["metrics"]["lets"] == 1 and x0 < v["metrics"]["landing_x_m"] < x1, v
    # the same again, but the second serve is a net cord too
    P.new().ready().strike(); net_cord("ball")
    P.keep(until=lambda: task.trackers["phase"] == "await")
    P.move(left=NEAR, seconds=0.8); P.move(left=SPARE, seconds=0.5); P.keep(0.1, grip=1.0)
    P.move(left=NEAR, seconds=0.5); P.move(left=LEFT, seconds=1.0); P.keep(0.7)
    P.toss(); P.keep(until=lambda: task.trackers["phase"] == "served")
    net_cord("ball2"); P.keep()
    assert verdict(w)["failed"] == "a second let", verdict(w)
    # and a fault on the replayed serve is a fault: the spare let drop
    P.new().ready().strike(); net_cord("ball")
    P.keep(until=lambda: task.trackers["phase"] == "await")
    P.move(left=NEAR, seconds=0.8); P.move(left=SPARE, seconds=0.5); P.keep(0.1, grip=1.0)
    P.move(left=NEAR, seconds=0.5); P.keep(0.6); P.keep(grip=0.0)
    assert verdict(w)["failed"] == "the tossed ball reached the ground unstruck", verdict(w)

    # ---- the robot
    P.new().keep(0.2); move_robot(w, x=nx - 0.10, y=cy, held=True); P.keep(0.5)        # at the net: the legs in it
    assert verdict(w)["failed"] == "you touched the net", verdict(w)
    P.new().keep(0.2); move_robot(w, z=0.30, held=True); P.keep(0.5)                   # on the ground
    assert verdict(w)["failed"] == "fell", verdict(w)
    print(f"PASS {FAMILY}")


if __name__ == "__main__":
    main()
