"""Camera-only reference player for robot badminton (no privileged state, no simulator code).

It uses only what any player gets: the `observe` camera images (2 cameras x 4 frames) with their frame times, the
state in the replies (game time, time since the shuttle was played, its own robot), and the camera poses / intrinsics
from `spec`. The physics it uses is the one in the instructions (point mass, gravity, drag K |v| v, the contact law).
Per shuttle coming to it:
  1. detect the orange cork in each of the 8 tiles (colour threshold + centroid) and triangulate each frame's two
     detections into a 3-D point; keep the frames of the current flight (after the opponent's hit or the serve);
  2. fit the flight (position and velocity at the first kept frame) with the drag model (Gauss-Newton), predict it;
  3. choose the contact: the first predicted point, early enough for the robot's base, 0.45-2.45 m high on its half,
     preferring overhead contacts; choose a target in the opponent's court and the launch velocity that reaches it
     over the net (the same drag model), and turn it into the racket state at contact with the contact law;
  4. act (T from the step the act takes effect); observe again while the shuttle flies and correct the command when
     the refined prediction moves the contact by more than a few cm.
numpy + Pillow only.
"""
from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image

G, K = 9.81, 9.81 / 6.8 ** 2        # gravity; drag K |v| v (terminal speed 6.8 m/s): from the instructions
DT = 0.002                           # integration step of the player's own flight model
NET_TOP, COURT_X, COURT_Y = 1.524, 2.59, 6.70
TILE_W, TILE_H = 480, 360


# ------------------------------------------------------------------------------------------------ cameras
class Cam:
    def __init__(self, c: dict):
        self.pos = np.array(c["position"], float)
        self.fw = np.array(c["forward"], float); self.fw /= np.linalg.norm(self.fw)
        self.up = np.array(c["up"], float); self.up /= np.linalg.norm(self.up)
        self.rt = np.cross(self.fw, self.up)
        self.f = float(c.get("focal_px", 434.6))
        pp = c.get("principal_point_px", [240, 180])
        self.cx, self.cy = float(pp[0]), float(pp[1])

    def ray(self, u, v):
        d = self.fw + ((u - self.cx) / self.f) * self.rt - ((v - self.cy) / self.f) * self.up
        return self.pos, d / np.linalg.norm(d)


def triangulate(rays):
    A = np.zeros((3, 3)); b = np.zeros(3)
    for o, d in rays:
        P = np.eye(3) - np.outer(d, d)
        A += P; b += P @ o
    X = np.linalg.solve(A, b)
    res = [np.linalg.norm((np.eye(3) - np.outer(d, d)) @ (X - o)) for o, d in rays]
    return X, float(np.sqrt(np.mean(np.square(res))))


def decode(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))


def detect_tile(t: np.ndarray):
    """(u, v) of the orange cork's centroid in a tile, or None."""
    r = t[..., 0].astype(np.int16); g = t[..., 1].astype(np.int16); b = t[..., 2].astype(np.int16)
    m = (r > 110) & (g * 100 > 25 * r) & (g * 100 < 72 * r) & (b * 100 < 35 * r)
    m[:16, :160] = False                     # the time stamp
    ys, xs = np.nonzero(m)
    if len(xs) == 0 or len(xs) > 3000:
        return None
    mx, my = np.median(xs), np.median(ys)
    sel = (np.abs(xs - mx) <= 25) & (np.abs(ys - my) <= 25)
    if sel.sum() == 0:
        return None
    return float(xs[sel].mean()) + 0.5, float(ys[sel].mean()) + 0.5


def detect_views(img, cams, times, max_res=0.12):
    out = []
    for j, tt in enumerate(times):
        rays = []
        for i, c in enumerate(cams):
            uv = detect_tile(img[i * TILE_H:(i + 1) * TILE_H, j * TILE_W:(j + 1) * TILE_W])
            if uv is not None:
                rays.append(c.ray(*uv))
        if len(rays) == 2:
            X, res = triangulate(rays)
            if res < max_res and -0.2 < X[2] < 12.0 and abs(X[0]) < 4.0 and abs(X[1]) < 8.0:
                out.append((float(tt), X))
    return out


