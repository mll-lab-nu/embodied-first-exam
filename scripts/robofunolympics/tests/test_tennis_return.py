"""tennis-return (v2, the ITF court, the 30 m/s serve, the 0.30 kg racket on the H1-2): the referee's test. No real
solution exists yet (FAMILIES.md: the task may be beyond today's controllers), so the positive is an INJECTION:

* real: the serve's flight and its bounce in the right service box (the module's numbers; checked here against the
  target they were solved for), the robot's forehand pose (reached through `stand` rows), and the contact of the
  bounced ball with the still racket's strings;
* injected: the robot is teleported sideways before the serve so that its racket is in the ball's path (the serve
  passes 1.5 m to the left of where the receiver stands), and at the real string contact the ball's velocity is set
  to a return's (24 m/s, 9 degrees up; a still racket alone sends the 15 m/s ball back at 7 m/s: the second test);
  the return's flight over the net and its landing are real again.

Negatives, each with its exact reason: standing still (the ball bounces twice), the still racket as a wall (the ball
comes down on the robot's side), a volley, a body touch, a second hit, a carry, a return into the net, through the
net (a teleport: the referee's guard against tunnelling), long, wide, a line ball in and a ball just out, touching the
net, standing on the far side, touching the ball before the serve, a fall. Legal by Rule 25 and accepted: a return
round the net post."""
import numpy as np

from rfo.testing import act, hold, make, move_robot, verdict
from rfo.tasks import tennis_return as T

FAMILY = "tennis-return"
ARM = np.array([-0.286, -1.200, -0.712, 1.226, 0.446, -0.119, -0.442])   # forehand: the racket out to the right, strings to the net
R = T.BALL["radius"]
TARGET = (5.354, 0.598)                 # tn.py's draw: metres from the net, metres to the right of the centre line
V_IN, V_LOB = (23.66, 1.542, 3.72), (17.113, 2.241, 5.11)         # returns that land in (from the contact point)
V_LONG, V_WIDE, V_SHORT = (29.607, 1.47, 4.614), (22.422, 7.707, 3.723), (11.326, 1.39, 3.712)


def row(w, arm=None):
    q = w.robot.rest[12:27].copy()
    if arm is not None:
        q[8:15] = arm
    return np.r_[q, 0.0, 0.0]


def ready(w, A, seconds=1.5):
    """The forehand pose, reached in `stand` mode."""
    rest, n = w.robot.rest[20:27], int(round(seconds / w.CONTROL_DT))
    for i in range(1, n + 1):
        act(w, A, "stand", row(w, rest + (ARM - rest) * i / n))


def strings(w):
    """The head's centre and the strings' normal (towards the net)."""
    g = w.m.geom("racket_head").id
    n = w.d.xmat[w.robot.mount["right"]].reshape(3, 3)[:, 0]
    return w.d.geom_xpos[g].copy(), n * np.sign(n[0])


def keep(w, A, seconds=None, until=None):
    n = None if seconds is None else int(round(seconds / w.CONTROL_DT))
    while not w.done and (n is None or n > 0) and not (until is not None and until()):
        act(w, A, "stand", row(w, ARM))
        n = None if n is None else n - 1


def to_contact(w, A, path):
    """Real: pose, serve, bounce, string contact. Injected: the robot's place (its racket in the serve's path)."""
    w.reset(); ready(w, A)
    c, n = strings(w)
    assert n[0] > 0.97, n                                                   # the strings face the net
    i = next(k for k, b in enumerate(path) if b[0] <= c[0] + 0.0125 + R)    # where the serve meets the strings' plane
    f = (path[i - 1][0] - (c[0] + 0.0125 + R)) / (path[i - 1][0] - path[i][0])
    hit = path[i - 1] + f * (path[i] - path[i - 1])
    assert abs(hit[2] - c[2]) < 0.08, (hit, c)                              # the ball arrives at the pose's height
    move_robot(w, y=w.pelvis()[1] + hit[1] - c[1])
    keep(w, A, until=lambda: w.ref.has("racket"))
    assert w.ref.stages == ["bounce", "racket"] and not w.done, verdict(w)


