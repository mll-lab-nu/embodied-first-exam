"""catch-and-shoot (v2, FIBA, the Unitree H1-2): the referee says yes to the chest pass caught on the fly, no step
with the ball, and a shot from the top of the key down through the official ring; no to a pass that is not caught, a
touch before the pass, a ball off a leg, travelling (a walk with the ball, a pivot foot that moves, steps after a catch
on the move), a shot that falls short, a second touch, a ball up through the ring, a fall.

The catch is REAL: the open right palm waits on the ball's path, facing it (`stand` mode), and the grip takes the
8 m/s pass as it meets the palm (7.2 m/s there; the robot stays on both feet). The shot is an INJECTION: the robot
really raises the arm and really lets go, but an arm that gives this ball 7.5 m/s cannot reach a ring 5.8 m away; at
the release the ball's velocity is set to the 8.7 m/s (52 degrees) that carries it from the real release point through
the real ring."""
import math

import numpy as np

from rfo.scene import AIR, OFFICIAL
from rfo.testing import act, hold, kick_robot, make, move_robot, verdict

BALL = OFFICIAL["basketball"]
CATCH = [0.167, 0.102, 0.028, -0.135, 0.428, -0.06, -0.075]   # right arm: the palm on the pass's line, facing the ball
SHOOT = [-1.3, -0.2, 0.0, -0.8, -1.8, 0.0, 0.0]               # ... raised, the palm behind the ball, facing the ring
NOT_CAUGHT = "the pass was not caught: the ball touched the floor"
EARLY = "the ball was touched before the pass"
LEG = "the ball touched a leg or a foot"
PIVOT_BACK = "travelling: a foot came back to the floor after the pivot foot had left it"
PIVOT_MOVED = "travelling: the pivot foot moved"
THIRD = "travelling: a third step with the ball in the hand"
FLOOR = "the ball touched the floor"
RETOUCH = "the ball was touched again after the release"
BELOW = "the ball came up through the ring from below"


def row(w, right=None, grip=0.0, cmd=None):
    up = w.robot.rest[12:27].copy()
    if right is not None:
        up[8:15] = right
    out = np.r_[up, 0.0, grip]
    return out if cmd is None else np.r_[cmd, out]


def fly(p0, speed, elev, az, z_at):
    """A ball leaving p0 in the venue's air (drag only): where its centre comes down through the height z_at."""
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
    lo, hi = 4.0, 25.0
    for _ in range(50):
        mid = (lo + hi) / 2
        q = fly(p0, mid, elev, az, target[2])
        if q is None or math.hypot(q[0] - p0[0], q[1] - p0[1]) < dist:
            lo = mid
        else:
            hi = mid
    return hi * np.array([math.cos(elev) * math.cos(az), math.cos(elev) * math.sin(az), math.sin(elev)])


def catch(w, A, lift_at=None):
    """The real catch: the palm to the pass's line before the pass, the grip closed from then on. lift_at: the time
    at which the robot is teleported 6 cm up (injection: its feet are off the floor when the ball arrives)."""
    rest = w.robot.rest[20:27]
    for i in range(1, 121):
        act(w, A, "stand", row(w, rest + (np.array(CATCH) - rest) * i / 120))
    while not w.done and w.task.trackers["caught"] is None and w.t < 3.5:
        act(w, A, "stand", row(w, CATCH, grip=1.0))
        if lift_at is not None and abs(w.t - lift_at) < 1e-6:
            move_robot(w, z=w.pelvis()[2] + 0.06)


def shoot(w, A, inject=True, wide=0.0, after=None):
    """Raise the arm, let go; inject: the ball's velocity set at the release towards the ring (`wide` of it)."""
    h = w.task.hoop
    for i in range(1, 61):
        act(w, A, "stand", row(w, np.array(CATCH) + (np.array(SHOOT) - CATCH) * i / 60, grip=1.0))
    act(w, A, "stand", row(w, SHOOT, grip=1.0), 40)
    act(w, A, "stand", row(w, SHOOT, grip=0.0))
    if inject and not w.done:
        b = w.pos("ball")
        w.put("ball", b, vel=aim(b, (h["x"], h["y"] + wide, h["z"]), math.radians(52)))
    k = 0
    while not w.done:
        act(w, A, "stand", row(w, SHOOT, grip=0.0))
        k += 1
        if after is not None and k == 12:
            after(w)


