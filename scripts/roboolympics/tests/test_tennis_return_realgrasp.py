"""tennis-return-realgrasp (tennis-return with a free 0.30 kg racket held only by the H1-2's right Dex1-1 gripper):
the referee's test.

Two positives. The first is a REAL CONTROLLER, the reference solution oracles/tennis-return-realgrasp/oracle.py
(walking policy rows only: it walks 0.7 m to the left, takes a backswing and plays a backhand at a fixed time; nothing
injected). The second is a forehand, a REAL SWING with one injection:
* injected: the robot's place. Before the serve it is teleported (with the racket in its gripper) to where its
  forehand meets the bounced serve: 2.1 m into the court and 3.0 m to the left of its start (the serve bounces 2.15 m
  to its left and the racket head is 1.2 m to the right of the pelvis; the walking policy cannot cover that in the
  3.8 s before the ball arrives);
* real: everything else. The arm goes to a backswing through `stand` rows, the swing is one `stand` row (the torso's
  yaw from -0.73 to +0.52 rad and a small arm change, found by a search of swings on the deterministic serve), the
  racket head reaches about 9 m/s, the bounced 16 m/s serve meets the strings, the racket twists in the 120 N grip and
  stays held, the ball leaves at about 20 m/s and 12 degrees up, flies over the net and lands in the far court; the
  robot then holds its pose on the walking policy at zero command. Moving the robot's place by 2 cm either way in x
  and y (9 variations) still returns the ball into the court (measured during the search).

Negatives, each with its exact reason: standing still (two bounces); the racket dropped (the gripper opened); the
racket let go in the swing (thrown: it leaves the hand); the racket put into the ball's path away from the hand (it
hits the ball but is not in the hand); the ball against the gripper and against the forearm (not the racket); a volley;
a second hit; a carry; returns that land short, long and wide; into the net; through the net (a teleport: the
referee's guard); a line ball in and a ball just out; the racket in the net; the robot in the net; standing on the far
side; the racket touching the waiting ball before the serve; a fall. Determinism: the positive twice gives the same
state hash."""
import importlib.util
import pathlib

import numpy as np

from rfo.testing import act, hold, make, move_robot, verdict
from rfo.tasks import tennis_return_realgrasp as T

FAMILY = "tennis-return-realgrasp"
R = T.BALL["radius"]
LEFT_THROWN = "the racket left your hand"
# the swing (search result, see the docstring): torso yaw back / forward, the arm's backswing and swing targets (right
# shoulder pitch, roll, yaw, elbow pitch, elbow roll, wrist pitch, wrist yaw), the swing's start, the robot's place
SWING = dict(TB=-0.7329, TF=0.5232,
             arm=[-0.3831, -0.9392, -0.9099, 1.0024, 0.2142, -0.4872, -0.0744],
             arm2=[-0.2677, -0.7801, -0.9131, 1.0367, 0.1419, -0.6311, -0.0185],
             ts=3.81, x=2.0821, y=3.0368, nsw=40)
TARGET = (5.354, 0.598)                 # tn.py's draw: metres from the net, metres to the right of the centre line
V_LONG, V_WIDE, V_SHORT = (29.607, 1.47, 4.614), (22.422, 7.707, 3.723), (11.326, 1.39, 3.712)


def row(torso, arm, grip=1.0):
    q = np.zeros(15)
    q[0], q[8:15] = torso, arm
    return np.r_[q, 0.0, grip]


def head(w):
    """The strings' centre and normal (towards +x)."""
    b = w.m.body("racket").id
    Rr = w.d.xmat[b].reshape(3, 3)
    n = Rr[:, 0]
    return w.d.xpos[b] + Rr @ np.array([0, 0, T.FREE_RACKET["head_centre_z_m"]]), n * np.sign(n[0])


def in_jaws(w):
    """The racket's rotation (deg) and the butt's offset (m) relative to the gripper's jaw frame."""
    c, Rj = w.jaw_frame("right")
    b = w.m.body("racket").id
    return Rj.T @ w.d.xmat[b].reshape(3, 3), Rj.T @ (w.d.xpos[b] - c)


