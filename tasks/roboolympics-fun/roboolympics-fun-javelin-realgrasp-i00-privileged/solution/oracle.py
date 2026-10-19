"""javelin-realgrasp: a standing throw with the javelin held at its cord only by the friction of the right Dex1-1
gripper. javelin's reference technique (five key poses of the whole body, the trunk's turn with the arm raised at the
side, Unitree LowCmd rows along a Catmull-Rom curve through the keys; oracles/javelin) loses the javelin here: its
wind-up twists the javelin in the jaws, pries them open and drops it. The technique below was found offline from it by
CMA-ES (the same parameterisation as scripts/roboolympics/search_technique.py: the upper body's joints of each key
(torso, the right arm's seven, the left shoulder and elbow), the key times and the moment the closure command goes to
0, the legs' keys kept), scored on the referee's verdict and distance in javelin-realgrasp, then on the worst of five
position-gain scalings (x 0.94 to 1.06). The closure command stays 1 until release_s, but the javelin leaves before that: in the
last 0.07 s of the swing the hand turns about 60 degrees while the javelin, held only by friction, turns in the jaws and
slides 44 mm along them and out past the fingertips (the release is the hold's end, at 1.073 s). Then the walking policy
at zero command walks backwards until the robot is 4 m behind the arc's ends, and stands.
Measured: release at 16.8 m/s from 1.83 m, 31.9 degrees up, the javelin 5.6 degrees nose down; it lands head first
30.96 m from the arc (the line is 20 m); success after 12.1 s. Succeeds on its start, on 4 of 4 position-gain scalings
(x 0.94 to 1.06), with the release command 5 ms early or late (the javelin is gone by then), on 6 of 6 starts moved by
up to 1 cm; on 5 of 10 techniques jittered by 0.02 rad on every upper-body key with 0.5 % on the times (the others
land tail first: the javelin's attitude when it slips out decides the landing)."""
import numpy as np

TECHNIQUE = {"times": [0.7052, 0.9158, 1.0555, 1.4193, 1.9607], "release_s": 1.178, "hand": 'right', "keys": [
        [0.43, -0.3488, -0.0167, 0.7477, -0.3989, 0.0169, 0.43, -0.444, -0.0442, 0.7294, -0.285, 0.041, -0.9426, -0.3231, 0.3198, 0, 1.6495, 0, 0, 0, 0.6404, -0.6798, -0.4461, 0.5432, -0.664, 0.1913, 0.6534],
        [-0.0072, -0.4714, -0.0591, 0.9271, -0.4557, 0.0591, -0.0073, -0.4697, -0.0591, 0.9271, -0.4575, 0.0591, -0.9979, 0.2684, 0.852, 0, 0.4231, 0, 0, 0, -0.9454, -1.4538, -0.1274, 1.2796, -0.6243, 0.0274, 1.0242],
        [-0.3906, -0.2253, 0.0411, 0.4343, -0.209, -0.0409, -0.3846, -0.1284, 0.0246, 0.4116, -0.2833, -0.0252, 0.829, -0.5396, -0.3344, 0, 0.4476, 0, 0, 0, -0.2276, -2.8223, -0.2231, 1.0327, -0.9343, -0.47, 0.1813],
        [-0.3412, -0.3202, 0.064, 0.4536, -0.133, -0.0624, -0.3346, -0.2683, 0.0513, 0.4935, -0.2251, -0.0512, 2.1901, 0.2073, 0.8466, 0, -0.95, 0, 0, 0, -0.1208, -1.5166, -0.4489, 2.3957, -1.2412, -0.47, 0.0697],
        [-0.0625, -0.013, 0.0093, -0.1206, 0.1336, -0.0093, -0.0622, 0.0142, 0.0089, -0.1477, 0.1335, -0.0089, 0.5851, -0.5734, -0.2281, 0, -0.95, 0, 0, 0, -0.4841, -0.5778, 0.3384, 0.5476, -0.4606, 0.3996, 0.3907]]}


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
