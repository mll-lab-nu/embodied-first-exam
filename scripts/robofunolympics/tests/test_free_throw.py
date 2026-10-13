"""free-throw (v2, FIBA, the Unitree H1-2): the referee says yes to a ball that is let go behind the line within five
seconds and enters the official basket from above, and no to holding the ball, dropping it, a throw that falls short,
taking the ball back, a foot on or over the line, leaving the semi-circle, a ball that comes up through the ring, a
fall.

The positive is an INJECTION, not a solution: the robot really swings its arm (an underhand straight-arm swing in
`stand` mode) and really lets go of the ball behind the line, but that swing gives the 0.62 kg ball only about
7.4 m/s (the shoulder's speed limit), which in air comes down well short of the ring; at the release the
ball's velocity is therefore set to the 8.1 m/s (at 58 degrees) that carries it from the real release point through the real ring.
The flight (with drag), the ring and the referee's passage are real. A second positive bounces the ball in off the
backboard."""
import math

import numpy as np

from rfo.scene import AIR, OFFICIAL
from rfo.testing import act, hold, kick_robot, make, move_robot, verdict

BALL = OFFICIAL["basketball"]
RETOUCH = "the ball was touched again after the release"
FLOOR = "the ball touched the floor"
LINE = "touched the free-throw line or the floor beyond it"
CIRCLE = "left the free-throw semi-circle"
LATE = "the ball was not released within the time allowed"
BELOW = "the ball came up through the ring from below"
BACK = [1.3, 0.0, 0.0, 1.57, 0.0, 0.0, 0.0]         # right arm straight, swung back
FWD = [-3.1, 0.0, 0.0, 1.57, 0.0, 0.0, 0.0]         # ... and the swing's target, forwards and up
K_REL = 38                                           # the release, control steps into the swing


def row(w, right=None, grip=1.0, cmd=None):
    """A `stand` row (or a `walk` row with cmd): the upper body at rest but the right arm."""
    up = w.robot.rest[12:27].copy()
    if right is not None:
        up[8:15] = right
    out = np.r_[up, 0.0, grip]
    return out if cmd is None else np.r_[cmd, out]


def fly(p0, speed, elev, az, z_at):
    """A ball leaving p0 at speed, elevation and azimuth in the venue's air (drag only): where its centre comes down
    through the height z_at."""
    k = 0.5 * AIR["density"] * BALL["drag"] * math.pi * BALL["radius"] ** 2 / BALL["mass"]
    p = np.array(p0, float)
    v = speed * np.array([math.cos(elev) * math.cos(az), math.cos(elev) * math.sin(az), math.sin(elev)])
    dt = 0.0005
    for _ in range(8000):
        a = -k * np.linalg.norm(v) * v - np.array([0.0, 0.0, 9.81])
        q = p + v * dt + 0.5 * a * dt * dt
        v = v + a * dt
        if p[2] >= z_at > q[2] and v[2] < 0:
            return q
        p = q
    return None


def aim(p0, target, elev):
    """The launch velocity at elevation `elev` that brings the ball down through the target (bisection on the speed)."""
    az = math.atan2(target[1] - p0[1], target[0] - p0[0])
    dist = math.hypot(target[0] - p0[0], target[1] - p0[1])
    lo, hi = 4.0, 20.0
    for _ in range(50):
        mid = (lo + hi) / 2
        q = fly(p0, mid, elev, az, target[2])
        if q is None or math.hypot(q[0] - p0[0], q[1] - p0[1]) < dist:
            lo = mid
        else:
            hi = mid
    return hi * np.array([math.cos(elev) * math.cos(az), math.cos(elev) * math.sin(az), math.sin(elev)])


def swing(w, A, inject=None):
    """The real swing and release; inject(w) is called right after the release (the ball is free then)."""
    rest = w.robot.rest[20:27]
    for k in range(120):
        act(w, A, "stand", row(w, rest + (np.array(BACK) - rest) * min(1.0, k / 72)))
    act(w, A, "stand", row(w, FWD), K_REL)
    act(w, A, "stand", row(w, FWD, grip=0.0))
    real = (w.pos("ball"), w.vel("ball"))
    if inject is not None and not w.done:
        inject(w)
    while not w.done:
        act(w, A, "stand", row(w, FWD, grip=0.0))
    return real


def free_ball(w, A, pos, vel, after=None):
    """Injection: the ball let go at once and put at pos with vel; the robot stands (after(w) once, 0.3 s later)."""
    hold(w, A, 0.2)
    act(w, A, "stand", row(w, grip=0.0))
    w.put("ball", pos, vel=vel)
    k = 0
    while not w.done:
        act(w, A, "stand", row(w, grip=0.0))
        k += 1
        if after is not None and k == 30:
            after(w)


