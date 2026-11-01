"""The capability-aware stroke choice for match play (pure numpy): the B9 planner's idea (screen/b9.py RANK=cap: the
options this striker executes well first) on the flight a player predicts, for services and rally balls alike.

From the predicted flight (ttplan.fit_flight: the state at t0 and the extra acceleration of the unknown spin) the
planner takes contact candidates every 20 ms on the arc after the ball's bounce on the player's half (ttplan's limits:
not more than G1_BEHIND behind the end line, not low over the table, before a second bounce), and for each candidate
every aim of the aim set (target points on the opponent's half) x outgoing forward speeds. The outgoing ball velocity
that lands at the aim is solved for all options at once (vectorised Newton on the documented flight model), the blade
state from the contact law (ttplan.paddle_for, HITTER's blade velocity along the face normal); options whose blade
speed exceeds vp_max are dropped. Each option's return chance under this striker's own execution is the capability
table's estimate (capability.py: the striker's measured outcomes on training balls, nearest neighbours of the blade
centre, face normal, blade velocity and the time from the command to the contact). The chosen option maximises

    estimate - w_aim * (the aim's distance from the preferred aim) - w_y * |contact depth - y_pref| (ties)

so the player keeps placement control (the preferred aim: a level's or a strategy's target) while the striker's
capability decides which contact and speed to use.
"""
from __future__ import annotations

import importlib.util
import os
import sys

import numpy as np


