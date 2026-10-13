"""catch (v2): the referee says yes to a fly ball gripped in flight and kept, and no to every cheap exit.

The positive is an INJECTION: no controller here walks the H1-2 the 1.25 m to where the ball comes down and puts its
palm on the ball's line within the grip's 3.5 cm in the three seconds of the flight. What is
real: the launch from 40 m, the ball's flight in air over its 11 m apex, the robot turning its right palm up and
closing the grip, the grip's own conditions, the hold. What is injected: when the ball has come down to 3 m its last
metres are replaced: it is put 0.12 m above the palm, falling at 3 m/s. Measured here too: untouched, the ball lands
1.25 m from where the robot stands (the family's "within 3 m"). Negatives: do nothing (the ball lands); a ball that
hits the body; a touch before the ball is past the top of its arc; letting go after the catch;
a fall during the hold."""
import numpy as np

import rcb_rfo
from rfo.testing import act, hold, make, move_robot, verdict

FAMILY = "catch"


def main():
    inst = rcb_rfo.make_instance(FAMILY, 0)
    w, A = make(FAMILY)
    T = w.task
    text = " ".join([T.sentence, T.rules, T.venue, T.difficulty] + T.deviations)
    assert all("{" + k + "}" in text for k in T.p), [k for k in T.p if "{" + k + "}" not in text]
    assert inst["robot"] == "unitree_h1" and inst["rulebook"] and len(inst["deviations"]) >= 3
    p = T.p
    names = [j[:-6] for j in w.L.JOINTS[12:]]
    up = A.current("stand", w)
    up[names.index("right_elbow_roll")] = 1.57                              # the right palm turned up
    up[-1] = 1.0                                                            # ... and its grip asked to close

    hold(w, A)                                                              # nop: the real fly ball, untouched
    v = verdict(w)
    assert v["failed"] == "the ball touched the ground" and v["stages"] == [], v
    assert v["metrics"]["landed_from_start_m"] <= p["land_within_m"], v     # FAMILIES.md: within 3 m of the robot
    land = w.ref.events[-1]
    assert 2.8 < land["t"] - p["launch_time_s"] < 3.2, land                 # about three seconds in the air
    print("fly ball: lands %.2f m from the robot, %.2f s after the launch" % (v["metrics"]["landed_from_start_m"],
                                                                             land["t"] - p["launch_time_s"]))

    def fly(until_z=3.0):
        """The real launch and flight (the palm up, the grip asked for) until the ball has come down to until_z."""
        w.reset()
        apex = 0.0
        while not w.done and not (T.trackers["falling"] and w.pos("ball")[2] < until_z):
            act(w, A, "stand", up)
            apex = max(apex, float(w.pos("ball")[2]))
        return apex

    def onto_palm(speed=3.0, dz=0.12):
        palm = w.d.site_xpos[w.robot.palm["right"]].copy()                  # the injection: the last metres replaced
        w.put("ball", palm + [0.0, 0.0, dz + 0.0365], vel=(0.0, 0.0, -speed))

    def positive():
        apex = fly()
        assert 10.0 < apex < 12.5 and not w.holder("ball"), apex
        v0 = float(np.linalg.norm(w.vel("ball")))
        onto_palm()
        while not w.done:
            act(w, A, "stand", up)
        return verdict(w), w.state_sha(), v0

    v, sha, v0 = positive()
    assert v["success"] and v["stages"] == ["catch", "hold"], v
    assert 14.0 < v0 < 18.0, v0                                             # the speed the real ball had at 3 m
    assert positive()[1] == sha, "the positive is not deterministic"

    fly()                                                                   # onto the trunk (injection)
    x, y, z = w.pelvis()[:3]
    w.put("ball", (x + 0.03, y, z + 1.1), vel=(0, 0, -3.0))
    while not w.done:
        act(w, A, "stand", up)
    assert verdict(w)["failed"] == "the ball touched the body before it was gripped", verdict(w)

    w.reset()                                                               # touched on its way up (injection: the
    while not w.done and w.t < p["launch_time_s"] + 0.3:                    # rising ball is put under the hand)
        act(w, A, "stand", up)
    onto_palm(speed=-4.0, dz=-0.14)
    while not w.done:
        act(w, A, "stand", up)
    v = verdict(w)
    assert v["failed"] == "the ball was touched before it had passed the top of its arc" and v["stages"] == [], v

    fly(); onto_palm()                                                      # caught, then let go
    while not w.done and not w.ref.has("catch"):
        act(w, A, "stand", up)
    act(w, A, "stand", up, 30)
    free = up.copy(); free[-1] = 0.0
    act(w, A, "stand", free, 3)
    assert verdict(w)["failed"] == "the ball was dropped after the catch" and verdict(w)["stages"] == ["catch"], verdict(w)

    fly(); onto_palm()                                                      # caught, then a fall (injection)
    while not w.done and not w.ref.has("catch"):
        act(w, A, "stand", up)
    move_robot(w, z=0.40)
    while not w.done:
        act(w, A, "stand", up)
    assert verdict(w)["failed"] == "fell" and verdict(w)["stages"] == ["catch"], verdict(w)
    print("PASS catch")


if __name__ == "__main__":
    main()