# ------------------------------------------------------------------------------------------------ flight model
def rollout(p, v, n, dt=DT):
    """(m, 3) states, integrated n steps (semi-implicit Euler); vectorised over m trajectories."""
    p = np.array(p, float, ndmin=2); v = np.array(v, float, ndmin=2)
    P = np.empty((n + 1,) + p.shape); V = np.empty_like(P); P[0] = p; V[0] = v
    for i in range(1, n + 1):
        s = np.sqrt((v * v).sum(-1, keepdims=True))
        v = v - (K * s * v + np.array([0.0, 0.0, G])) * dt
        p = p + v * dt
        P[i] = p; V[i] = v
    return P, V


def positions_at(p, v, t0, times):
    times = np.asarray(times, float)
    n = int(math.ceil((times.max() - t0) / DT)) + 1
    P, _ = rollout(p, v, n)
    idx = (times - t0) / DT
    i0 = np.clip(np.floor(idx).astype(int), 0, n - 1); f = (idx - i0)[:, None, None]
    return P[i0] * (1 - f) + P[i0 + 1] * f                      # (len(times), m, 3)


def fit(obs):
    """Least-squares (p, v) at the first observation time from [(t, X)] (Gauss-Newton, numerical Jacobian)."""
    obs = sorted(obs, key=lambda o: o[0])
    t0 = obs[0][0]
    ts = np.array([o[0] for o in obs]); Xs = np.array([o[1] for o in obs])
    p = Xs[0].copy()
    v = (Xs[-1] - Xs[0]) / max(ts[-1] - t0, 0.02) if len(obs) > 1 else np.zeros(3)
    x = np.r_[p, v]
    for _ in range(8):
        eps = np.r_[np.full(3, 1e-3), np.full(3, 1e-3)]
        X = np.vstack([x] + [x + np.eye(6)[i] * eps[i] for i in range(6)])
        Pt = positions_at(X[:, :3], X[:, 3:], t0, ts)          # (T, 7, 3)
        r = (Xs - Pt[:, 0]).ravel()
        J = np.stack([((Pt[:, i + 1] - Pt[:, 0]) / eps[i]).ravel() for i in range(6)], 1)
        dx = np.linalg.lstsq(J.T @ J + 1e-6 * np.eye(6), J.T @ r, rcond=None)[0]
        x = x + dx
        if np.abs(dx).max() < 1e-4:
            break
    Pt = positions_at(x[None, :3], x[None, 3:], t0, ts)[:, 0]
    return t0, x[:3], x[3:], float(np.sqrt(np.mean(np.sum((Xs - Pt) ** 2, 1))))


def predict(p, v, t0, t_max=4.0):
    """Times, positions, velocities until the floor or the net plane below the top."""
    P, V = rollout(p, v, int(t_max / DT))
    P, V = P[:, 0], V[:, 0]
    end = len(P)
    below = np.nonzero(P[:, 2] <= 0.0)[0]
    if len(below):
        end = below[0] + 1
    cross = np.nonzero((np.sign(P[1:end, 1]) != np.sign(P[:end - 1, 1])) & (P[1:end, 2] < NET_TOP))[0]
    if len(cross):
        end = cross[0] + 1
    return t0 + DT * np.arange(end), P[:end], V[:end]


