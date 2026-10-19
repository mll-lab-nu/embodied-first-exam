"""shot-put-realgrasp: a standing put (no glide, no spin) from a technique found offline by CMA-ES in this family's
own physics (scripts/roboolympics/search_technique.py's method: four key poses of the whole body, the legs as
synergies that keep both feet flat (crouch, shift, sway, the pelvis' turn), the trunk and the arms by joint, and their
times). The shot is not gripped: it rests on the open right palm against the neck, and the technique's curve starts
from the command in force (the start command carries the shot; a curve from the measured joint angles would drop the
arm under it). The start keys: a crouch with the arm as it holds the shot, then the legs' drive with the arm moved
along a path on which the hand travels along the palm's normal (found by a kinematic search), so that the palm stays
behind the shot while it turns from the neck towards the throw; the search ran 200 + 200 + 50 generations of 24
trials (the last ones scoring a valid landing past the line above a short one even when a foul or a fall followed).
Played as Unitree LowCmd rows along a Catmull-Rom curve through the keys, the grip columns 0. Then the walking policy at
zero command, backwards out of the rear half of the circle, and stands.
Measured: the shot leaves the palm (its last contact) at 7.5 m/s from 1.92 m, pushed (0.952 of its speed away from the
shoulder), and lands 6.65 m from the rim (the line is 6 m); success after 6.0 s. Open loop on the one frozen start and
on a knife edge (a few trials of the search's later generations succeeded)."""
import numpy as np

TECHNIQUE = {"times": [0.767, 0.9042, 1.0296, 1.9845], "release_s": 0.8686, "hand": None, "keys": [
        [-0.0514, -0.7726, -0.0566, 1.6947, -0.8973, 0.0543, -0.052, -0.7514, -0.057, 1.6917, -0.8973, 0.0555, -1.4175, -0.9494, 1.2212, 0.3276, 0.0195, 0, 0, 0, -0.5969, -0.8601, 1.0446, -0.95, -1.0901, -0.47, -1.27],
        [-0.43, -0.4185, -0.0685, 0.8321, -0.413, 0.065, -0.43, -0.2889, -0.0938, 0.7952, -0.5055, 0.0924, 1.9814, -1.981, -0.38, -0.9385, 0.0369, 0, 0, 0, -0.1478, -0.585, 0.5101, 0.4821, -1.0949, 0.47, -1.27],
        [-0.43, -0.097, 0.1642, 0.3556, -0.2601, -0.1652, -0.43, 0.3591, 0.107, -0.2292, -0.1346, -0.103, -0.2082, -0.389, 0.4207, -0.6879, -0.1493, 0, 0, 0, -1.4564, -1.4666, -1.5143, 1.7952, -0.2872, 0.47, -0.1524],
        [-0.2854, -0.3549, 0.1434, 0.665, -0.3098, -0.1433, -0.2739, -0.2905, 0.1342, 0.6668, -0.3769, -0.1375, -1.7641, 0.2004, -0.38, -0.6311, 0.4221, 0, 0, 0, 0.0311, 0.2573, 0.0182, -0.1074, -0.4125, -0.47, -1.27]]}


def curve(q0, keys, times, dt):
    """Positions and speeds every dt along the cubic Hermite curve through q0 (t = 0) and the keys, Catmull-Rom
    tangents, zero speed at both ends (RoboOlympics' kit/throwing/technique.py)."""
    p = np.vstack([q0, keys])
    t = np.concatenate([[0.0], times])
    v = np.zeros_like(p)
    v[1:-1] = (p[2:] - p[:-2]) / (t[2:] - t[:-2])[:, None]
    s = np.arange(1, int(np.ceil(t[-1] / dt - 1e-9)) + 1) * dt
    s = np.minimum(s, t[-1])
    i = np.clip(np.searchsorted(t, s, side="right") - 1, 0, len(t) - 2)
    h = (t[i + 1] - t[i])[:, None]
    u = (s - t[i])[:, None] / h
    q = ((2 * u ** 3 - 3 * u ** 2 + 1) * p[i] + (u ** 3 - 2 * u ** 2 + u) * h * v[i]
         + (-2 * u ** 3 + 3 * u ** 2) * p[i + 1] + (u ** 3 - u ** 2) * h * v[i + 1])
    qd = ((6 * u ** 2 - 6 * u) * p[i] / h + (3 * u ** 2 - 4 * u + 1) * v[i]
          + (-6 * u ** 2 + 6 * u) * p[i + 1] / h + (3 * u ** 2 - 2 * u) * v[i + 1])
    return q, qd


def play(s, tech, watch=None):
    """The technique from the current state (after its walk, if any): one LowCmd row per control step to its last
    key; the grip of tech["hand"] (if any) on until release_s. watch(s) is called after every step (the search's probe). Returns True if the episode ended."""
    w = s.world
    r = w.robot
    n = r.L.NJ
    for vx, vy, wz, secs in tech.get("prelude", []):     # a walk first (the walking policy), the arms as they are
        up = w.d.qpos[r.qadr][12:].copy()
        for _ in range(int(round(secs / w.CONTROL_DT))):
            if s.step("walk", np.r_[vx, vy, wz, up, 0.0, 0.0]):
                return True
            if watch:
                watch(s)
    q0 = r.arb.target().copy()                  # from the command in force (the start command carries the shot)
    Q, QD = curve(q0, np.asarray(tech["keys"], float), np.asarray(tech["times"], float), w.CONTROL_DT)
    kp, kd = r.kp0 * tech.get("kp_scale", 1.0), r.kd0
    g = {"right": 1, "left": 0}.get(tech.get("hand", "right"))
    for k in range(len(Q)):
        if tech.get("walk_s") is not None and (k + 1) * w.CONTROL_DT > tech["walk_s"]:
            return False                          # the walking policy takes over here (recover)
        grip = np.zeros(2)
        if g is not None:
            grip[g] = 1.0 if (k + 1) * w.CONTROL_DT < tech["release_s"] else 0.0
        if tech.get("legs") == "walk":           # the walking policy keeps the balance; the keys give the upper body
            row = np.r_[0.0, 0.0, 0.0, Q[k][12:], grip]
            if s.step("walk", row):
                return True
        elif s.step("lowcmd", np.r_[Q[k], QD[k], np.zeros(n), kp, kd, grip]):
            return True
        if watch:
            watch(s)
    return False


def upper(s):
    w = s.world
    return w.d.qpos[w.robot.qadr][12:].copy()


def recover(s, back_s=None, vx=-0.3, settle_s=1.5, watch=None):
    """The walking policy at zero command (the arms where they are, brought down), then backwards for back_s s (or
    until the referee's exit stage), then at rest to the end."""
    w = s.world
    r = w.robot
    up0 = upper(s)
    rest = r.rest[12:]
    k = 0
    while not s.done:
        t = k * w.CONTROL_DT
        f = min(1.0, t / 1.0)
        up = up0 + (rest - up0) * f
        moving = settle_s <= t and not w.ref.has("exit") and (back_s is None or t < settle_s + back_s)
        if s.step("walk", np.r_[vx if moving else 0.0, 0.0, 0.0, up, 0.0, 0.0]):
            return
        if watch:
            watch(s)
        k += 1


def solve(s, tech=None):
    tech = tech or TECHNIQUE
    if not play(s, tech):
        recover(s, **tech.get("recover", {}))
