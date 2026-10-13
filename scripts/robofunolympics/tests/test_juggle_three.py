"""juggle-three (v2): the referee counts ten catches of a three-ball cascade and refuses every cheap exit.

The positive is an INJECTION: no controller of the G1 throws a ball from the palm it was caught on so that it lands on
the other palm, three balls in turn. What is real: the hands (still, the forearms level, the palms up), the grip's
own release and catch (a ball is gripped only when it arrives within 3.5 cm of the palm, slower than 6 m/s), the
venue's first throw, every flight in air, the order of the events. What is injected: at each release the ball is
put 0.20 m in front of the palm that let it go and given the velocity of an arc that rises 0.5 m and comes down on the
other palm (in front, because the hands do not move: a ball that leaves a palm on the line between the palms meets
the ball that is coming down on it). A hand lets go of its ball 0.30 s before the next ball reaches it.
Negatives: do nothing (the first ball falls); a ball thrown up that comes down on, or is gripped by, the hand that
threw it; a low hand-to-hand pass (no flight); a catch out of the cascade's order; the waiting ball pushed before its
launch (a real arm motion); a ball that lands on the body; a fall."""
import math

import numpy as np

import rcb_rfo
from rfo.testing import act, hold, make, move_robot, verdict

FAMILY = "juggle-three"
G = 9.81
OTHER = {"left": "right", "right": "left"}
I = {"left": 0, "right": 1}