def main():
    w, A = make("catch-and-shoot")
    p, h = w.task.p, w.task.hoop
    tr = lambda: w.task.trackers                                              # noqa: E731
    src = np.array([p["pass_from_x_m"], p["pass_from_y_m"], p["pass_from_z_m"]])
    v0 = np.array([p["pass_vx"], p["pass_vy"], p["pass_vz"]])
    assert p["spot_to_ring_m"] == 5.8 and abs(np.linalg.norm(v0) - p["pass_speed_m_s"]) < 1e-3
    assert abs(np.linalg.norm(src - [p["pass_to_x_m"], 0.0, p["pass_to_z_m"]]) - p["pass_distance_m"]) < 0.01

    hold(w, A, 2.0)                                                           # nop: the pass really goes where the
    near = 9.0                                                                # venue text says (within 2 cm), ...
    while not w.done:
        hold(w, A, 0.01)
        near = min(near, float(np.linalg.norm(w.pos("ball") - [p["pass_to_x_m"], 0.0, p["pass_to_z_m"]])))
        if abs(w.pos("ball")[1]) < 0.04:
            assert 7.0 < np.linalg.norm(w.vel("ball")) < 7.4, w.vel("ball")
    assert near < 0.04, near                                                  # (sampled every 10 ms: 7 cm of flight)
    assert verdict(w)["failed"] == NOT_CAUGHT and verdict(w)["stages"] == [], verdict(w)   # ... and is not caught

    def positive():
        w.reset(); catch(w, A)
        assert tr()["caught"] is not None and tr()["travel"].mode == "pivot" and w.held["right"] == "ball", w.ref.events
        shoot(w, A)
    positive()
    v = verdict(w)
    assert v["success"] and v["stages"] == ["catch", "release", "through the ring"], (v, w.ref.events)
    assert tr()["travel"].pivot is None and w.t < 8.0, (tr()["travel"].state(), w.t)   # no foot was lifted
    sha = w.state_sha()
    positive()
    assert w.state_sha() == sha                                               # deterministic

    w.reset(); catch(w, A); shoot(w, A, inject=False)                         # let go on the raised, still hand: the
    v = verdict(w)                                                            # ball stays against the palm
    assert v["failed"] == RETOUCH and v["stages"] == ["catch", "release"], v

    w.reset(); catch(w, A); shoot(w, A, wide=1.0)                             # a shot 1 m wide
    assert verdict(w)["failed"] == FLOOR, verdict(w)

    w.reset(); catch(w, A); hold(w, A)                                        # caught and held
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == ["catch"], verdict(w)

    w.reset(); catch(w, A)                                                    # caught, then walking with the ball
    while not w.done:
        act(w, A, "walk", row(w, CATCH, grip=1.0, cmd=(0.6, 0.0, 0.0)))
    v = verdict(w)
    assert v["failed"] == PIVOT_BACK and tr()["travel"].pivot in ("left", "right") and w.pelvis()[0] < 0.5, (v, w.pelvis())

    w.reset(); catch(w, A)                                                    # injection: the pivot foot dragged 0.3 m
    while not w.done and tr()["travel"].pivot is None:                        # (the robot teleported once it has one)
        act(w, A, "walk", row(w, CATCH, grip=1.0, cmd=(0.0, 0.0, 0.0)))
    assert not w.done
    move_robot(w, x=w.pelvis()[0] + 0.3); w.put("ball", w.pos("ball") + [0.3, 0, 0])
    act(w, A, "walk", row(w, CATCH, grip=1.0, cmd=(0.0, 0.0, 0.0)), 3)
    assert verdict(w)["failed"] == PIVOT_MOVED, verdict(w)

    w.reset()                                                                 # caught with the feet off the floor
    catch(w, A, lift_at=2.72)                                                 # (injection: the robot lifted 6 cm just
    assert tr()["caught"] is not None and tr()["travel"].mode == "steps", w.ref.events   # before the ball arrives), then
    while not w.done:                                                         # walking on: landing, a step, a third
        act(w, A, "walk", row(w, CATCH, grip=1.0, cmd=(0.0, 0.0, 0.0)))
    assert verdict(w)["failed"] == THIRD and tr()["travel"].steps[0][1] == "both", (verdict(w), tr()["travel"].steps)

    w.reset(); hold(w, A, 0.5); move_robot(w, x=src[0] - 0.12, y=src[1]); hold(w, A, 0.3)          # at the passer
    assert verdict(w)["failed"] == EARLY, verdict(w)

    w.reset(); hold(w, A, 2.05)                                               # injection: the pass at the thigh
    w.put("ball", (0.02, 1.0, 0.75), vel=(0.0, -7.0, 0.3)); hold(w, A, 1.0)
    assert verdict(w)["failed"] == LEG, verdict(w)

    def back_on_the_hand(w):                                                  # injection: the ball against the palm
        R = w.d.xmat[w.robot.mount["right"]].reshape(3, 3)
        w.put("ball", w.d.site_xpos[w.robot.palm["right"]] + R[:, 0] * (0.022 + BALL["radius"] - 0.004))
    w.reset(); catch(w, A); shoot(w, A, after=back_on_the_hand)
    assert verdict(w)["failed"] == RETOUCH and w.held["right"] is None, verdict(w)

    def from_below(w):                                                        # injection: up through the ring
        w.put("ball", (h["x"], h["y"], h["z"] - 0.5), vel=(-0.5, 0.0, 6.0))
    w.reset(); catch(w, A); shoot(w, A, after=from_below)
    assert verdict(w)["failed"] == BELOW, verdict(w)

    w.reset(); hold(w, A, 0.2); kick_robot(w, vel=(0.0, 3.0, 0.0)); hold(w, A)   # a fall
    assert verdict(w)["failed"] == "fell", verdict(w)
    print("PASS catch-and-shoot")


if __name__ == "__main__":
    main()