def _ttplan():
    """ttplan.py of this directory (the module already imported under that name if it is this file, else a fresh one:
    the reference library is also loaded by file path, next to other sports' ttplan modules)."""
    here = os.path.dirname(os.path.abspath(__file__))
    m = sys.modules.get("ttplan")
    if m is not None and os.path.dirname(os.path.abspath(getattr(m, "__file__", "") or "")) == here:
        return m
    spec = importlib.util.spec_from_file_location("g1tt_rallyplan_ttplan", os.path.join(here, "ttplan.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TP = _ttplan()

G = 9.81
KD = TP.KD
BALL_R, NET_Z = TP.BALL_R, TP.NET_Z
TABLE_X, TABLE_Y = TP.TABLE_X, TP.TABLE_Y


def landing_batch(p, v, dt=0.008, n=120, with_time=False):
    """First table contact (x, y) on the opponent's half (y > 0) for N flights from p (N, 3) at v (N, 3) and whether
    the ball cleared the net by 3 cm. Returns (land (N, 2), ok (N,)) [, flight time (N,)]; land is NaN where the ball
    never comes down on the far half within n steps."""
    p = np.array(p, float)
    v = np.array(v, float)
    N = len(p)
    land = np.full((N, 2), np.nan)
    tl = np.full(N, np.nan)
    clear = np.zeros(N, bool)
    crossed = np.zeros(N, bool)
    done = np.zeros(N, bool)
    g = np.array([0.0, 0.0, -G])
    for i in range(n):
        sp = np.sqrt((v * v).sum(1))[:, None]
        v = v + (-KD * sp * v + g) * dt
        p_new = p + v * dt
        cross = ~crossed & (p[:, 1] < 0) & (p_new[:, 1] >= 0)
        if cross.any():
            f = -p[cross, 1] / np.maximum(p_new[cross, 1] - p[cross, 1], 1e-9)
            z_net = p[cross, 2] + f * (p_new[cross, 2] - p[cross, 2])
            clear[cross] = z_net > NET_Z + BALL_R + 0.03
            crossed |= cross
        hit = ~done & (p_new[:, 2] < BALL_R) & (v[:, 2] < 0)
        if hit.any():
            f = (p[hit, 2] - BALL_R) / np.maximum(p[hit, 2] - p_new[hit, 2], 1e-9)
            land[hit] = p[hit, :2] + f[:, None] * (p_new[hit, :2] - p[hit, :2])
            tl[hit] = (i + f) * dt
            done |= hit
        p = p_new
        if done.all():
            break
    on = (land[:, 1] > 0) & (land[:, 1] <= TABLE_Y) & (np.abs(land[:, 0]) <= TABLE_X)
    ok = crossed & clear & on & done
    return (land, ok, tl) if with_time else (land, ok)


def solve_out_batch(p, aim, vy, iters=6):
    """Outgoing velocities (N, 3) from p (N, 3) with forward speed vy (N,) that land at aim (N, 2), all options at
    once: Newton on (vx, vz) with the drag-free Jacobian at the simulated flight time (one rollout per iteration);
    ok (N,): within 3 cm of the aim, over the net with 3 cm to spare."""
    p = np.asarray(p, float)
    aim = np.asarray(aim, float)
    vy = np.asarray(vy, float)
    N = len(p)
    T = np.maximum(0.25, (aim[:, 1] - p[:, 1]) / np.maximum(vy, 0.5))
    v = np.c_[(aim[:, 0] - p[:, 0]) / T, vy, (BALL_R - p[:, 2]) / T + 0.5 * G * T]
    for _ in range(iters):
        L, _ok, tl = landing_batch(p, v, with_time=True)
        bad = ~np.isfinite(L).all(1)
        Tf = np.where(bad, T, tl)
        dT = Tf / np.maximum(G * Tf - v[:, 2], 0.3)          # d(flight time) / d(vz), drag-free
        e = np.where(bad[:, None], 0.0, L - aim)
        # J = [[T, vx dT], [0, vy dT]] (landing x, y w.r.t. vx, vz)
        dvz = e[:, 1] / np.maximum(v[:, 1] * dT, 1e-3)
        dvx = (e[:, 0] - v[:, 0] * dT * dvz) / np.maximum(Tf, 1e-3)
        v = v - np.c_[np.clip(dvx, -1.0, 1.0), np.zeros(N), np.clip(dvz, -1.0, 1.0)]
        v[bad, 2] += 0.4                                     # never came down on the far half: lift it
        T = Tf
    L, ok = landing_batch(p, v)
    ok = ok & (np.linalg.norm(np.nan_to_num(L, nan=9.0) - aim, axis=1) < 0.03)
    return v, ok


def paddle_for_batch(p_hit, v_in, v_out):
    """ttplan.paddle_for (tangential=False) for N options."""
    dv = v_out - v_in
    n = dv / np.linalg.norm(dv, axis=1, keepdims=True)
    vpn = ((v_out * n).sum(1) + TP.E_PADDLE * (v_in * n).sum(1)) / (1 + TP.E_PADDLE)
    return p_hit - TP.OFFSET * n, n, vpn[:, None] * n


def predict_arc(samples, start_t, own_bounce_t=None, sig_meas=0.01, sig_p=0.03, sig_v=0.3, t_max=1.6, dt=0.002):
    """The ball's predicted arc after its bounce on the player's half from noisy position samples [(t, X)] (own
    frame) of the flight that started at start_t (the opponent's contact, or a service's bounce on the server's
    half). The flight before the bounce is fitted (ttplan.fit_flight with the extra acceleration of the unknown spin)
    and rolled through the bounce (ttplan's restitution model); once the bounce is heard (own_bounce_t), the
    samples after it correct the model's arc by an offset and a velocity change (weighted least squares with a prior:
    the bounce model's error, sig_p / sig_v, against the measurement noise sig_meas).
    Returns (t (n,), P (n, 3), V (n, 3), info) of the arc from the bounce to the end of the horizon, or None."""
    pre = [(t, X) for t, X in samples if t > start_t + 0.005 and (own_bounce_t is None or t < own_bounce_t - 0.003)]
    if len(pre) < 3:
        return None
    fa = TP.fit_flight(pre, fit_accel=True)
    if fa is None:
        return None
    t0, p0, v0, ae = fa[0], fa[1], fa[2], fa[3]
    P, V, b = TP.rollout(p0, v0, dt, int(t_max / dt), bounce=True, a_extra=ae)
    own = [i for i in b if P[i, 1] < 0]
    if not own:
        return None
    i_b = own[0]
    nxt = [j for j in b if j > i_b]
    end = nxt[0] if nxt else len(P) - 1
    T = t0 + dt * np.arange(i_b, end + 1)
    P, V = P[i_b:end + 1].copy(), V[i_b:end + 1].copy()
    info = {"n_pre": len(pre), "n_post": 0, "rms": fa[4], "t_bounce_pred": float(T[0])}
    if own_bounce_t is not None:
        post = [(t, X) for t, X in samples if t > own_bounce_t + 0.003]
        if post:
            tb = float(T[0])
            A_rows, r_rows = [], []
            for t, X in post:
                j = int(round((t - tb) / dt))
                if not 0 <= j < len(T):
                    continue
                tau = t - tb
                A_rows.append(tau)
                r_rows.append(np.asarray(X, float) - P[j])
            if A_rows:
                tau = np.asarray(A_rows)
                r = np.asarray(r_rows)
                wm = 1.0 / sig_meas ** 2
                M = np.array([[len(tau) * wm + 1.0 / sig_p ** 2, tau.sum() * wm],
                              [tau.sum() * wm, (tau * tau).sum() * wm + 1.0 / sig_v ** 2]])
                rhs = np.stack([r.sum(0) * wm, (tau[:, None] * r).sum(0) * wm])      # (2, 3)
                sol = np.linalg.solve(M, rhs)
                dp, dv = sol[0], sol[1]
                P = P + dp[None] + (T - tb)[:, None] * dv[None]
                V = V + dv[None]
                info.update(n_post=len(tau), dp=dp.round(3).tolist(), dv=dv.round(3).tolist())
    return T, P, V, info


def arc_contacts(arc, t_min=0.0, step_s=0.02):
    """Contact candidates (t, ball p, ball v) every step_s on a predicted arc (predict_arc) after the bounce
    (ttplan.predict_contact's limits)."""
    if arc is None:
        return []
    T, P, V = arc[0], arc[1], arc[2]
    dt = T[1] - T[0] if len(T) > 1 else 0.002
    k = max(1, int(round(step_s / dt)))
    out = []
    for i in range(int(round(0.015 / dt)), len(T), k):
        p = P[i]
        if p[1] < TP.G1_BEHIND:
            break
        if T[i] < t_min:
            continue
        over = p[1] > -TABLE_Y and abs(p[0]) < TABLE_X
        if p[2] < (TP.G1_MIN_Z_OVER if over else TP.G1_MIN_Z) or p[2] > 0.55:
            continue
        out.append((float(T[i]), P[i].copy(), V[i].copy()))
    return out


def contact_at(arc, t):
    """The one candidate at contact time t on a predicted arc (or [] when the arc does not reach it)."""
    if arc is None:
        return []
    T, P, V = arc[0], arc[1], arc[2]
    if not len(T) or t < T[0] or t > T[-1]:
        return []
    i = int(np.argmin(np.abs(T - t)))
    return [(float(T[i]), P[i].copy(), V[i].copy())]


def contacts(t0, p0, v0, a_extra, need_bounce=True, t_min=0.0, step_s=0.02, t_max=1.6):
    """Contact candidates (t, ball p, ball v) every step_s on the arc after the ball's bounce on the player's half
    (ttplan.predict_contact's limits), no earlier than t_min."""
    dt = 0.002
    P, V, b = TP.rollout(p0, v0, dt, int(t_max / dt), bounce=True, a_extra=a_extra)
    if need_bounce:
        own = [i for i in b if P[i, 1] < 0]
        if not own:
            return []
        i_b = own[0]
    else:
        i_b = 0
    nxt = [j for j in b if j > i_b]
    end = nxt[0] if nxt else len(P) - 1
    out = []
    k = max(1, int(round(step_s / dt)))
    for i in range(i_b + int(round(0.015 / dt)), end, k):
        p = P[i]
        t = t0 + i * dt
        if p[1] < TP.G1_BEHIND:
            break
        if t < t_min:
            continue
        over = p[1] > -TABLE_Y and abs(p[0]) < TABLE_X
        if p[2] < (TP.G1_MIN_Z_OVER if over else TP.G1_MIN_Z) or p[2] > 0.55:
            continue
        out.append((t, P[i].copy(), V[i].copy()))
    return out


AIMS = np.array([(x, y) for y in (0.55, 0.80, 1.05) for x in (-0.50, -0.25, 0.0, 0.25, 0.50)])
VYS = np.array([5.0, 4.4, 3.8, 3.2])
AIM_BIAS = (0.0, 0.15)
GAINS = (1.0, 1.15, 1.3, 1.45)   # the blade velocity commanded = the contact law's x a gain the planner chooses: the G1
                        # striker delivers less than it is asked (as the H2's, ~3/4), and the capability (fitted to
                        # full-world plays at these gains, prototypes/tabletennis_g1/cap_cpu.py) says which gain
                        # returns the ball best for each option
V_GAIN = 1.0            # (the H2 port's fixed gain; with GAINS the planner's v is already the commanded one)
RISK = dict(wide=0.10, short=0.05, slow=0.05, far=0.0, low=2.0)   # far: the G1 capability is measured in the world


class Planner:
    def __init__(self, cap, aims=AIMS, vys=VYS, vp_max=1.6, y_pref=TP.G1_Y_PREF, w_aim=0.25, w_y=0.05,
                 aim_bias=AIM_BIAS, risk=RISK, gains=GAINS):
        self.cap = cap                                  # capability.Capability (or None: the cost alone)
        self.aims, self.vys, self.vp_max = np.asarray(aims, float), np.asarray(vys, float), float(vp_max)
        self.y_pref, self.w_aim, self.w_y = float(y_pref), float(w_aim), float(w_y)
        self.aim_bias = np.asarray(aim_bias, float)    # solved for aim + bias: the striker lands short of the law
        self.risk = dict(risk)
        self.gains = np.asarray(gains if cap is not None else (1.0,), float)
        self.last = None

    def prior(self, aims, vy, p_ball):
        """The risk prior (subtracted from the capability estimate): the rally screen's failures (screen/rally.py,
        capability planner, h2s striker, 253 rally strokes) concentrate on wide aims, short aims, the slow vy,
        contacts far behind the end line and low contacts, which the capability (labelled in the MJX trainer with
        exact ball knowledge) does not see."""
        r = self.risk
        return (r["wide"] * np.abs(aims[:, 0]) / 0.5 + r["short"] * np.clip(0.8 - aims[:, 1], 0, None) / 0.25
                + r["slow"] * np.clip(4.4 - vy, 0, None) + r["far"] * np.clip(np.abs(p_ball[:, 1]) - 1.15, 0, None)
                + r["low"] * np.clip(0.12 - p_ball[:, 2], 0, None))

    def choose(self, cands, t_cmd, aim_pref=None, aims=None, vys=None, gains=None, pick=None):
        """cands: contacts(); t_cmd: when the command takes effect (the striker's T = t_contact - t_cmd).
        Every option is estimated at each command gain (the commanded blade velocity = gain x the contact law's);
        the returned v is the commanded one. pick = (u, tol): a mixed choice, the option at u in [0, 1) among those
        scoring within tol of the best (u drawn by the caller; None: the best). Returns dict(t, ball, p, n, v, aim, vy,
        gain, est, n_opts) or None."""
        if not cands:
            return None
        aims = self.aims if aims is None else np.asarray(aims, float)
        vys = self.vys if vys is None else np.asarray(vys, float)
        C = len(cands)
        A, S = len(aims), len(vys)
        ti = np.repeat(np.arange(C), A * S)
        ai = np.tile(np.repeat(np.arange(A), S), C)
        si = np.tile(np.arange(S), C * A)
        tc = np.array([c[0] for c in cands])[ti]
        pb = np.array([c[1] for c in cands])[ti]
        vb = np.array([c[2] for c in cands])[ti]
        v_out, ok = solve_out_batch(pb, aims[ai] + self.aim_bias, vys[si])
        p_c, n, v_p = paddle_for_batch(pb, vb, v_out)
        sp = np.linalg.norm(v_p, axis=1)
        ok &= sp <= self.vp_max
        ok &= tc - t_cmd > 0.06
        if not ok.any():
            return None
        gs = self.gains if gains is None else np.asarray(gains, float)
        idx = np.repeat(np.where(ok)[0], len(gs))
        gg = np.tile(gs, int(ok.sum()))
        T = tc[idx] - t_cmd
        v_cmd = v_p[idx] * gg[:, None]
        est = self.cap.estimate(p_c[idx], n[idx], v_cmd, T) if self.cap is not None else np.zeros(len(idx))
        score = est - self.w_y * np.abs(p_c[idx, 1] - self.y_pref) - self.prior(aims[ai[idx]], vys[si[idx]], pb[idx])
        if aim_pref is not None:
            score = score - self.w_aim * np.linalg.norm(aims[ai[idx]] - np.asarray(aim_pref, float), axis=1)
        jj = int(np.argmax(score))
        if pick is not None and pick[1] > 0:
            near = np.flatnonzero(score >= score[jj] - float(pick[1]))
            jj = int(near[min(len(near) - 1, int(float(pick[0]) * len(near)))])
        j = idx[jj]
        self.last = dict(t=float(tc[j]), ball=pb[j], p=p_c[j], n=n[j], v=v_cmd[jj], aim=aims[ai[j]].tolist(),
                         vy=float(vys[si[j]]), gain=float(gg[jj]), est=float(est[jj]), score=float(score[jj]),
                         n_opts=int(ok.sum()))
        return self.last
