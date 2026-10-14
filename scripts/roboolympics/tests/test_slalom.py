"""slalom (the Illinois agility test): the referee says no to standing still, to skipping the first leg, to passing two
centre cones on the same side, to turning back in the weave, to not rounding the top cone, to a touched cone, to a
finish in the wrong half or before the last leg, to lying on the floor for 10 s, and to the walking gait (too slow).

Two positives, neither a solution:
 * a real walk (the walking policy steered through waypoints) round the whole prescribed path latches all twelve gates
   and finishes, with the test's own time limit (200 s instead of the official 60 s: the walk takes about 110 s);
   under the official limit the same walk fails with "time";
 * an INJECTION at the official limit: the robot is moved by hand (rfo.testing.move_robot) from waypoint to waypoint
   of the same path, 0.3 s apart, so that the referee sees every crossing in order and the finish inside 60 s."""
import math

import numpy as np

from rfo.testing import act, hold, make, move_robot, verdict

# the pelvis' waypoints of the prescribed path (0.6 to 0.7 m clear of every cone)
PATH = [(10.6, 1.9), (10.7, 3.1), (9.6, 3.1), (0.7, 0.75), (-0.65, 0.6), (-0.65, -0.6), (0.3, -0.7), (1.65, 0.0),
        (3.3, 0.65), (4.95, 0.0), (6.6, -0.65), (8.25, 0.0), (9.9, 0.65), (10.55, 0.4), (10.55, -0.4), (9.9, -0.65),
        (8.25, 0.0), (6.6, 0.65), (4.95, 0.0), (3.3, -0.65), (1.65, 0.0), (0.3, 0.7), (-0.65, 0.6), (-0.65, -0.6),
        (0.6, -1.3), (10.6, -1.9), (10.7, -3.1), (9.6, -3.1), (-0.8, -3.1)]


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def walk_path(w, A, path=PATH):
    up = w.robot.rest[12:]
    for (tx, ty) in path:
        while not w.done:
            x, y, _, yaw = w.pelvis()
            if math.hypot(tx - x, ty - y) < 0.25:
                break
            e = wrap(math.atan2(ty - y, tx - x) - yaw)
            act(w, A, "walk", np.r_[0.8 * max(0.0, math.cos(e)) if abs(e) < 0.9 else 0.0, 0.0,
                                    np.clip(2.5 * e, -1.5, 1.5), up, 0, 0])


def hop_path(w, A, path, dwell=0.3):
    """Injected motion: the robot is put on each waypoint in turn (those on the centre line left out: a robot
    standing on the line sways across it), facing the way it came from."""
    for (tx, ty) in path:
        if ty == 0.0:
            continue
        if w.done:
            return
        x, y, _, _ = w.pelvis()
        move_robot(w, x=tx, y=ty, yaw=math.atan2(ty - y, tx - x))
        hold(w, A, dwell)


def main():
    w, A = make("slalom")
    p = w.task.p
    assert (p["length_m"], p["width_m"], p["cone_spacing_m"]) == (10.0, 5.0, 3.3) and w.task.time_limit_s == 60.0
    hold(w, A)
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)          # nop
    w.reset(); hop_path(w, A, PATH)                                      # positive at the official limit (injection)
    v = verdict(w)
    assert v["success"] and v["stages"] == w.task.stages and v["metrics"]["time_s"] < 60.0, v
    sha = w.state_sha()
    w.reset(); hop_path(w, A, PATH)
    assert w.state_sha() == sha                                                               # determinism
    w.reset(); walk_path(w, A)                                           # the real walk, official limit: too slow
    v = verdict(w)
    assert v["failed"] == "time" and 3 <= v["metrics"]["gates"] < 12, v
    print("  the walking gait in 60 s:", v["metrics"], v["stages"][-1])
    w.reset(); w.task.time_limit_s = 200.0; walk_path(w, A)              # the real walk, the test's own limit
    v = verdict(w)
    del w.task.time_limit_s
    assert v["success"] and v["stages"] == w.task.stages and 60.0 < v["metrics"]["time_s"] < 200.0, v
    print("  the walking gait round the whole path:", v["metrics"])
    assert w.task.time_limit_s == 60.0
    w.reset(); hop_path(w, A, PATH[3:6])                                 # the first leg skipped
    assert verdict(w)["failed"] == "left the prescribed path" and verdict(w)["stages"] == [], verdict(w)
    w.reset(); hop_path(w, A, PATH[:7] + [(3.3, -0.65), (6.6, 0.65)])    # the first two centre cones on the same side
    assert verdict(w)["failed"] == "left the prescribed path", verdict(w)
    assert verdict(w)["stages"] == w.task.stages[:2] and w.ref.events[-1]["crossed"] == "centre line at 2-3, RL", w.ref.events[-1]
    w.reset(); hop_path(w, A, PATH[:6] + [(-0.65, 0.6)])                 # back the way it came round the bottom cone
    assert verdict(w)["failed"] == "left the prescribed path" and verdict(w)["stages"] == w.task.stages[:2], verdict(w)
    w.reset(); hop_path(w, A, PATH[:13] + [(8.25, -0.5)])                # down again without rounding the top cone
    assert verdict(w)["failed"] == "left the prescribed path" and verdict(w)["stages"] == w.task.stages[:5], verdict(w)
    w.reset(); hold(w, A, 0.2); x, y = w.pelvis()[:2]                    # a cone against the robot's foot
    w.put("cone_centre2", (x + 0.16, y + 0.12, 0.0)); hold(w, A, 0.3)
    v = verdict(w)
    assert v["failed"] == "touched a cone" and w.ref.events[-1]["cone"] == "centre2", (v, w.ref.events[-1])
    w.reset(); hold(w, A, 0.2); move_robot(w, x=2.6, y=0.12)             # walking on: the right foot into a centre cone
    while not w.done:
        _, y, _, yaw = w.pelvis()
        act(w, A, "walk", np.r_[0.5, np.clip(2 * (0.12 - y), -0.3, 0.3), np.clip(-2 * yaw, -1, 1), w.robot.rest[12:], 0, 0])
    assert verdict(w)["failed"] == "touched a cone" and w.ref.events[-1]["cone"] == "centre2", w.ref.events[-1]
    assert "right_foot" in w.ref.events[-1]["parts"] and verdict(w)["stages"] == [], w.ref.events[-1]
    w.reset(); hop_path(w, A, PATH[:24] + [(0.6, -1.3), (-0.8, -1.3)]); hold(w, A)            # the last leg skipped
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == w.task.stages[:10], verdict(w)
    w.reset(); hop_path(w, A, PATH[:27] + [(9.6, 3.1), (0.6, 2.0), (-0.8, 2.0)])              # "finish" in the left half
    assert verdict(w)["failed"] == "left the prescribed path" and verdict(w)["stages"] == w.task.stages[:11], verdict(w)
    w.reset(); hold(w, A, 0.5); move_robot(w, x=5.0, z=0.30); hold(w, A)                      # lying on the floor
    assert verdict(w)["failed"] == "did not finish: down for too long" and w.t < 16.0, (verdict(w), w.t)
    print("PASS slalom")


if __name__ == "__main__":
    main()
