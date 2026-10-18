"""shot-put (v2): a standing put (no glide, no spin) from a technique found offline by
scripts/roboolympics/search_technique.py, RoboOlympics' method (pingyue's kit/throwing/optimize.py): four key poses
of the whole body (the legs as synergies that keep both feet flat where they stand: crouch, shift, sway and the
pelvis' turn; the trunk and the arms by joint), their times and the release time, searched by CMA-ES (48 trials a
generation, 300 generations) in the task's own frozen instance, each trial scored on the referee's verdict and
distance. The technique is played as Unitree LowCmd rows along a Catmull-Rom curve through the key poses (positions
and speeds, the default gains); the grip lets go at the release time. Then the walking policy takes the legs at zero
command, walks backwards out of the rear half of the circle and stands.
Measured: the shot leaves the hand at 8.1 m/s from 1.78 m, pushed (0.997 of its speed away from the shoulder), and
lands 8.20 m from the rim (the line is 6 m); success after 6.1 s. The technique is open loop on the one frozen
start: it is not robust (in the search's last generation 2 of 48 neighbouring techniques succeeded)."""
import numpy as np

TECHNIQUE = {"times": [0.6515, 0.9073, 1.017, 1.8465], "release_s": 0.8853, "keys": [
        [0.1538, -0.4631, 0.0107, 1.2409, -0.7779, -0.0077, 0.155, -0.5187, 0.0072, 1.2585, -0.7398, -0.0044, -2.185, 0.8431, 0.7871, 0.2762, -0.95, 0, 0, 0, -1.2991, -0.6964, -0.3811, -0.95, -1.8445, -0.47, -1.27],
        [-0.43, -0.2117, -0.1169, 0.6198, -0.4067, 0.1143, -0.43, -0.0194, -0.1449, 0.4618, -0.4423, 0.145, 1.9804, -0.4335, -0.38, -1.012, -0.6467, 0, 0, 0, -1.7457, -1.6296, -0.1626, 1.0763, -1.653, -0.1545, -0.8298],
        [-0.2084, -0.2694, 0.0074, 0.3204, -0.051, -0.0067, -0.2071, -0.248, 0.0026, 0.365, -0.117, -0.0021, 1.5777, 0.2907, 0.5083, 0.6656, 1.0249, 0, 0, 0, -1.4341, -0.2398, 0.0092, 0.6263, 0.0347, -0.47, -0.5505],
        [0.0566, -0.2102, -0.2044, 0.6274, -0.4179, 0.2055, 0.0606, -0.2293, -0.205, 0.6362, -0.4072, 0.2053, 1.1831, -0.0491, -0.38, 0.0644, 0.0623, 0, 0, 0, 0.3699, 0.38, -0.4854, 1.5483, -0.7945, -0.47, -0.5328]]}


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
