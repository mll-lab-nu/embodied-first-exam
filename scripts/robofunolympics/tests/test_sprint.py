"""sprint (50 m, World Athletics start procedure): the referee says yes to the reference solution (a real run through
the action interface: stand to the gun, then the running policy) and no to standing still, to a start movement before
the gun and inside the 0.100 s after it, to a foot on the start line before "set", to leaving the lane, to walking (too
slow), to lying on the track for 10 s, and to arms over the finish line while the torso is not."""
import importlib.util
import os

import numpy as np

from rfo.testing import act, hold, make, move_robot, verdict

ORACLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "oracles", "sprint", "oracle.py")


class Driver:
    """What an oracle needs of a Session, on a bare world."""

    def __init__(self, w, A):
        self.world, self.A = w, A

    @property
    def done(self):
        return self.world.done

    def hold(self):
        return self.A.hold(self.world)

    def state(self):
        w = self.world
        return {"pelvis_xyz_yaw": w.pelvis().tolist(), "task": w.task.privileged(w)}

    def step(self, typ, row):
        act(self.world, self.A, typ, row)
        return self.world.done


def solve(w, A, **kw):
    spec = importlib.util.spec_from_file_location("oracle", ORACLE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.solve(Driver(w, A), **kw)


def run_from(w, A, t_cmd, vx=3.5, seconds=1.0):
    """Hold to t_cmd, then the running policy for `seconds`."""
    hold(w, A, t_cmd)
    for _ in range(int(seconds / w.CONTROL_DT)):
        if w.done:
            break
        _, y, _, yaw = w.pelvis()
        act(w, A, "run", [vx, 0.0, float(np.clip(-1.5 * yaw - 1.0 * y, -0.5, 0.5)), 0, 0])


def main():
    w, A = make("sprint")
    p = w.task.p
    gun = p["set_at_s"] + p["gun_after_set_s"]
    D = p["distance_m"]
    assert p["distance_m"] == 50.0 and p["lane_width_m"] == 1.22 and p["reaction_min_s"] == 0.100
    assert -0.021 < w.task.foot_front(w) + p["start_line_m"] < -0.019          # the feet 2 cm behind the start line
    assert tuple(w.m.geom_rgba[w.task.lamp][:3]) == (0.9, 0.1, 0.1)             # the lamp: red
    hold(w, A)
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == [] and abs(w.t - (gun + p["finish_limit_s"])) < 0.011, (v, w.t)   # nop
    assert [e["ev"] for e in w.ref.events[:3]] == ["on_your_marks", "set", "gun"], w.ref.events[:3]
    assert w.ref.events[1]["t"] == 2.0 and abs(w.ref.events[2]["t"] - gun) < 1e-9
    w.reset(); hold(w, A, p["set_at_s"] + 0.5)
    assert w.task.privileged(w)["phase"] == "set" and tuple(w.m.geom_rgba[w.task.lamp][:3]) == (0.98, 0.85, 0.1)
    hold(w, A, gun - w.t)
    assert w.task.privileged(w)["phase"] == "running" and tuple(w.m.geom_rgba[w.task.lamp][:3]) == (0.1, 0.85, 0.2)
    w.reset(); solve(w, A)                                                      # positive: a real run
    v = verdict(w)
    assert v["success"] and v["stages"] == ["start", "finish"], v
    assert 12.0 < v["metrics"]["time_s"] < 18.0 and v["metrics"]["reaction_s"] >= 0.1, v
    print("  the reference run:", v["metrics"])
    sha = w.state_sha()
    w.reset(); solve(w, A)
    assert w.state_sha() == sha                                                 # the same run again: the same state
    w.reset(); run_from(w, A, gun - 0.20)                                       # running 0.2 s before the gun
    v = verdict(w)
    assert v["failed"] == "false start" and v["stages"] == [] and w.ref.events[-1]["reaction_s"] < 0.1, (v, w.ref.events[-1])
    w.reset(); run_from(w, A, p["set_at_s"] + 0.3)                              # running during "set"
    assert verdict(w)["failed"] == "false start" and w.ref.events[-1]["reaction_s"] < 0, w.ref.events[-1]
    w.reset(); hold(w, A, 0.5); move_robot(w, x=w.pelvis()[0] + 0.03); hold(w, A, 0.1)   # a foot on the line at "on your marks"
    assert verdict(w)["failed"] == "false start" and w.ref.events[-1]["what"] == "a foot on the start line", w.ref.events[-1]
    w.reset(); hold(w, A, 1.0); move_robot(w, x=w.pelvis()[0] - 0.5); hold(w, A, gun + 0.2 - w.t)
    assert verdict(w)["failed"] is None and verdict(w)["stages"] == [], verdict(w)   # moving back before "set" is no start
    move_robot(w, x=w.pelvis()[0] + 0.3); hold(w, A, 0.05)                      # the start movement 0.2 s after the gun
    assert verdict(w)["stages"] == ["start"] and verdict(w)["metrics"]["reaction_s"] >= 0.2, verdict(w)
    move_robot(w, y=0.7); hold(w, A, 0.05)                                      # out of the lane
    assert verdict(w)["failed"] == "left the lane", verdict(w)
    w.reset(); hold(w, A, gun + 0.5); move_robot(w, x=5.0, z=0.30); hold(w, A)  # lying on the track
    v = verdict(w)
    assert v["failed"] == "did not finish: down for too long" and w.t < gun + 15.0, (v, w.t)
    # the arms over the line, the torso not: no finish; the torso over it: the finish
    w.reset(); hold(w, A, gun + 0.5); move_robot(w, x=D - 0.105); hold(w, A, 0.02)
    lo, hi = w.ref.robot_span((1, 0, 0))
    assert hi > D and w.task.torso_front(w) < D and verdict(w)["stages"] == ["start"] and not w.done, (hi, verdict(w))
    move_robot(w, x=D - 0.05); hold(w, A, 0.05)
    assert verdict(w)["success"], verdict(w)
    w.reset(); hold(w, A, gun)                                                  # walking: too slow
    up = w.robot.rest[12:]
    while not w.done:
        _, y, _, yaw = w.pelvis()
        act(w, A, "walk", np.r_[0.8, np.clip(-2 * y, -0.4, 0.4), np.clip(-2 * yaw, -1, 1), up, 0, 0])
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == ["start"] and v["metrics"]["distance_m"] < 50.0, v
    print("  walking for the time limit:", v["metrics"])
    print("PASS sprint")


if __name__ == "__main__":
    main()
