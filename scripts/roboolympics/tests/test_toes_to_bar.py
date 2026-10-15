"""toes-to-bar (the FIG bar, CrossFit's standard, 5 repetitions): the referee says no to hanging still, to feet that
touch the bar outside the hands, to one foot between the hands and one outside, to staying at the bar or coming only
part of the way down (one touch, no repetition), to letting go, to touching the uprights or the mats; a swing is legal.

The positive is a REAL solution through the action interface (oracles/toes-to-bar: `joints` rows, a kipped snap of
hips, knees and elbows timed on the swing, five repetitions in about 8 s), with five variations of its parameters:
no injection."""
import importlib.util
import os

import mujoco
import numpy as np

from rfo.testing import act, hold, make, verdict

ORACLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "oracles", "toes-to-bar", "oracle.py")
REPS = ["rep 1", "rep 2", "rep 3", "rep 4", "rep 5"]


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


def snap(w, A, seconds, roll=(0.0, 0.0), down=None):
    """The oracle's snap, held for `seconds` (legs spread by the hip rolls `roll`), then the legs to `down` (a
    fraction of the way back to the hang; None: stay up) to the end. Returns which feet really touched the bar."""
    T, base = w.task, w.robot.arb.target()
    q = base.copy()
    q[0] = q[6] = -2.53
    q[3] = q[9] = 1.2
    q[4] = q[10] = 0.4
    q[14], q[18], q[25] = 0.52, 2.09, 2.09
    q[1], q[7] = roll[0], -roll[1]
    seen = set()
    n = int(round(seconds / w.CONTROL_DT))
    while not w.done:
        tgt = q if n > 0 or down is None else q + down * (base - q)
        act(w, A, "joints", np.r_[tgt, 1, 1])
        n -= 1
        seen |= {s for s in ("left", "right") if w.ref.touching(T.foot[s], T.bar_g)}
    return seen


def main():
    spec = importlib.util.spec_from_file_location("toes_to_bar_oracle", ORACLE)
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    w, A = make("toes-to-bar")
    p, r = w.task.p, w.robot
    limit = w.task.time_limit_s
    assert (p["bar_height_m"], p["bar_length_m"], p["bar_diameter_m"], p["reps"]) == (2.80, 2.40, 0.028, 5)
    assert w.task.stages == REPS
    assert w.holder("bar") == ["left", "right"] and not w.ref.parts_touching(w.ref.ground)   # t = 0: hanging
    f = w.task.feet(w)
    assert all(1.5 < below < 1.6 and ahead < 0 for below, ahead in f.values()), f             # a full hang
    hold(w, A)
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == [] and "touches" not in v["metrics"], v   # nop: hangs still

    w.reset(); oracle.solve(Drive(w, A))                                                  # positive: real
    v = verdict(w)
    assert v["success"] and v["stages"] == REPS and v["metrics"]["touches"] == 5, v
    assert w.t < 0.5 * limit, w.t
    sha = w.state_sha()
    w.reset(); oracle.solve(Drive(w, A))
    assert w.state_sha() == sha                                                           # the same run again
    for kw in (dict(phase=0.5), dict(knee=1.5), dict(elbow=1.8), dict(ankle=0.2, phase=0.8), dict(hip=-2.45)):
        w.reset(); oracle.solve(Drive(w, A), **kw)                                        # ... not on a knife edge
        assert verdict(w)["success"] and w.t < 0.5 * limit, (kw, verdict(w), w.t)

    w.task.time_limit_s = 4.0                                                             # (short episodes below)
    w.reset(); seen = snap(w, A, 4.0)                                                     # the feet stay at the bar
    v = verdict(w)
    assert seen == {"left", "right"} and v["failed"] == "time" and v["stages"] == [] and v["metrics"]["touches"] == 1, v
    w.reset(); seen = snap(w, A, 0.6, down=0.2)                                           # a fifth of the way down
    v = verdict(w)
    assert seen == {"left", "right"} and v["failed"] == "time" and v["stages"] == [] and v["metrics"]["touches"] == 1, v
    w.reset(); seen = snap(w, A, 4.0, roll=(0.4, 0.4))                                    # legs apart: both feet on
    v = verdict(w)                                                                        # the bar outside the hands
    assert seen == {"left", "right"} and v["failed"] == "time" and "touches" not in v["metrics"], (seen, v)
    w.reset(); seen = snap(w, A, 4.0, roll=(0.0, 0.4))                                    # one foot between the
    v = verdict(w)                                                                        # hands, one outside
    assert seen == {"left", "right"} and v["failed"] == "time" and "touches" not in v["metrics"], (seen, v)
    w.reset(); hold(w, A, 0.3)                                                            # swinging is legal: the
    mujoco.mj_forward(w.m, w.d)                                                           # body thrown to a swing
    om = np.array([0.0, -3.5, 0.0])                                                       # of about 60 degrees
    w.d.qvel[r.fv:r.fv + 3] = np.cross(om, w.d.qpos[r.fq:r.fq + 3] - np.array([0.0, 0.0, p["bar_height_m"]]))
    w.d.qvel[r.fv + 3:r.fv + 6] = om
    w.d.qvel[w.m.joint("bar").dofadr[0]] = om[1]
    peak = 0.0
    while not w.done:
        hold(w, A, 0.01)
        peak = max(peak, abs(w.task.privileged(w)["swing_deg"]))
    assert peak > 45 and verdict(w)["failed"] == "time", (peak, verdict(w))
    w.task.time_limit_s = limit
    w.reset(); hold(w, A, 0.5); hold(w, A, 0.1, grips=[0, 1])                             # a hand opens
    assert verdict(w)["failed"] == "let go of the bar", verdict(w)
    w.reset(); q = w.robot.arb.target()                                                   # ... also on the way up
    q[0] = q[6] = -2.0
    act(w, A, "joints", np.r_[q, 1, 1], 25); hold(w, A, 0.1, grips=[0, 0])
    assert verdict(w)["failed"] == "let go of the bar", verdict(w)
    w.close()
    w, A = make("toes-to-bar", bar_length_m=1.20)                                         # uprights 0.6 m away (the
    q = w.robot.arb.target()                                                              # real ones are out of reach):
    q[1], q[3] = 2.2, 0.0                                                                 # a leg out to the side
    act(w, A, "joints", np.r_[q, 1, 1], 300)
    assert verdict(w)["failed"] == "touched the uprights", verdict(w)
    w.close()
    w, A = make("toes-to-bar", bar_height_m=1.80)                                         # a bar too low to hang from
    hold(w, A, 0.5)
    assert not w.done, verdict(w)
    q = w.robot.arb.target()
    q[0] = q[6] = q[3] = q[9] = 0.0
    q[4] = q[10] = 0.5                                                                    # legs straight, toes down
    act(w, A, "joints", np.r_[q, 1, 1], 300)
    assert verdict(w)["failed"] == "touched the ground", verdict(w)
    print("PASS toes-to-bar")


if __name__ == "__main__":
    main()
