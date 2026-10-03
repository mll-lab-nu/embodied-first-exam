"""Perception-based reference player for the wall-clock tennis match (no privileged state, no simulator).

It uses only what any player gets: the `observe` camera images (2 cameras x 4 frames) with their frame steps, the
robot's own state in the replies, the camera poses / intrinsics from `spec` and the physics documented in the
instructions. Pipeline:
  1. detect the yellow-green ball in each of the 8 tiles (colour threshold + centroid) and turn it into a ray;
  2. fit the ball's flight since it was played to every ray seen so far (start position, velocity and spin; gravity,
     drag, Magnus lift and the court bounce law; Levenberg-Marquardt), and predict it through the bounce on our half;
  3. choose the contact after the bounce (near the top of the arc, 0.55-1.4 m high, where the base can get in time),
     an aim deep and wide in the opponent's court away from where it played the ball, and the racket face from the
     documented contact law (Newton on the landing point);
  4. send `move` early to bring the base towards the stance and `act` with T counted from the predicted effect step;
     re-act when the prediction moves or the act took effect at another step.
numpy + Pillow only.
"""
from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------------------------- documented physics
G = 9.81
R = 0.0335                                   # ball radius
K_DRAG = 0.5 * 1.21 * 0.55 * math.pi * R * R / 0.0577
K_LIFT = 0.5 * 1.21 * math.pi * R * R / 0.0577
ALPHA = 0.55
E_COURT, MU_COURT = 0.76, 0.6
E_NET, MU_NET = 0.3, 0.3                  # net cord (the net's top edge)
E_RACKET, MU_RACKET, GAIN = 0.82, 0.4, 5.0
COURT_X, COURT_Y = 4.115, 11.885
NET_C, NET_P, NET_STICK, NET_POST = 0.914, 1.07, 5.029, 6.40
STANCE_OFF = np.array([0.62, 0.30])
BASE_LO, BASE_HI = np.array([-5.9, -15.4]), np.array([5.9, -7.6])
HOME = np.array([0.0, -11.4])
BASE_V, BASE_A = 4.0, 8.0
DT = 0.01
TILE_W, TILE_H = 640, 480


def net_top(x):
    return NET_C + (NET_P - NET_C) * min(abs(x), NET_STICK) / NET_STICK


def impact(v, w, n, e, mu):
    """The documented impulse law on a rigid surface with unit normal n (towards the ball); v relative to it."""
    v = np.asarray(v, float); w = np.asarray(w, float); n = np.asarray(n, float)
    vn = float(v @ n)
    if vn >= 0:
        return v.copy(), w.copy()
    r = -R * n
    u = v + np.cross(w, r)
    t = u - (u @ n) * n
    tn = float(np.linalg.norm(t))
    jn = (1.0 + e) * (-vn)
    J = jn * n
    if tn > 1e-12:
        jt = min(mu * jn, tn * ALPHA / (1.0 + ALPHA))
        J = J - jt * t / tn
    return v + J, w + np.cross(r, J) / (ALPHA * R * R)


def accel(V, W):
    """Batch acceleration: V, W (N, 3)."""
    sp = np.linalg.norm(V, axis=1, keepdims=True)
    a = -K_DRAG * sp * V
    a[:, 2] -= G
    c = np.cross(W, V)
    cn = np.linalg.norm(c, axis=1, keepdims=True)
    wn = np.linalg.norm(W, axis=1, keepdims=True)
    ok = (cn > 1e-9) & (sp > 0.1)
    S = R * wn / np.maximum(sp, 1e-9)
    cl = S / (2.0 * S + 1.0)
    f = np.where(ok, K_LIFT * cl * sp * sp / np.maximum(cn, 1e-12), 0.0)
    return a + f * c


