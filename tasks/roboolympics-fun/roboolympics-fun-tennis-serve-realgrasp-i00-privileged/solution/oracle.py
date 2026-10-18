"""tennis-serve-realgrasp: an underarm serve from a technique found offline (a key-pose search in the manner of
scripts/roboolympics/search_technique.py: CMA-ES over six key poses of the whole body (leg synergies that keep both
feet flat, the trunk, the right arm's seven joints, the left arm's shoulder and elbow), their times and the moment the
left gripper opens; scored on where the ball's drag flight from just after the hit crosses the net and comes down, each
candidate played under its own gain and release-time variations). Played as Unitree LowCmd rows along a Catmull-Rom
curve through the keys with the legs' gravity support as feed-forward torque, the right gripper closed on the racket
throughout; then the walking policy at zero command.
Measured: the left gripper opens at 1.24 s while the robot stands at rest, the ball falls about 0.8 m and meets the
strings at 4.2 m/s, 0.58 m above the ground; it leaves at 13.3 m/s, clears the net by 2.3 m and lands in the box at
(16.3, 3.1), 2.5 m inside its back line; success at 3.5 s. Succeeds on its start, on 10 of 10 variations of its gains
(x 0.94 to 1.06) with the release 5 ms early or late, on 4 of 4 gain scalings 0.9 to 1.1, on 10 of 10 starts moved
by up to 1 cm, and on 7 of 10 techniques jittered by 0.02 rad on every upper-body key with 0.5 % on the times."""
import numpy as np

TECHNIQUE = {"times": [0.6663, 1.2324, 1.385, 1.6386, 1.8975, 2.7099], "release_s": 1.2415, "keys": [
        [-0.0065, -0.1342, -0.0049, 0.3411, -0.2069, 0.0049, -0.0065, -0.1324, -0.0049, 0.3405, -0.2081, 0.0049, -0.2679, -0.5287, -0.38, -0.446, -0.0514, 0, 0, 0, 0.619, -0.2119, 0.1311, 1.315, 1.5385, -0.0849, -0.2598],
        [0.043, -0.1293, 0.0066, 0.3644, -0.2351, -0.0066, 0.0429, -0.1415, 0.0064, 0.3694, -0.2279, -0.0064, 0.0508, -0.5073, -0.3781, -0.5902, -0.0026, 0, 0, 0, 0.893, 0.108, 0.0049, 1.635, 1.9406, 0.252, -0.0749],
        [-0.0279, -0.0797, 0.0024, 0.2603, -0.1806, -0.0024, -0.0279, -0.071, 0.0023, 0.2552, -0.1842, -0.0023, -0.0784, -0.5544, -0.1275, -0.2706, 0.0256, 0, 0, 0, 0.9799, -0.2186, -0.1306, 1.3079, 1.5648, 0.0024, 0.2557],
        [-0.1202, -0.3098, -0.0143, 0.609, -0.2993, 0.0142, -0.1202, -0.2813, -0.0159, 0.6074, -0.3261, 0.0159, 0.1477, -0.1969, 0.5884, -0.2346, -0.3061, 0, 0, 0, 0.0535, -0.1373, -0.2172, 1.0558, 1.4935, 0.0189, 0.0135],
        [0.08, -0.1348, 0.0178, 0.3164, -0.1816, -0.0178, 0.0798, -0.1542, 0.0171, 0.3198, -0.1655, -0.0171, 0.1734, -0.05, 0.6057, 0.1094, 0.0592, 0, 0, 0, -1.1921, 0.1364, -0.1537, 0.6163, 1.6461, -0.1374, 0.2288],
        [-0.0382, -0.1673, 0.0177, 0.3525, -0.1852, -0.0176, -0.038, -0.1582, 0.0175, 0.3512, -0.193, -0.0175, -0.2311, 0.1449, -0, -0.0272, 0.1338, 0, 0, 0, -0.5064, -0.3774, -0.2084, 0.5731, 0.5053, 0.0396, 0.0738]]}


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
    """The technique from t = 0: one LowCmd row per control step to its last key, with the legs' gravity support as
    feed-forward torque (the weight on both feet, from the privileged state: what `stand` adds; without it the H1-2
    with a gripper and a racket on its arms tips forward within a second); the left gripper closed on the ball until
    release_s, then open; the right gripper closed on the racket. Returns True if the episode ended."""
    w = s.world
    r = w.robot
    n = r.L.NJ
    q0 = w.d.qpos[r.qadr].copy()
    Q, QD = curve(q0, np.asarray(tech["keys"], float), np.asarray(tech["times"], float), w.CONTROL_DT)
    kp, kd = r.kp0 * tech.get("kp_scale", 1.0), r.kd0
    for k in range(len(Q)):
        grip = np.array([1.0 if (k + 1) * w.CONTROL_DT < tech["release_s"] else 0.0, 1.0])
        tau = np.zeros(n)
        tau[:12] = np.clip(r.arb._support_ff(w.d), -r.tau_max[:12], r.tau_max[:12])
        if s.step("lowcmd", np.r_[Q[k], QD[k], tau, kp, kd, grip]):
            return True
        if watch:
            watch(s)
    return False


def recover(s, settle_s=1.0, watch=None):
    """The walking policy at zero command, the arms brought back towards the rest pose (the racket kept closed in the
    right gripper), to the end."""
    w = s.world
    r = w.robot
    up0 = w.d.qpos[r.qadr][12:].copy()
    rest = r.rest[12:]
    k = 0
    while not s.done:
        f = min(1.0, k * w.CONTROL_DT / settle_s)
        if s.step("walk", np.r_[0.0, 0.0, 0.0, up0 + (rest - up0) * f, 0.0, 1.0]):
            return
        if watch:
            watch(s)
        k += 1


def solve(s, tech=None):
    tech = tech or TECHNIQUE
    if not play(s, tech):
        recover(s)
