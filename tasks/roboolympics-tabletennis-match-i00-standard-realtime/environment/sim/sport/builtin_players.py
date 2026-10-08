"""Table tennis' built-in players (core/client.py plays them over HTTP, core/local.py in-process; the same action
interface as a model's program). Camera images, the replies and /spec only: no simulator import, no ball state.

  Reference  the legacy reference player of Season 1 (scripts/olympiad/tabletennis/*/solution: wc_player.py + arm.py
             + the oracle loops), one class for every format and action level:
               perception  detect the orange ball in the 8 tiles (2 cameras x 4 frames), triangulate each frame from
                           the two cameras (/spec intrinsics), fit the flight (gravity + quadratic drag, an extra
                           constant acceleration for the unknown spin) and predict the contact after our bounce;
               shot        the paddle state at contact from the contact law, aimed away from the opponent;
               high level  `act` {t, pos, normal, vel} (the service plans the stroke);
               low level   its own arm model from /spec (FK of the documented chain, damped least-squares IK, a
                           joint-speed-limited Hermite swing) streamed as `traj` joint targets, a slew back to the
                           ready pose between balls.
             Over HTTP it estimates when its act takes effect from the observation's step, the render time and its
             own latency; in-process (no `timing` in /spec) the act takes effect at the observed step.
  Idle       never acts (the generic tests' check policy: every point ends quickly).
numpy + Pillow only: this file is also the task's oracle (solution/)."""
from __future__ import annotations

import base64
import io
import math
import time

import numpy as np
from PIL import Image


# ================================================================================================ perception and shot (wc_player.py)
G = np.array([0.0, 0.0, -9.81])
KD = 0.13                 # drag: deceleration KD |v| v (instructions: about 0.13)
E_BOUNCE_Z, E_BOUNCE_XY = 0.96, 0.87
BALL_R = 0.02
OFFSET = 0.0275           # blade centre = ball centre - OFFSET * normal (ball radius + half the blade thickness)
E_PADDLE = 0.96
TILE_W, TILE_H = 480, 360
TABLE_X, TABLE_Y = 0.7625, 1.37
NET_Z = 0.1525


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

    def project(self, X):
        d = np.asarray(X, float) - self.pos
        z = d @ self.fw
        return self.cx + self.f * (d @ self.rt) / z, self.cy - self.f * (d @ self.up) / z

    def ray(self, u, v):
        d = self.fw + ((u - self.cx) / self.f) * self.rt - ((v - self.cy) / self.f) * self.up
        return self.pos, d / np.linalg.norm(d)


def triangulate(rays):
    """Least-squares point closest to all rays; (point, rms distance to the rays)."""
    A = np.zeros((3, 3)); b = np.zeros(3)
    for o, d in rays:
        P = np.eye(3) - np.outer(d, d)
        A += P; b += P @ o
    X = np.linalg.solve(A, b)
    res = [np.linalg.norm((np.eye(3) - np.outer(d, d)) @ (X - o)) for o, d in rays]
    return X, float(np.sqrt(np.mean(np.square(res))))


# ------------------------------------------------------------------------------------------------ detection
def decode(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))


def ball_mask(t: np.ndarray) -> np.ndarray:
    r = t[..., 0].astype(np.int16); g = t[..., 1].astype(np.int16); b = t[..., 2].astype(np.int16)
    return (r > 70) & (b * 8 < r) & (g * 100 > 58 * r) & (g * 100 < 82 * r)


def detect_tile(t: np.ndarray):
    """(u, v) of the ball's centroid in a tile, or None."""
    m = ball_mask(t)
    m[:16, :70] = False                      # the time stamp
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        return None
    if len(xs) > 400:                        # far too many: not a ball
        return None
    mx, my = np.median(xs), np.median(ys)
    sel = (np.abs(xs - mx) <= 8) & (np.abs(ys - my) <= 8)
    if sel.sum() == 0:
        return None
    w = t[ys[sel], xs[sel], 0].astype(float)
    # +0.5: pixel i covers [i, i + 1) in the pinhole model
    return float(np.average(xs[sel], weights=w)) + 0.5, float(np.average(ys[sel], weights=w)) + 0.5


