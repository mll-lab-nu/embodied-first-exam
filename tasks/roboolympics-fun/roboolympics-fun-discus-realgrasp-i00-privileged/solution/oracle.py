"""discus-realgrasp: a standing throw (no spin across the circle) from a technique found offline by CMA-ES in this
family's own physics (scripts/roboolympics/search_technique.py's method and its Discus search space: five key poses of
the whole body, the legs as synergies that keep both feet flat, the trunk and the arms by joint, their times and the
release time; 24 trials a generation, 120 generations, each scored on the referee's verdict and distance). The
discus is held by friction only, clamped by its rim in the right Dex1-1 gripper (the closure command 1 until
release_s, then 0). Played as Unitree LowCmd rows along a Catmull-Rom curve through the keys; then the walking policy
at zero command, backwards out of the rear half of the circle, and stands.
Measured: the trunk's turn pulls the discus out of the still-closed jaws at 1.34 s (0.14 s before the commanded
opening: the pull exceeds the clamp's friction), at 12.5 m/s, tilted 39 degrees, spinning at 18.5 rad/s; it lands
15.95 m from the rim (the line is 15 m); success after 8.1 s. Open loop on the one frozen start and on a knife edge
(a single trial of the search's last generation succeeded)."""
import numpy as np

TECHNIQUE = {"times": [0.6313, 0.9741, 1.1824, 1.3423, 2.4483], "release_s": 1.4863, "hand": 'right', "keys": [
        [0.2306, -0.1859, -0.0681, 0.3607, -0.1748, 0.0685, 0.2345, -0.2255, -0.0739, 0.3384, -0.1127, 0.0736, -0.4135, -0.9507, -0.38, 0, 1.0106, 0, 0, 0, 0.1812, -1.0517, 0.5057, 1.3359, -0.5581, -0.0172, 0.932],
        [0.2509, -0.1181, -0.0592, 0.3226, -0.2046, 0.0597, 0.2556, -0.1767, -0.0662, 0.3278, -0.1511, 0.0661, -1.1629, 0.2433, 0.0301, 0, 0.4143, 0, 0, 0, 0.067, -1.4585, 0.7816, 1.3181, 0.5985, -0.3182, -0.3522],
        [-0.0553, -0.2706, -0.0378, 0.6468, -0.3761, 0.0376, -0.0558, -0.2551, -0.0382, 0.642, -0.3869, 0.0381, -0.4145, 0.4027, 0.3339, 0, -0.1286, 0, 0, 0, -0.5037, -1.9313, 0.3426, 2.0578, 0.395, 0.071, 0.5999],
        [-0.3407, -0.0863, 0.0038, 0.1372, -0.0509, -0.0038, -0.3405, 0.0122, -0.0085, 0.0867, -0.0989, 0.0085, 1.6136, -0.31, 0.0185, 0, -0.3031, 0, 0, 0, 0.0439, -2.2727, 0.1183, 1.1458, 0.1565, 0.0423, 0.3611],
        [-0.43, -0.4065, 0.0223, 0.7719, -0.3654, -0.022, -0.43, -0.277, -0.0093, 0.7499, -0.4729, 0.0074, 0.6142, 0.1035, 0.5843, 0, -0.3828, 0, 0, 0, 0.1181, -0.5574, 0.0692, 0.9972, 0.2236, 0.1066, 0.1847]]}


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
