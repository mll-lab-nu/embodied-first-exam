"""long-rope (跳长绳): the referee says no to standing still (the rope runs into the shins), to jumping too late (the
rope catches the feet: a miss ends the attempt even though the turners go on), to a crouch under the rope, to
leaving the middle of the rope, to lying down, to a fall in a jump, and to a landing on the back after the last jump;
it counts one jump per turn of the rope however often the robot hops; yes to ten jumps in a row and a landing.

The positive is an INJECTION, not a solution: the robot stands in `stand` rows; each time the rope (read from the
simulator) is 0.18 s from passing under it, the robot is given 2.0 m/s upwards by hand (rfo.testing.kick_robot);
it really flies about 0.4 s, the real rope (a free chain of 40 capsules turned by the scripted hands) really passes
under both its feet about 8 cm below the soles and over its head, and it really lands on its feet, ten times.

A REAL solution is shown too: the reference controller (oracles/long-rope/oracle.py: `joints` and `lowcmd` rows, a
periodic hop from a balanced crouch timed to the rope, closed loop on privileged state) jumps the rope ten times and
lands and stands; the referee says success. After the tenth jump the robot must land on its feet and stand
still 0.5 s before the rope (still turning) comes round again."""
import importlib.util
import pathlib

import numpy as np

from rfo.tasks.long_rope import rope_point_at_y
from rfo.testing import act, hold, kick_robot, make, move_robot, verdict

FAMILY = "long-rope"


def hopper(w, A, vz=2.0, lead=0.18, extra=False, angvel=(0.0, 0.0, 0.0), last_angvel=None, before=None):
    """The injected jumper: a kick upwards when the rope at the robot's middle is `lead` s from passing under it
    (its speed from the last control step), once per turn (re-armed when the rope is above the axis); extra: one more
    hop half a turn later (the rope above). before(w): called every control step."""
    w.reset()
    typ, row = A.hold(w)
    hz, prev, armed, kicks, extra_at = w.task.g["hz"], None, True, 0, None
    n = int(w.task.p["jumps_required"])
    while not w.done:
        if before is not None:
            before(w)
            if w.done:
                break
        pt = rope_point_at_y(w.task._rope_nodes(w), 0.0)
        if pt is not None and prev is not None:
            vx = (pt[0] - prev[0]) / w.CONTROL_DT
            if pt[2] > hz:
                armed = True
            if (armed and pt[2] < hz and pt[0] > 0 and vx < -0.5 and pt[0] / -vx <= lead
                    and not w.ref.airborne() and kicks < n):
                kicks += 1
                kick_robot(w, (0.0, 0.0, vz), last_angvel if (last_angvel and kicks == n) else angvel)
                armed = False
                extra_at = w.t + 0.5 if extra else None
            elif extra_at is not None and w.t >= extra_at and not w.ref.airborne():
                kick_robot(w, (0.0, 0.0, 1.2))
                extra_at = None
        prev = pt
        w.step(A.to_raw(typ, row, w))


class _Session:
    """What an oracle's solve(s) uses of rcb_rfo.Session, on a world of this test."""

    def __init__(self, w, A):
        self.world, self.A = w, A

    @property
    def done(self):
        return self.world.done

    def step(self, typ, row):
        act(self.world, self.A, typ, row)
        return self.world.done


