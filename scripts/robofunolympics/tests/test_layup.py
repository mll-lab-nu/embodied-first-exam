"""layup (v2, FIBA, the Unitree H1-2): the referee says yes to at most two steps with the ball, a take-off, a release
in the air inside the no-charge semi-circle's radius of the ring, and the ball down through the official ring; no to a
third step, to the same feet twice in a row, to a release from the floor, in the air without a take-off or too far
from the ring, to a miss, a second touch, a ball that comes up through the ring, a fall.

The positive is an INJECTION, not a solution (the robot has no jump): the robot really raises the ball arm (`stand`
mode) and really takes two steps on its walking gait (two real touchdowns: the referee's step count); it is then
teleported so that the ball is 0.9 m from the ring's axis and given a take-off velocity of 2.6 m/s upwards (a "ghost"
jump); it really lets go of the ball at the apex of that flight, where the ball's velocity is set to the toss that an
arm would give it (4.4 m/s). The flight of the body, the release in the air, the ball's flight over the real ring and
the landing are physics."""
import math

import numpy as np

from rfo.scene import OFFICIAL
from rfo.testing import act, hold, kick_robot, make, move_robot, verdict

BALL = OFFICIAL["basketball"]
UP = np.array([-2.5, -0.6, 0.0, 1.57, 0.0, 0.0, 0.0])          # right arm up and forwards, the ball above the head
BENT = np.array([-2.5, -0.6, 0.0, -0.5, 0.0, 0.0, 0.0])        # ... the elbow bent: the hand out of the ball's way
THIRD = "travelling: a third step with the ball in the hand"
SAME = "travelling: the same foot touched the floor twice in a row"
GROUND = "the ball was let go with the robot not in the air"
NO_JUMP = "the ball was let go in the air without a take-off"
FAR = "the ball was let go too far from the ring"
FLOOR = "the ball touched the floor"
RETOUCH = "the ball was touched again after the release"
BELOW = "the ball came up through the ring from below"


def row(w, right=None, grip=1.0, cmd=None):
    up = w.robot.rest[12:27].copy()
    if right is not None:
        up[8:15] = right
    out = np.r_[up, 0.0, grip]
    return out if cmd is None else np.r_[cmd, out]


def arm_up(w, A, seconds=1.5, settle=1.0):
    rest = w.robot.rest[20:27]
    n = int(seconds * 100)
    for i in range(1, n + 1):
        act(w, A, "stand", row(w, rest + (UP - rest) * i / n))
    act(w, A, "stand", row(w, UP), int(settle * 100))


def shift(w, x):
    """Injection: teleport the robot and the ball it grips so that the ball's centre is at x."""
    pel, b = w.pelvis(), w.pos("ball")
    qa, _ = w.free["ball"]
    quat = w.d.qpos[qa + 3:qa + 7].copy()
    move_robot(w, x=pel[0] + x - b[0])
    tv = w.task.trackers["travel"]                       # (the teleport is not a slide of the feet)
    tv.anchor = {k: (None if v is None else [v[0] + x - b[0], v[1]]) for k, v in tv.anchor.items()}
    w.put("ball", b + [x - b[0], 0.0, 0.0], quat=quat, vel=w.vel("ball"))


def two_steps(w, A):
    tr = w.task.trackers["travel"]
    while len(tr.steps) < 2 and not w.done:
        act(w, A, "walk", row(w, UP, cmd=(0.8, 0.0, 0.0)))
    act(w, A, "stand", row(w, UP))


def jump(w, A, vz=2.6, vx=0.4, k_rel=26, wide=0.0, after=None):
    """The ghost take-off; the release k_rel control steps later (about the apex), with the toss injected (`wide` of the ring's centre)."""
    h = w.task.hoop
    kick_robot(w, (vx, 0.0, vz))
    for k in range(1, 400):
        if w.done:
            return
        act(w, A, "stand", row(w, UP if k < k_rel + 4 else BENT, grip=1.0 if k < k_rel else 0.0))
        if k == k_rel and not w.done:
            b, T = w.pos("ball"), 0.75
            w.put("ball", b, vel=(1.06 * (h["x"] - b[0]) / T, 1.06 * (h["y"] + wide - b[1]) / T, 4.0))
        if after is not None and k == k_rel + 12 and not w.done:
            after(w)


