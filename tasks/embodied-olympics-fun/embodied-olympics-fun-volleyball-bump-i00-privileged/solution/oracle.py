"""volleyball-bump (v2): a forearm pass from a technique found offline by scripts/roboolympics/search_technique.py,
RoboOlympics' method (pingyue's kit/throwing/optimize.py): first the walking policy walks the robot forwards and to the
left to where the serve comes down (its speeds and how long, searched), then stands at zero command while four key
poses of the trunk and the arms (both arms out and down as a platform, the referee test's, turned and lifted a little;
their times searched) play on the walking policy, which keeps the legs. Searched by CMA-ES in the task's own frozen
instance, each trial scored on how near a forearm comes to the ball, then on the pass's height and where it comes
down (the referee's distance from the target).
Measured: the serve comes in at 11.4 m/s, leaves the forearms at 7.3 m/s, rises to 3.08 m and lands 0.13 m from the
target's centre (radius 1 m); success after 5.8 s. Open loop on the one frozen start (in the last generation of the
search 7 of 48 neighbouring techniques also succeeded)."""
import numpy as np

TECHNIQUE = {"times": [0.5722, 1.5166, 1.8352, 2.7922], "release_s": 0.05, "hand": None, "legs": 'walk', "prelude": [[0.4425, 0.2643, 0.0, 2.33], [0.0, 0.0, 0.0, 0.37]], "keys": [
        [0, -0.16, 0, 0.36, -0.2, -0, 0, -0.16, 0, 0.36, -0.2, -0, -0.0274, -0.586, -0.0247, -0.0832, 1.1315, 0, 0, 0, -0.5607, 0.0895, -0.1678, 1.1943, 0, 0, 0],
        [0, -0.16, 0, 0.36, -0.2, -0, 0, -0.16, 0, 0.36, -0.2, -0, -0.2197, -0.5906, -0.1702, -0.0434, 1.0435, 0, 0, 0, -0.6008, 0.0779, -0.0523, 1.0625, 0, 0, 0],
        [0, -0.16, 0, 0.36, -0.2, -0, 0, -0.16, 0, 0.36, -0.2, -0, -0.3047, -0.8945, -0.0267, -0.2047, 1.1882, 0, 0, 0, -0.7665, 0.0022, 0.0058, 1.3261, 0, 0, 0],
        [0, -0.16, 0, 0.36, -0.2, -0, 0, -0.16, 0, 0.36, -0.2, -0, 0.0093, 0.1336, 0.2254, -0.1248, 0.0017, 0, 0, 0, -0.102, 0.019, -0.0414, 0.0397, 0, 0, 0]]}


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
