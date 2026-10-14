"""table-tennis-return: the referee on the official table with RoboOlympics' library service (entry 221).

No reference solution exists. The positive is a real stroke with one injection: the robot is put at the table (its
right arm already stretched towards where the ball will be: the pose is taken a metre behind the start and the robot
is then moved to the end line; walking there and reaching over the table without touching it is the unsolved part).
From there everything is real and goes through the action interface: a waist-turn stroke in `stand` mode meets the
ball 0.63 m inside the end line after its bounce, and the ball flies over the net and lands on the opponent's court.
Two more positives are injections of the ball's state (said where they are): a return that clips the net's top
(Law 2.7.1) and a strike with the racket hand below the wrist (Law 2.5.7).

Negatives, each with its exact reason: doing nothing (the short service bounces twice); a still blade in the ball's
path (a real block: the ball drops on the robot's own court); the service's own facts (it is the library's legal
service; a changed one is refused); the ball touched before the service; obstruction; the handle; the body; a second
strike; the return into the net and back; the side of the table; the floor; the robot touching the net; the free hand
on the playing surface; a fall; time."""
import math

import numpy as np

from rfo.tasks import table_tennis_return as T
from rfo.testing import act, hold, kick_robot, make, move_robot, verdict

FAMILY = "table-tennis-return"
# waist 3 + left arm 7 + right arm 7 (rad): the pre-stroke pose and the stroke's end (found by inverse kinematics on the
# ball's path: the blade's face 45 degrees up towards the net where the ball is at 4.04 s), the left arm held back
QA = np.array([1.7588, -0.032, -0.5034, 0.8, 0.2, 0.0, 0.3, 0.0, 0.0, 0.0, -2.7918, -2.2415, -0.0654, 1.196, -1.9622, 0.5699, 1.3203])
QB = np.array([2.4681, 0.3982, -0.41, 0.8, 0.2, 0.0, 0.3, 0.0, 0.0, 0.0, -3.0629, -1.0316, -0.0474, 1.4594, -1.9622, 1.2722, -0.765])
# the left hand flat on the playing surface (robot at the end line)
QL = np.array([0.0, 0.0, 0.0, -1.117, -0.168, 1.325, 0.755, -1.621, -1.22, 0.717, 0.2, -0.2, 0.0, 1.28, 0.0, 0.0, 0.0])
K_STROKE, N_STROKE = 393, 20          # the stroke: QA -> QB over 0.20 s from 3.93 s on


def at_table(w, A, until=None, pose=QA, stroke=True, hold_at=None):
    """Drive the robot (stand mode): `pose` is taken a metre behind the start, the robot is moved to the end line at
    1.7 s (the injection), then the stroke pose -> QB at K_STROKE (or a still blade at QA + hold_at (QB - QA))."""
    q0 = w.robot.rest[12:29].copy()
    if w.k == 0:
        move_robot(w, x=-0.63)
    while not w.done and (until is None or w.k < until):
        k = w.k
        if k == 170:
            move_robot(w, x=float(w.pelvis()[0]) + 1.0)
        if k < 150:
            q = q0 + (pose - q0) * (k + 1) / 150
        elif hold_at is not None:
            q = pose + (QB - pose) * hold_at * min(1.0, max(0.0, (k - 199) / 100))
        elif not stroke or k < K_STROKE:
            q = pose
        else:
            q = pose + (QB - pose) * min(1.0, (k - K_STROKE + 1) / N_STROKE)
        act(w, A, "stand", np.r_[q, 0, 0])


def relaunch(w, A, k_at, pos, vel, at_strike=None):
    """The stroke's episode with the ball's state set at control step k_at (pos, vel: callables evaluated then), and,
    with at_strike, its velocity set again at the step its strike is latched (the contact is real)."""
    w.reset()
    at_table(w, A, until=k_at)
    w.launch("ball", pos(), vel())
    while not w.done:
        had = w.ref.has("strike")
        at_table(w, A, until=w.k + 1)
        if at_strike is not None and w.ref.has("strike") and not had:
            w.launch("ball", w.pos("ball"), at_strike)
    return verdict(w)


def events(w, name):
    return [e for e in w.ref.events if e["ev"] == name or e.get("stage") == name]