def fly(P, V, W, times, dt=0.002, bounce_court=True):
    """Batch flight from t = 0 of N states; positions at the requested times (sorted, >= 0): (N, len(times), 3), and
    the first court bounce time / position of each state (nan if none)."""
    P, V, W = P.copy(), V.copy(), W.copy()
    N = len(P)
    out = np.zeros((N, len(times), 3))
    bt = np.full(N, np.nan); bp = np.full((N, 2), np.nan)
    t, j = 0.0, 0
    while j < len(times) and times[j] <= 1e-12:
        out[:, j] = P; j += 1
    while j < len(times):
        h = min(dt, times[j] - t)
        A = accel(V, W)
        V2 = V + A * h
        P2 = P + V2 * h
        if bounce_court:
            hit = (P2[:, 2] < R) & (V2[:, 2] < 0)
            for i in np.nonzero(hit)[0]:
                f = (P[i, 2] - R) / (P[i, 2] - P2[i, 2]) if P[i, 2] != P2[i, 2] else 1.0
                f = min(max(f, 0.0), 1.0)
                c = P[i] + f * (P2[i] - P[i])
                v2, w2 = impact(V2[i], W[i], (0.0, 0.0, 1.0), E_COURT, MU_COURT)
                rem = (1.0 - f) * h
                P2[i] = [c[0] + v2[0] * rem, c[1] + v2[1] * rem, R + v2[2] * rem]
                V2[i] = v2; W[i] = w2
                if np.isnan(bt[i]):
                    bt[i] = t + f * h; bp[i] = c[:2]
        P, V = P2, V2
        t += h
        while j < len(times) and times[j] - t <= 1e-9:
            out[:, j] = P; j += 1
    return out, bt, bp


def _cord(p, q):
    """The documented net cord: where the step p -> q first brings the ball's centre within R of the net's top edge
    (y = 0, z = net top): (fraction, contact point, unit normal from the edge to the ball) or None."""
    xm = 0.5 * (p[0] + q[0])
    if abs(xm) > NET_POST:
        return None
    top = net_top(xm)
    y0, dy, z0, dz = p[1], q[1] - p[1], p[2] - top, q[2] - p[2]
    c = y0 * y0 + z0 * z0 - R * R
    a = dy * dy + dz * dz
    if c <= 0 or a <= 0:
        return None
    b = 2 * (y0 * dy + z0 * dz)
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    s = (-b - math.sqrt(disc)) / (2 * a)
    if not 0 <= s <= 1:
        return None
    cp = p + s * (q - p)
    n = np.array([0.0, cp[1], cp[2] - top]); n /= np.linalg.norm(n)
    return s, cp, n


def trajectory(p, v, w, t_end, dt=0.001):
    """Single flight sampled every dt: times, P, V, W and court bounces [(t, x, y)] (stops at a net crossing below the
    net top, or the second bounce)."""
    p = np.asarray(p, float).copy(); v = np.asarray(v, float).copy(); w = np.asarray(w, float).copy()
    ts, Ps, Vs, Ws, bounces = [0.0], [p.copy()], [v.copy()], [w.copy()], []
    t = 0.0
    while t < t_end - 1e-9:
        a = accel(v[None], w[None])[0]
        v2 = v + a * dt
        p2 = p + v2 * dt
        cord = _cord(p, p2)
        if cord is not None and v2[1] * cord[2][1] + v2[2] * cord[2][2] < 0:
            s, cp, n = cord                                  # the ball touches the net's top edge and goes on
            v2, w = impact(v2, w, n, E_NET, MU_NET)
            p2 = cp + v2 * (1.0 - s) * dt
            bounces.append((t + s * dt, cp[0], cp[2], "cord"))
        elif (p[1] > 0) != (p2[1] > 0) and p[1] != p2[1]:
            f = p[1] / (p[1] - p2[1])
            xn, zn = p[0] + f * (p2[0] - p[0]), p[2] + f * (p2[2] - p[2])
            if abs(xn) <= NET_POST and zn < net_top(xn) - R:
                bounces.append((t + f * dt, xn, 0.0, "net"))
                break
        if p2[2] < R and v2[2] < 0:
            f = (p[2] - R) / (p[2] - p2[2]) if p[2] != p2[2] else 1.0
            f = min(max(f, 0.0), 1.0)
            c = p + f * (p2 - p)
            v2, w = impact(v2, w, (0.0, 0.0, 1.0), E_COURT, MU_COURT)
            rem = (1.0 - f) * dt
            p2 = np.array([c[0] + v2[0] * rem, c[1] + v2[1] * rem, R + v2[2] * rem])
            bounces.append((t + f * dt, c[0], c[1], "bounce"))
        p, v = p2, v2
        t += dt
        ts.append(t); Ps.append(p.copy()); Vs.append(v.copy()); Ws.append(w.copy())
        if sum(1 for b in bounces if b[3] == "bounce") >= 2:
            break
    return np.array(ts), np.array(Ps), np.array(Vs), np.array(Ws), bounces