def oracle():
    src = pathlib.Path(__file__).resolve().parent.parent / "oracles" / FAMILY / "oracle.py"
    spec = importlib.util.spec_from_file_location("long_rope_oracle", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    w, A = make(FAMILY)
    p, g, m = w.task.p, w.task.g, w.m
    assert p["turner_distance_m"] == 3.6 and p["rope_length_m"] >= 6.0 and abs(g["free"] - 3.2) < 1e-9
    assert abs(m.body("rope0").mass[0] * 40 - 3.2 * 0.06) < 1e-9 and abs(m.geom("rope0").size[0] - 0.005) < 1e-12
    hands = [w.d.xpos[m.body(n).id] for n in ("hand_a", "hand_b")]
    assert abs(hands[1][1] - hands[0][1] - 2.8) < 1e-9 and abs(np.hypot(hands[0][0], hands[0][2] - 1.0) - 0.4) < 1e-9
    assert not w.ref.touching(w.task.rope, w.task.robot_sel)                 # the rope behind, clear of the robot

    hold(w, A)                                                               # nop: the rope runs into the legs
    v = verdict(w)
    assert v["failed"] == "the rope touched the robot" and v["stages"] == [], v
    t_nop = w.ref.events[-1]["t"]
    assert 0.8 < t_nop < 1.1, t_nop
    print("  nop:", v["failed"], w.ref.events[-1])

    hopper(w, A)                                                             # positive (injection)
    v = verdict(w)
    assert v["success"] and v["metrics"]["jumps"] == 10 and v["stages"][-2:] == ["landing", "stand"], v
    unders = [e for e in w.ref.events if e["ev"] == "under"]
    assert len(unders) == 20 and min(e["clearance_m"] for e in unders) > 0.03, unders
    print("  injected: 10 jumps, landing and stand at %.2f s; clearance %.3f-%.3f m" % (
        w.ref.time, min(e["clearance_m"] for e in unders), max(e["clearance_m"] for e in unders)))
    sha = w.state_sha()
    hopper(w, A)
    assert w.state_sha() == sha                                              # determinism

    w.reset()                                                                # a real controller (the oracle)
    oracle().solve(_Session(w, A))
    v = verdict(w)
    unders = [e for e in w.ref.events if e["ev"] == "under"]
    assert v["success"] and v["metrics"]["jumps"] == 10 and len(unders) == 20, v
    print("  real controller: 10 jumps, landing and stand at %.2f s; clearance %.3f-%.3f m" % (
        w.ref.time, min(e["clearance_m"] for e in unders), max(e["clearance_m"] for e in unders)))

    hopper(w, A, extra=True)                                                 # two hops per turn: one jump per turn
    v = verdict(w)
    hops = sum(1 for e in w.ref.events if e["ev"] == "under") // 2
    assert v["metrics"]["jumps"] == hops and hops >= 3, v
    print("  two hops per turn:", v["failed"] or "success", "jumps", v["metrics"]["jumps"])

    hopper(w, A, lead=0.02)                                                  # too late: the rope catches the feet
    v = verdict(w)
    assert v["failed"] == "the rope touched the robot" and v["stages"] == [], v
    assert set(w.ref.events[-1]["parts"]) & {"left_foot", "right_foot", "left_shin", "right_shin"}, w.ref.events[-1]

    hopper(w, A, vz=1.0)                                                     # too low a hop
    v = verdict(w)
    assert v["failed"] == "the rope touched the robot" and v["stages"] == [], v

    w.reset()                                                                # duck: a deep, balanced squat
    h, k, a = oracle().balanced_crouch(w, 1.7, w.robot.rest[12:])
    q0 = w.robot.arb.target().copy()
    q = q0.copy()
    for i in (0, 6):
        q[i], q[i + 3], q[i + 4] = h, k, a
    while not w.done:
        f = min(1.0, w.k / 50)
        act(w, A, "joints", np.r_[q0 + f * (q - q0), 0, 0])
    v = verdict(w)
    assert v["failed"] == "the rope touched the robot" and v["stages"] == [], v
    print("  crouch:", v["failed"], w.ref.events[-1].get("parts", ""), "pelvis z %.2f" % w.pelvis()[2])

    w.reset(); hold(w, A, 0.2); move_robot(w, x=1.6); hold(w, A)              # out of the rope's sweep
    v = verdict(w)
    assert v["failed"] == "the robot left the centre zone" and v["stages"] == [], v
    w.reset(); hold(w, A, 0.2); move_robot(w, y=0.7); hold(w, A)              # towards a turner
    assert verdict(w)["failed"] == "the robot left the centre zone", verdict(w)
    w.reset(); hold(w, A, 0.2); move_robot(w, z=0.2); hold(w, A)              # lying on the floor
    v = verdict(w)
    assert v["failed"] == "fell" and v["stages"] == [], v

    hopper(w, A, angvel=(0.0, 6.0, 0.0))                                      # a jump that tips over
    v = verdict(w)
    assert v["failed"] in ("fell", "the rope touched the robot") and not v["success"], v
    print("  tipping jump:", v["failed"], len(v["stages"]))

    def bounce(w):                                                           # landed, but no stand: a hop
        if w.ref.has("landing") and w.ref.time > bounce.t and not w.ref.airborne():
            kick_robot(w, (0.0, 0.0, 1.0))
            bounce.t = w.ref.time + 0.25
    bounce.t = 0.0
    hopper(w, A, before=bounce)
    v = verdict(w)
    assert v["stages"][-1] == "landing" and v["failed"] == "the rope touched the robot", v
    print("  no stand after the landing:", v["failed"])

    hopper(w, A, last_angvel=(0.0, -6.0, 0.0))                                # the last jump: a landing on the head
    v = verdict(w)
    assert v["stages"][-1] == "jump 10" and v["failed"] == "the landing was not on the feet", v
    print("  bad last landing:", v["failed"])
    print("PASS", FAMILY)


if __name__ == "__main__":
    main()