SW = {"k": 0}                           # the swing's step counter (across calls of swing())


def ready(w, A, P=SWING):
    """Backswing pose through `stand` rows (1.5 s), then the injected place."""
    arm, n = np.array(P["arm"]), 150
    for i in range(1, n + 1):
        act(w, A, "stand", row(P["TB"] * i / n, arm * i / n))
    move_robot(w, x=P["x"], y=P["y"], held=True)
    SW["k"] = 0


def swing(w, A, P=SWING, until=None, grip=None):
    """Wait in the backswing until ts, swing (one `stand` row for nsw steps), then hold the pose on the walking policy;
    `grip(k)` may change the gripper's command at swing step k; stops at `until()`."""
    arm, arm2 = np.array(P["arm"]), np.array(P["arm2"])
    stop = (lambda: False) if until is None else until
    while not w.done and w.t < P["ts"] - 1e-9 and not stop():
        act(w, A, "stand", row(P["TB"], arm))
    while not w.done and not stop():
        k = SW["k"]
        g = 1.0 if grip is None else grip(k)
        if k < P["nsw"]:
            act(w, A, "stand", row(P["TF"], arm2, g))
        else:
            act(w, A, "walk", np.r_[0.0, 0.0, 0.0, row(P["TF"], arm2, g)])
        SW["k"] = k + 1


def to_hit(w, A):
    """The real swing up to the first contact of the racket with the ball."""
    w.reset()
    ready(w, A)
    swing(w, A, until=lambda: w.ref.has("racket"))
    assert w.ref.stages == ["bounce", "racket"] and not w.done, verdict(w)


def keep(w, A, seconds=None):
    n = None if seconds is None else int(round(seconds / w.CONTROL_DT))
    while not w.done and (n is None or n > 0):
        act(w, A, "walk", np.r_[0.0, 0.0, 0.0, row(SWING["TF"], SWING["arm2"])])
        n = None if n is None else n - 1


def shoot(w, v):
    """After the real contact: the ball leaves with the velocity v (set 3 cm clear of the strings)."""
    w.put("ball", w.pos("ball") + 0.03 * head(w)[1], vel=v)


class Driver:
    """The part of rcb_rfo.Session an oracle uses, on a bare World."""

    def __init__(self, w, A):
        self.world, self.A = w, A

    @property
    def done(self):
        return self.world.done

    def step(self, typ, row):
        act(self.world, self.A, typ, row)
        return self.world.done


