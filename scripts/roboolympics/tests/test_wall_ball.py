"""wall-ball (v2): the referee says yes to a throw onto the target whose rebound is gripped in the air and kept, and no
to every cheap exit.

The positive is an INJECTION: the ball must leave the hand at about 20 m/s to come back five metres through the air
(a straight-arm swing of the H1-2 releases it at about half of that, see the family's report), and it returns at 12 m/s. What
is real: the release behind the line, the ball's flight in air (20 m/s at the hand, 17 m/s at the wall), its bounce on
the target, the rebound's flight back to the robot, the palm turned up with the grip closing, the hold. What is
injected: the ball's velocity at the release, and its last 0.8 m: when the rebound is that close it is put 0.12 m
above the palm, falling at 3 m/s. Negatives: do nothing; walking over the line; a hit outside the target; a throw
that bounces before the wall; a rebound onto the body; the ball taken back before the wall; letting go after the
catch; a fall during the hold."""
import numpy as np

import rcb_rfo
from rfo.testing import act, hold, make, move_robot, verdict

FAMILY = "wall-ball"


def main():
    inst = rcb_rfo.make_instance(FAMILY, 0)
    w, A = make(FAMILY)
    T = w.task
    text = " ".join([T.sentence, T.rules, T.venue, T.difficulty] + T.deviations)
    assert all("{" + k + "}" in text for k in T.p), [k for k in T.p if "{" + k + "}" not in text]
    assert inst["robot"] == "unitree_h1" and len(inst["deviations"]) >= 3
    p = T.p
    names = [j[:-6] for j in w.L.JOINTS[12:]]
    rest = A.current("stand", w)
    free = rest.copy(); free[-1] = 0.0
    up = rest.copy()
    up[names.index("right_elbow_roll")] = 1.57                              # the right palm turned up
    up[-1] = 1.0                                                            # ... and its grip asked to close

    def throw(vel=(20.0, 0.45, 3.0)):
        """A real release behind the line; then (the injection) the ball is given a velocity."""
        w.reset()
        act(w, A, "stand", rest, 20)
        act(w, A, "stand", free)
        if vel is not None:
            w.put("ball", w.pos("ball") + [0.1, 0.0, 0.1], vel=vel)

    def run(row, cond=lambda: False):
        while not w.done and not cond():
            act(w, A, "stand", row)
        return verdict(w)

    def onto_palm(speed=3.0):
        palm = w.d.site_xpos[w.robot.palm["right"]].copy()                  # the injection: the last 0.8 m replaced
        w.put("ball", palm + [0.0, 0.0, 0.12 + 0.0335], vel=(0.0, 0.0, -speed))

    def caught():
        throw()
        run(up, lambda: w.ref.has("target") and w.pos("ball")[0] < 0.8)
        assert w.ref.has("target") and not w.done and w.pos("ball")[2] > 0.5 and w.vel("ball")[0] < -8.0, verdict(w)
        onto_palm()
        run(up, lambda: w.ref.has("catch"))

    caught(); v = run(up); sha = w.state_sha()                              # the positive
    assert v["success"] and v["stages"] == ["release", "target", "catch", "hold"], v
    assert v["metrics"]["target_offset_m"] <= p["target_diameter_m"] / 2 and 15.0 < v["metrics"]["wall_speed_m_s"] < 19.0, v
    caught(); run(up)
    assert w.state_sha() == sha, "the positive is not deterministic"

    w.reset(); hold(w, A); v = verdict(w)                                   # nop
    assert v["failed"] == "time" and v["stages"] == [], v

    w.reset()                                                               # walking over the line with the ball
    while not w.done:
        act(w, A, "walk", np.r_[0.6, 0.0, 0.0, rest])
    assert verdict(w)["failed"] == "touched the ground on or beyond the line", verdict(w)

    throw((16.0, 0.36, 4.0)); v = run(up)                                   # onto the wall above the circle
    assert v["failed"] == "the ball hit the wall outside the target" and v["stages"] == ["release"], v
    throw((6.0, 0.1, 1.0)); v = run(up)                                     # a weak throw: it bounces before the wall
    assert v["failed"] == "the ball touched the ground" and v["stages"] == ["release"], v
    throw((20.0, 0.45, 2.6)); v = run(free)                                 # a good hit, the rebound comes back onto
    assert v["failed"] == "the rebound touched the body before it was gripped", v      # the body
    assert v["stages"] == ["release", "target"], v
    throw((16.0, 0.36, 3.2)); v = run(free)                                 # a good hit, nobody catches: it lands
    assert v["failed"] == "the ball touched the ground" and v["stages"] == ["release", "target"], v

    throw(None)                                                             # let go and taken back before the wall
    act(w, A, "stand", up, 20)                                              # (injection: put back on the palm): the
    onto_palm(speed=0.5)                                                    # grip does not take it
    v = run(up)
    assert v["failed"] == "the ball was touched again before it had hit the wall" and not w.holder("ball"), v

    caught(); act(w, A, "stand", up, 30); v = run(free)                     # caught, then let go
    assert v["failed"] == "the ball was dropped after the catch" and v["stages"] == ["release", "target", "catch"], v

    caught(); move_robot(w, z=0.40); v = run(up)                            # caught, then a fall (injection)
    assert v["failed"] == "fell" and v["stages"] == ["release", "target", "catch"], v
    print("PASS wall-ball")


if __name__ == "__main__":
    main()
