"""basketball-dribble (v2, FIBA, the Unitree H1-2): the referee says yes to a ball dribbled from the end line until
ball and both feet are in the frontcourt (14 m), and no to carrying the gripped ball, a ball that comes to rest in the
hand, two hand touches without the floor in between, both hands on the ball, a touch by a leg, a ball left behind or
thrown ahead, ball or robot out of bounds, dribbling on the spot, a fall.

The positive is an INJECTION, not a solution: the robot really stands, turns its right palm down, lets go of the ball
before it lifts a foot, and really walks the 14 m on its gait (0.8 m/s commanded, heading held by feedback on the
simulator's state); the ball really bounces on the floor and really meets the palm 40 times. The palm's push is
replaced by setting the ball's velocity at the release and at each real touch of the hand: 4 m/s downwards, and
horizontally towards where the palm will be when the ball is back up."""
import numpy as np

from rfo.scene import OFFICIAL
from rfo.testing import act, hold, kick_robot, make, move_robot, verdict

BALL = OFFICIAL["basketball"]
RB, G, E = BALL["radius"], 9.81, 0.82                          # (0.82: the bounce measured on this floor)
POSE = np.array([-0.5, -0.5, -0.3, 0.5, -1.57, 0.0, 0.0])      # right arm: the palm out to the front right, facing down
UP = np.array([-3.14, -0.4, 0.0, 1.57, 0.0, 0.0, 0.0])         # right arm straight up: the ball on top of the fist
PALM_UP = np.array([0.0, 0.0, 0.0, 0.0, 1.57, 0.0, 0.0])       # right forearm forwards, the palm up
TRAVEL = "travelling: the pivot foot left the floor before the ball was released"
REST = "the ball came to rest in a hand: a touch lasted too long"
TWICE = "a hand touched the ball twice without the ball touching the floor in between"
BOTH = "both hands touched the ball at the same time"
BODY = "the ball touched a part of you other than a hand"
AWAY = "the ball got away: it was further from you than the control distance"
OUT_BALL = "out of bounds: the ball touched the floor on or outside a boundary line"
OUT_YOU = "out of bounds: you touched the floor on or outside a boundary line"


def row(w, right=None, left=None, grip=1.0, cmd=(0.0, 0.0, 0.0)):
    up = w.robot.rest[12:27].copy()
    if left is not None:
        up[1:8] = left
    if right is not None:
        up[8:15] = right
    return np.r_[cmd, up, 0.0, grip]


def palm(w):
    """Where the ball's centre is when the ball is against the right palm's face."""
    b = w.robot.mount["right"]
    return w.d.site_xpos[w.robot.palm["right"]] + w.d.xmat[b].reshape(3, 3)[:, 0] * (0.022 + RB)


def push(w, v_walk, vz=4.0):
    """The injected push: the ball leaves downwards at vz, towards where the palm will be when it is back up."""
    b, z0 = w.pos("ball"), palm(w)[2]
    v_imp = np.sqrt(vz ** 2 + 2 * G * (b[2] - RB))
    v_reb = E * v_imp
    T = (v_imp - vz) / G + (v_reb - np.sqrt(max(v_reb ** 2 - 2 * G * (z0 - RB), 0.0))) / G + 0.02
    yaw = w.pelvis()[3]
    v = (palm(w)[:2] + v_walk * np.array([np.cos(yaw), np.sin(yaw)]) * T - b[:2]) / T
    w.put("ball", b, vel=(v[0], v[1], -vz))


def arm(w, A, pose, steps=60, settle=0):
    rest = w.robot.rest[20:27]
    for i in range(1, steps + 1):
        act(w, A, "stand", row(w, rest + (np.array(pose) - rest) * i / steps)[3:])
    act(w, A, "stand", row(w, pose)[3:], settle)


def dribble(w, A, vx=0.8, until=58.0, on_touch=None, n_max=None):
    """Palm down, release (standing), then walk at the command vx; the injected push (or on_touch(w, n)) at every
    real touch of the hand."""
    arm(w, A, POSE)
    act(w, A, "stand", row(w, POSE, grip=0.0)[3:])
    push(w, 0.0)
    tr, n = w.task.trackers, 0
    while not w.done and w.t < until:
        _, y, _, yaw = w.pelvis()
        act(w, A, "walk", row(w, POSE, grip=0.0, cmd=(vx, np.clip(-1.5 * y, -0.3, 0.3), np.clip(-2 * yaw, -1, 1))))
        if tr["hand"].count > n and not w.done:
            n = tr["hand"].count
            if n_max is not None and n > n_max:
                return
            if on_touch is not None and on_touch(w, n):
                continue
            push(w, max(float(w.d.qvel[w.robot.fv]), 0.3) if vx else 0.0)