def landings(P0, V0, W0, dt=0.003, t_max=2.5):
    """Batch first landing of outgoing shots (towards +y): landing xy (nan if none), net clearance at y = 0."""
    P, V, W = P0.copy(), V0.copy(), W0.copy()
    N = len(P)
    land = np.full((N, 2), np.nan); clear = np.full(N, np.nan)
    alive = np.ones(N, bool)
    t = 0.0
    while t < t_max and alive.any():
        A = accel(V, W)
        V2 = V + A * dt
        P2 = P + V2 * dt
        cross = alive & (P[:, 1] <= 0) & (P2[:, 1] > 0)
        for i in np.nonzero(cross)[0]:
            f = -P[i, 1] / (P2[i, 1] - P[i, 1])
            xn, zn = P[i, 0] + f * (P2[i, 0] - P[i, 0]), P[i, 2] + f * (P2[i, 2] - P[i, 2])
            clear[i] = zn - R - net_top(xn)
            if abs(xn) <= NET_POST and clear[i] < 0:
                alive[i] = False
        down = alive & (P2[:, 2] < R) & (V2[:, 2] < 0)
        for i in np.nonzero(down)[0]:
            f = (P[i, 2] - R) / (P[i, 2] - P2[i, 2])
            land[i] = (P[i, :2] + f * (P2[i, :2] - P[i, :2]))
            alive[i] = False
        P, V = P2, V2
        t += dt
    return land, clear


def contact_out(v_in, w_in, n, s):
    """The documented racket contact law at the head centre: commanded head velocity s * n."""
    vr = s * np.asarray(n, float) * GAIN
    u2, w2 = impact(np.asarray(v_in, float) - vr, w_in, n, E_RACKET, MU_RACKET)
    return u2 + vr, w2


def nvec(az, el):
    return np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])


def base_time(dist):
    a, vm = BASE_A * 0.85, BASE_V * 0.98
    return 2 * math.sqrt(dist / a) if dist < vm * vm / a else dist / vm + vm / a


def stance(pc):
    return np.clip(np.asarray(pc[:2], float) - STANCE_OFF, BASE_LO, BASE_HI)


# ---------------------------------------------------------------------------------------------- cameras
class Cam:
    def __init__(self, c: dict):
        self.pos = np.array(c["position"], float)
        self.fw = np.array(c["forward"], float); self.fw /= np.linalg.norm(self.fw)
        self.up = np.array(c["up"], float); self.up /= np.linalg.norm(self.up)
        self.rt = np.cross(self.fw, self.up)
        self.f = float(c.get("focal_px", 579.4))
        pp = c.get("principal_point_px", [320, 240])
        self.cx, self.cy = float(pp[0]), float(pp[1])

    def ray(self, u, v):
        d = self.fw + ((u - self.cx) / self.f) * self.rt - ((v - self.cy) / self.f) * self.up
        return self.pos, d / np.linalg.norm(d)


def decode(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))


def detect(img: np.ndarray):
    """[(row, col, u, v)] of the ball's centroid in each tile where it is seen (yellow-green: G high, G > R, B low)."""
    a = img.astype(np.int16)
    Rr, Gg, Bb = a[..., 0], a[..., 1], a[..., 2]
    mask = (Gg > 110) & (Gg > Rr + 8) & (Gg > 2 * Bb + 20)
    out = []
    rows, cols = img.shape[0] // TILE_H, img.shape[1] // TILE_W
    for r in range(rows):
        for c in range(cols):
            m = mask[r * TILE_H:(r + 1) * TILE_H, c * TILE_W:(c + 1) * TILE_W]
            ys, xs = np.nonzero(m)
            if len(xs) < 2:
                continue
            g = Gg[r * TILE_H:(r + 1) * TILE_H, c * TILE_W:(c + 1) * TILE_W][ys, xs]
            i = int(np.argmax(g))
            near = (np.abs(xs - xs[i]) < 25) & (np.abs(ys - ys[i]) < 25)
            if near.sum() < 2:
                continue
            wgt = g[near].astype(float)
            out.append((r, c, float((xs[near] * wgt).sum() / wgt.sum()) + 0.5, float((ys[near] * wgt).sum() / wgt.sum()) + 0.5))
    return out


