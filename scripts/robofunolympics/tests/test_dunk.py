"""dunk (v2, FIBA, the Unitree H1-2): the referee says yes to the gripped ball going down through the official ring
(3.05 m) and a landing held on the feet; no to a ball let go before it is in the ring, to a ball that comes up through
the ring from below, to a ball that goes in by itself, to travelling, and to a landing that is a fall.

The positive is an INJECTION, not a solution; none exists: with the arm straight up the gripped ball's centre is
2.37 m above the floor (asserted below), so the body has to rise more than 0.8 m, and the robot has no jump. The robot
really raises the ball arm (`stand` mode); it is teleported so that the ball is 0.55 m in front of the ring's axis and
given a take-off velocity of 4.5 m/s upwards (a "ghost" jump: the ball's centre peaks at 3.4 m); at the apex robot
and ball are teleported 0.55 m forwards, the ball over the ring. From there physics: the body falls, the gripped ball
goes down through the real ring, the hand lets go. The landing is a second injection (0.3 m above its standing
height the falling robot is put down upright on the floor, at rest; without it the open-loop stance does not survive
the landing from 1 m: that fall is a negative below), and the robot really stands for the second the referee asks."""
import numpy as np

from rfo.scene import OFFICIAL
from rfo.testing import act, hold, kick_robot, make, move_robot, verdict

BALL = OFFICIAL["basketball"]
UP = np.array([-3.14, -0.4, 0.0, 1.57, 0.0, 0.0, 0.0])          # right arm straight up, the ball on top of the fist
EARLY = "the ball was let go before the dunk"
BELOW = "the ball came up through the ring from below"
NO_HAND = "the ball went through the ring without a hand on it"
OUT = "the ball did not go through the ring"
THIRD = "travelling: a third step with the ball in the hand"


def row(w, right=None, grip=1.0, cmd=None):
    up = w.robot.rest[12:27].copy()
    if right is not None:
        up[8:15] = right
    out = np.r_[up, 0.0, grip]
    return out if cmd is None else np.r_[cmd, out]


def arm_up(w, A, seconds=1.5, settle=1.5):
    rest = w.robot.rest[20:27]
    n = int(seconds * 100)
    for i in range(1, n + 1):
        act(w, A, "stand", row(w, rest + (UP - rest) * i / n))
    act(w, A, "stand", row(w, UP), int(settle * 100))


def shift(w, x, y=0.0):
    """Injection: teleport the robot and the ball it grips so that the ball's centre is at (x, y)."""
    pel, b = w.pelvis(), w.pos("ball")
    qa, _ = w.free["ball"]
    quat = w.d.qpos[qa + 3:qa + 7].copy()
    move_robot(w, x=pel[0] + x - b[0], y=pel[1] + y - b[1])
    tv = w.task.trackers["travel"]                       # (the teleport is not a slide of the feet)
    tv.anchor = {k: (None if v is None else [v[0] + x - b[0], v[1] + y - b[1]]) for k, v in tv.anchor.items()}
    w.put("ball", b + [x - b[0], y - b[1], 0.0], quat=quat, vel=w.vel("ball"))