def shoot(w, v):
    """The ball leaves the strings with the velocity v (set 3 cm clear of them, so that the contact adds nothing)."""
    w.put("ball", w.pos("ball") + 0.03 * strings(w)[1], vel=v)


def main():
    w, A = make(FAMILY)
    p, task = w.task.p, w.task
    nx, cy = p["net_x_m"], p["centre_y_m"]
    assert (w.robot.name, task.robot) == ("unitree_h1", "unitree_h1") and task.rulebook and len(task.deviations) >= 5
    for text in (task.sentence, task.rules, task.venue, task.difficulty, *task.deviations):
        text.format(**p, time_limit_s=task.time_limit_s)                    # every number quoted is a parameter
    assert abs(T.net_top(0.0) - 0.914) < 1e-9 and abs(T.net_top(T.POST_Y) - 1.07) < 1e-9 and abs(T.POST_Y - 5.029) < 1e-3
    # the net's geometry is the profile the referee judges with: the mesh's top at the centre and at the posts
    g = w.m.geom("net_L").id
    v = w.m.mesh_vert[w.m.mesh_vertadr[w.m.geom_dataid[g]]:][:8]
    top = w.d.geom_xpos[g] + v @ w.d.geom_xmat[g].reshape(3, 3).T
    assert abs(top[:, 2].max() - 1.07) < 1e-4 and abs(sorted(set(np.round(top[:, 2], 4)))[1] - 0.914) < 1e-4, top
    assert abs(w.m.body_mass[w.robot.mount["right"]] - 0.30) < 1e-6        # the racket: 0.30 kg on the hand, nothing else
    assert "right_tool" in task.legal_ground                               # the racket may touch the ground

    # ---- nop: the real serve; it bounces in the right service box at the target, passes, and bounces again
    path = []
    hold(w, A, p["serve_time_s"])
    while not w.done:
        hold(w, A, w.CONTROL_DT)
        path.append(w.pos("ball"))
    v = verdict(w)
    assert v["failed"] == "the ball bounced twice before the racket hit it" and v["stages"] == ["bounce"], v
    b = next(e for e in w.ref.events if e.get("stage") == "bounce")
    assert abs(b["x"] - (nx - TARGET[0])) < 0.05 and abs(b["y"] - (cy - TARGET[1])) < 0.05, b      # on tn.py's target
    assert 0.65 < b["t"] - p["serve_time_s"] < 0.75, b                      # 30 m/s: 0.70 s to the bounce
    path = np.array(path)

    # ---- the positive (injection, see the docstring)
    to_contact(w, A, path)
    e = next(e for e in w.ref.events if e.get("stage") == "racket")
    assert 12.0 < e["speed_in_m_s"] < 18.0, e                                # the bounced serve is still fast
    shoot(w, V_IN); keep(w, A)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["bounce", "racket", "over the net", "in"], v
    assert nx < v["metrics"]["landing_x_m"] < nx + T.HALF_LENGTH and w.t < 6.0, (v, w.t)
    sha = w.state_sha()
    to_contact(w, A, path); shoot(w, V_IN); keep(w, A)
    assert w.state_sha() == sha                                             # the same run again: the same state
    to_contact(w, A, path); shoot(w, V_LOB); keep(w, A)                     # a slower, higher return is as good
    assert verdict(w)["success"], verdict(w)

    # ---- the still racket alone (real contact, nothing injected but the robot's place): no return
    to_contact(w, A, path); keep(w, A)
    assert verdict(w)["failed"] == "the ball landed on your own side", verdict(w)

    # ---- where the return goes
    for vel, why in ((V_SHORT, "the ball landed on your own side"), (V_LONG, "the ball landed outside the court"),
                     (V_WIDE, "the ball landed outside the court")):
        to_contact(w, A, path); shoot(w, vel); keep(w, A)
        assert verdict(w)["failed"] == why and "in" not in verdict(w)["stages"], (vel, verdict(w))
    to_contact(w, A, path)                                                  # into the net: it stops there and drops
    w.put("ball", (nx - 1.0, cy, 0.5), vel=(25.0, 0.0, 0.0)); keep(w, A)
    assert verdict(w)["failed"] == "the ball landed on your own side", verdict(w)
    assert w.pos("ball")[0] < nx, w.pos("ball")
    to_contact(w, A, path)                                                  # (a teleport through the net: the guard)
    w.put("ball", (nx - 0.02, cy + 1.0, 0.5)); keep(w, A, 0.01)
    w.put("ball", (nx + 0.10, cy + 1.0, 0.5)); keep(w, A)
    assert verdict(w)["failed"] == "the ball went through the net", verdict(w)
    to_contact(w, A, path)                                                  # round the post and in: Rule 25 b, good
    w.put("ball", (nx - 1.0, cy + T.POST_Y + 0.5, 0.6), vel=(12.0, -4.0, 3.0)); keep(w, A)
    v = verdict(w)
    e = next(e for e in w.ref.events if e.get("stage") == "over the net")
    assert v["success"] and e["y"] - cy > T.POST_Y and e["z"] < 1.07, (v, e)
    for dx, good in ((-0.02, True), (0.02, False)):                         # Rule 12: on the baseline is in; the
        to_contact(w, A, path)                                              # point under the centre decides
        w.put("ball", (nx + 2.0, cy, 3.0)); keep(w, A, 0.01)                # (carried over the net by hand, then
        w.put("ball", (nx + T.HALF_LENGTH + dx, cy + T.HALF_WIDTH - 0.02, 0.3)); keep(w, A)     # dropped on the corner)
        v = verdict(w)
        assert v["success"] if good else v["failed"] == "the ball landed outside the court", (dx, v)

    # ---- how the ball may be played
    w.reset(); ready(w, A); keep(w, A, until=lambda: w.t >= p["serve_time_s"] + 0.30)      # a volley: before the bounce
    c, n = strings(w)
    w.put("ball", c + 0.30 * n, vel=-15.0 * n); keep(w, A)
    assert verdict(w)["failed"] == "the racket hit the ball before it bounced", verdict(w)
    w.reset(); hold(w, A, p["serve_time_s"] + 0.2)                          # the ball against the chest
    w.put("ball", (0.6, 0.0, 1.3), vel=(-8.0, 0.0, 0.0)); hold(w, A)
    assert verdict(w)["failed"] == "the ball touched you", verdict(w)
    to_contact(w, A, path); shoot(w, (3.0, 0.0, 2.0)); keep(w, A, 0.15)     # a second hit, 0.15 s after the first
    c, n = strings(w)
    assert not w.done
    w.put("ball", c + 0.20 * n, vel=-8.0 * n); keep(w, A)
    assert verdict(w)["failed"] == "the racket hit the ball twice", verdict(w)
    to_contact(w, A, path)                                                  # held on the strings: a carry
    while not w.done:
        c, n = strings(w)
        w.put("ball", c + (0.0125 + R - 0.002) * n)
        act(w, A, "stand", row(w, ARM))
    assert verdict(w)["failed"] == "the racket carried the ball", verdict(w)

    # ---- where the robot may be
    w.reset(); hold(w, A, 0.2); move_robot(w, x=nx - 0.10, y=cy); hold(w, A, 0.5)           # at the net: the legs in it
    assert verdict(w)["failed"] == "you touched the net", verdict(w)
    w.reset(); hold(w, A, 0.2); move_robot(w, x=nx + 2.0, y=cy); hold(w, A, 0.5)            # on the server's side
    assert verdict(w)["failed"] == "you touched the far side of the court", verdict(w)
    w.reset(); w.pin("ball", (0.45, -0.17, 1.13)); hold(w, A, 0.2)          # the waiting ball is not to be touched
    assert verdict(w)["failed"] == "the ball was touched before the serve", verdict(w)
    w.reset(); hold(w, A, 0.2); move_robot(w, z=0.30); hold(w, A, 0.5)      # on the ground
    assert verdict(w)["failed"] == "fell", verdict(w)
    print(f"PASS {FAMILY}")


if __name__ == "__main__":
    main()