# ---------------------------------------------------------------------------------------------- flight fit
class Flight:
    """The rays of one ball (one leg) and the fitted flight."""

    def __init__(self, leg_id, launch_k):
        self.leg_id, self.launch_k = leg_id, launch_k
        self.rays = {}                     # (k, cam) -> (origin, direction)
        self.fit = None                    # (t_ref k, p, v, w, rms)
        self.n_fit = 0

    def add(self, k, cam, o, d):
        self.rays[(k, cam)] = (o, d)

    def span(self):
        ks = sorted({k for k, _ in self.rays})
        return (ks[-1] - ks[0]) if ks else 0, len(ks)

    def solve(self):
        keys = sorted(self.rays)
        if len({k for k, _ in keys}) < 3:
            return None
        k0 = keys[0][0]
        ts = np.array([(k - k0) * DT for k, _ in keys])
        O = np.array([self.rays[x][0] for x in keys]); D = np.array([self.rays[x][1] for x in keys])
        Pm = np.eye(3)[None] - D[:, :, None] * D[:, None, :]              # projectors orthogonal to each ray
        wgt = 1.0 / (0.002 * np.maximum(5.0, np.linalg.norm(O - np.array([0, -8.0, 1.0]), axis=1)))
        if self.fit is not None and self.fit[0] == k0:
            x = np.r_[self.fit[1], self.fit[2], self.fit[3]]
        else:
            # init: gravity-only fit to the rays before any bounce (linear in p, v)
            pre = ts <= ts.min() + 0.25
            A, b = [], []
            for i in np.nonzero(pre)[0]:
                t = ts[i]
                M = np.hstack([Pm[i], Pm[i] * t])
                A.append(M); b.append(Pm[i] @ (O[i] - np.array([0, 0, -0.5 * G * t * t])))
            A = np.vstack(A); b = np.concatenate(b)
            sol = np.linalg.lstsq(A, b, rcond=None)[0]
            x = np.r_[sol, 0.0, 0.0, 0.0]
        uniq = np.unique(ts)
        idx = np.searchsorted(uniq, ts)
        lam = 1e-2
        prior = np.array([0, 0, 0, 0, 0, 0, 1 / 400., 1 / 400., 1 / 400.])

        def resid(X):
            out, _, _ = fly(X[:, :3], X[:, 3:6], X[:, 6:9], uniq)
            Q = out[:, idx]                                               # (N, n_rays, 3)
            r = np.einsum("nij,mnj->mni", Pm, Q - O[None]) * wgt[None, :, None]
            r = r.reshape(len(X), -1)
            return np.hstack([r, X * prior[None]])

        cost = None
        for _ in range(8):
            h = np.array([1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1.0, 1.0, 1.0])
            X = np.vstack([x] + [x + np.eye(9)[i] * h[i] for i in range(9)])
            Rr = resid(X)
            r0 = Rr[0]; c0 = float(r0 @ r0)
            J = ((Rr[1:] - r0) / h[:, None]).T
            H = J.T @ J; g = J.T @ r0
            for _try in range(4):
                dx = -np.linalg.solve(H + lam * np.diag(np.diag(H) + 1e-9), g)
                xn = x + dx
                rn = resid(xn[None])[0]; cn = float(rn @ rn)
                if cn < c0:
                    x, lam = xn, max(lam * 0.3, 1e-6)
                    break
                lam *= 10
            else:
                break
            cost = cn
            if abs(c0 - cn) < 1e-4 * c0:
                break
        r = resid(x[None])[0][:-9].reshape(-1, 3) / wgt[:, None]
        rms = float(np.sqrt(np.mean(np.sum(r * r, axis=1))))
        self.fit = (k0, x[:3], x[3:6], x[6:9], rms)
        self.n_fit = len(keys)
        return self.fit