def main():
    w, A = make(FAMILY)
    p, m, d = w.task.p, w.m, w.d
    net_x, top = w.task.net_x, p["table_height_m"]
    assert w.task.robot == "unitree_g1"
    assert (p["table_length_m"], p["table_width_m"], p["table_height_m"], p["net_height_m"]) == (2.74, 1.525, 0.76, 0.1525)
    assert abs(m.geom("table").size[0] - 1.37) < 1e-9 and abs(m.geom("table").size[1] - 0.7625) < 1e-9
    assert abs(m.geom("net").size[1] - 0.915) < 1e-9 and abs(d.geom_xpos[m.geom("net").id][2] + m.geom("net").size[2] - 0.9125) < 1e-9
    assert abs(m.body_mass[m.body("ball").id] - 0.0027) < 1e-9 and abs(m.geom("ball").size[0] - 0.020) < 1e-9
    blade_mass = m.body_mass[w.robot.mount["right"]]
    assert abs(blade_mass - 0.14) < 1e-6, blade_mass

    # ---- nop: the service is the library's (a legal service: the server's court, then yours), and it is short:
    # left alone it bounces a second time on the robot's court
    hold(w, A)
    v = verdict(w)
    assert v["failed"] == T.DOUBLE_BOUNCE and v["stages"] == ["bounce"], v
    srv, rcv = events(w, "bounce on the server's court")[0], events(w, "bounce")[0]
    assert abs(srv["x"] - (net_x + 0.431)) < 0.005 and abs(srv["y"] + 0.074) < 0.005, srv      # serve_library.json's
    assert abs(rcv["x"] - (net_x - 0.334)) < 0.005 and abs(rcv["y"] - 0.023) < 0.005, rcv      # bounce_srv, bounce_rcv
    assert abs(srv["t"] - p["serve_time_s"] - 0.383) < 0.003 and not w.task.trackers["net_touch"]

    # ---- the table's bounce is DeepMind's identified pair (injection: a ball dropped from 30.5 cm before the service)
    w2, A2 = make(FAMILY, serve_time_s=7.9)
    w2.unpin("ball"); w2.put("ball", (net_x + 0.6, 0.2, top + 0.02 + 0.305))
    zs = []
    for _ in range(70):
        hold(w2, A2, 0.01); zs.append(float(w2.pos("ball")[2]) - top - 0.02)
    i = int(np.argmin(zs))
    assert 0.262 <= max(zs[i:]) <= 0.276, max(zs[i:])

    # ---- positive: the real stroke from the end line
    w.reset(); at_table(w, A)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["bounce", "strike", "opponent's court"], v
    st = events(w, "strike")[0]
    assert not st["with_hand"] and 0.55 < st["x"] - p["table_near_x_m"] < 0.70 and st["z"] > top + 0.1, st
    assert net_x + 0.2 < v["metrics"]["landing_x_m"] < net_x + 1.2 and v["metrics"]["net_touch"] == 0.0, v
    assert abs(w.pelvis()[0] - 0.37) < 0.12 and w.t < 5.0, (w.pelvis(), w.t)
    sha = w.state_sha()
    w.reset(); at_table(w, A)
    assert w.state_sha() == sha                                              # the same episode again: the same state

    # ---- a still blade in the ball's path (a real block): the ball drops on the robot's own court
    w.reset(); at_table(w, A, hold_at=0.3)
    v = verdict(w)
    assert v["failed"] == T.OWN_COURT and v["stages"] == ["bounce", "strike"], v

    blade = lambda: d.geom_xpos[m.geom("paddle_blade").id].copy()            # noqa: E731
    def face():                                                              # the blade's face that looks up
        n = d.geom_xmat[m.geom("paddle_blade").id].reshape(3, 3)[:, 0]
        return n if n[2] > 0 else -n

    # ---- injections of the ball's state around the real stroke
    v = relaunch(w, A, 345, lambda: blade() + 0.30 * face(), lambda: -3.0 * face())      # onto the blade before the
    assert v["failed"] == T.OBSTRUCTION and v["stages"] == [], v                           # ball's bounce on the court
    handle = lambda: d.geom_xpos[m.geom("paddle_handle").id].copy()          # noqa: E731
    v = relaunch(w, A, 385, lambda: handle() + 0.15 * face(), lambda: -3.0 * face())     # after the bounce: the handle
    assert v["failed"] == T.BODY and w.ref.events[-1]["handle"] and v["stages"] == ["bounce"], (v, w.ref.events[-1])
    chest = lambda: d.xpos[w.robot.torso] + d.xmat[w.robot.torso].reshape(3, 3) @ np.array([0.0, 0.0, 0.2])  # noqa: E731
    o = np.array([0.3, 0.2, 0.05])
    v = relaunch(w, A, 385, lambda: chest() + o, lambda: -o / np.linalg.norm(o) * 4.0)   # ... the body
    assert v["failed"] == T.BODY and "torso" in w.ref.events[-1]["parts"], (v, w.ref.events[-1])
    v = relaunch(w, A, 440, lambda: blade() + 0.06 * face(), lambda: -3.0 * face())      # back onto the blade 0.37 s
    assert v["failed"] == T.TWICE and v["stages"] == ["bounce", "strike"], v             # after the real strike
    assert w.ref.events[-1]["after_s"] > p["strike_window_s"]
    cord = lambda dz: (lambda: np.array([net_x - 0.10, 0.0, top + p["net_height_m"] + dz]))   # noqa: E731
    v = relaunch(w, A, 420, cord(0.010), lambda: np.array([3.0, 0.0, 0.0]))              # into the net's top and back
    assert v["failed"] == T.OWN_COURT and w.task.trackers["net_touch"], v
    v = relaunch(w, A, 420, cord(0.017), lambda: np.array([3.0, 0.0, 0.0]))              # off the net's top and over:
    assert v["success"] and v["metrics"]["net_touch"] == 1.0, v                          # a good return (Law 2.7.1)
    v = relaunch(w, A, 420, lambda: np.array([net_x + 0.7, 0.7625 + 0.06, top - 0.015]),
                 lambda: np.array([0.0, -2.0, 0.0]))                                     # the opponent's side face
    assert v["failed"] == T.SIDE, v
    v = relaunch(w, A, 420, lambda: np.array([1.2, 1.2, 1.0]), lambda: np.array([0.0, 1.0, 0.0]))    # wide
    assert v["failed"] == T.FLOOR and v["stages"] == ["bounce", "strike"], v
    hand = lambda: d.geom_xpos[m.geom("right_wrist_pitch_link_sc0").id].copy()            # noqa: E731
    v = relaunch(w, A, 385, lambda: hand() + [0.0, 0.0, 0.15], lambda: np.array([0.0, 0.0, -3.0]),
                 at_strike=(3.0, 0.4, 1.6))                                  # struck with the racket hand below the
    assert v["success"] and events(w, "strike")[0]["with_hand"], (v, events(w, "strike"))   # wrist: legal (Law 2.5.7)

    # ---- the service
    w3, A3 = make(FAMILY, serve_x_m=0.03, serve_y_m=-0.276, serve_z_m=0.476)             # the ball waits on the blade
    hold(w3, A3)
    assert verdict(w3)["failed"] == T.EARLY and w3.t < 0.05, verdict(w3)
    w3, A3 = make(FAMILY, serve_vx=-6.0, serve_vz=1.0)                       # not a legal service (it hits the net)
    hold(w3, A3)
    assert verdict(w3)["failed"] == T.BAD_SERVICE, verdict(w3)
    w3, A3 = make(FAMILY, serve_time_s=7.995)                                # no service in time
    hold(w3, A3)
    assert verdict(w3)["failed"] == "time" and verdict(w3)["stages"] == [], verdict(w3)

    # ---- the robot and the table
    w.reset(); move_robot(w, x=net_x, y=-1.35, yaw=math.pi / 2)              # walking into the net's end
    up = w.robot.rest[12:29]
    while not w.done:
        act(w, A, "walk", np.r_[0.4, 0.0, 0.0, up, 0, 0])
    assert verdict(w)["failed"] == T.NET and w.t < p["serve_time_s"], (verdict(w), w.t, w.pelvis())
    w.reset(); at_table(w, A, pose=QL, stroke=False)                         # the free hand on the playing surface
    v = verdict(w)                                                           # when the ball comes into play
    assert v["failed"] == T.FREE_HAND and abs(w.t - p["serve_time_s"]) < 0.02, (v, w.t)
    w.reset(); hold(w, A, 0.2); kick_robot(w, vel=(-2.5, 0.0, 0.0)); hold(w, A)
    assert verdict(w)["failed"] == "fell", verdict(w)
    print("PASS table-tennis-return")


if __name__ == "__main__":
    main()
