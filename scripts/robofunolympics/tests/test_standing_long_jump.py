"""standing-long-jump: the referee says no to standing still, to walking over the line, to a foot on or over the line,
to a shuffle forward before the jump, to one foot lifted before the other, to a "flight" made by pulling the feet up,
to a short jump, to a dive, to a jump that is spoilt by a step back, and to a landing that falls.

The positive is an INJECTION, not a solution: the standing robot is given a take-off velocity by hand
(rfo.testing.kick_robot: 3.5 m/s forward, 2.5 m/s up), really flies 0.5 s and really lands on its feet 1.5 m beyond the
line; at the touch-down its horizontal velocity is taken away by hand (a perfect landing); the stand that follows is
the robot's own (`stand` rows).

A REAL push-off is shown too (tests/g1_open_loop_jump.py: a crouch and an open-loop extension through `joints` and
`lowcmd` rows): the referee latches "take-off" (v1's pelvis rule refused every real push-off, the body being 0.3 m
ahead of the toes at toe-off); the jump has no flight or landing control and comes down on the head."""
import numpy as np

from g1_open_loop_jump import jump as real_jump
from rfo.testing import act, hold, kick_robot, make, move_robot, verdict


def jump(w, A, vx, vz, settle=True, before=None, angvel=(0.0, 0.0, 0.0), after=None):
    w.reset()
    hold(w, A, 0.3)
    if before:
        before()
        hold(w, A, 0.3)
    if w.done:
        return
    kick_robot(w, (vx, 0.0, vz), angvel)
    typ, row = A.hold(w)
    landed = False
    while not w.done:
        w.step(A.to_raw(typ, row, w))
        if not landed and w.ref.has("landing"):
            landed = True
            if settle:
                w.d.qvel[w.robot.fv:w.robot.fv + 2] = 0.0
            if after:
                hold(w, A, 0.2)
                after()


def main():
    w, A = make("standing-long-jump")
    p = w.task.p
    assert p["qualifying_mark_m"] == 1.32
    assert abs(w.task.privileged(w)["feet_front_x"] + p["toe_gap_m"]) < 1e-3                   # the toes behind the line
    hold(w, A)
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)          # nop
    jump(w, A, 3.5, 2.5)                                                                      # positive (injection)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["take-off", "landing", "stand"] and v["metrics"]["mark_m"] >= 1.32, v
    assert v["metrics"]["air_s"] > 0.45 and v["metrics"]["rise_m"] > 0.25, v
    print("  injected jump:", v["metrics"])
    sha = w.state_sha()
    jump(w, A, 3.5, 2.5)
    assert w.state_sha() == sha                                                               # determinism
    w.reset(); real_jump(w, A, act, knee=1.3, bias=0.05, lean=-0.4)                           # a real push-off
    v = verdict(w)
    assert v["stages"] == ["take-off"] and v["failed"] == "the landing was not on the feet", v
    assert v["metrics"]["air_s"] > 0.3 and v["metrics"]["rise_m"] > 0.15, v
    print("  real open-loop push-off:", v["metrics"], w.ref.events[-1])
    jump(w, A, 2.6, 2.5)                                                 # 1.1 m: short of the robot's height
    v = verdict(w)
    assert v["failed"] == "the jump is too short" and v["stages"] == ["take-off", "landing"] and 0.9 < v["metrics"]["mark_m"] < 1.32, v
    jump(w, A, 3.5, 2.5, settle=False)                                   # the landing at 3.5 m/s: down
    assert verdict(w)["failed"] == "fell" and verdict(w)["stages"] == ["take-off", "landing"], verdict(w)
    jump(w, A, 3.5, 2.5, after=lambda: move_robot(w, x=w.pelvis()[0] - 0.4))   # a step back after the landing
    assert verdict(w)["failed"] == "the jump is too short" and verdict(w)["stages"] == ["take-off", "landing"], verdict(w)
    jump(w, A, 3.5, 2.5, angvel=(0.0, 5.0, 0.0))                         # a dive
    assert verdict(w)["failed"] == "the landing was not on the feet" and verdict(w)["stages"] == ["take-off"], verdict(w)
    jump(w, A, 3.5, 2.5, before=lambda: move_robot(w, x=w.pelvis()[0] + 0.06))   # the toes 1 cm over the line
    assert verdict(w)["failed"] == "a foot on or over the take-off line" and verdict(w)["stages"] == [], verdict(w)
    jump(w, A, 3.5, 2.5, before=lambda: move_robot(w, x=w.pelvis()[0] + 0.025))  # 2.5 cm nearer the line: no foul
    assert verdict(w)["success"], verdict(w)
    jump(w, A, 3.5, 2.5, before=lambda: move_robot(w, x=w.pelvis()[0] - 0.5))    # moved back for a run-up
    assert verdict(w)["failed"] == "a step or shuffle before the take-off" and verdict(w)["stages"] == [], verdict(w)
    w.reset()                                                            # walking across the line
    rest = w.robot.rest[12:]
    while not w.done:
        act(w, A, "walk", np.r_[0.6, 0, 0, rest, 0, 0])
    assert verdict(w)["failed"] == "a foot left the ground before the take-off" and verdict(w)["stages"] == [], verdict(w)
    w.reset(); hold(w, A, 0.3)                                           # the feet pulled up: a flight, but no jump
    q = w.robot.arb.target().copy()
    for s in (0, 6):
        q[s], q[s + 3] = -1.6, 2.4
    w.d.qvel[w.robot.fv] = 3.0                                           # (even with a run-up's speed given by hand)
    while not w.done:
        act(w, A, "joints", np.r_[q, 0, 0])
    v = verdict(w)
    assert v["failed"] == "the flight was not a jump" and v["stages"] == [] and v["metrics"]["rise_m"] < 0.05, v
    print("  feet pulled up:", v["metrics"])
    print("PASS standing-long-jump")


if __name__ == "__main__":
    main()