# ---------------------------------------------------------------------------------------------- the player
class Player:
    def __init__(self, cams, lead_steps):
        self.cams = cams
        self.lead = int(lead_steps)
        self.flight = None
        self.cmd = None             # the act in effect for this ball: dict(t_c abs, pos, normal, k_e, ...)
        self.moved = None           # base goal sent for this ball
        self.n_shots = 0
        self.opp_x = 0.0
        self.log = []
        self.hit_done = None

    # ------------------------------------------------ observations
    def update(self, ob, img):
        legs = ob.get("view_leg_ids") or []
        steps = ob.get("view_steps") or []
        times = ob.get("view_times") or []
        if not legs:
            return
        cur = legs[-1]
        if self.flight is None or self.flight.leg_id != cur:
            launch = int(steps[-1] - round(times[-1] / DT))
            self.flight = Flight(cur, launch)
            self.cmd = None; self.moved = None; self.hit_done = None
        if img is None:
            return
        for (r, c, u, v) in detect(img):
            if c >= len(steps) or legs[c] != cur or times[c] <= 0.0:
                continue
            o, d = self.cams[r].ray(u, v)
            self.flight.add(int(steps[c]), r, o, d)

    # ------------------------------------------------ prediction and stroke
    def predict(self):
        f = self.flight
        if f is None:
            return None
        fit = f.solve()
        if fit is None:
            return None
        k0, p, v, w, rms = fit
        t_off = k0 * DT
        ts, P, V, W, bounces = trajectory(p, v, w, 3.0)
        return dict(k0=k0, t0=t_off, ts=ts + t_off, P=P, V=V, W=W, bounces=bounces, rms=rms, p=p, v=v, w=w)

    def choose(self, pr, k_now, base_now, latency_s):
        """The contact on the predicted flight after its bounce on our half: index into pr arrays, or None."""
        bs = [b for b in pr["bounces"] if b[3] == "bounce"]
        if not bs or any(b[3] == "net" for b in pr["bounces"]):
            return None, "no bounce"
        b0 = bs[0]
        if not (abs(b0[1]) <= COURT_X and -COURT_Y <= b0[2] < 0):
            return None, "lands out"
        tb0 = b0[0] + pr["t0"]
        tb1 = bs[1][0] + pr["t0"] if len(bs) > 1 else pr["ts"][-1]
        ts, P = pr["ts"], pr["P"]
        t_now = k_now * DT
        cands, late = [], []
        for i in range(len(ts)):
            t = ts[i]
            if t <= tb0 + 0.02 or t >= tb1 - 0.02:
                continue
            k = int(round(t / DT))
            if abs(t - k * DT) > 1e-6:
                continue
            q = P[i]
            if not (0.55 <= q[2] <= 1.4) or q[1] > -7.4 or q[1] < -15.0 or abs(q[0]) > 6.4:
                continue
            st = stance(q)
            avail = t - t_now - latency_s - self.lead * DT
            if avail < 0.12:
                continue
            need = base_time(float(np.hypot(*(st - base_now))))
            if need > avail + (0.0 if self.moved is None else 0.25):
                late.append((need - avail, i))
                continue
            cands.append(i)
        if not cands and late:
            # the base cannot get to any stance in time: try the contact it misses by the least (the controller
            # brings the base as far as it gets; a weak or missed shot is still better than none)
            return min(late)[1], "ok (base late)"
        if not cands:
            return None, "no reachable contact"
        seg = [i for i in range(len(ts)) if tb0 < ts[i] < tb1]
        apex = max(seg, key=lambda i: P[i, 2]) if seg else cands[0]
        for i in cands:
            if i >= apex and P[i, 2] <= 1.15:
                return i, "ok"
        return min(cands, key=lambda i: abs(P[i, 2] - 1.0)), "ok"

    def aim(self):
        ox = self.opp_x
        sgn = -1.0 if ox > 0.4 else (1.0 if ox < -0.4 else (1.0 if self.n_shots % 2 else -1.0))
        return np.array([sgn * 3.2, 9.8])

    def stroke(self, p_b, v_in, w_in, aim, sp=3.0):
        """Face normal for head speed sp along it so that the ball lands at aim: (n, sp, v_out) or None."""
        for _ in range(4):
            d_out = np.r_[aim - p_b[:2], 0.0]; d_out /= np.linalg.norm(d_out); d_out[2] = 0.12
            d_out /= np.linalg.norm(d_out)
            n0 = d_out - v_in / np.linalg.norm(v_in); n0 /= np.linalg.norm(n0)
            az = math.atan2(n0[1], n0[0])
            els = np.linspace(-0.25, 0.75, 21)
            outs = [contact_out(v_in, w_in, nvec(az, e), sp) for e in els]
            L, C = landings(np.tile(p_b, (len(els), 1)), np.array([o[0] for o in outs]), np.array([o[1] for o in outs]))
            ok = ~np.isnan(L[:, 0]) & (C > 0.1)
            if not ok.any():
                sp *= 0.85; continue
            e_ = np.where(ok, np.abs(L[:, 1] - aim[1]) + 0.3 * np.abs(L[:, 0] - aim[0]), np.inf)
            el = float(els[int(np.argmin(e_))])
            sol = None
            for _it in range(14):
                N3 = [nvec(az, el), nvec(az + 2e-3, el), nvec(az, el + 2e-3)]
                outs = [contact_out(v_in, w_in, n, sp) for n in N3]
                L, C = landings(np.tile(p_b, (3, 1)), np.array([o[0] for o in outs]), np.array([o[1] for o in outs]))
                if np.isnan(L).any():
                    break
                err = L[0] - aim
                if np.linalg.norm(err) < 0.08:
                    sol = (N3[0], outs[0][0], C[0], L[0])
                    break
                J = np.column_stack([(L[1] - L[0]) / 2e-3, (L[2] - L[0]) / 2e-3])
                try:
                    dx = np.clip(np.linalg.solve(J, err), -0.08, 0.08)
                except np.linalg.LinAlgError:
                    break
                az -= dx[0]; el -= dx[1]
            if sol is None or np.isnan(sol[2]) or sol[2] < 0.4:
                sp *= 0.85
                continue
            return sol[0], sp, sol[1], sol[3]
        return None

    def plan(self, pr, k_now, base_now, latency_s):
        i, why = self.choose(pr, k_now, base_now, latency_s)
        if i is None:
            return None, why
        p_b, v_in, w_in = pr["P"][i], pr["V"][i], pr["W"][i]
        r = self.stroke(p_b, v_in, w_in, self.aim())
        if r is None:
            return None, "no stroke"
        n, sp, vo, land = r
        return dict(t_c=float(pr["ts"][i]), k_c=int(round(pr["ts"][i] / DT)), p_b=p_b, pos=p_b - R * n, normal=n,
                    vel=sp * n, v_out=vo, land=land), "ok"


