"""Ball flight, contact choice, stroke and serve planning for the G1 (pure numpy): the camera-only reference player of
the table-tennis family (sports/tabletennis builtin_players.py, revision wallclock-15) with the G1's choices (the G1
preview's reference, archive/20261020/g1-ttplay builtin_players.py): the contact point the G1 reaches best, HITTER's
blade velocity along the face normal, the G1 serve repertoire. Used by the platform's opponent (sim/opponent.py) and
our reference player (builtin_players.OpenReference; the task's solution/skill). The flight model is the instructions'
(gravity, drag about 0.13 |v| v, the table bounce 0.90 / 0.87); the contact law the instructions' (restitution 0.80
along the face normal)."""
from __future__ import annotations

import math

import numpy as np

G = np.array([0.0, 0.0, -9.81])
KD = 0.13                 # drag: deceleration KD |v| v (instructions: about 0.13)
E_BOUNCE_Z, E_BOUNCE_XY = 0.90, 0.87   # the venue's ball-table pair (ITTF drop 30 -> 23 cm)
BALL_R = 0.02
OFFSET = 0.0275           # blade centre = ball centre - OFFSET * normal (ball radius + half the blade thickness)
E_PADDLE = 0.80           # the venue's ball-blade pair (normal restitution 0.80)
TABLE_X, TABLE_Y = 0.7625, 1.37
NET_Z = 0.1525


# ------------------------------------------------------------------------------------------------ flight model
def rollout(p, v, dt, n, bounce=True, a_extra=None):
    """Explicit integration (semi-implicit Euler) of gravity + drag (+ a constant extra acceleration); the table bounce
    (restitution) when bounce=True. Returns positions (n+1, 3), velocities (n+1, 3), list of bounce indices. Scalar
    float arithmetic (the same operations as the vector form, about 10 times faster in Python)."""
    px, py, pz = (float(x) for x in p)
    vx, vy, vz = (float(x) for x in v)
    ax, ay, az = (0.0, 0.0, 0.0) if a_extra is None else (float(x) for x in a_extra)
    gz = float(G[2])
    P = [(px, py, pz)]
    V = [(vx, vy, vz)]
    bounces = []
    sq = math.sqrt
    for i in range(1, n + 1):
        sp = sq(vx * vx + vy * vy + vz * vz)
        vx += (-KD * sp * vx + ax) * dt
        vy += (-KD * sp * vy + ay) * dt
        vz += (gz - KD * sp * vz + az) * dt
        px += vx * dt
        py += vy * dt
        pz += vz * dt
        if bounce and pz < BALL_R and vz < 0 and abs(px) <= TABLE_X + 0.01 and abs(py) <= TABLE_Y + 0.01:
            vx, vy, vz = vx * E_BOUNCE_XY, vy * E_BOUNCE_XY, -vz * E_BOUNCE_Z
            pz = 2 * BALL_R - pz
            bounces.append(i)
        P.append((px, py, pz))
        V.append((vx, vy, vz))
    return np.array(P), np.array(V), bounces


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


LATE_Y, LATE_Z, LATE_APEX_Y, SHORT_Z = -1.42, 0.06, -1.25, 0.15
SERVE_LATE = True                  # services: take a short ball late (predict_contact late=True)