def oracle():
    src = pathlib.Path(__file__).resolve().parent.parent / "oracles" / FAMILY / "oracle.py"
    spec = importlib.util.spec_from_file_location("oracle_tennis_return_realgrasp", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    w, A = make(FAMILY)
    p, task = w.task.p, w.task
    nx, cy = p["net_x_m"], p["centre_y_m"]
    assert (w.robot.name, task.robot) == ("unitree_h1", "unitree_h1") and task.rulebook and len(task.deviations) >= 6
    for text in (task.sentence, task.rules, task.venue, task.difficulty, *task.deviations):
        text.format(**p, time_limit_s=task.time_limit_s)                    # every number quoted is a parameter
    assert abs(T.net_top(0.0) - 0.914) < 1e-9 and abs(T.net_top(T.POST_Y) - 1.07) < 1e-9
    # the racket: a free 0.30 kg body balanced 0.33 m from the butt, ITF Appendix II, an octagonal 4 3/8 in handle
    b = w.m.body("racket").id
    assert "racket" in w.free and abs(w.m.body_mass[b] - 0.30) < 1e-9 and abs(w.m.body_ipos[b][2] - 0.33) < 1e-9
    g = w.m.geom("racket_handle").id
    v = w.m.mesh_vert[w.m.mesh_vertadr[w.m.geom_dataid[g]]:][:w.m.mesh_vertnum[w.m.geom_dataid[g]]]
    v = v @ w.d.geom_xmat[g].reshape(3, 3).T + w.d.geom_xpos[g] - w.d.xpos[b]      # (MuJoCo centres a mesh)
    loc = v @ w.d.xmat[b].reshape(3, 3)
    assert abs(np.ptp(loc[:, 0]) - 0.0335) < 1e-4 and abs(np.ptp(loc[:, 1]) - 0.0335) < 1e-4, np.ptp(loc, axis=0)
    per = sum(np.linalg.norm(loc[i, :2] - loc[(i + 1) % 8, :2]) for i in range(8))
    assert abs(per - 0.111) < 0.001, per                                    # grip size 4 3/8 in = 111 mm round
    tips, Rb = [], w.d.xmat[b].reshape(3, 3)
    for gg in range(w.m.ngeom):
        if w.m.geom_bodyid[gg] == b and w.m.geom(gg).name.startswith("racket_frame"):
            r, hl = w.m.geom_size[gg][:2]
            ax = w.d.geom_xmat[gg].reshape(3, 3)[:, 2]
            tips += [(Rb.T @ (w.d.geom_xpos[gg] + s * hl * ax - w.d.xpos[b]))[2] + r for s in (-1, 1)]
    assert abs(max(tips) - 0.685) < 0.002 and abs(min(loc[:, 2])) < 1e-6, max(tips)     # 0.685 m from the butt
    # the real hand: no weld anywhere; the racket in the right gripper at 120 N, the handle along the jaws
    assert w.real_hands == {"right": "dex1"} and w.held["right"] == "racket" and not w.welds
    assert task.grasp["force_n"] > 119.0 and abs(task.grasp["opening_m"] - 0.0335) < 0.002, task.grasp
    Rel, off = in_jaws(w)
    assert np.allclose(Rel, np.eye(3), atol=0.02) and abs(off[2] + 0.035) < 0.003, (Rel, off)

    # ---- nop: the racket stays in the hand at rest; the serve bounces on tn.py's target, passes, and bounces again
    path = []
    hold(w, A, p["serve_time_s"])
    assert w.held["right"] == "racket" and not w.done
    rot0 = np.degrees(np.arccos(np.clip((np.trace(in_jaws(w)[0]) - 1) / 2, -1, 1)))
    assert rot0 < 1.0, rot0                                                  # 3 s of gravity: under a degree
    while not w.done:
        hold(w, A, w.CONTROL_DT)
        path.append(w.pos("ball"))
    v = verdict(w)
    assert v["failed"] == "the ball bounced twice before the racket hit it" and v["stages"] == ["bounce"], v
    e = next(e for e in w.ref.events if e.get("stage") == "bounce")
    assert abs(e["x"] - (nx - TARGET[0])) < 0.05 and abs(e["y"] - (cy - TARGET[1])) < 0.05, e
    assert 0.65 < e["t"] - p["serve_time_s"] < 0.75, e

    # ---- the positive by a real controller: the reference solution (a walk and a backhand), twice
    o = oracle()
    w.reset(); o.solve(Driver(w, A))
    v = verdict(w)
    assert v["success"] and w.held["right"] == "racket", v
    print(f"oracle: success at {w.t:.2f} s, landing {v['metrics']['landing_x_m'] - nx:.2f} m past the net", flush=True)
    sha = w.state_sha()
    w.reset(); o.solve(Driver(w, A))
    assert w.state_sha() == sha

    # ---- the positive: a real swing (the robot's place injected, see the docstring)
    w.reset()
    ready(w, A)
    swing(w, A, until=lambda: w.ref.has("racket"))
    before, _ = in_jaws(w)
    e = next(e for e in w.ref.events if e.get("stage") == "racket")
    assert 14.0 < e["speed_in_m_s"] < 18.0, e                               # the bounced serve is still fast
    swing(w, A, until=lambda: w.ref.time > e["t"] + 0.03)
    vout = w.vel("ball")
    twist = []

    def turned():
        twist.append(np.degrees(np.arccos(np.clip((np.trace(before.T @ in_jaws(w)[0]) - 1) / 2, -1, 1))))
        return w.ref.time > e["t"] + 0.15
    swing(w, A, until=turned)
    swing(w, A)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["bounce", "racket", "over the net", "in"], v
    assert np.linalg.norm(vout) > 15.0 and vout[0] > 0, vout                # the swing sent it back fast
    assert w.held["right"] == "racket" and v["metrics"].get("grip_break_max_s", 0.0) < p["out_of_hand_s"], v
    print(f"positive: ball in {e['speed_in_m_s']:.1f} m/s, out {np.linalg.norm(vout):.1f} m/s "
          f"({np.degrees(np.arcsin(vout[2] / np.linalg.norm(vout))):.1f} deg up), racket turned in the grip "
          f"{max(twist):.1f} deg in the 0.12 s after the hit, landing {v['metrics']['landing_x_m'] - nx:.2f} m past "
          f"the net, longest two-jaw break {v['metrics'].get('grip_break_max_s', 0.0) * 1000:.0f} ms", flush=True)
    sha = w.state_sha()
    w.reset(); ready(w, A); swing(w, A)
    assert verdict(w)["success"] and w.state_sha() == sha                   # the same run again: the same state

    # ---- the racket must stay in the hand
    w.reset(); hold(w, A, 1.0, grips=(0.0, 0.0))                             # dropped: the gripper opened
    v = verdict(w)
    assert v["failed"] == LEFT_THROWN and v["stages"] == [] and w.t < 1.0, v
    w.reset(); ready(w, A)                                                  # thrown: let go 50 ms before the hit
    swing(w, A, grip=lambda k: 1.0 if k < 14 else 0.0)
    assert verdict(w)["failed"] == LEFT_THROWN, verdict(w)
    w.reset()                                                               # the racket out of the hand, still,
    i = next(i for i, q in enumerate(path) if q[0] < 1.0)                   # in the bounced ball's path 1 m ahead
    hold(w, A, p["serve_time_s"] + (i + 1) * w.CONTROL_DT - 0.02)
    w.put("racket", path[i] - (0.0, 0.0, T.FREE_RACKET["head_centre_z_m"]))
    hold(w, A)
    v = verdict(w)
    assert v["failed"] == LEFT_THROWN and "racket" in v["stages"], v        # it hit the ball, but not in the hand

    # ---- the ball must be played with the racket
    for part, where in (("right_hand", "right_hand_housing"), ("right_forearm", None)):
        w.reset(); hold(w, A, p["serve_time_s"] + 0.75)                     # the bounce has happened
        assert w.ref.has("bounce") and not w.done
        if where:
            tgt = w.d.geom_xpos[w.m.geom(where).id]
        else:
            tgt = w.d.xpos[w.m.body("right_elbow_roll_link").id] + 0.0
        w.put("ball", tgt + (0.0, 0.25, 0.0), vel=(0.0, -8.0, 0.0)); hold(w, A)
        v = verdict(w)
        assert v["failed"] == "the ball touched you", v
        ev = next(x for x in w.ref.events if x.get("reason") == "the ball touched you")
        assert part in ev["parts"], (part, ev)
    w.reset(); ready(w, A); swing(w, A, until=lambda: w.t >= p["serve_time_s"] + 0.30)  # a volley: before the bounce
    c, n = head(w)
    w.put("ball", c + 0.20 * n, vel=-12.0 * n); swing(w, A)
    assert verdict(w)["failed"] == "the racket hit the ball before it bounced", verdict(w)
    to_hit(w, A); swing(w, A, until=lambda: w.ref.time > e["t"] + 0.15)     # a second hit, 0.15 s after the first
    assert not w.done, verdict(w)
    c, n = head(w)
    w.put("ball", c + 0.20 * n, vel=-8.0 * n); swing(w, A)
    assert verdict(w)["failed"] == "the racket hit the ball twice", verdict(w)
    to_hit(w, A)                                                            # held on the strings: a carry
    while not w.done:
        c, n = head(w)
        w.put("ball", c + (T.FREE_RACKET["strings_half_thickness_m"] + R - 0.002) * n, vel=(0.0, 0.0, 0.0))
        act(w, A, "walk", np.r_[0.0, 0.0, 0.0, row(SWING["TF"], SWING["arm2"])])
    assert verdict(w)["failed"] == "the racket carried the ball", verdict(w)

    # ---- where the return goes
    for vel, why in ((V_SHORT, "the ball landed on your own side"), (V_LONG, "the ball landed outside the court"),
                     (V_WIDE, "the ball landed outside the court")):
        to_hit(w, A); shoot(w, vel); keep(w, A)
        assert verdict(w)["failed"] == why and "in" not in verdict(w)["stages"], (vel, verdict(w))
    to_hit(w, A)                                                            # into the net: it stops and drops
    w.put("ball", (nx - 1.0, cy, 0.5), vel=(25.0, 0.0, 0.0)); keep(w, A)
    assert verdict(w)["failed"] == "the ball landed on your own side" and w.pos("ball")[0] < nx, verdict(w)
    to_hit(w, A)                                                            # (a teleport through the net: the guard)
    w.put("ball", (nx - 0.02, cy + 1.0, 0.5)); keep(w, A, 0.01)
    w.put("ball", (nx + 0.10, cy + 1.0, 0.5)); keep(w, A)
    assert verdict(w)["failed"] == "the ball went through the net", verdict(w)
    for dx, good in ((-0.02, True), (0.02, False)):                         # Rule 12: on the baseline is in
        to_hit(w, A)
        w.put("ball", (nx + 2.0, cy, 3.0)); keep(w, A, 0.01)
        w.put("ball", (nx + T.HALF_LENGTH + dx, cy + T.HALF_WIDTH - 0.02, 0.3)); keep(w, A)
        v = verdict(w)
        assert v["success"] if good else v["failed"] == "the ball landed outside the court", (dx, v)

    # ---- where the robot and the racket may be
    w.reset(); hold(w, A, 0.2)                                              # the racket's tip (held, pointing
    rb = w.m.body("racket").id                                              # ahead) on a net post, the robot 0.9 m off
    tip = max(w.d.geom_xpos[g][0] + w.m.geom_rbound[g] for g in range(w.m.ngeom) if w.m.geom_bodyid[g] == rb)
    post_y = cy + T.POST_Y + T.POST_R + T.NET_HALF_THICK
    move_robot(w, x=w.pelvis()[0] + (nx - T.POST_R + 0.01 - tip), y=w.pelvis()[1] + post_y - head(w)[0][1], held=True)
    hold(w, A, 0.3)
    assert verdict(w)["failed"] == "the racket touched the net", verdict(w)
    w.reset(); hold(w, A, 0.2); move_robot(w, x=nx - 0.10, y=cy - 2.0, held=True); hold(w, A, 0.5)
    assert verdict(w)["failed"] in ("you touched the net", "the racket touched the net"), verdict(w)
    w.reset(); hold(w, A, 0.2); move_robot(w, x=nx + 2.0, y=cy, held=True); hold(w, A, 0.5)
    assert verdict(w)["failed"] == "you touched the far side of the court", verdict(w)
    w.reset(); hold(w, A, 0.2)                                              # the waiting ball is not to be touched
    c, n = head(w)
    w.pin("ball", tuple(c + (T.FREE_RACKET["strings_half_thickness_m"] + R - 0.003) * n)); hold(w, A, 0.2)
    assert verdict(w)["failed"] == "the ball was touched before the serve", verdict(w)
    w.reset(); hold(w, A, 0.2); move_robot(w, z=0.30, held=True); hold(w, A, 0.5)     # on the ground
    assert verdict(w)["failed"] == "fell", verdict(w)
    print(f"PASS {FAMILY}")


if __name__ == "__main__":
    main()