def jump(w, A, front=0.55, peak=3.40, soft=True, release="dunked", after=None):
    """The ghost jump from `front` metres before the ring's axis to a ball height of `peak`, the teleport over the
    ring at the apex, the release (when the ball is through: "dunked"; when its centre is inside the ring: "entered"; or a number of
    control steps after the apex; after(w) is called right after the release),
    and the injected landing (soft)."""
    h, tr = w.task.hoop, w.task.trackers
    arm_up(w, A)
    shift(w, h["x"] - front)
    vz = float(np.sqrt(2 * 9.81 * (peak - w.pos("ball")[2])))
    k_apex = int(round(vz / 9.81 * 100))
    kick_robot(w, (0.0, 0.0, vz))
    let_go, landed = False, False
    for k in range(1, 500):
        if w.done:
            return
        was = let_go
        if release == "dunked":
            let_go = let_go or tr["dunked"] is not None
        elif release == "entered":
            let_go = let_go or tr["hoop"].entered
        else:
            let_go = let_go or k >= k_apex + release
        act(w, A, "stand", row(w, UP if not landed else None, grip=0.0 if let_go else 1.0))
        if k == k_apex and front:
            shift(w, h["x"])
        if after is not None and let_go and not was and not w.done:
            after(w)
        vz_now = float(w.d.qvel[w.robot.fv + 2])
        if soft and not landed and k > k_apex and w.pelvis()[2] < w.robot.stand_z + 0.30 and vz_now < -1.0:
            move_robot(w, z=w.robot.stand_z + 0.03, yaw=0.0)                   # injection: put down upright, at rest
            w.d.qvel[:] = 0.0
            landed = True


def main():
    w, A = make("dunk")
    p, h = w.task.p, w.task.hoop
    tr = lambda: w.task.trackers                                              # noqa: E731
    assert p["ring_height_m"] == 3.05 and p["ring_inner_diameter_m"] == 0.45 and p["start_to_ring_m"] == 1.25

    hold(w, A)                                                                # nop
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)

    w.reset(); arm_up(w, A)                                                   # the standing reach: the ball's centre
    assert 2.30 < w.pos("ball")[2] < 2.45, w.pos("ball")                      # 0.7 m below the ring's top edge
    shift(w, h["x"]); hold(w, A, 0.3); hold(w, A, 0.1, grips=(0, 0))          # and let go under the ring
    assert verdict(w)["failed"] == EARLY, verdict(w)

    w.reset(); jump(w, A)                                                     # positive (injection)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["dunk", "stand"], (v, w.ref.events)
    assert tr()["hand_on"] and tr()["released"] > tr()["dunked"] and w.t < 8.0, (tr()["released"], tr()["dunked"], w.t)
    sha = w.state_sha()
    w.reset(); jump(w, A)
    assert w.state_sha() == sha                                               # deterministic

    w.reset(); jump(w, A, soft=False)                                         # the same dunk with its real landing
    v = verdict(w)
    assert v["failed"] == "fell" and v["stages"] == ["dunk"], v

    w.reset(); jump(w, A, front=0.0)                                          # straight up under the ring: the ball
    assert verdict(w)["failed"] == BELOW and verdict(w)["stages"] == [], verdict(w)   # comes up through it

    w.reset(); jump(w, A, release=2)                                          # let go above the ring (a drop, no dunk)
    assert verdict(w)["failed"] == EARLY, verdict(w)

    def lift_out(w):                                                          # injection: the ball, let go inside the
        w.put("ball", (h["x"], h["y"], h["z"] + 0.6), vel=(0, 0, 0))          # ring, is put above it and falls in alone
    w.reset(); jump(w, A, release="entered", after=lift_out)
    assert tr()["hoop"].through and verdict(w)["failed"] == NO_HAND, (verdict(w), w.ref.events)

    def throw_out(w):                                                         # injection: ... or is put outside the ring
        w.put("ball", (h["x"] - 0.8, h["y"], h["z"] + 0.2), vel=(-1.0, 0, 0))
    w.reset(); jump(w, A, release="entered", after=throw_out)
    assert verdict(w)["failed"] == OUT and verdict(w)["stages"] == [], verdict(w)

    w.reset(); arm_up(w, A)                                                   # walking with the ball in the hand
    while not w.done:
        act(w, A, "walk", row(w, UP, cmd=(0.5, 0.0, 0.0)))
    assert verdict(w)["failed"] == THIRD, verdict(w)

    w.reset(); hold(w, A, 0.2); kick_robot(w, vel=(0.0, 3.0, 0.0)); hold(w, A)   # a fall
    assert verdict(w)["failed"] == "fell", verdict(w)
    print("PASS dunk")


if __name__ == "__main__":
    main()