def detect_views(img: np.ndarray, cams: list[Cam], times: list[float], max_res: float = 0.03):
    """Per frame time: the triangulated ball centre (or nothing). img: 2 rows (cameras) x 4 columns (frames)."""
    out = []
    for j, tt in enumerate(times):
        rays = []
        for i, c in enumerate(cams):
            tile = img[i * TILE_H:(i + 1) * TILE_H, j * TILE_W:(j + 1) * TILE_W]
            uv = detect_tile(tile)
            if uv is not None:
                rays.append(c.ray(*uv))
        if len(rays) == 2:
            X, res = triangulate(rays)
            if res < max_res and -0.2 < X[2] < 2.0 and abs(X[1]) < 3.0:
                out.append((float(tt), X))
    return out


# ------------------------------------------------------------------------------------------------ flight model
def rollout(p, v, dt, n, bounce=True, a_extra=None):
    """Explicit integration (semi-implicit Euler) of gravity + drag (+ a constant extra acceleration); the table bounce
    (restitution) when bounce=True. Returns positions (n+1, 3), velocities (n+1, 3), list of bounce indices."""
    p = np.array(p, float); v = np.array(v, float)
    P = np.empty((n + 1, 3)); V = np.empty((n + 1, 3)); P[0] = p; V[0] = v
    ae = np.zeros(3) if a_extra is None else np.asarray(a_extra, float)
    bounces = []
    for i in range(1, n + 1):
        sp = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
        a = G - KD * sp * v + ae
        v = v + a * dt
        p = p + v * dt
        if bounce and p[2] < BALL_R and v[2] < 0 and abs(p[0]) <= TABLE_X + 0.01 and abs(p[1]) <= TABLE_Y + 0.01:
            v = np.array([v[0] * E_BOUNCE_XY, v[1] * E_BOUNCE_XY, -v[2] * E_BOUNCE_Z])
            p[2] = 2 * BALL_R - p[2]
            bounces.append(i)
        P[i] = p; V[i] = v
    return P, V, bounces


def _states_at(p0, v0, t0, times, dt=0.002, a_extra=None):
    """Positions at `times` (all >= t0, no bounce in between) from the state (p0, v0) at t0."""
    times = np.asarray(times, float)
    n = int(math.ceil((times.max() - t0) / dt)) + 1
    P, _, _ = rollout(p0, v0, dt, n, bounce=False, a_extra=a_extra)
    idx = (times - t0) / dt
    i0 = np.clip(np.floor(idx).astype(int), 0, n - 1)
    f = (idx - i0)[:, None]
    return P[i0] * (1 - f) + P[i0 + 1] * f


