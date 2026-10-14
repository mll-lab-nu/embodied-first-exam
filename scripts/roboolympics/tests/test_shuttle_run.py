"""shuttle-run (4 x 10 m): the referee says no to standing still, to turning short of the far line, to a foot on the
line instead of beyond it, to finishing after two legs, to arms over the finish while the torso is not, to lying on
the floor for 10 s, and to walking (19 m in the 30 s).

The positive is an INJECTION for the turns only: the robot really runs all four legs with the running policy (it
really brakes to a stop with a foot on the ground beyond each line, and its torso really crosses the start line at the
end), but each about-turn is done by hand (rfo.testing.move_robot: the standing robot's yaw flipped by 180 degrees).
With the robot's own turn (the walking policy, 3 to 3.6 s each) the same run takes about 33 s; no controller of ours
makes the 30 s."""
import math

import numpy as np

from rfo.testing import act, hold, make, move_robot, verdict


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def run_legs(w, A, run_v=3.2, accel=1.5, gain=1.1, beyond=0.45):
    """The running policy on every leg, braked to a stop beyond the line; the about-turns injected."""
    D = w.task.p["distance_m"]
    for leg in range(4):
        sgn, line = (1.0, D) if leg % 2 == 0 else (-1.0, 0.0)
        heading = 0.0 if sgn > 0 else math.pi
        cmd = 0.0
        while not w.done:
            x, y, _, yaw = w.pelvis()
            v = float(np.hypot(*w.d.qvel[w.robot.fv:w.robot.fv + 2]))
            left = sgn * (line - x) + beyond
            wz = float(np.clip(wrap(heading - yaw) - 0.8 * sgn * y, -0.3, 0.3))
            if leg == 3:
                want = run_v
            elif w.task.trackers["leg"] > leg and v < 0.35:
                break
            else:
                want = 0.5 if (left < 0.05 and v < 0.35) else float(np.clip(gain * left, 0.0, run_v))
            cmd = min(want, cmd + accel * w.CONTROL_DT)
            act(w, A, "run", [cmd, 0.0, wz, 0, 0])
        if not w.done:                                   # the injected about-turn
            move_robot(w, yaw=math.pi - heading)
            w.d.qvel[w.robot.fv:w.robot.fv + 6] = 0.0


def main():
    w, A = make("shuttle-run")
    D = w.task.p["distance_m"]
    assert D == 10.0 and w.task.time_limit_s == 30.0
    hold(w, A)
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)          # nop
    w.reset(); run_legs(w, A)                                            # positive (the turns injected)
    v = verdict(w)
    assert v["success"] and v["stages"] == w.task.stages and v["metrics"]["time_s"] < 30.0, v
    print("  real running, injected turns:", v["metrics"])
    sha = w.state_sha()
    w.reset(); run_legs(w, A)
    assert w.state_sha() == sha                                                               # determinism
    # turning short of the far line, then "finishing"
    w.reset(); hold(w, A, 0.2); move_robot(w, x=9.5); hold(w, A, 0.2); move_robot(w, x=0.5); hold(w, A, 0.2)
    move_robot(w, x=-0.5); hold(w, A)
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)
    # a foot on the far line (the pelvis over it: the feet reach from 9.90 to 10.11 m), not beyond it
    w.reset(); hold(w, A, 0.2); move_robot(w, x=D); hold(w, A, 0.5)
    assert verdict(w)["stages"] == [] and not w.done, verdict(w)
    move_robot(w, x=D + 0.12); hold(w, A, 0.1)                           # ... now wholly beyond it (heels at 10.02 m)
    assert verdict(w)["stages"] == ["turn 1"], verdict(w)
    move_robot(w, x=0.0); hold(w, A, 0.3)                                # on the start line: no turn
    assert verdict(w)["stages"] == ["turn 1"], verdict(w)
    move_robot(w, x=-0.14); hold(w, A, 0.1)                              # beyond it (toes at -0.03 m)
    assert verdict(w)["stages"] == ["turn 1", "turn 2"], verdict(w)
    # finishing after two legs: back into the course and over the start line again, without the third turn
    move_robot(w, x=3.0); hold(w, A, 0.2); move_robot(w, x=-1.0); hold(w, A)
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == ["turn 1", "turn 2"], verdict(w)
    # three turns, then the arms over the finish (the robot faces the start line) while the torso is not
    w.reset(); hold(w, A, 0.2)
    for x in (D + 0.3, -0.3, D + 0.3):
        move_robot(w, x=x); hold(w, A, 0.2)
    assert verdict(w)["stages"] == ["turn 1", "turn 2", "turn 3"], verdict(w)
    move_robot(w, x=0.105, yaw=math.pi); hold(w, A, 0.03)
    lo, hi = w.ref.robot_span((1, 0, 0))
    assert lo < 0.0 < w.task.torso_low_x(w) and not w.done and verdict(w)["stages"][-1] == "turn 3", (lo, verdict(w))
    move_robot(w, x=0.05); hold(w, A, 0.05)
    assert verdict(w)["success"], verdict(w)
    w.reset(); hold(w, A, 0.5); move_robot(w, x=5.0, z=0.30); hold(w, A)                      # lying on the floor
    assert verdict(w)["failed"] == "did not finish: down for too long" and w.t < 16.0, (verdict(w), w.t)
    w.reset()                                                            # walking there and back: too slow
    up = w.robot.rest[12:]
    while not w.done:
        x, y, _, yaw = w.pelvis()
        back = w.task.trackers["leg"] % 2 == 1
        e = wrap((math.pi if back else 0.0) - yaw)
        act(w, A, "walk", np.r_[0.8 if abs(e) < 0.5 else 0.0, 0, np.clip(2 * e, -1.5, 1.5), up, 0, 0])
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] in (["turn 1"], ["turn 1", "turn 2"]), verdict(w)
    print("PASS shuttle-run")


if __name__ == "__main__":
    main()
