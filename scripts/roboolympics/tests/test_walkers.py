"""The G1's optional walking policies, `walk_falcon` and `walk_agile` (rfo/world.py; the robot library's numpy ports of
the released FALCON and WBC-AGILE G1 policies): on a G1 venue each one stands still for 10 s, walks forward and
sideways along its command, turns, carries the arms raised, hands over to and from the other modes without a fall, and
replays to the same state; `stand` straight after a walker falls (as the instruction says: through `walk` at rest it
does not); the H1-2 does not offer them. Not a family: no referee is judged here (the slalom venue is
only the floor; its referee has nothing to say before the runner leaves the start)."""
import math

import numpy as np

from rfo.testing import act, make
from rfo.world import WALK_AGILE, WALK_FALCON


def upper(w):
    return np.r_[w.robot.rest[12:]]


def run(w, A, typ, cmd, seconds, arms=None):
    up = upper(w) if arms is None else arms
    for _ in range(int(round(seconds / w.CONTROL_DT))):
        act(w, A, typ, np.r_[cmd, up, 0, 0])


def rel(w, p0):
    """The pelvis' displacement since p0 in the robot's starting frame (x forward, y left) and its yaw change."""
    p = w.pelvis()
    return p[0] - p0[0], p[1] - p0[1], (p[3] - p0[3] + math.pi) % (2 * math.pi) - math.pi


def main():
    w, A = make("slalom")
    w.task.fall_rule = False
    w.task.time_limit_s = 400.0                                          # (the test walks longer than a slalom)
    assert {"walk_falcon", "walk_agile"} <= set(A.types), list(A.types)
    for typ, mode in (("walk_falcon", WALK_FALCON), ("walk_agile", WALK_AGILE)):
        lo, hi = A.types[typ]["bounds"]
        assert A.types[typ]["dim"] == A.types["walk"]["dim"] == 22, A.types[typ]
        w.reset(); act(w, A, "stand", np.r_[upper(w), 0, 0], 50)
        p0 = w.pelvis().copy()
        run(w, A, typ, (0, 0, 0), 10.0)                                  # stand on the walker
        dx, dy, dyaw = rel(w, p0)
        assert w.mode == mode and not w.unstable and w.pelvis()[2] > 0.6, (typ, w.pelvis())
        assert math.hypot(dx, dy) < 0.15 and abs(dyaw) < 0.15, (typ, dx, dy, dyaw)
        p0 = w.pelvis().copy()
        run(w, A, typ, (0.5, 0, 0), 8.0)                                 # forward at 0.5 m/s
        dx, dy, _ = rel(w, p0)
        assert 2.4 < dx < 5.0 and abs(dy) < 1.0 and w.pelvis()[2] > 0.6, (typ, dx, dy, w.pelvis())
        p0 = w.pelvis().copy()
        run(w, A, typ, (0, 0.3, 0), 5.0)                                 # to the left
        p = w.pelvis()
        c, s = math.cos(p0[3]), math.sin(p0[3])
        left = -s * (p[0] - p0[0]) + c * (p[1] - p0[1])
        assert left > 0.6 and p[2] > 0.6, (typ, left, p)
        p0 = w.pelvis().copy()
        run(w, A, typ, (0.3, 0, 0.8), 3.0)                               # a walking turn to the left
        _, _, dyaw = rel(w, p0)
        assert 1.2 < dyaw < 3.0, (typ, dyaw)
        arms = upper(w).copy()                                           # the arms raised forward while it walks
        arms[w.L.ARMS.start - 12 + 0] = arms[w.L.ARMS.start - 12 + 7] = -1.2
        run(w, A, typ, (0.3, 0, 0), 4.0, arms=arms)
        assert w.pelvis()[2] > 0.6 and not w.unstable, (typ, w.pelvis())
        run(w, A, "walk", (0.3, 0, 0), 3.0)                              # handovers: Unitree's policy, the other
        other = "walk_agile" if typ == "walk_falcon" else "walk_falcon"  # walker, stand
        run(w, A, other, (0.3, 0, 0), 3.0)
        run(w, A, "walk", (0, 0, 0), 2.0)                                # to `stand` through Unitree's policy at rest
        act(w, A, "stand", np.r_[upper(w), 0, 0], 300)                   # (straight from a walker it falls: below)
        assert w.pelvis()[2] > 0.6 and not w.unstable and w.ref.failed is None, (typ, w.pelvis(), w.ref.failed)
        hold_typ, row = A.hold(w)
        assert hold_typ == "stand", hold_typ
        print(f"  {typ}: bounds vx [{lo[0]:g}, {hi[0]:g}] vy [{lo[1]:g}, {hi[1]:g}] wz [{lo[2]:g}, {hi[2]:g}]; ok")

    falls = 0                                                            # straight from a walker to `stand`: the
    for typ in ("walk_falcon", "walk_agile"):                            # platform's stance is not the walker's, and
        for t in (2.0, 3.0):                                             # `stand` does not balance (the instruction
            w.reset(); act(w, A, "stand", np.r_[upper(w), 0, 0], 50)     # says so)
            run(w, A, typ, (0, 0, 0), t)
            act(w, A, "stand", np.r_[upper(w), 0, 0], 300)
            falls += w.pelvis()[2] < 0.3
    assert falls >= 3, falls

    def episode():                                                       # determinism: the same rows, the same state
        w.reset()
        run(w, A, "walk_falcon", (0.4, 0.1, 0.2), 2.0)
        run(w, A, "walk_agile", (0.4, -0.1, 0.0), 2.0)
        run(w, A, "walk_falcon", (0, 0, 0), 1.0)
        return w.state_sha()
    assert episode() == episode()
    w.close()

    w, A = make("box-jump")                                              # the H1-2: no such policies
    assert "walk_falcon" not in A.types and "walk_agile" not in A.types and not w.robot.walkers, list(A.types)
    raw = A.to_raw("stand", np.r_[upper(w), 0, 0], w)
    raw[0] = WALK_AGILE
    try:
        w.step(raw)
        raise AssertionError("an H1-2 accepted the walk_agile mode")
    except ValueError:
        pass
    print("PASS walkers")


if __name__ == "__main__":
    main()
