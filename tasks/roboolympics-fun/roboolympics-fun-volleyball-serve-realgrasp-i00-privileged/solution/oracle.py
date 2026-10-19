"""volleyball-serve-realgrasp: a toss from the open left palm and an underarm serve, played as Unitree LowCmd rows along
a Catmull-Rom curve through key poses (volleyball-serve's oracle method, RoboOlympics' kit/throwing), then the walking
policy at zero command. The first key (at 0.07 s) is the toss: the left elbow flexes while the wrist turns the other
way, so the palm stays level and rises, and stops; the ball flies on (nothing holds it: it leaves the palm when the
palm slows down faster than gravity). In the second key the left arm still holds that pose; the keys after it turn
the trunk and swing the straight right arm through the ball. The technique was found offline by CMA-ES (the method
of scripts/roboolympics/search_technique.py, with the toss's numbers searched too) in the task's own start, each
trial scored on seven neighbours of itself (the servo gains x 0.97 / 1.03, the swing keys 0.01 s earlier / later): a
tiny toss (the ball leaves the palm at 0.9 m/s and is struck near its apex).
Measured: in at 0.87 m/s, out at 11.8 m/s, over the net between the antennas, lands 12.1 m ahead (2.6 m beyond the
net), 3.4 m to the right of the middle; success after 1.7 s. On a grid of ten neighbours (gains x 0.97 / 1.0 / 1.03
times the swing 0.01 s early / on time / late, and a toss 2 % smaller) 8 succeed: gains x 1.03 on time falls after
the hit, x 1.03 late lands short."""
import numpy as np

TECHNIQUE = {"times": [0.0659, 0.247, 0.8118, 1.0285, 1.1986, 2.076], "keys": [
        [-0.0159, -0.159, 0.0303, 0.3595, -0.2044, 0.1951, 0.0155, -0.1613, -0.0263, 0.3602, -0.1973, -0.1773, -0, 0.3248, -0.0546, -0.1642, -0.3492, -2.9181, 0, 0.0529, 0.0122, 0.0001, -0, 0.0182, 0.0001, 0.0076, -0],
        [0.1164, -0.2629, 0.0165, 0.391, -0.1281, -0.0169, 0.1166, -0.2776, 0.015, 0.3707, -0.0931, -0.0153, -2.35, -0.9096, 2.3787, -1.665, -0.95, -2.9181, 0, 0.0529, -0.381, 0.38, -0.3032, 2.6339, 0, 0, 0],
        [0.43, -0.3287, 0.0705, 0.8523, -0.5231, -0.0688, 0.43, -0.4606, 0.0403, 0.8786, -0.4179, -0.0381, 0.38, 0.831, 0.1565, 0.4712, 0.0573, -2.9181, 0, 0.0529, 0.3653, -0.4083, -0.4354, 2.4255, 0, 0, 0],
        [-0.0228, -0.0717, -0.0285, 0.3097, -0.238, 0.0285, -0.023, -0.0638, -0.0286, 0.304, -0.2403, 0.0286, -2.35, 0.9469, -0.38, 1.0712, 0.1119, -2.9181, 0, 0.0529, -2.4998, -1.5722, -1.2988, 1.3436, 0, 0, 0],
        [0.0023, -0.2022, 0.0117, 0.4729, -0.2707, -0.0117, 0.0023, -0.2028, 0.0117, 0.4731, -0.2703, -0.0117, -1.3944, 0.6376, -0.38, -1.7999, -0.95, -2.9181, 0, 0.0529, -2.0603, 0.3342, -0.2479, 1.8435, 0, 0, 0],
        [0.1842, -0.0726, 0.0225, 0.264, -0.1914, -0.0225, 0.1835, -0.1252, 0.0189, 0.288, -0.1628, -0.0188, -0.6354, 0.5368, -0.2622, -2.069, 0.3452, -2.9181, 0, 0.0529, -0.0853, -1.6554, 0.4011, 1.4099, 0, 0, 0]]}


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
    """The technique from the start: one LowCmd row per control step to its last key (the grip columns are 0: this
    task has no grip). watch(s) is called after every step. Returns True if the episode ended."""
    w = s.world
    r = w.robot
    n = r.L.NJ
    q0 = w.d.qpos[r.qadr].copy()
    Q, QD = curve(q0, np.asarray(tech["keys"], float), np.asarray(tech["times"], float), w.CONTROL_DT)
    kp, kd = r.kp0 * tech.get("kp_scale", 1.0), r.kd0
    for k in range(len(Q)):
        if s.step("lowcmd", np.r_[Q[k], QD[k], np.zeros(n), kp, kd, 0.0, 0.0]):
            return True
        if watch:
            watch(s)
    return False


def recover(s, settle_s=1.5, watch=None, **_):
    """The walking policy at zero command, the arms brought down to rest over 1 s, to the end."""
    w = s.world
    r = w.robot
    up0 = w.d.qpos[r.qadr][12:].copy()
    rest = r.rest[12:]
    k = 0
    while not s.done:
        f = min(1.0, k * w.CONTROL_DT / 1.0)
        if s.step("walk", np.r_[0.0, 0.0, 0.0, up0 + (rest - up0) * f, 0.0, 0.0]):
            return
        if watch:
            watch(s)
        k += 1


def solve(s, tech=None):
    tech = tech or TECHNIQUE
    if not play(s, tech):
        recover(s)