def fit_flight(obs, n_iter=6, fit_accel=False, a_fixed=None):
    """obs: [(t, X)] of one flight segment (no bounce in between). Returns (t0, p0, v0, a_extra, rms) with t0 = the
    first observation's time, or None. fit_accel: also fit a constant extra acceleration (the Magnus force of the
    unknown spin) when there are >= 6 points; a_fixed: use this extra acceleration instead."""
    af = None if a_fixed is None else np.asarray(a_fixed, float)
    if len(obs) < 2:
        return None
    obs = sorted(obs, key=lambda o: o[0])
    T = np.array([o[0] for o in obs]); X = np.array([o[1] for o in obs])
    t0 = T[0]
    if len(obs) == 2:
        v = (X[1] - X[0]) / (T[1] - T[0]) - 0.5 * G * (T[1] - T[0])
        return t0, X[0], v, (np.zeros(3) if af is None else af), 0.0
    # initial guess: quadratic fit per axis
    A = np.vstack([np.ones_like(T), T - t0, (T - t0) ** 2]).T
    coef = np.linalg.lstsq(A, X, rcond=None)[0]
    th = np.r_[coef[0], coef[1], np.zeros(3)]
    npar = 9 if (fit_accel and af is None and len(obs) >= 6) else 6
    th = th[:npar]
    for _ in range(n_iter):
        def pred(th_):
            ae = th_[6:9] if npar == 9 else af
            return _states_at(th_[0:3], th_[3:6], t0, T, a_extra=ae).ravel()
        r = X.ravel() - pred(th)
        J = np.zeros((len(r), npar))
        for c in range(npar):
            d = np.zeros(npar); d[c] = 1e-4
            J[:, c] = (pred(th + d) - pred(th)) / 1e-4
        reg = 1e-6 * np.eye(npar)
        if npar == 9:
            reg[6:, 6:] = np.eye(3) * 1e-2       # keep the extra acceleration small unless the data insist
        step = np.linalg.solve(J.T @ J + reg, J.T @ r)
        th = th + step
        if np.linalg.norm(step) < 1e-6:
            break
    rms = float(np.sqrt(np.mean((X.ravel() - pred(th)) ** 2)))
    ae = th[6:9] if npar == 9 else (np.zeros(3) if af is None else af)
    return t0, th[0:3], th[3:6], ae, rms


def predict_contact(t0, p0, v0, a_extra=None, need_bounce=True, t_max=1.6, dt=0.001):
    """From the state at t0: our bounce (if need_bounce), then the top of the arc after it (or the point where the ball
    crosses y = -1.38 going down-table, if earlier). Returns (t_contact, p, v) or None."""
    n = int(t_max / dt)
    P, V, bounces = rollout(p0, v0, dt, n, bounce=True, a_extra=a_extra)
    if need_bounce:
        own = [i for i in bounces if P[i, 1] < 0]
        if not own:
            return None
        i_b = own[0]
    else:
        i_b = 0
    for i in range(i_b + 1, n):
        if V[i, 2] <= 0 or P[i, 1] < -1.38:
            return t0 + i * dt, P[i].copy(), V[i].copy()
        if P[i, 2] < BALL_R:
            return None
    return None


# ------------------------------------------------------------------------------------------------ stroke
def landing(p, v, dt=0.004, n=450):
    """First table contact (x, y) of a free flight after our hit and whether it cleared the net."""
    P, _, b = rollout(p, v, dt, n, bounce=True)
    i_net = None
    for i in range(1, len(P)):
        if P[i - 1, 1] < 0 <= P[i, 1]:
            i_net = i
        if b and i == b[0]:
            clear = i_net is not None and P[i_net, 2] > NET_Z + BALL_R + 0.03
            return P[i, :2], clear
        if P[i, 2] < -0.5:
            break
    return None, False


def solve_out(p, aim, vy=5.0):
    """Outgoing ball velocity (vx, vy, vz) from p that lands at `aim` (Newton on vx, vz)."""
    v = np.array([(aim[0] - p[0]) * vy / max(0.5, aim[1] - p[1]), vy, 1.2])
    for _ in range(12):
        L, ok = landing(p, v)
        if L is None:
            v[2] += 0.3
            continue
        err = L - np.asarray(aim)
        if np.linalg.norm(err) < 0.01:
            return v, ok
        J = np.zeros((2, 2))
        for c, ix in enumerate((0, 2)):
            dv = np.zeros(3); dv[ix] = 0.02
            L2, _ = landing(p, v + dv)
            if L2 is None:
                return v, False
            J[:, c] = (L2 - L) / 0.02
        try:
            dx = np.linalg.solve(J, err)
        except np.linalg.LinAlgError:
            return v, False
        dx = np.clip(dx, -1.0, 1.0)
        v[0] -= dx[0]; v[2] -= dx[1]
    L, ok = landing(p, v)
    return v, bool(ok and L is not None and np.linalg.norm(L - np.asarray(aim)) < 0.05)