def main():
    inst = rcb_rfo.make_instance(FAMILY, 0)
    w, A = make(FAMILY)
    T, p = w.task, w.task.p
    text = " ".join([T.sentence, T.rules, T.venue, T.difficulty] + T.deviations)
    assert all("{" + k + "}" in text for k in p), [k for k in p if "{" + k + "}" not in text]
    assert inst["robot"] == "unitree_g1" and len(inst["deviations"]) >= 3
    R = p["ball_diameter_m"] / 2
    pose = A.current("stand", w)[:-2]                                       # the start pose: forearms level, palms up

    def palm(side):
        return w.d.site_xpos[w.robot.palm[side]].copy() + [0.0, 0.0, 0.022 + R]     # a ball's centre lying on it

    def arc(name, to, rise, forward=0.20):
        """The injection: the ball is put `forward` in front of where it was let go and given the velocity of an arc
        that rises `rise` and comes down on the palm `to`."""
        p0, target = w.pos(name) + [forward, 0.0, 0.0], palm(to)
        vz = math.sqrt(2 * G * rise)
        t = (vz + math.sqrt(vz * vz + 2 * G * max(float(p0[2] - target[2]), -vz * vz / (2 * G)))) / G
        w.put(name, p0, vel=((target[0] - p0[0]) / t, (target[1] - p0[1]) / t, vz))

    def arrives_in(name, side):
        """Seconds until the flying ball is down at the palm's height (privileged ballistics)."""
        z, vz = w.pos(name)[2] - palm(side)[2], w.vel(name)[2]
        disc = vz * vz + 2 * G * z
        return (vz + math.sqrt(disc)) / G if disc > 0 else 0.0

    def step(grip, n=1):
        act(w, A, "stand", np.r_[pose, grip["left"], grip["right"]], n)

    def cascade(lead=0.30, rise={"left": 0.5, "right": 0.5}, blind=None):
        w.reset()
        grip, cool = {"left": 1.0, "right": 1.0}, {"left": 0, "right": 0}
        while not w.done:
            tr = T.trackers
            for side in ("left", "right"):
                cool[side] = max(0, cool[side] - 1)
                if cool[side] == 0 and not (side == blind and not w.held[side]):
                    grip[side] = 1.0                                         # ready to catch (or still holding)
                mine = w.held[side]
                coming = [n for n in ("ball_a", "ball_b", "ball_c")
                          if tr[n]["at"] == "flight" and tr[n]["by"] == OTHER[side] and w.vel(n)[2] < 0]
                if mine and coming and min(arrives_in(n, side) for n in coming) <= lead:
                    grip[side], cool[side] = 0.0, 10                         # let go ...
                    step(grip)
                    if w.done:
                        break
                    arc(mine, OTHER[side], rise[side])                       # ... on an arc to the other palm
            else:
                step(grip)
        return verdict(w)

    v = cascade(); sha = w.state_sha()                                      # the positive: ten catches
    assert v["success"] and v["stages"] == ["first catch", "half way", "ten catches"] and v["metrics"]["catches"] == 10, v
    catches = [e for e in w.ref.events if e["ev"] == "catch"]
    assert [e["ball"][-1] for e in catches] == list("abcabcabca"), catches
    assert [e["hand"] for e in catches] == ["left", "right"] * 5, catches
    assert all(e["rise_m"] >= p["min_rise_m"] for e in catches), catches
    cascade()
    assert w.state_sha() == sha, "the positive is not deterministic"

    w.reset(); hold(w, A); v = verdict(w)                                   # nop: the first ball comes down on a
    assert v["failed"] in ("a ball touched the ground", "a ball that came down on a hand was not caught") \
        and v["stages"] == [], v                                            # full hand: not caught, it falls

    both, left_open, right_open = {"left": 1.0, "right": 1.0}, {"left": 0.0, "right": 1.0}, {"left": 1.0, "right": 0.0}

    w.reset(); step(both, 20); step(left_open)                              # thrown straight up, it comes down on
    w.put("ball_b", w.pos("ball_b"), vel=(0.0, 0.0, 3.0))                   # the hand that threw it
    step(left_open, 10)
    while not w.done and w.t < 1.9:
        step(both)
    v = verdict(w)
    assert v["failed"] == "a ball in flight was touched again by the hand that threw it", v

    w.reset(); step(both, 20); step(left_open)                              # ... and gripped by it before it touches
    w.put("ball_b", w.pos("ball_b"), vel=(0.0, 0.0, 3.0))                   # (injection: at its apex the ball is put
    step(left_open, 30)                                                     # 5 mm above that palm, sinking)
    w.put("ball_b", palm("left") + [0.0, 0.0, 0.005], vel=(0.0, 0.0, -0.3))
    step(both, 3)
    v = verdict(w)
    assert v["failed"] == "a ball was gripped by the hand that let go of it", v

    w.reset(); step(both, 20); step(left_open)                              # the left hand throws its ball high, the
    arc("ball_b", "right", 1.2)                                             # right hand passes its ball across low:
    step(left_open, 9); step({"left": 0.0, "right": 0.0})                   # a pass, not a throw
    arc("ball_c", "left", 0.08)
    for _ in range(40):
        if not w.done:
            step(right_open)
    v = verdict(w)
    assert v["failed"] == "a ball was gripped before it had made its flight" and v["stages"] == [], v

    v = cascade(blind="left")                                               # the left hand throws but never catches:
    assert v["failed"] in ("a catch out of the cascade's order", "a ball that came down on a hand was not caught") \
        and v["stages"] == [], v                                            # the red ball lies on the open left palm
    assert w.ref.events[-1]["ball"] in ("ball_a", "ball_b"), w.ref.events[-1]

    w.reset(); step(both, 20); step(left_open)                              # a ball laid on the other palm and left
    w.put("ball_b", palm("right") + [0.12, 0.0, 0.01], vel=(0.0, 0.0, 0.0))  # there ungripped (the carry of a pass)
    while not w.done and w.t < 1.9:
        step(left_open)
    v = verdict(w)
    assert v["failed"] in ("a ball that came down on a hand was not caught", "a ball touched the ground",
                           "a ball in flight touched the body"), v

    w.reset(); step(both, 20)                                               # the right hand lifted into the waiting
    up = pose.copy()                                                        # ball (a real arm motion)
    names = [j[:-6] for j in w.L.JOINTS[12:]]
    up[names.index("right_elbow")] -= 0.5
    while not w.done and w.t < 1.5:
        act(w, A, "stand", np.r_[up, 1.0, 1.0])
    assert verdict(w)["failed"] == "the waiting ball was touched before its launch", verdict(w)

    w.reset(); step(both, 20); step(left_open)                              # a ball that comes down on the head
    x, y = w.pelvis()[:2]                                                   # (injection)
    w.put("ball_b", (x + 0.02, y, 1.9))
    while not w.done and w.t < 1.9:
        step(left_open)
    v = verdict(w)
    assert v["failed"] == "a ball in flight touched the body", v

    w.reset(); step(both, 20); move_robot(w, z=0.30)                        # a fall (injection)
    while not w.done and w.t < 1.9:
        step(both)
    assert verdict(w)["failed"] == "fell", verdict(w)
    print("PASS juggle-three")


if __name__ == "__main__":
    main()
