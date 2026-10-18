"""volleyball-serve (v2): an underarm serve from a technique found offline by
scripts/roboolympics/search_technique.py, RoboOlympics' method (pingyue's kit/throwing/optimize.py): five key
poses (leg synergies that keep both feet flat, the trunk, the right arm's shoulder and elbow, the left arm), their
times and the time the left fist lets go of the ball (the toss), searched by CMA-ES in the task's own frozen instance,
each trial scored on how near the right hand comes to the tossed ball and then on where the ball's flight from just
after the hit crosses the net and comes down. The trunk's turn and the straight right arm's swing hit the ball in
front of the hip. Played as Unitree LowCmd rows along a Catmull-Rom curve through the keys; then the walking policy at
zero command.
Measured: the ball arrives at 2.2 m/s and leaves the hit at 11.4 m/s; over the net between the antennas, it lands in
the opponent's court 1.8 m beyond the net, 0.18 m from the middle; success after 3.3 s. Open loop on the one frozen
start; in the search's last generation 32 of 48 neighbouring techniques also succeeded."""
import numpy as np

TECHNIQUE = {"times": [0.5507, 1.0746, 1.3589, 1.6667, 2.4352], "release_s": 1.0852, "hand": 'left', "keys": [
        [0.1164, -0.2629, 0.0165, 0.391, -0.1281, -0.0169, 0.1166, -0.2776, 0.015, 0.3707, -0.0931, -0.0153, -1.2444, -0.0915, 0.0743, -0.7813, 0.2674, 0, 0, 0, 0.4361, -0.7359, 0.1392, 1.8081, 0, 0, 0],
        [0.43, -0.3287, 0.0705, 0.8523, -0.5231, -0.0688, 0.43, -0.4606, 0.0403, 0.8786, -0.4179, -0.0381, -1.0336, -0.73, 0.4388, -0.4748, -0.4292, 0, 0, 0, 1.2998, -0.6398, -0.0333, 2.2385, 0, 0, 0],
        [-0.0228, -0.0717, -0.0285, 0.3097, -0.238, 0.0285, -0.023, -0.0638, -0.0286, 0.304, -0.2403, 0.0286, 0.4644, -0.6125, -0.2117, -0.0785, -0.1683, 0, 0, 0, -1.2432, -0.2029, -0.0604, 1.0545, 0, 0, 0],
        [0.0023, -0.2022, 0.0117, 0.4729, -0.2707, -0.0117, 0.0023, -0.2028, 0.0117, 0.4731, -0.2703, -0.0117, -0.1439, 0.0184, 0.2401, -0.2683, -0.2666, 0, 0, 0, -1.1401, 0.38, 0.4423, 1.2316, 0, 0, 0],
        [0.1842, -0.0726, 0.0225, 0.264, -0.1914, -0.0225, 0.1835, -0.1252, 0.0189, 0.288, -0.1628, -0.0188, 0.7405, -0.2317, 0.1594, 0.2802, 0.211, 0, 0, 0, 0.0565, -0.7306, -0.2641, 1.1694, 0, 0, 0]]}


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