def paddle_for(p_hit, v_in, v_out, tangential=True):
    """Contact law (instructions): the normal component of the relative velocity reverses with restitution E_PADDLE,
    the tangential one is kept. With n along (v_out - v_in) the tangential part of the ball is unchanged, so the paddle
    moves with the ball tangentially and v_p.n = (v_out.n + E v_in.n) / (1 + E)."""
    dv = v_out - v_in
    n = dv / np.linalg.norm(dv)
    vpn = (v_out @ n + E_PADDLE * (v_in @ n)) / (1 + E_PADDLE)
    v_t = v_in - (v_in @ n) * n
    v_p = vpn * n + (v_t if tangential else 0.0)
    p_c = p_hit - OFFSET * n
    return p_c, n, v_p


# ------------------------------------------------------------------------------------------------ the player
DT = 0.01


class Player:
    """Keeps the frames of the current incoming ball, predicts the contact, decides when to (re-)act.

    update(obs, img, k_req): one observation (its `view_times`, `heard`, `t_since_played`, `step`, `point`, `ball`).
    decide(k_now): an act dict {"t", "pos", "normal", "vel"} (T from the step k_now) or None.
    """

    def __init__(self, cams, aim_y=0.85, aim_x=0.45, vys=(5.0, 4.6, 4.2, 3.8, 3.4, 3.0), vp_max=1.4, tangential=True,
                 verbose=False):
        self.cams = cams
        self.aim_y, self.aim_x, self.vys, self.vp_max, self.tangential = aim_y, aim_x, tuple(vys), vp_max, tangential
        self.verbose = verbose
        self.leg = None
        self.log = []

    def _new_leg(self, key, obs):
        self.leg = {"key": key, "frames": {}, "heard": [], "acts": [], "launch": key[2], "kind": obs.get("ball"),
                    "opp_x": None, "done": False, "pred": None}

    def update(self, obs: dict, img, k_req: int):
        launch = int(round(k_req - float(obs["t_since_played"]) / DT))
        key = (obs.get("point"), obs.get("ball"), launch)
        if self.leg is None or self.leg["key"] != key:
            self._new_leg(key, obs)
        L = self.leg
        L["heard"] = obs.get("heard") or []
        if any(h["event"] in ("paddle", "robot") for h in L["heard"]):
            L["done"] = True
        if obs.get("ball_state") != "coming to you":
            L["done"] = True
        if img is not None and not L["done"]:
            # frame times on this ball's clock from the absolute frame steps (a tile's own stamp is relative to the
            # ball that was current when the frame was taken: right after the opponent's hit, older tiles show our
            # outgoing ball with that ball's clock)
            if obs.get("view_steps") is not None:
                times = [round((k - L["launch"]) * DT, 3) for k in obs["view_steps"]]
            else:
                times = obs["view_times"]
            for t, X in detect_views(img, self.cams, times):
                if t > 0.005:
                    L["frames"][round(t, 3)] = X
        return L

    def _bounce_t(self, which):
        ev = {"opp": "bounce on the opponent's half", "own": "bounce on your half"}[which]
        ts = [h["t"] for h in self.leg["heard"] if h["event"] == ev]
        return ts[0] if ts else None

    def predict(self):
        L = self.leg
        F = sorted(L["frames"].items())
        t_own = self._bounce_t("own")
        if L["kind"] == "serve":
            t_opp = self._bounce_t("opp")
            if t_opp is None:
                return None
            start = t_opp + 0.005
        else:
            start = 0.0
        A = [(t, X) for t, X in F if start < t and (t_own is None or t < t_own - 0.003)]
        fa = fit_flight(A, fit_accel=True) if len(A) >= 3 else None
        if t_own is not None:
            B = [(t, X) for t, X in F if t > t_own + 0.003]
            if len(B) >= 3:
                fb = fit_flight(B, a_fixed=None if fa is None else fa[3])
                pc = predict_contact(fb[0], fb[1], fb[2], fb[3], need_bounce=False)
                if pc is not None:
                    return pc + ("post", len(B))
        if fa is None:
            return None
        pc = predict_contact(fa[0], fa[1], fa[2], fa[3], need_bounce=t_own is None)
        if pc is None:
            return None
        return pc + ("pre", len(A))

    def opp_x(self):
        """Where the opponent is: for a return, where it hit the ball (the first frames of this ball); at a serve it
        stands at the centre."""
        L = self.leg
        if L["kind"] == "serve" or not L["frames"]:
            return 0.0
        t, X = min(L["frames"].items())
        return float(X[0]) if t < 0.2 else 0.0

    def stroke(self, p_hit, v_in, vp_max=None):
        """Aim away from the opponent; among outgoing speeds (vy = 5.0 ... 3.8 m/s) take the fastest whose paddle
        speed the arm can deliver (about VP_MAX m/s at the usual contact poses, from the `act` replies)."""
        ox = self.opp_x()
        side = -1.0 if ox > 0.05 else (1.0 if ox < -0.05 else (-1.0 if p_hit[0] > 0 else 1.0))
        aim = np.array([side * self.aim_x, self.aim_y])
        best = None
        for vy in self.vys:
            v_out, ok = solve_out(p_hit, aim, vy)
            if not ok:
                continue
            p_c, n, v_p = paddle_for(p_hit, v_in, v_out, self.tangential)
            sp = float(np.linalg.norm(v_p))
            if sp <= (self.vp_max if vp_max is None else vp_max):
                return p_c, n, v_p, aim
            if best is None or sp < best[0]:
                best = (sp, p_c, n, v_p)
        if best is None:
            v_out, _ = solve_out(p_hit, aim, self.vys[-1])
            p_c, n, v_p = paddle_for(p_hit, v_in, v_out, self.tangential)
            return p_c, n, v_p, aim
        return best[1], best[2], best[3], aim

    def decide(self, k_now_fn):
        """k_now_fn(): the current game time in (fractional) control steps, as well as the client can tell; called
        again after the stroke is computed, so T counts from when the act will reach the service."""
        L = self.leg
        if L is None or L["done"]:
            return None
        pr = self.predict()
        if pr is None:
            return None
        tc, p, v, phase, nfr = pr
        L["pred"] = pr
        t_now = (k_now_fn() - L["launch"]) * DT
        lead = tc - t_now
        if lead < 0.04:
            return None
        last = L["acts"][-1] if L["acts"] else None
        cap_changed = last is not None and last.get("vp_cap") != L.get("vp_cap")
        if last is not None and not cap_changed:
            dp = float(np.linalg.norm(p - last["p_hit"]))
            dtc = abs(tc - last["tc"])
            new_phase = phase == "post" and last["phase"] == "pre"
            if not new_phase and dp < 0.012 and dtc < 0.006:
                return None
            if lead < 0.07 and dp < 0.03 and not new_phase:
                return None
        p_c, n, v_p, aim = self.stroke(p, v, L.get("vp_cap", self.vp_max))
        k_eff = math.floor(k_now_fn())           # the act applies at the start of the step after the current state
        T = tc - (k_eff - L["launch"]) * DT
        if T <= 0.02:
            return None
        act = {"t": round(float(T), 4), "pos": [round(float(x), 4) for x in p_c],
               "normal": [round(float(x), 4) for x in n], "vel": [round(float(x), 3) for x in v_p]}
        L["acts"].append({"tc": tc, "p_hit": p.copy(), "phase": phase, "k_eff": k_eff, "act": act, "nfr": nfr,
                          "aim": aim.tolist(), "vp": float(np.linalg.norm(v_p)), "vp_cap": L.get("vp_cap")})
        return act

    def on_act_reply(self, stroke: dict | None):
        """The service says how much of the paddle speed the arm can deliver (speed_scale): cap the next strokes of this
        ball below that, and re-plan."""
        L = self.leg
        if not stroke or L is None or not L["acts"]:
            return
        sc = stroke.get("speed_scale") or 1.0
        if sc > 1.02:
            cap = 0.95 * L["acts"][-1]["vp"] / sc
            L["vp_cap"] = round(min(cap, L.get("vp_cap", self.vp_max)), 3)