def predict_contact(t0, p0, v0, a_extra=None, need_bounce=True, t_max=1.6, dt=0.001, late=False):
    """G1: from the state at t0, our bounce (if need_bounce), then the contact point on the arc after it that the G1
    reaches best (the planner's preference of the controller's B9, prototypes/tabletennis_g1/b9.py rank): as little
    over the table as possible (a G1 must lean over it), not low over the table (the blade would touch it), not
    high; at most G1_BEHIND behind the end line; before a second bounce. (The Franka reference takes the top of the
    arc or the end-line crossing.) Returns (t_contact, p, v) or None. `late` is accepted and ignored."""
    n = int(t_max / dt)
    P, V, bounces = rollout(p0, v0, dt, n, bounce=True, a_extra=a_extra)
    if need_bounce:
        own = [i for i in bounces if P[i, 1] < 0]
        if not own:
            return None
        i_b = own[0]
    else:
        i_b = 0
    nxt = [j for j in bounces if j > i_b]
    end = nxt[0] if nxt else n
    best = None
    for i in range(i_b + 1, end, 5):
        p = P[i]
        if p[1] < G1_BEHIND:
            break
        over_table = p[1] > -TABLE_Y and abs(p[0]) < TABLE_X
        if p[2] < (G1_MIN_Z_OVER if over_table else G1_MIN_Z):
            continue
        over = max(0.0, p[1] - (-TABLE_Y - 0.05))
        low = max(0.0, 0.10 - p[2]) if over_table else 0.0
        c = 3.0 * over + 2.0 * low + 1.0 * max(0.0, p[2] - 0.40) + 0.3 * abs(p[1] - (-TABLE_Y - 0.05))
        if best is None or c < best[0]:
            best = (c, i)
    if best is None:
        return None
    i = best[1]
    return t0 + i * dt, P[i].copy(), V[i].copy()


G1_BEHIND = -1.75                  # G1: no contact more than 0.38 m behind the end line (the stance rule's reach)
G1_MIN_Z = 0.05                    # G1: no contact lower than this behind the end line (the ball's centre, table frame)
G1_MIN_Z_OVER = 0.10               # ... and over the table (receive study 10-15: 43 vs 25 of 93 library serves with 0.05;
                                   # B9's first options of this controller: blade centre ~0.09 m, first-try 156 of 318)
G1_Y_PREF = -1.25                  # the capability planner's tie-break: contacts near the end line (rallyplan.Planner)


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


def paddle_for(p_hit, v_in, v_out, tangential=False):
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


# ================================================================================================ the G1 serve
TOSS_REST = 10                     # the toss rests 0.1 s at its point before it is projected (Law 2.6.1)
SERVE_VZ_OUT = (-2.0, -1.5, -1.0, -0.6, -0.3, 0.0, 0.3, 0.6, 1.0, 1.4, 1.8, 2.2)   # outgoing vertical speed families
END_Y = -1.37
G1_SERVES = {   # contact (x, y, z) of the falling toss, the receiver's bounce b2 the plan aims at, the blade speed cap,
                # the toss point's height above the contact (the toss rises 0.30 m). From the G1 preview's serve study
                # (olympiad_review/screening/g1ttplay_zh.md), recalibrated in tabletennis_g1's world (the striker through
                # the joint interface, D13 0.3 m, the service zone |x| <= 0.6 m): the delivered bounce lands short of b2,
                # so b2 and the blade cap are the variants whose delivered bounce is 0.57-0.63 m from the net with
                # neighbours that are legal too (screening: 64 variants, olympiad_review/handoff/g1tt_v2_1021.md)
    "wide_bh": dict(contact=(-0.20, -1.45, 0.28), b2=(-0.4, 0.6), vp_max=1.5, toss_dz=0.18),     # delivered (-0.34, 0.57)
    "wide_fh": dict(contact=(0.10, -1.45, 0.28), b2=(0.4, 0.75), vp_max=1.8),                     # (0.42, 0.59)
    "wide_bh_high": dict(contact=(-0.20, -1.45, 0.35), b2=(-0.4, 0.9), vp_max=1.8),               # (-0.38, 0.60)
    "mid": dict(contact=(0.10, -1.45, 0.35), b2=(0.0, 0.9), vp_max=1.8),                          # (-0.01, 0.63)
}
SERVE_ORDER = ("wide_fh", "wide_bh_high", "mid")   # wide_bh left out: the robot fell after it in 48 of 96 matches of
                                                   # the level screening (2026-10-21)
TOSS_DZ, TOSS_H = 0.10, 0.30       # the toss point 10 cm above the contact, rising 0.30 m


