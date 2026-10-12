"""golf-putt (v2): the referee's test on the official green.

The venue is measured first: stimp 10 (a ball that starts rolling at 1.83 m/s stops after 3.05 m) and a hole that is a
real hole (a ball rolling over its centre at 1 m/s at the lip drops in and stays; one at 2 m/s jumps it; one
over its edge lips out).

The positive is the real putt of the reference solution (oracles/golf-putt/oracle.py: a one-armed pendulum stroke
through the action interface, no injection), run twice for determinism.

The other cases are injections, said here once: `strike` makes a real contact between the putter's head and the ball
(the ball is put against the face where the club is, for one control step, which is what starts a stroke for the
referee) and the ball is then put back on its spot rolling with a chosen velocity; what follows (the roll over 3 m
of green, the drop into the hole or the lip-out, the rest) is physics. So are a ball held against the face for
several steps (a push), a ball thrown at the shaft, and the robot set astride the line. Real through the action interface: the nop, the kick
(a walk into the ball), the putter grounded with a wrist joint."""
import importlib.util
import os

import numpy as np

from rfo.scene import OFFICIAL
from rfo.testing import act, hold, make, move_robot, verdict

FAMILY = "golf-putt"
R = OFFICIAL["golf"]["radius"]
OUTSIDE = "the ball came to rest outside the hole"
OTHER = "the ball was touched by something other than the putter's head"
PUSH = "the ball was pushed, not struck"
SECOND = "a second stroke"
ASTRIDE = "the stance was astride or on the line of play"
LEFT = "the ball left the green"


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

    def state(self):
        return {"task": self.world.task.privileged(self.world)}


def face(w):
    g = w.m.geom("putter_face").id
    return w.d.geom_xpos[g].copy(), w.d.geom_xmat[g].reshape(3, 3).copy()


def strike(w, A):
    """Injection: a real contact of the head's face with the ball, wherever the club is (one control step)."""
    c, F = face(w)
    w.put("ball", c + F[:, 1] * (0.0015 + R - 0.0005))
    hold(w, A, 0.01)


def roll(w, speed, start=None, towards=None, aim_off=0.0):
    """Injection: the ball on the green at `start` (default: its spot), rolling at `speed` towards `towards` (default:
    the hole's centre, `aim_off` m to the right of it)."""
    p = w.task.p
    start = np.array([p["ball_x_m"], p["ball_y_m"]] if start is None else start, float)
    tgt = w.task.hole() + np.array([aim_off, 0.0]) if towards is None else np.array(towards, float)
    u = (tgt - start) / np.linalg.norm(tgt - start)
    w.put("ball", (start[0], start[1], R), vel=(speed * u[0], speed * u[1], 0.0),
          angvel=(-speed * u[1] / R, speed * u[0] / R, 0.0))


def rest_row(w, **joints):
    q = w.robot.rest[12:w.L.NJ].copy()
    names = [j[:-6] for j in w.L.JOINTS[12:]]
    for k, v in joints.items():
        q[names.index(k)] = v
    return np.r_[q, 0, 0]