# ================================================================================================ the arm model (arm.py, low level)


def quat_mat(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def axis_rot(a, t):
    a = np.asarray(a, float) / np.linalg.norm(a)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + np.sin(t) * K + (1 - np.cos(t)) * K @ K


def hermite(q0, v0, q1, v1, T, n):
    t = np.arange(1, n + 1) * (T / n)
    s = t / T
    h00 = 2 * s**3 - 3 * s**2 + 1; h10 = s**3 - 2 * s**2 + s; h01 = -2 * s**3 + 3 * s**2; h11 = s**3 - s**2
    return h00[:, None] * q0 + h10[:, None] * T * v0 + h01[:, None] * q1 + h11[:, None] * T * v1


class Arm:
    def __init__(self, spec: dict):
        kin, lim = spec["kinematics"], spec["limits"]
        self.chain = [(np.array(b["pos_in_parent"], float), quat_mat(b["quat_in_parent_wxyz"]),
                       None if "joint" not in b else np.array(b["joint_axis_in_body"], float)) for b in kin["chain"]]
        self.site = np.array(kin["blade_center_in_paddle"], float)
        self.low = np.array(lim["joint_low_rad"], float)
        self.high = np.array(lim["joint_high_rad"], float)
        self.vlim = np.array(lim["joint_speed_limit_rad_s"], float)
        self.step_lim = np.array(lim["max_target_step_rad"], float)
        self.q0 = np.array(lim["ready_pose_rad"], float)
        rng = np.random.default_rng(0)
        self.starts = [self.q0] + [np.clip(self.q0 + rng.normal(0, .8, 7), self.low + .05, self.high - .05)
                                   for _ in range(12)]

    def fk_full(self, q):
        """(blade centre, paddle rotation (columns: x = face normal), joint axes (7, 3), joint origins (7, 3))."""
        p, R = np.zeros(3), np.eye(3)
        axes, origins, j = [], [], 0
        for pos, Rb, ax in self.chain:
            p = p + R @ pos
            R = R @ Rb
            if ax is not None:
                axes.append(R @ ax); origins.append(p.copy())
                R = R @ axis_rot(ax, q[j]); j += 1
        return p + R @ self.site, R, np.array(axes), np.array(origins)

    def fk(self, q):
        p, R, _, _ = self.fk_full(q)
        return p, R

    def jacobian(self, q):
        p, R, Z, O = self.fk_full(q)
        Jp = np.cross(Z, p - O).T
        return np.vstack([Jp, Z.T]), p, R

    def ik(self, pos, normal, q_init, iters=200, tol=1e-4):
        q = np.array(q_init, float)
        n_t = np.asarray(normal, float) / np.linalg.norm(normal)
        err = np.inf
        for _ in range(iters):
            J, p, R = self.jacobian(q)
            n = R[:, 0]
            e = np.concatenate((pos - p, np.cross(n, n_t)))
            err = float(np.linalg.norm(e[:3]) + np.arcsin(min(1.0, np.linalg.norm(e[3:]))))
            if n @ n_t < 0:
                e[3:] = np.cross(n, n_t) + 0.5 * np.cross(n, R[:, 1]); err += np.pi / 2
            if err < tol:
                break
            q = np.clip(q + J.T @ np.linalg.solve(J @ J.T + 1e-3 * np.eye(6), e), self.low + 1e-4, self.high - 1e-4)
        return q, err

    def ik_best(self, pos, normal, q_ref):
        """An accurate branch with little joint travel from q_ref (as the high-level service chooses it)."""
        def travel(c):
            return float(np.max(np.abs(c[0] - q_ref) / self.vlim))
        def rank(c):
            return (0, travel(c)) if c[1] < 1e-4 else (1, c[1])
        best = self.ik(pos, normal, q_ref)
        if best[1] < 1e-4 and travel(best) <= .35:
            return best
        for s in self.starts:
            c = self.ik(pos, normal, s)
            if rank(c) < rank(best):
                best = c
            if best[1] < 1e-4 and travel(best) <= .35:
                break
        return best

    def stroke(self, q_s, v_s, n_avail, p_c, nrm, v_p, q_ref=None):
        """Joint targets for the next n_avail steps + a follow-through, from the target q_s moving at v_s, so that at
        the end of step n_avail the blade centre is at p_c with face normal nrm and velocity v_p. Returns (rows, info).
        """
        nrm = np.asarray(nrm, float) / np.linalg.norm(nrm)
        q_h, res = self.ik_best(np.asarray(p_c, float), nrm, q_s if q_ref is None else q_ref)
        J, _, _ = self.jacobian(q_h)
        Jp = J[:3]
        W = np.diag(self.vlim ** 2)
        qd_h = W @ Jp.T @ np.linalg.solve(Jp @ W @ Jp.T, np.asarray(v_p, float))
        ratio = float(np.max(np.abs(qd_h) / self.vlim))
        scale = max(1.0, ratio / 0.9)
        qd_h = qd_h / scale
        n_sw = n_avail
        if np.max(np.abs(v_s)) < 1e-6:
            for n in range(25, n_avail + 1):
                sw = hermite(q_s, np.zeros(7), q_h, qd_h, n * DT, n)
                if np.max(np.abs(np.diff(np.vstack([q_s, sw]), axis=0)) / (self.vlim * DT)) <= 0.97:
                    n_sw = n
                    break
        n_sw = int(min(n_sw, n_avail))
        pre = np.tile(q_s, (n_avail - n_sw, 1))
        swing = hermite(q_s, v_s if n_sw == n_avail else np.zeros(7), q_h, qd_h, n_sw * DT, n_sw)
        n_f = 25
        follow = hermite(q_h, qd_h, q_h + qd_h * 0.5 * n_f * DT, np.zeros(7), n_f * DT, n_f)
        rows, prev = [], q_s
        lim = self.step_lim * 0.995
        for q in np.vstack([pre, swing, follow]):
            q = np.clip(q, self.low + 1e-4, self.high - 1e-4)
            q = prev + np.clip(q - prev, -lim, lim)
            rows.append(q); prev = q
        return np.array(rows), {"ik_residual": round(float(res), 5), "speed_scale": round(scale, 3), "n_swing": n_sw}

    def back_to_ready(self, q_s, n=60, frac=0.6):
        """Speed-limited joint-space return to the ready pose (60 % of the speed limits)."""
        rows, q = [], np.array(q_s, float)
        lim = self.step_lim * frac
        for _ in range(n):
            q = q + np.clip(self.q0 - q, -lim, lim)
            rows.append(q.copy())
        return np.array(rows)


# ================================================================================================ the built-in players
LEAD = 2                                     # low level: steps between "now" and where a new swing branches off
MAX_ROWS = 300                               # low level: rows per traj command (/spec limits.max_rows_per_command)


def _in_range(a):
    p, v, n = (np.asarray(a[k], float) for k in ("pos", "vel", "normal"))
    return bool(0 < a["t"] <= 2.5 and abs(p[0]) <= 1.2 and -2.5 <= p[1] <= -0.5 and 0 <= p[2] <= 1.2
                and np.linalg.norm(v) <= 8 and np.linalg.norm(n) > 1e-6 and np.all(np.isfinite(np.r_[p, v, n])))


class Reference:
    def __init__(self, spec: dict, seat: str, seed: int = 0):
        self.low = spec.get("action_level") == "low"
        self.period = (spec.get("timing") or {}).get("period_s")      # None in-process (core/local.py)
        self.P = Player([Cam(c) for c in spec["cameras"]])
        self.A = Arm(spec) if self.low else None
        q0 = self.A.q0.copy() if self.low else None
        self.cmd = {"kind": "hold", "k0": 0, "rows": None, "anchor": (0, q0), "slew": None}

    # ---------------------------------------------------------------- when an act takes effect
    def _clock(self, st, ob):
        step, t0 = float(st["step"]), time.monotonic()
        if self.period is None:
            return lambda: step                  # in-process: the act takes effect before this control step
        # the state is from before the images were drawn; an act takes effect at the control-step boundary after it
        # arrives, i.e. before step floor(now) runs (+ about 30 ms for the request and, in the duel, the IK)
        lag = float(ob.get("render_wall_s") or 0.0) + 0.03
        return lambda: step + (lag + time.monotonic() - t0) / self.period

    # ---------------------------------------------------------------- low level: the command in force
    def _observe_cmd(self, st):
        c = self.cmd
        c["anchor"] = (int(st["step"]) - 1, np.array(st["q_target"], float))
        now = st.get("command")
        if now == "hold":
            c["kind"] = "hold"
        elif isinstance(now, dict) and now.get("type") == "slew" and c["kind"] == "traj":
            c["kind"], c["slew"] = "slew", np.array(now["q"], float)

    def _target(self, k):
        c = self.cmd
        ka, qa = c["anchor"]
        if c["kind"] == "traj" and k >= c["k0"]:
            return c["rows"][min(k - c["k0"], len(c["rows"]) - 1)]
        if c["kind"] == "slew":
            q, lim = qa.copy(), self.A.step_lim * 0.6
            for _ in range(max(0, k - ka)):
                q = q + np.clip(c["slew"] - q, -lim, lim)
            return q
        return qa.copy()

    # ---------------------------------------------------------------- one decision
    def act(self, view):
        st, ob = view["state"], view.get("observation") or {}
        if st.get("world") not in (None, "running"):
            return None
        k_now = self._clock(st, ob)
        incoming = st.get("ball_state") == "coming to you" and bool(st.get("ball_in_play"))
        if self.low:
            self._observe_cmd(st)
        img = None
        if incoming and ob.get("image_png_b64"):
            img = decode(base64.b64decode(ob["image_png_b64"]))
        obs = dict(st, view_steps=ob.get("view_steps"), view_times=ob.get("view_times"))
        self.P.update(obs, img, int(st["step"]))
        a = self.P.decide(k_now) if incoming else None
        if a and not self.low and not _in_range(a):   # the act limits (/spec actions): never send a 400
            a = None
        if not self.low:
            return {"type": "act", **a} if a else None
        if a:
            k_eff = math.floor(k_now())
            k_hit, kb = k_eff + int(round(a["t"] / DT)), k_eff + LEAD
            if k_hit - kb >= 3:
                q_s = self._target(kb - 1)
                v_s = (self._target(kb - 1) - self._target(kb - 2)) / DT
                rows, info = self.A.stroke(q_s, v_s, k_hit - kb, a["pos"], a["normal"], a["vel"])
                self.P.on_act_reply({"speed_scale": info["speed_scale"]})
                head = np.array([self._target(k) for k in range(k_eff, kb)]).reshape(-1, 7)
                rows = np.round(np.vstack([head, rows]), 6)[:MAX_ROWS]
                self.cmd.update(kind="traj", k0=int(k_eff), rows=rows)
                return {"type": "traj", "k0": int(k_eff), "q": rows.tolist()}
            return None
        k = int(st["step"])
        c = self.cmd
        busy = c["kind"] == "traj" and k < c["k0"] + len(c["rows"]) - 1
        if not incoming and not busy and c["kind"] != "slew" and np.max(np.abs(self._target(k) - self.A.q0)) > 1e-4:
            q0 = self.A.q0.round(6)
            c.update(kind="slew", slew=q0)
            return {"type": "slew", "q": q0.tolist(), "speed": 0.6}
        return None

    def review(self, reply):
        return "reference player: scripted", "reference player: same policy"


class Idle:
    def __init__(self, spec: dict, seat: str, seed: int = 0):
        pass

    def act(self, view):
        return None