def toss_speed(h):
    """The upward speed that makes the ball rise h metres (flight model: gravity, drag KD |v| v)."""
    return math.sqrt(9.81 / KD * (math.exp(2 * KD * h) - 1.0))


def toss_flight(p, vz, t):
    n = max(1, int(round(t / 0.001)))
    P, V, _ = rollout(p, [0.0, 0.0, vz], 0.001, n, bounce=False)
    return P[-1], V[-1]


def serve_bounces(p, v, dt=0.002, n=900):
    P, _, b = rollout(p, v, dt, n, bounce=True)
    out, clear = [], False
    for i in b[:2]:
        out.append(P[i, :2].copy())
    if len(b) >= 2:
        seg = P[b[0]:b[1] + 1]
        j = int(np.argmin(np.abs(seg[:, 1])))
        clear = bool(seg[j, 2] > NET_Z + BALL_R + 0.02)
    return out, clear


def solve_serve(p_hit, b2, vz_out):
    """= the frozen reference's: outgoing velocity from p_hit, bouncing on your court, then at b2 on the receiver's."""
    v = np.array([(b2[0] - p_hit[0]) / 0.6, 3.5, float(vz_out)])
    for _ in range(30):
        L, ok = serve_bounces(p_hit, v)
        if len(L) < 2 or L[0][1] >= 0 or abs(L[0][0]) > TABLE_X or L[0][1] < -TABLE_Y:
            v[1] *= 0.92
            continue
        e = L[1] - np.asarray(b2, float)
        if np.linalg.norm(e) < 0.01:
            return v if ok else None
        J = np.zeros((2, 2))
        for c in range(2):
            dv = np.zeros(3); dv[c] = 0.02
            L2, _ = serve_bounces(p_hit, v + dv)
            if len(L2) < 2:
                return None
            J[:, c] = (L2[1] - L[1]) / 0.02
        try:
            v[:2] -= np.clip(np.linalg.solve(J, e), -1.0, 1.0)
        except np.linalg.LinAlgError:
            return None
    return None


def stance_for(p, pelvis_now, base_gap=0.13, base_dx=(0.30, 0.25, 0.55, 0.03)):
    """The controller's stance rule (/spec controller.stance_rule): the pelvis target for a contact p."""
    fore = p[0] - pelvis_now[0] > -0.12
    dx0, d0, d1, dx1 = base_dx
    dx = dx0 + (dx1 - dx0) * min(max((p[1] - END_Y - d0) / (d1 - d0), 0.0), 1.0)
    return np.array([p[0] - dx if fore else p[0] + 0.02, min(p[1] - 0.42, END_Y - base_gap)])


def serve_plan(recipe):
    """(toss {pos, height}, the hit's paddle state with its time from the projection, the stance) of a G1 serve."""
    c = np.asarray(recipe["contact"], float)
    P = c + np.array([0.0, 0.0, recipe.get("toss_dz", TOSS_DZ)])
    h = recipe.get("height", TOSS_H)
    t = 0.0
    while True:
        t += 0.002
        p, v = toss_flight(P, toss_speed(h), t)
        if v[2] < 0 and p[2] <= c[2]:
            break
        if t > 2.0:
            return None
    best = None
    for vz in recipe.get("vz_out", SERVE_VZ_OUT):
        v_out = solve_serve(p, recipe["b2"], vz)
        if v_out is None:
            continue
        p_c, n, v_p = paddle_for(p, v, v_out, tangential=False)
        if float(np.linalg.norm(v_p)) <= recipe["vp_max"] and (best is None or np.linalg.norm(v_out) > np.linalg.norm(best[0])):
            best = (v_out, p_c, n, v_p)
    if best is None:
        return None
    v_out, p_c, n, v_p = best
    stance = stance_for(p_c, np.array([-0.30, -1.52]))
    return ({"pos": P.round(4).tolist(), "height": h},
            {"t_from_projection": round(t, 3), "pos": p_c, "normal": n, "vel": v_p, "stance": stance, "v_out": v_out})