def main():
    w, A = make(FAMILY)
    p = w.task.p
    hx, hy = w.task.hole()
    bx, by = p["ball_x_m"], p["ball_y_m"]
    D, Rh = p["hole_depth_m"], p["hole_diameter_m"] / 2

    # ---- the venue is the official one: the numbers, the hole is a hole, the green's speed
    assert (p["hole_diameter_m"], p["hole_depth_m"], p["putt_distance_m"]) == (0.108, 0.1016, 3.0), p
    assert abs(R - 0.02135) < 1e-6 and abs(OFFICIAL["golf"]["mass"] - 0.0459) < 1e-6
    m = w.m
    tool = [g for g in range(m.ngeom) if m.geom(g).name.startswith("putter_")]
    mass = float(m.body_mass[m.body("right_mount").id])
    assert len(tool) == 4 and abs(mass - 0.5) < 1e-6, (tool, mass)
    c, F = face(w)                                                   # nothing of the club is in the ground at t = 0
    assert c[2] > 0.3 and not w.ref.touching(w.ref.part("right_tool"), w.ref.ground)
    assert abs(float(np.hypot(hx - bx, hy - by)) - 3.0) < 1e-9

    roll(w, 1.83, start=(bx + 1.2, by - 1.0), towards=(bx + 1.2, by + 9.0))     # stimp: beside the line, past the hole
    hold(w, A, 7.0)
    run = float(w.pos("ball")[1] - (by - 1.0))
    assert abs(run - 3.05) < 0.03 and np.linalg.norm(w.vel("ball")) < 1e-2, run
    assert not w.done and verdict(w)["stages"] == [], verdict(w)     # (no stroke was made: nothing to judge)

    # ---- nop
    w.reset(); hold(w, A)
    assert verdict(w)["failed"] == "time" and not verdict(w)["stages"], verdict(w)

    # ---- positive: the real putt (the reference solution through the action interface)
    w.reset(); oracle().solve(Shim(w, A))
    v = verdict(w)
    assert v["success"] and v["stages"] == ["stroke", "holed"], v
    b = w.pos("ball")
    assert np.hypot(b[0] - hx, b[1] - hy) < Rh - R + 0.002 and b[2] < -D + R + 0.002, b      # on the hole's bottom
    assert v["metrics"]["head_hits"] == 1 and v["metrics"]["head_contact_s"] <= 0.02 and w.t < 20.0, (v, w.t)
    sha = w.state_sha()
    w.reset(); oracle().solve(Shim(w, A))
    assert w.state_sha() == sha                                              # the same run again: the same state

    # ---- positive by injection: a good putt's roll (2.05 m/s) is holed; the whole ball is below the surface
    w.reset(); hold(w, A, 0.2); strike(w, A)
    assert verdict(w)["stages"] == ["stroke"] and not w.done, verdict(w)
    roll(w, 2.05); hold(w, A)
    v = verdict(w)
    assert v["success"] and w.pos("ball")[2] + R < 0.0 and v["metrics"]["ball_to_hole_m"] < Rh, v
    sha = w.state_sha()
    w.reset(); hold(w, A, 0.2); strike(w, A); roll(w, 2.05); hold(w, A)
    assert w.state_sha() == sha

    w.reset(); hold(w, A, 0.2); strike(w, A)                                 # a ball that dies on the lip, 4 mm of
    w.put("ball", (hx, hy - Rh + 0.004, R)); hold(w, A)                      # its centre over the hole, tips in
    assert verdict(w)["success"], verdict(w)

    # ---- negatives: the ball's roll
    def after_roll(speed, **kw):
        w.reset(); hold(w, A, 0.2); strike(w, A); roll(w, speed, **kw)
        near = 9.0
        while not w.done:
            hold(w, A, 0.01)
            bb = w.pos("ball")
            near = min(near, float(np.hypot(bb[0] - hx, bb[1] - hy)))
        return verdict(w), near

    v, near = after_roll(1.60)                                               # too soft: short of the hole
    assert v["failed"] == OUTSIDE and v["stages"] == ["stroke"] and 0.3 < v["metrics"]["ball_to_hole_m"] < 1.2, v
    v, near = after_roll(2.75)                                               # too hard: over the hole's centre and on
    assert v["failed"] == OUTSIDE and near < 0.01 and w.pos("ball")[1] > hy + 0.2, (v, near, w.pos("ball"))
    v, near = after_roll(2.20, aim_off=0.045)                                # over the hole's edge: a lip-out
    assert v["failed"] == OUTSIDE and near < Rh and v["metrics"]["ball_to_hole_m"] > 0.1, (v, near)
    v, near = after_roll(1.85, aim_off=0.12)                                 # past the hole, a ball's width outside it
    assert v["failed"] == OUTSIDE and near > Rh + R, (v, near)
    w.reset(); hold(w, A, 0.2); strike(w, A)                                 # at rest on the lip (centre 6 mm outside)
    w.put("ball", (hx, hy - Rh - 0.006, R)); hold(w, A)
    assert verdict(w)["failed"] == OUTSIDE and w.pos("ball")[2] > 0.0, verdict(w)
    v, near = after_roll(3.0, towards=(bx + 5.0, by))                        # off the green's edge
    assert v["failed"] == LEFT, v

    # ---- negatives: the stroke
    w.reset(); hold(w, A, 0.2)                                               # a push: the ball stays on the face
    for _ in range(8):                                                       # (held against it step after step)
        if not w.done:
            strike(w, A)
    v = verdict(w)
    assert v["failed"] == PUSH and v["stages"] == ["stroke"] and v["metrics"]["head_contact_s"] > p["max_contact_s"], v

    w.reset(); hold(w, A, 0.2); strike(w, A)                                 # a double hit inside the window: one stroke
    roll(w, 0.0); hold(w, A, 0.05); strike(w, A)
    assert verdict(w)["failed"] is None and verdict(w)["metrics"]["head_hits"] == 2, verdict(w)
    roll(w, 0.0); hold(w, A, 0.3); strike(w, A)                              # ... and another touch later: a second one
    assert verdict(w)["failed"] == SECOND, verdict(w)

    w.reset(); hold(w, A, 0.2)                                               # the shaft (a thrown ball)
    mid = (w.d.xpos[w.robot.mount["right"]] + face(w)[0]) / 2
    w.put("ball", mid + np.array([0.4, 0.0, 0.05]), vel=(-4.0, 0.0, 0.0))
    hold(w, A, 0.5)
    assert verdict(w)["failed"] == OTHER and w.ref.events[-1]["parts"] == ["right_tool"], w.ref.events[-1:]
    assert verdict(w)["stages"] == [], verdict(w)

    w.reset(); w.put("ball", (0.17, -0.12, R))                               # a kick: the robot walks into the ball
    while not w.done and w.t < 4.0:
        act(w, A, "walk", np.r_[0.5, 0, 0, w.robot.rest[12:w.L.NJ], 0, 0])
    assert verdict(w)["failed"] == OTHER and w.ref.events[-1]["parts"] == ["right_foot"], w.ref.events[-1:]

    w.reset(); w.put("ball", (bx, by + 1.0, R))                              # astride the line of play (Rule 10.1c):
    move_robot(w, x=bx - 0.01); hold(w, A, 0.3)                              # the robot set on the line (the ball moved
    pts = w.ref.contact_points(w.ref.part("feet"), w.ref.ground)             # up the line, out of its feet's way)
    assert pts[:, 0].min() < bx < pts[:, 0].max(), pts
    strike(w, A)
    assert verdict(w)["failed"] == ASTRIDE and verdict(w)["stages"] == [], verdict(w)

    # ---- the putter on the green is not a fall (real: the arm out a little, the wrist lowers the club); a fall is
    w.reset()
    for i in range(1, 201):
        act(w, A, "stand", rest_row(w, right_shoulder_roll=-0.2 - 0.3 * min(1.0, i / 100),
                                    right_wrist_yaw=1.5 * max(0.0, (i - 100) / 100)))
    hold(w, A, 1.0)
    assert "right_tool" in w.ref.parts_touching(w.ref.ground) and verdict(w)["failed"] is None, \
        (w.ref.parts_touching(w.ref.ground), verdict(w))
    move_robot(w, z=0.30); hold(w, A, 0.5)
    assert verdict(w)["failed"] == "fell", verdict(w)
    print("PASS golf-putt")


if __name__ == "__main__":
    main()
