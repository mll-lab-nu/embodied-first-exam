"""dribble-slalom (v2: six cones 2 m apart, out, round the last and back, a size-5 ball, 90 s): the referee says no to
standing still, to a ball or a robot that passes a cone on the wrong side, to a ball that gets more than 2 m away, to a
touched cone (by the ball or by a foot) and to a handball; yes to the ball and the robot through all twelve planes and
back over the start line.

The positive is an INJECTION: no dribbling controller fast enough exists (the v1 reference, small pushes on the walking
policy, covered 4.9 m in 29 s; this course is about 31 m in 90 s). Real: the robot really walks the whole slalom on the
walking policy, out, round the last cone and back, without touching a cone. Injected: the ball is escorted, put 0.45 m
in front of the robot's pelvis at every control step with the pelvis' velocity (it is not kicked)."""
import math

import numpy as np

from rfo.testing import act, hold, make, move_robot, verdict

FAMILY = "dribble-slalom"
R = 0.11


def course(task, off=0.6):
    """The pelvis' waypoints through the slalom: beside each cone on its side, round the last, back, home."""
    c = task.cones()
    out = [(x, s * off) for x, s in c]
    back = [(x, -s * off) for x, s in reversed(c)]
    return out + [(c[-1][0] + 0.9, 0.0)] + back + [(task.p["start_line_m"] - 0.7, 0.0)]


def escort(w, A, way, ball_offset=(0.45, 0.0), lead=True, until=None):
    """Walk through the waypoints (the walking policy, real); with `lead` the ball is put at ball_offset (forward,
    left) of the pelvis at every step."""
    rest = w.robot.rest[12:]
    r, d = w.robot, w.d
    k = 0
    while not w.done and k < len(way):
        x, y, _, yaw = w.pelvis()
        dx, dy = way[k][0] - x, way[k][1] - y
        if math.hypot(dx, dy) < 0.30:
            k += 1
            continue
        err = math.atan2(dy, dx) - yaw
        err = math.atan2(math.sin(err), math.cos(err))
        vx = 0.8 * max(0.0, math.cos(err)) if abs(err) < 1.2 else 0.0
        act(w, A, "walk", np.r_[vx, 0.0, float(np.clip(2.5 * err, -1.4, 1.4)), rest, 0, 0])
        if lead and not w.done:
            x, y, _, yaw = w.pelvis()
            c, s = math.cos(yaw), math.sin(yaw)
            v = d.qvel[r.fv:r.fv + 2]
            w.put("ball", (x + c * ball_offset[0] - s * ball_offset[1], y + s * ball_offset[0] + c * ball_offset[1], R),
                  vel=(v[0], v[1], 0.0))
        if until is not None and until(w):
            return
    if not w.done:
        hold(w, A)


def roll(w, pos, vel):
    """Injection: the ball rolling from pos (x, y) with velocity vel (x, y)."""
    w.put("ball", (pos[0], pos[1], R), vel=(vel[0], vel[1], 0.0), angvel=(-vel[1] / R, vel[0] / R, 0.0))


def main():
    w, A = make(FAMILY)
    p, m = w.task.p, w.m
    cones = w.task.cones()
    assert [x for x, _ in cones] == [3.0, 5.0, 7.0, 9.0, 11.0, 13.0] and len(w.task.gates()) == 12
    assert abs(m.geom("ball").size[0] - 0.11) < 1e-9 and abs(m.body("ball").mass[0] - 0.43) < 1e-9
    hold(w, A)                                                             # nop
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == [], v

    w.reset(); escort(w, A, course(w.task))                                # positive (injection, see the docstring)
    v = verdict(w)
    assert v["success"] and v["stages"] == w.task.stages and len(v["stages"]) == 13, v
    assert v["metrics"]["max_ball_distance_m"] < p["control_m"], v
    sha, t_ok = w.state_sha(), w.t
    w.reset(); escort(w, A, course(w.task))
    assert w.state_sha() == sha                                            # the same run again: the same state

    w.reset(); escort(w, A, [(3.0, -0.6), (4.0, -0.6)])                    # cone 1 on the wrong side (ball first)
    v = verdict(w)
    assert v["failed"] == "the ball passed a cone on the wrong side" and v["stages"] == [], v

    w.reset(); escort(w, A, [(3.0, -0.6), (4.0, -0.6)], ball_offset=(0.45, 1.2))   # the ball right, the robot wrong
    v = verdict(w)
    assert v["failed"] == "the robot passed a cone on the wrong side" and v["metrics"]["planes_ball"] == 1, v

    # out through the six cones, then straight back along one side instead of weaving
    c6 = cones[-1][0]
    w.reset(); escort(w, A, course(w.task)[:7] + [(c6, 0.6), (c6 - 2.0, 0.6), (c6 - 3.0, 0.6)])
    v = verdict(w)
    assert v["failed"] == "the ball passed a cone on the wrong side" and v["stages"][-1] == "back 6", v
    assert w.ref.events[-1]["plane"] == "back 5", w.ref.events[-1]

    w.reset(); hold(w, A, 0.1); roll(w, (1.2, 0.8), (6.0, 0.0)); hold(w, A)   # one long kick: the ball gets away
    v = verdict(w)
    assert v["failed"] == "the ball got away from the robot" and v["stages"] == [], v

    w.reset(); move_robot(w, x=1.6); hold(w, A, 0.1); roll(w, (2.2, 0.0), (2.0, 0.0)); hold(w, A)   # the ball into cone 1
    v = verdict(w)
    assert v["failed"] == "cone 1 was touched" and w.ref.events[-1]["by"] == ["ball"], (v, w.ref.events[-1])

    w.reset(); escort(w, A, [(3.2, 0.0)], ball_offset=(0.45, 0.6))         # a foot into cone 1 (the ball beside it)
    v = verdict(w)
    assert v["failed"] == "cone 1 was touched" and set(w.ref.events[-1]["by"]) & {"left_foot", "right_foot", "left_shin", "right_shin"}, (v, w.ref.events[-1])

    w.reset(); hold(w, A, 0.1)                                             # handball (injected: the ball at the hand)
    w.launch("ball", w.d.site_xpos[w.robot.palm["right"]] + [0.0, -0.60, 0.25], (0.0, 2.5, 0.0)); hold(w, A)
    v = verdict(w)
    assert v["failed"] == "handball" and "right_hand" in w.ref.events[-1]["parts"], (v, w.ref.events[-1])

    w.reset(); hold(w, A, 0.2); move_robot(w, z=0.30); hold(w, A, 0.5)     # on the ground
    assert verdict(w)["failed"] == "fell", verdict(w)
    print(f"injection (escorted ball, real walk): the course in {t_ok:.1f} s of 90 s")
    print(f"PASS {FAMILY}")


if __name__ == "__main__":
    main()