# ------------------------------------------------------------------------------------------------ shots
def solve_launch(p, target, thetas, vmax=45.0, dt=0.003):
    """Launch velocities from p landing near `target` (xy, opponent's court), clearing the net by 20 cm: one per launch
    angle that works, in the order given. Planar flights along the heading, vectorised over angle x speed."""
    p = np.asarray(p, float); d = np.asarray(target, float) - p[:2]; H = float(np.linalg.norm(d)); hd = d / H
    th = np.radians(np.asarray(thetas, float))[:, None]; sp = np.linspace(2.0, vmax, 120)[None, :]
    vh = (np.cos(th) * sp).ravel(); vz = (np.sin(th) * sp).ravel()
    h = np.zeros_like(vh); z = np.full_like(vh, p[2])
    s_net = -p[1] / hd[1] if hd[1] > 1e-9 else np.inf
    rng_ = np.full(vh.size, np.nan); znet = np.full(vh.size, np.nan); alive = np.ones(vh.size, bool)
    for _ in range(int(4.0 / dt)):
        s = np.sqrt(vh * vh + vz * vz)
        vh = vh - K * s * vh * dt; vz = vz - (G + K * s * vz) * dt
        h1 = h + vh * dt; z1 = z + vz * dt
        cr = alive & (h < s_net) & (h1 >= s_net)
        znet[cr] = z[cr] + (s_net - h[cr]) / (h1[cr] - h[cr]) * (z1[cr] - z[cr])
        ld = alive & (z1 <= 0)
        rng_[ld] = h[ld] + z[ld] / (z[ld] - z1[ld]) * (h1[ld] - h[ld]); alive &= ~ld
        h, z = h1, z1
        if not alive.any():
            break
    R = rng_.reshape(th.shape[0], -1); ZN = znet.reshape(th.shape[0], -1); S = sp[0]
    out = []
    for a, tdeg in enumerate(thetas):
        ok = np.nonzero(np.isfinite(R[a]) & (R[a] >= H))[0]
        if not len(ok) or ok[0] == 0:
            continue
        k = ok[0]; f = (H - R[a][k - 1]) / (R[a][k] - R[a][k - 1])
        v = S[k - 1] + f * (S[k] - S[k - 1]); zn = ZN[a][k - 1] + f * (ZN[a][k] - ZN[a][k - 1])
        if not np.isfinite(zn) or zn < NET_TOP + 0.20:
            continue
        c, s_ = math.cos(math.radians(tdeg)), math.sin(math.radians(tdeg))
        out.append((tdeg, float(v), np.array([hd[0] * c * v, hd[1] * c * v, s_ * v])))
    return out


def racket_state(v_in, v_out):
    """Contact law: the shuttle leaves along n at 20 (v_head . n) + 0.15 max(0, -v_in . n)."""
    sp = float(np.linalg.norm(v_out)); n = v_out / sp
    u = max(0.05, (sp - 0.15 * max(0.0, -float(v_in @ n))) / 20.0)
    return n, u * n


def base_time(dist, vmax, amax):
    a, vm = 0.85 * amax, 0.98 * vmax
    return 2 * math.sqrt(dist / a) if dist < vm * vm / a else dist / vm + vm / a


def stance(p):
    dz = float(p[2]) - 1.333
    r = max(0.30, 0.95 - 0.35 * abs(dz))
    return np.asarray(p[:2], float) - 0.62 * r


def choose(ts, P, V, t_now, base_xy, vmax, amax, rng, margin=0.12):
    """Contact (time, position, incoming velocity) and racket state, or None."""
    cands = []
    for i in range(0, len(ts), 5):
        p = P[i]; dt = ts[i] - t_now
        if dt < 0.22 or not (0.45 <= p[2] <= 2.45 and p[1] < -0.45):
            continue
        if base_time(float(np.linalg.norm(stance(p) - base_xy)), vmax, amax) <= dt - margin:
            cands.append(i)
    if not cands:
        ok = [i for i in range(0, len(ts), 5) if ts[i] - t_now >= 0.22 and P[i][2] >= 0.45 and P[i][1] < -0.45]
        if not ok:
            return None
        cands = [ok[-1]]
    hi = [i for i in cands if 1.7 <= P[i][2] <= 2.45]
    i = hi[0] if hi else max(cands, key=lambda j: P[j][2])
    p, v_in = P[i], V[i]
    deep = rng.random() < 0.65
    side = 1.0 if rng.random() < 0.5 else -1.0
    target = np.array([side * 1.8, 5.6]) if deep else np.array([side * 1.5, 2.4])
    thetas = DEEP_THETAS if deep else SHORT_THETAS
    opts = strokes(p, v_in, target, thetas) or strokes(p, v_in, np.array([0.0, 4.5]), (45, 35, 55, 25, 60))
    if not opts:
        return None
    return ts[i], p, v_in, opts, target


def strokes(p, v_in, target, thetas, vmax_head=2.2):
    """Racket states (normal, head velocity) for the shots from p to target, the slowest head first."""
    out = []
    for th, sp, v_out in solve_launch(p, target, thetas):
        n, vel = racket_state(v_in, v_out)
        if np.linalg.norm(vel) <= vmax_head:
            out.append((float(np.linalg.norm(vel)), n, vel))
    return [(n, vel) for _, n, vel in sorted(out, key=lambda o: o[0])]


DEEP_THETAS, SHORT_THETAS = (40, 30, 50, 20, 55, 10, 60), (10, 0, 20, -5, 30)
