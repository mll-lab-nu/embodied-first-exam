"""javelin (v2): a standing throw (no run-up) from a technique found offline by
scripts/robofunolympics/search_technique.py, RoboOlympics' method (pingyue's kit/throwing/optimize.py, whose G1
javelin is also thrown by the trunk's turn with the arm raised at the side): five key poses of the whole body (leg
synergies that keep both feet flat, the trunk and the arms by joint), their times and the release time, searched by
CMA-ES in the task's own frozen instance, each trial scored on the referee's verdict and distance. Played as Unitree
LowCmd rows along a Catmull-Rom curve through the keys; the grip lets go at the release time, the hand above the
shoulder. Then the walking policy at zero command walks backwards until the robot is 4 m behind the arc's ends, and
stands.
Measured: release at 15.0 m/s from 1.79 m, 36.6 degrees up; the javelin lands head first 21.58 m from the arc (the
line is 20 m); success after 15.3 s. Open loop on the one frozen start, not robust."""
import numpy as np

TECHNIQUE = {"times": [0.5891, 0.9503, 1.1268, 1.3265, 2.3129], "release_s": 1.1251, "hand": 'right', "keys": [
        [0.43, -0.3488, -0.0167, 0.7477, -0.3989, 0.0169, 0.43, -0.444, -0.0442, 0.7294, -0.285, 0.041, -1.5227, -0.4174, -0.1869, 0, 0.7294, 0, 0, 0, 0.9971, -1.318, -0.2547, 0.4781, -0.297, 0.1251, -0.5889],
        [-0.0072, -0.4714, -0.0591, 0.9271, -0.4557, 0.0591, -0.0073, -0.4697, -0.0591, 0.9271, -0.4575, 0.0591, -1.1616, 0.2466, 0.7169, 0, 0.26, 0, 0, 0, -0.1135, -1.119, -0.1054, 1.6292, -0.6634, 0.4152, 1.2201],
        [-0.3906, -0.2253, 0.0411, 0.4343, -0.209, -0.0409, -0.3846, -0.1284, 0.0246, 0.4116, -0.2833, -0.0252, 0.888, -0.6877, -0.38, 0, -0.1994, 0, 0, 0, -0.3452, -2.7758, 0.8214, 1.4301, -0.5483, -0.47, -0.6594],
        [-0.3412, -0.3202, 0.064, 0.4536, -0.133, -0.0624, -0.3346, -0.2683, 0.0513, 0.4935, -0.2251, -0.0512, 1.4999, -0.3256, 0.2019, 0, -0.3212, 0, 0, 0, -0.5216, -1.7016, -0.1824, 1.9767, -0.8447, 0.47, 0.0945],
        [-0.0625, -0.013, 0.0093, -0.1206, 0.1336, -0.0093, -0.0622, 0.0142, 0.0089, -0.1477, 0.1335, -0.0089, 0.694, -0.1954, 0.4615, 0, -0.7945, 0, 0, 0, -0.0646, -0.007, -0.1275, 1.1091, -0.0252, 0.47, 0.6422]]}


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
