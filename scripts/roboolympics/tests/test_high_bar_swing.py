"""high-bar-swing (FIG bar, 2.80 m; a giant swing): the referee says no to hanging still, to a swing that does not go
over the top (however high), to a circle round the bar with the body tucked, to letting go, to touching the uprights
or the mats; yes to a full circle of the extended body.

Two positives. (a) A REAL solution through the action interface: the reference controller (oracles/high-bar-swing,
`joints` rows: a leg pump from the dead hang, about 24 s) and three variations of its parameters. (b) An INJECTION, to
test the referee quickly: the hanging robot and the bar are given the angular velocity 7 rad/s about the bar's axis
(the test writes the velocities), so the body, held extended by its joints, really goes once round the bar."""
import importlib.util
import os

import mujoco
import numpy as np

from rfo.testing import act, hold, make, verdict

ORACLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "oracles", "high-bar-swing", "oracle.py")


class Drive:
    """What the reference solution needs of a session: the world, its state and typed steps."""

    def __init__(self, w, A):
        self.world, self.A = w, A

    @property
    def done(self):
        return self.world.done

    def state(self):
        w = self.world
        return {"q_target": w.robot.arb.target().tolist(), "task": w.task.privileged(w)}

    def step(self, typ, row):
        return self.world.step(self.A.to_raw(typ, self.A.clip(typ, row), self.world))


def spin(w, omega):
    """The hanging robot and the bar turn about the bar's axis at omega (rad/s; negative: the body goes forwards)."""
    r, d, m = w.robot, w.d, w.m
    mujoco.mj_forward(m, d)
    p = d.qpos[r.fq:r.fq + 3] - np.array([0.0, 0.0, w.task.p["bar_height_m"]])
    wv = np.array([0.0, omega, 0.0])
    d.qvel[r.fv:r.fv + 3] = np.cross(wv, p)
    d.qvel[r.fv + 3:r.fv + 6] = d.xmat[r.pelvis].reshape(3, 3).T @ wv
    d.qvel[m.joint("bar").dofadr[0]] = omega


def thrown(w, A, omega, limit=6.0, tuck=False):
    w.task.time_limit_s = limit                       # (the test's own short episode)
    q = w.robot.arb.target()
    if tuck:
        q[0] = q[6] = -2.2
        q[3] = q[9] = 2.2
        q[14] = 0.5
        act(w, A, "joints", np.r_[q, 1, 1], 400)
    act(w, A, "joints", np.r_[q, 1, 1], 30)
    spin(w, omega)
    while not w.done:
        act(w, A, "joints", np.r_[q, 1, 1])
    return verdict(w)


def main():
    spec = importlib.util.spec_from_file_location("high_bar_oracle", ORACLE)
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    w, A = make("high-bar-swing")
    p = w.task.p
    limit = w.task.time_limit_s
    assert (p["bar_height_m"], p["bar_length_m"], p["bar_diameter_m"]) == (2.80, 2.40, 0.028)   # the FIG bar
    assert w.holder("bar") == ["left", "right"] and not w.ref.parts_touching(w.ref.ground)   # t = 0: hanging
    r0 = w.task.privileged(w)["com_radius_m"]
    assert 0.80 < r0 < 0.84 and p["min_radius_m"] == 0.74, r0
    hold(w, A)
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == [] and v["metrics"]["travel_deg"] < 5, v  # nop: hangs still

    w.reset(); oracle.solve(Drive(w, A))                                                  # positive (a): real
    v = verdict(w)
    assert v["success"] and v["stages"] == ["over the top", "full circle"], v
    assert v["metrics"]["travel_deg"] >= 360.0 and w.t < 0.6 * limit, (v, w.t)
    sha = w.state_sha()
    w.reset(); oracle.solve(Drive(w, A))
    assert w.state_sha() == sha                                                           # the same run again
    for kw in (dict(open_deg=80.0), dict(flex=1.6, knee=1.5, open_deg=110.0), dict(waist=0.0, open_deg=120.0)):
        w.reset(); oracle.solve(Drive(w, A), **kw)                                        # ... not on a knife edge
        assert verdict(w)["success"] and w.t < 0.7 * limit, (kw, verdict(w), w.t)

    w.reset(); v = thrown(w, A, -7.0)                                                     # positive (b): injection
    assert v["success"] and v["stages"] == ["over the top", "full circle"] and w.t < 2.5, (v, w.t)
    w.reset(); v = thrown(w, A, 7.0)                                                      # ... and backwards
    assert v["success"] and v["metrics"]["max_backward_deg"] >= 360.0, v
    w.reset(); v = thrown(w, A, -6.0)                                                     # a swing to 146 degrees
    assert v["failed"] == "time" and v["stages"] == [], v                                 # each way: no circle
    assert 280 < v["metrics"]["travel_deg"] < 360 and v["metrics"]["max_forward_deg"] < 180, v
    w.reset(); v = thrown(w, A, -9.0, tuck=True)                                          # round the bar tucked
    assert v["failed"] == "time" and v["stages"] == [], v
    assert any(e["ev"] == "not extended over the bar" for e in w.ref.events) and v["metrics"]["max_forward_deg"] > 360, v
    w.task.time_limit_s = limit
    w.reset(); hold(w, A, 0.5); hold(w, A, 0.1, grips=[1, 0])                             # one hand opens
    assert verdict(w)["failed"] == "let go of the bar", verdict(w)
    w.reset(); hold(w, A, 0.5); hold(w, A, 3.0, grips=[0, 0])                             # both: the first rule broken
    assert verdict(w)["failed"] == "let go of the bar", verdict(w)
    w.close()
    w, A = make("high-bar-swing", bar_length_m=1.20)                                      # uprights 0.6 m away (the
    q = w.robot.arb.target()                                                              # real ones are out of reach):
    q[1], q[3] = 2.2, 0.0                                                                 # a leg out to the side
    act(w, A, "joints", np.r_[q, 1, 1], 300)
    assert verdict(w)["failed"] == "touched the uprights", verdict(w)
    w.close()
    w, A = make("high-bar-swing", bar_height_m=1.80)                                      # a bar too low to hang from
    hold(w, A, 0.5)
    assert not w.done, verdict(w)
    q = w.robot.arb.target()
    q[0] = q[6] = q[3] = q[9] = 0.0
    q[4] = q[10] = 0.5                                                                    # legs straight, toes down
    act(w, A, "joints", np.r_[q, 1, 1], 300)
    assert verdict(w)["failed"] == "touched the ground", verdict(w)
    print("PASS high-bar-swing")


if __name__ == "__main__":
    main()