# ---------------------------------------------------------------------------------------------- the play loop
def play(client, log=None):
    """Play the match through `client` (observe() -> (reply, png or None), act(body) -> reply, ready(), wait(dt),
    now_k(reply, t_sent) -> the current step as a float, spec)."""
    spec = client.spec
    cams = [Cam(c) for c in spec["cameras"]]
    lead = int(spec["timing"]["act_lead_steps"])
    period = float(spec["timing"]["wall_s_per_control_step"])
    P = Player(cams, lead)
    stats = {"observe": 0, "act": 0, "move": 0, "ready": 0, "replan": 0, "mismatch": 0, "skip": 0}
    lat = [0.3]                                  # wall seconds from an observation's request to an act's arrival

    def L(x):
        if log:
            log(x)

    def review(o):
        if o.get("review_prompt"):
            client.ready()
            stats["ready"] += 1
            return True
        return False

    def send_act(plan, k_send):
        k_e = int(math.floor(k_send + 0.002 / period)) + lead
        T = round(plan["t_c"] - k_e * DT, 4)
        if not (0.0 < T <= 4.9):
            return None
        body = {"type": "act", "t": T, "pos": [float(x) for x in plan["pos"]],
                "normal": [float(x) for x in plan["normal"]], "vel": [float(x) for x in plan["vel"]]}
        r = client.act(body)
        stats["act"] += 1
        te = r.get("took_effect") or {}
        k_true = te.get("step")
        if k_true is not None and k_true != k_e:
            stats["mismatch"] += 1
        plan = dict(plan, k_e=k_e, k_true=k_true, T=T,
                    k_c_true=None if k_true is None else int(k_true + round(T / DT)))
        L({"act": body, "k_e": k_e, "k_c": plan["k_c"], "took_effect": te, "stroke": r.get("stroke"), "land_plan": plan["land"].tolist(),
           "v_out": plan["v_out"].tolist(), "p_b": plan["p_b"].tolist()})
        return plan, r

    started = client.start()
    L({"start": started.get("note")})
    home_sent = None
    while True:
        o, png, t_sent = client.observe()
        if o.get("done"):
            break
        if review(o):
            P.flight = None
            continue
        ob = o.get("observation")
        if not ob:
            client.wait(0.02)
            continue
        stats["observe"] += 1
        state = ob.get("ball_state")
        incoming = state == "coming to you" and ob.get("ball_in_play")
        base_now = np.array(ob.get("robot_base_xy", HOME), float)
        if not incoming:
            if state == "going to the opponent" and home_sent != ob.get("view_leg_ids", [None])[-1]:
                home_sent = ob.get("view_leg_ids", [None])[-1]
                if P.cmd is not None:
                    P.n_shots += 1
                r = client.act({"type": "move", "base": [0.0, -11.4]})
                stats["move"] += 1
                if r.get("done"):
                    break
                review(r)
                P.cmd = None; P.moved = None
            else:
                r = client.wait(0.03)
                if r.get("done"):
                    break
                review(r)
            continue
        img = decode(png) if png else None
        P.update(ob, img)
        f = P.flight
        span, nk = f.span()
        if nk < 3:
            continue
        k_obs = client.now_k(ob, t_sent)
        pr = P.predict()
        if pr is None:
            continue
        # where the opponent played the ball from (the flight's start, extrapolated to the launch)
        if pr["k0"] - f.launch_k < 30:
            P.opp_x = float(pr["p"][0] - pr["v"][0] * (pr["k0"] - f.launch_k) * DT) * 0.4
        k_now = client.now_k(ob, t_sent)
        plan, why = P.plan(pr, k_now, base_now, max(lat[-5:]) * 1.2 / period * DT + 0.0)
        L({"k": k_now, "span": span, "frames": nk, "rms": pr["rms"], "why": why,
           "plan": None if plan is None else {"k_c": plan["k_c"], "p_b": plan["p_b"].round(3).tolist(), "land": plan["land"].round(2).tolist()}})
        if plan is None:
            continue
        cmd = P.cmd
        lat_g = max(lat[-5:]) * DT / period                 # recent decision latency in game seconds
        left = (plan["k_c"] - k_now) * DT - lead * DT - lat_g   # swing time an act sent now would leave
        if cmd is not None:
            same = (abs(cmd["k_c"] - plan["k_c"]) <= 1 and np.linalg.norm(cmd["pos"] - plan["pos"]) < 0.06
                    and cmd.get("k_c_true") == cmd["k_c"])
            if same or left < 0.3:
                continue                                    # unchanged, or too close to the contact to re-plan
            stats["replan"] += 1
        elif span < 25 and left > 0.45:
            # not yet sure where the ball goes: only bring the base towards the stance for now
            st = stance(plan["pos"])
            if (P.moved is None or np.linalg.norm(P.moved - st) > 0.5) and np.linalg.norm(st - base_now) > 0.5:
                r = client.act({"type": "move", "base": [float(st[0]), float(st[1])]})
                stats["move"] += 1
                P.moved = st
                if r.get("done"):
                    break
                review(r)
            continue
        # early base move towards the stance (takes effect at the next step, the act only after its lead)
        st = stance(plan["pos"])
        if P.moved is None or np.linalg.norm(P.moved - st) > 0.3:
            if np.linalg.norm(st - base_now) > 0.25:
                r = client.act({"type": "move", "base": [float(st[0]), float(st[1])]})
                stats["move"] += 1
                P.moved = st
                if r.get("done"):
                    break
                if review(r):
                    continue
        k_send = client.now_k(ob, t_sent)
        lat.append((k_send - k_obs) * period + 0.05)
        res = send_act(plan, k_send)
        if res is None:
            continue
        P.cmd, r = res
        if r.get("done"):
            break
        review(r)
    return stats
