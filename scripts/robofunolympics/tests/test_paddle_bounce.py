"""paddle-bounce: the referee says yes to twenty real bounces (the reference solution, oracles/paddle-bounce/oracle.py,
through the action interface: no injection) and no to: doing nothing; a still, level blade under the drop (the v1
hole: the drop paid for bounces; now the first passive rebound already fails); a still blade that is lowered after the
first bounce; real hits that reach the drop height but rise less than the minimum above the blade; a ball at rest on
the blade (an injection: the ball is put on the blade); the handle; the hand; touching the ball before the drop; a
fall; and running out of time while still bouncing."""
import importlib.util
import os

import numpy as np

from rfo.tasks.paddle_bounce import EARLY, FLOOR, LOW, OTHER, REST
from rfo.testing import act, hold, make, move_robot, verdict

FAMILY = "paddle-bounce"
BLADE_Z = 0.87                    # where the tests hold the blade's centre (m above the floor), under the drop point


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


def hold_pose(w, xy=None, z=BLADE_Z):
    """The waist and arm joints that hold the blade level, its centre at xy (default: under the drop point), z."""
    p = w.task.p
    xy = (p["drop_x_m"], p["drop_y_m"]) if xy is None else xy
    return oracle().Arm(w).solve(np.r_[xy, z], (0, 0, 1), iters=300)


def raise_paddle(w, A, q, seconds=1.0):
    q0 = w.robot.rest[12:29].copy()
    n = int(round(seconds / w.CONTROL_DT))
    for i in range(1, n + 1):
        act(w, A, "stand", np.r_[q0 + (q - q0) * i / n, 0, 0])


def still_paddle(xy=None, **params):
    w, A = make(FAMILY, **params)
    q = hold_pose(w, xy)
    raise_paddle(w, A, q)
    hold(w, A)
    return w


def main():
    w, A = make(FAMILY)
    p = w.task.p
    assert w.task.robot == "unitree_g1" and len(w.task.stages) == p["bounces"] == 20
    hold(w, A)
    assert verdict(w)["failed"] == FLOOR and not verdict(w)["stages"], verdict(w)                 # nop

    w.reset(); oracle().solve(Shim(w, A))                                    # positive: the real solution
    v = verdict(w)
    assert v["success"] and v["stages"] == [f"bounce {i}" for i in range(1, 21)] and w.t < 16.0, (v, w.t)
    assert 20 <= w.task.trackers["blade"].count <= 24 and w.task.trackers["blade"].longest <= 0.005, \
        w.task.trackers["blade"].state()                 # (a bounce the blade did not speed up is not counted)
    left = [e["left_z"] for e in w.ref.events if e["ev"] == "stage"]
    assert max(left) <= p["drop_z_m"] - p["min_rise_m"], left                # every bounce left the blade well below
    sha = w.state_sha()
    w.reset(); oracle().solve(Shim(w, A))
    assert w.state_sha() == sha                                              # the same run again: the same state
    for gains in (dict(apex_m=0.42), dict(blade_z_m=0.84)):                  # not on a knife edge
        w.reset(); oracle().solve(Shim(w, A), **gains)
        assert verdict(w)["success"], (gains, verdict(w))

    w.reset(); q = hold_pose(w); raise_paddle(w, A, q); hold(w, A)           # a still, level blade under the ball:
    v, ev = verdict(w), w.ref.events[-1]                                     # the rebound rises 0.27 m, not to the drop
    assert v["failed"] == LOW and v["stages"] == [], v                       # height: no bounce is paid by the drop
    assert ev["rise_m"] >= p["min_rise_m"] and ev["apex_m"] < p["drop_z_m"] - 0.02, ev

    w.reset(); raise_paddle(w, A, q)                                         # ... and a blade lowered 6 cm after the
    while not w.done and w.task.trackers["blade"].count == 0:                # first touch (a sinking, passive blade)
        act(w, A, "stand", np.r_[q, 0, 0])
    q_low = hold_pose(w, z=BLADE_Z - 0.06)
    for i in range(1, 16):
        act(w, A, "stand", np.r_[q + (q_low - q) * i / 15, 0, 0])
    hold(w, A)
    v, ev = verdict(w), w.ref.events[-1]
    assert v["failed"] == LOW and v["stages"] == [] and ev["apex_m"] < p["drop_z_m"], (v, ev)

    w2, A2 = make(FAMILY, drop_z_m=0.95)                                     # real hits that come back to the (low)
    oracle().solve(Shim(w2, A2), apex_m=0.10)                                # drop height but rise only 0.10 m
    v, ev = verdict(w2), w2.ref.events[-1]
    assert v["failed"] == LOW and v["stages"] == [], v
    assert ev["apex_m"] >= 0.95 and ev["rise_m"] < p["min_rise_m"], ev

    w.reset(); raise_paddle(w, A, q); hold(w, A, 1.05)                       # resting (injection: put on the blade)
    c = w.d.geom_xpos[w.m.geom("paddle_blade").id]
    w.put("ball", c + [0.0, 0.0, 0.0075 + 0.0202])
    hold(w, A)
    assert verdict(w)["failed"] == REST, verdict(w)

    w.reset(); raise_paddle(w, A, q)                                         # where the handle and the hand are then
    handle = w.d.geom_xpos[w.m.geom("paddle_handle").id][:2].copy()
    wrist = w.d.xpos[w.m.body("right_wrist_pitch_link").id][:2].copy()
    for xy, is_handle, part in ((handle, True, "right_tool"), (wrist, False, "right_hand")):       # the blade stays
        w3 = still_paddle(xy=(p["drop_x_m"], p["drop_y_m"]), drop_x_m=float(xy[0]), drop_y_m=float(xy[1]))
        ev = w3.ref.events[-1]
        assert verdict(w3)["failed"] == OTHER and not verdict(w3)["stages"], (xy, ev)
        assert ev["handle"] == is_handle and part in ev["parts"], (xy, ev)

    v = verdict(still_paddle(drop_z_m=0.875))                                # the blade raised into the hanging ball
    assert v["failed"] == EARLY, v

    w.reset(); hold(w, A, 0.2); move_robot(w, z=0.30); hold(w, A, 0.5)       # on the ground
    assert verdict(w)["failed"] == "fell", verdict(w)

    w4, A4 = make(FAMILY, bounces=60)                                        # bouncing on, but not done in time
    oracle().solve(Shim(w4, A4))
    v = verdict(w4)
    assert v["failed"] == "time" and v["metrics"]["bounces"] >= 25, v
    print("PASS paddle-bounce")


if __name__ == "__main__":
    main()