def main():
    w, A = make("layup")
    p, h = w.task.p, w.task.hoop
    tr = lambda: w.task.trackers                                              # noqa: E731
    assert p["start_to_ring_m"] == 3.0 and p["layup_radius_m"] == 1.25 and p["ring_height_m"] == 3.05

    hold(w, A)                                                                # nop
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)
    assert tr()["travel"].steps == [], tr()["travel"].steps                   # standing still is no step

    def positive():
        w.reset(); arm_up(w, A); two_steps(w, A)
        assert len(tr()["travel"].steps) == 2 and {s[1] for s in tr()["travel"].steps} == {"left", "right"}, tr()["travel"].steps
        shift(w, h["x"] - 0.9); jump(w, A)
    positive()
    v = verdict(w)
    assert v["success"] and v["stages"] == ["approach", "release in the air", "through the ring"], (v, w.ref.events)
    rel = next(e for e in w.ref.events if e.get("stage") == "release in the air")
    assert rel["air_s"] > 0.2 and rel["ball_to_ring_m"] < p["layup_radius_m"] and rel["ball_height_m"] < p["ring_height_m"], rel
    assert tr()["takeoff_vz"] > 2.0 and w.t < 6.0, (tr()["takeoff_vz"], w.t)
    sha = w.state_sha()
    positive()
    assert w.state_sha() == sha                                               # deterministic

    w.reset(); arm_up(w, A)                                                   # walking on with the ball: a third step
    while not w.done:
        act(w, A, "walk", row(w, UP, cmd=(0.8, 0.0, 0.0)))
    v = verdict(w)
    assert v["failed"] == THIRD and len(tr()["travel"].steps) == 3 and v["metrics"]["pelvis_to_ring_m"] > 2.0, (v, tr()["travel"].steps)

    w.reset(); arm_up(w, A)                                                   # two hops on both feet (ghost jumps)
    for _ in range(2):
        kick_robot(w, (0.0, 0.0, 1.5)); hold(w, A, 1.0)
    assert verdict(w)["failed"] == SAME and [s[1] for s in tr()["travel"].steps] == ["both", "both"], (verdict(w), tr()["travel"].steps)

    w.reset(); arm_up(w, A); shift(w, h["x"] - 0.9); hold(w, A, 0.3)          # let go under the ring, from the floor
    hold(w, A, 0.1, grips=(0, 0))
    assert verdict(w)["failed"] == GROUND and verdict(w)["stages"] == ["approach"], verdict(w)

    w.reset(); arm_up(w, A); shift(w, h["x"] - 0.9)                           # in the air without a take-off: the
    move_robot(w, z=w.pelvis()[2] + 0.35); hold(w, A, 0.1)                    # robot lifted 0.35 m and dropped
    hold(w, A, 0.02, grips=(0, 0))
    assert verdict(w)["failed"] == NO_JUMP, (verdict(w), tr()["takeoff_vz"])

    w.reset(); arm_up(w, A); jump(w, A)                                       # a jump shot from the start: too far
    assert verdict(w)["failed"] == FAR and verdict(w)["stages"] == [], verdict(w)

    w.reset(); arm_up(w, A); shift(w, h["x"] - 0.9); jump(w, A, vz=1.5, vx=0.0, k_rel=12, wide=0.8)   # a toss wide of the ring: a miss
    v = verdict(w)
    assert v["failed"] == FLOOR and v["stages"] == ["approach", "release in the air"], v

    def back_on_the_hand(w):                                                  # injection: the ball against the palm
        R = w.d.xmat[w.robot.mount["right"]].reshape(3, 3)
        w.put("ball", w.d.site_xpos[w.robot.palm["right"]] + R[:, 0] * (0.022 + BALL["radius"] - 0.004), vel=w.d.qvel[w.robot.fv:w.robot.fv + 3])
    w.reset(); arm_up(w, A); shift(w, h["x"] - 0.9); jump(w, A, after=back_on_the_hand)
    assert verdict(w)["failed"] == RETOUCH and w.held["right"] is None, verdict(w)

    def from_below(w):                                                        # injection: the ball up through the ring
        w.put("ball", (h["x"], h["y"], h["z"] - 0.5), vel=(-0.5, 0.0, 6.0))
    w.reset(); arm_up(w, A); shift(w, h["x"] - 0.9); jump(w, A, after=from_below)
    assert verdict(w)["failed"] == BELOW, verdict(w)

    w.reset(); hold(w, A, 0.2); kick_robot(w, vel=(0.0, 3.0, 0.0)); hold(w, A)   # a fall
    assert verdict(w)["failed"] == "fell", verdict(w)

    w.reset(); hold(w, A, 0.2); move_robot(w, x=w.pelvis()[0] + 0.3); hold(w, A, 0.2)   # a shuffle: the feet 0.3 m on
    assert verdict(w)["failed"] == "travelling: a foot slid along the floor", verdict(w)  # without a lift (injection)
    print("PASS layup")


if __name__ == "__main__":
    main()