def main():
    w, A = make("basketball-dribble")
    t, p = w.task, w.task.p
    tr = lambda: w.task.trackers                                              # noqa: E731
    assert p["centre_line_m"] == 14.0 and p["court_width_m"] == 15.0 and abs(t.x_front - t.x_end - 14.025) < 1e-9
    assert t.y_hi - t.y_lo == 15.0 and t.y_lo < 0 < t.y_hi and t.x_end == -p["start_from_end_line_m"]

    hold(w, A)                                                                # nop: the ball stays in the hand
    assert verdict(w)["failed"] == "time" and not verdict(w)["stages"], verdict(w)

    w.reset(); dribble(w, A)                                                  # positive (injection)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["dribble", "past the free-throw line", "in the frontcourt"], (v, w.ref.events[-4:])
    assert v["metrics"]["dribbles"] >= 30 and v["metrics"]["distance_m"] >= 14.0 and w.t < 30.0, (v, w.t)
    assert min(tr()["foot_x"].values()) > t.x_front and tr()["hand"].longest < 0.05, (tr()["foot_x"], tr()["hand"].state())
    sha = w.state_sha()
    w.reset(); dribble(w, A)
    assert w.state_sha() == sha                                               # deterministic

    w.reset()                                                                 # carrying the gripped ball
    while not w.done:
        act(w, A, "walk", row(w, cmd=(0.8, 0.0, 0.0)))
    v = verdict(w)
    assert v["failed"] == TRAVEL and v["metrics"]["distance_m"] < 1.2 and not v["stages"], v

    w.reset(); hold(w, A, 0.3); hold(w, A, 4.0, grips=(0, 0))                 # dropped and left: no violation yet
    assert not w.done and not w.task.may_grip(w, "right", "ball")             # (and it cannot be picked up again);
    while not w.done:                                                         # then walking away from it
        act(w, A, "walk", row(w, grip=0.0, cmd=(0.8, 0.0, 0.0)))
    assert verdict(w)["failed"] == AWAY and not verdict(w)["stages"], verdict(w)

    w.reset(); hold(w, A, 0.3); hold(w, A, 1.0, grips=(0, 0))                 # dropped, then walking backwards over
    while not w.done:                                                         # the end line
        act(w, A, "walk", row(w, grip=0.0, cmd=(-0.5, 0.0, 0.0)))
    assert verdict(w)["failed"] == OUT_YOU, verdict(w)

    w.reset(); arm(w, A, UP, 150, 100)                                        # let go with the ball on top of the
    act(w, A, "stand", row(w, UP, grip=0.0)[3:], 100)                         # fist: it comes down on the hand again
    assert verdict(w)["failed"] == TWICE, (verdict(w), w.ref.events)

    w.reset(); arm(w, A, PALM_UP, 60, 60)                                     # injection: the gripped ball moved onto
    R = w.d.xmat[w.robot.mount["right"]].reshape(3, 3)                        # the upturned palm; let go there, it
    w.put("ball", w.d.site_xpos[w.robot.palm["right"]] + R[:, 0] * (0.022 + RB))   # stays lying in the hand
    w.grab("right", "ball", event=False)
    act(w, A, "stand", row(w, PALM_UP)[3:], 30)
    act(w, A, "stand", row(w, PALM_UP, grip=0.0)[3:], 60)
    assert verdict(w)["failed"] == REST, (verdict(w), w.ref.events)

    def again(w, n):                                                          # up against the palm again, no bounce
        if n >= 3:
            w.put("ball", palm(w) - [0, 0, 0.25], vel=(float(w.d.qvel[w.robot.fv]), 0, 3.0))
            return True
    w.reset(); dribble(w, A, on_touch=again)
    assert verdict(w)["failed"] == TWICE and verdict(w)["stages"] == ["dribble"], (verdict(w), w.ref.events)

    def at_the_leg(w, n):                                                     # the ball thrown at the thigh
        if n >= 3:
            x, y, z, _ = w.pelvis()
            w.put("ball", (x + 0.02, y - 0.9, 0.75), vel=(0.6, 6.0, 0.0))
            return True
    w.reset(); dribble(w, A, on_touch=at_the_leg)
    v = verdict(w)
    assert v["failed"] == BODY and w.ref.events[-1]["parts"], (v, w.ref.events)

    def ahead(w, n):                                                          # a "pass to oneself": thrown 6 m ahead
        if n >= 3:
            w.put("ball", w.pos("ball"), vel=(7.0, 0.0, 3.0))
            return True
    w.reset(); dribble(w, A, on_touch=ahead)
    assert verdict(w)["failed"] == AWAY, verdict(w)

    def behind(w, n):                                                         # thrown back over the end line
        if n >= 2:
            w.put("ball", w.pos("ball"), vel=(-3.0, 0.0, 0.5))
            return True
    w.reset(); dribble(w, A, vx=0.0, on_touch=behind)
    assert verdict(w)["failed"] == OUT_BALL, verdict(w)

    w.reset()                                                                 # injection: the ball between both palms
    inward = np.zeros(7)
    inward[2] = 0.17
    for i in range(1, 51):
        act(w, A, "stand", row(w, right=inward * i / 50, left=-inward * i / 50)[3:])
    act(w, A, "stand", row(w, right=inward, left=-inward, grip=0.0)[3:], 12)
    mid = (w.d.site_xpos[w.robot.palm["left"]] + w.d.site_xpos[w.robot.palm["right"]]) / 2
    w.put("ball", mid)
    act(w, A, "stand", row(w, right=inward, left=-inward, grip=0.0)[3:], 3)
    assert verdict(w)["failed"] == BOTH, (verdict(w), w.ref.events)

    w.reset(); dribble(w, A, vx=0.0, until=70.0)                              # dribbling on the spot: no distance
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == ["dribble"] and v["metrics"]["dribbles"] > 60, v

    w.reset(); dribble(w, A, n_max=3); move_robot(w, z=0.30); hold(w, A, 0.3)   # a fall
    assert verdict(w)["failed"] == "fell", verdict(w)
    print("PASS basketball-dribble")


if __name__ == "__main__":
    main()