def main():
    w, A = make("free-throw")
    p, h = w.task.p, w.task.hoop
    ring = np.array([h["x"], h["y"], h["z"]])
    assert abs(h["x"] - h["free_throw_line_x"] - 4.225) < 1e-9 and abs(h["end_line_x"] - h["free_throw_line_x"] - 5.80) < 1e-9
    assert abs(h["board_face_x"] - h["x"] - 0.375) < 1e-9 and p["ring_height_m"] == 3.05

    hold(w, A)                                                               # nop: the ball stays in the hand
    assert verdict(w)["failed"] == LATE and verdict(w)["stages"] == [] and abs(w.t - 5.01) < 1e-6, (verdict(w), w.t)

    w.reset()                                                                # the real swing alone falls short
    p0, v0 = swing(w, A)
    v = verdict(w)
    assert v["failed"] == FLOOR and v["stages"] == ["release"], v
    assert 7.0 < np.linalg.norm(v0) < 7.8, np.linalg.norm(v0)                # what the arm gives the ball
    need = aim(p0, ring, math.radians(58))
    assert np.linalg.norm(need) > 8.0, np.linalg.norm(need)                  # what the ring needs from there

    def push(w):                                                             # the injection: the ball's velocity
        w.put("ball", w.pos("ball"), vel=aim(w.pos("ball"), ring, math.radians(58)))
    w.reset(); swing(w, A, push)                                             # positive
    v = verdict(w)
    assert v["success"] and v["stages"] == ["release", "through the ring"], (v, w.ref.events)
    assert w.t < 5.0 and w.task.trackers["released"] < p["release_limit_s"], (w.t, w.task.trackers["released"])
    sha = w.state_sha()
    w.reset(); swing(w, A, push)
    assert w.state_sha() == sha                                              # deterministic

    w.reset()                                                                # a bank shot: in off the backboard
    free_ball(w, A, (h["x"] - 1.5, 0.0, 3.3), aim((h["x"] - 1.5, 0.0, 3.3), (h["board_face_x"] - 0.12, 0.0, 3.42), math.radians(50)))
    v = verdict(w)
    assert v["success"] and w.task.trackers["live"] is False, (v, w.ref.events)

    w.reset(); hold(w, A, 0.2)                                               # dropping the ball
    while not w.done:
        act(w, A, "stand", row(w, grip=0.0))
    assert verdict(w)["failed"] == FLOOR, verdict(w)

    w.reset(); hold(w, A, 0.2)                                               # letting go and taking it back: the
    act(w, A, "stand", row(w, grip=0.0))                                     # grip no longer takes it, and the touch
    assert verdict(w)["stages"] == ["release"] and not w.done, verdict(w)    # is a fault (injection: the released ball
    act(w, A, "stand", row(w, grip=0.0), 8)                                  # put against the palm after the grace)
    R = w.d.xmat[w.robot.mount["right"]].reshape(3, 3)
    w.put("ball", w.d.site_xpos[w.robot.palm["right"]] + R[:, 0] * (0.022 + BALL["radius"] - 0.004))
    act(w, A, "stand", row(w, grip=1.0), 10)
    assert verdict(w)["failed"] == RETOUCH and w.held["right"] is None, (verdict(w), w.held)

    w.reset()                                                                # carrying the ball towards the basket
    while not w.done:
        act(w, A, "walk", row(w, cmd=(0.8, 0.0, 0.0)))
    assert verdict(w)["failed"] == LINE and verdict(w)["stages"] == [], verdict(w)
    assert w.pelvis()[0] < p["start_behind_line_m"] + 0.05, w.pelvis()

    w.reset(); hold(w, A, 0.2)                                               # injection: the robot put behind the
    move_robot(w, x=-1.75); hold(w, A, 0.5)                                  # semi-circle
    assert verdict(w)["failed"] == CIRCLE, verdict(w)

    w.reset()                                                                # injection: the robot beyond the line
    free_ball(w, A, ring + [0.0, 0.0, 1.2], (0, 0, 0), after=lambda w: move_robot(w, x=1.5))   # while the ball drops in
    assert verdict(w)["failed"] == LINE, verdict(w)

    w.reset(); free_ball(w, A, ring + [0.0, 0.0, 0.5], (0, 0, 0))            # injection: the same drop with the robot
    assert verdict(w)["success"], verdict(w)                                 # behind the line is a goal

    w.reset(); free_ball(w, A, ring - [0.0, 0.0, 0.5], (-0.5, 0.0, 6.0))     # injection: up through the ring from below
    assert verdict(w)["failed"] == BELOW, verdict(w)

    w.reset(); hold(w, A, 0.2); act(w, A, "stand", row(w, grip=0.0))         # the ring's rebound (FIBA: it absorbs 35
    w.put("ball", ring + [-0.234, 0.0, BALL["radius"] + 0.5], vel=(0, 0, 0))  # to 50 % of the impact energy): the ball
    vin = vout = 0.0                                                         # dropped onto the ring's front
    while not w.done and w.t < 1.2:
        act(w, A, "stand", row(w, grip=0.0))
        vz = w.vel("ball")[2]
        vin = min(vin, vz)
        if vin < -2.5 and vz > 0:
            vout = max(vout, float(np.linalg.norm(w.vel("ball"))))
    assert 0.35 <= 1 - (vout / vin) ** 2 <= 0.50, (vin, vout, 1 - (vout / vin) ** 2)

    w.reset(); hold(w, A, 0.2); kick_robot(w, vel=(-3.0, 0.0, 0.0)); hold(w, A)   # a fall (with the ball in the hand)
    assert verdict(w)["failed"] == "fell", verdict(w)
    print("PASS free-throw")


if __name__ == "__main__":
    main()
