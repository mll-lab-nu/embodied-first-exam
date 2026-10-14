"""discus (v2): a standing throw (no spin across the circle) from a technique found offline by
scripts/robofunolympics/search_technique.py, RoboOlympics' method (pingyue's kit/throwing/optimize.py): five key
poses of the whole body (the legs as synergies that keep both feet flat: crouch, shift, sway and the pelvis' turn;
the trunk and the arms by joint; the start a hand-made wind-up: the trunk turned far to the right, the arm out at the
side), their times and the release time, searched by CMA-ES in the task's own frozen instance, each trial scored on
the referee's verdict and distance. The trunk's turn (the H1-2's waist motor, 200 N m) throws; the arm only carries
the discus. Played as Unitree LowCmd rows along a Catmull-Rom curve through the keys; the grip lets go at the release
time. Then the walking policy at zero command, backwards out of the rear half of the circle, and stands.
Measured: release at 12.9 m/s from 1.82 m, the discus tilted 51 degrees and spinning at 24 rad/s; it lands 15.87 m
from the rim (the line is 15 m); success after 8.5 s. Open loop on the one frozen start, not robust (a few of each
generation's 48 neighbours succeed)."""
import numpy as np

TECHNIQUE = {"times": [0.8249, 1.2163, 1.3917, 1.619, 3.2126], "release_s": 1.4132, "hand": 'right', "keys": [
        [0.3607, -0.3331, -0.0199, 0.7476, -0.4146, 0.0207, 0.3688, -0.4153, -0.0361, 0.7452, -0.3298, 0.0349, -1.671, -0.4805, 0.3875, 0, 1.2313, 0, 0, 0, 0.1163, -1.2419, -0.2503, 2.1856, 0.064, 0.1289, 0.3897],
        [0.3035, -0.4453, -0.0357, 1.017, -0.5719, 0.0382, 0.3126, -0.5254, -0.0488, 1.0223, -0.4968, 0.0482, -0.8844, -0.7162, 0.7646, 0, 0.0205, 0, 0, 0, -0.7684, -1.3143, -0.2901, 2.4468, -0.4028, -0.0893, -0.1835],
        [-0.3066, -0.1479, -0.0102, 0.4564, -0.3085, 0.01, -0.3072, -0.0417, -0.0204, 0.3807, -0.3391, 0.0203, 0.858, -0.1811, -0.2889, 0, 0.3146, 0, 0, 0, -0.277, -2.2289, -0.2556, 0.6373, -0.0724, 0.3382, -0.172],
        [-0.43, -0.346, -0.03, 0.6287, -0.2826, 0.0287, -0.43, -0.179, -0.0766, 0.5774, -0.398, 0.0759, 1.6886, -0.2166, 0.5658, 0, -0.3121, 0, 0, 0, 0.1038, -2.2998, 0.2768, 1.5151, -0.2836, -0.3811, 0.1109],
        [-0.2404, -0.2152, 0.0925, 0.406, -0.1908, -0.0924, -0.2344, -0.1606, 0.0863, 0.4034, -0.2431, -0.0872, -0.1719, -0.0074, -0.1379, 0, 0.1239, 0, 0, 0, 0.1828, -0.411, -0.4077, 1.4091, 0.1841, 0.47, -0.4777]]}


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
    q0 = w.d.qpos[r.qadr].copy()
    Q, QD = curve(q0, np.asarray(tech["keys"], float), np.asarray(tech["times"], float), w.CONTROL_DT)
    kp, kd = r.kp0 * tech.get("kp_scale", 1.0), r.kd0
    g = {"right": 1, "left": 0}.get(tech.get("hand", "right"))
    for k in range(len(Q)):
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
        recover(s)
