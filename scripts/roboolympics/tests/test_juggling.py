"""juggling (v2: keepie-uppie with a size-5 ball from the hand, ten touches in a row): the referee says no to holding
the ball, to dropping it on the ground, to a ball that only bounces on a still head (the passive case: the bounces
die away), to touches that do not send the ball up a ball's diameter, to a hand after the drop, to the trunk and to a
ball that rests on the robot; yes to ten touches by the head and a foot, each sending the ball up.

The positive is an INJECTION: no juggling controller exists for the G1. Real: the right hand really lets go of the ball
(the drop); the ball really falls onto the head ten times and rises again, and nothing else touches it. Injected: after
the drop the ball is put above the head; each time it comes off the head its velocity is set to 2.6 m/s straight up
(what a nod would have given it) and it is put back over the middle of the head. A touch by a foot is shown to count
in the same way (one touch on the right toe)."""
import numpy as np

from rfo.testing import act, hold, make, move_robot, verdict

FAMILY = "juggling"
R = 0.11


def head_top(w):
    return w.d.site_xpos[w.robot.head_site] + np.array([-0.05, 0.0, 0.09])


def toe(w):
    return w.d.site_xpos[w.robot.foot_site["right"]] + np.array([0.16, 0.0, 0.03])


def juggle(w, A, n=10, up=2.6, drop_at=1.0, above=None, first_drop=0.35, last=(0.0, 0.0)):
    """Hold the ball for drop_at seconds, let go (real), then put the ball `first_drop` above the head (or above(w)),
    falling. Each time the ball has touched the robot and come off it again, its velocity is set to `up` m/s straight
    up (None: left alone) and it is put back over the same spot, for n touches (the n-th also gets the horizontal
    velocity `last`)."""
    rest = w.robot.rest[12:]
    placed, k, spot = False, 0, None
    while not w.done:
        act(w, A, "stand", np.r_[rest, 0, float(w.t < drop_at)])
        if w.done:
            break
        tr = w.task.trackers
        if tr["dropped"] is None:
            continue
        if not placed:
            placed = True
            spot = head_top(w) if above is None else above(w)
            w.launch("ball", spot + [0.0, 0.0, R + first_drop], (0.0, 0.0, -0.5))
            continue
        if up is not None and tr["touch"].count > k and k < n and not w.ref.touching(w.task.ball, w.ref.robot_mask):
            k = tr["touch"].count                           # a touch has happened and the ball is off again
            w.put("ball", (spot[0], spot[1], w.pos("ball")[2]), vel=(last[0], last[1], up) if k >= n else (0.0, 0.0, up))


def main():
    w, A = make(FAMILY)
    p, m = w.task.p, w.m
    assert abs(m.geom("ball").size[0] - 0.11) < 1e-9 and abs(m.body("ball").mass[0] - 0.43) < 1e-9
    assert w.held["right"] == "ball" and p["touches"] == 10

    hold(w, A, grips=[0, 1])                                               # nop: the ball stays in the hand
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == [], v

    w.reset(); juggle(w, A)                                                # positive (injection, see the docstring)
    v = verdict(w)
    assert v["success"] and v["stages"] == [f"touch {i + 1}" for i in range(10)], v
    sha, t_ok = w.state_sha(), w.t
    w.reset(); juggle(w, A)
    assert w.state_sha() == sha                                            # the same run again: the same state

    w.reset(); juggle(w, A, up=None, first_drop=0.60)                      # the passive case: bouncing on a still head
    v = verdict(w)
    passive = v["metrics"]["touches"]
    assert not v["success"] and passive < 4, v
    assert v["failed"] in ("the ball was touched again before it had risen enough", "the ball touched the ground",
                           "the ball was touched by the trunk", "handball"), v
    passive_end = v["failed"]

    w.reset(); juggle(w, A, n=1, up=2.3, above=toe, first_drop=0.20)       # a foot counts: one touch on the right toe
    v = verdict(w)
    ev = [e for e in w.ref.events if e["ev"] == "stage"]
    assert v["stages"] == ["touch 1"] and v["failed"] == "the ball touched the ground", v

    w.reset(); juggle(w, A, n=9, last=(1.5, 0.0))                          # nine touches, the ninth sent off forwards
    v = verdict(w)
    assert v["failed"] == "the ball touched the ground" and v["stages"] == [f"touch {i + 1}" for i in range(9)], v

    w.reset(); juggle(w, A, up=None, first_drop=3.0)                       # passive again, from a 3 m toss' height
    v = verdict(w)
    assert not v["success"] and v["metrics"]["touches"] <= 1, v              # only the first bounce counts: no strike
    passive_high = v["metrics"]["touches"]

    w.reset(); juggle(w, A, up=1.2)                                        # touches that send the ball up 7 cm
    v = verdict(w)
    assert v["failed"] == "the ball was touched again before it had risen enough" and v["stages"] == [], v

    w.reset()                                                              # dropped: straight to the ground
    hold(w, A, 0.5, grips=[0, 1]); hold(w, A, grips=[0, 0])
    v = verdict(w)
    assert v["failed"] == "the ball touched the ground" and v["stages"] == [], v

    w.reset()                                                              # onto the left hand after the drop
    hold(w, A, 0.5, grips=[0, 1]); hold(w, A, 0.02, grips=[0, 0])
    w.launch("ball", w.d.site_xpos[w.robot.palm["left"]] + [0.0, 0.60, 0.25], (0.0, -2.5, 0.0)); hold(w, A, grips=[0, 0])
    v = verdict(w)
    assert v["failed"] == "handball" and "left_hand" in w.ref.events[-1]["parts"], (v, w.ref.events[-1])

    w.reset()                                                              # onto the chest after the drop
    hold(w, A, 0.5, grips=[0, 1]); hold(w, A, 0.02, grips=[0, 0])
    w.launch("ball", w.pos("torso_link") + [0.60, 0.0, 0.12], (-3.5, 0.0, 0.5)); hold(w, A, grips=[0, 0])
    v = verdict(w)
    assert v["failed"] == "the ball was touched by the trunk" and v["stages"] == [], v

    w2, A2 = make(FAMILY, carry_s=0.002)                                   # below a real contact's time: a carry
    juggle(w2, A2)
    assert verdict(w2)["failed"] == "the ball was carried", verdict(w2)

    w.reset()                                                              # the ball cannot be gripped again
    hold(w, A, 0.5, grips=[0, 1]); hold(w, A, 0.05, grips=[0, 0])
    w.put("ball", w.d.site_xpos[w.robot.palm["right"]] + [0.0, 0.0, 0.0]); hold(w, A, 0.02, grips=[0, 1])
    assert w.held["right"] is None, w.held

    w.reset(); hold(w, A, 0.2, grips=[0, 1]); move_robot(w, z=0.30); hold(w, A, 0.5, grips=[0, 1])   # on the ground
    assert verdict(w)["failed"] == "fell", verdict(w)
    print(f"injection: ten touches at t = {t_ok:.2f} s; a ball bouncing on a still head makes {passive} counted "
          f"touch(es) from 0.6 m and {passive_high} from 3 m (then: {passive_end})")
    print(f"PASS {FAMILY}")


if __name__ == "__main__":
    main()
