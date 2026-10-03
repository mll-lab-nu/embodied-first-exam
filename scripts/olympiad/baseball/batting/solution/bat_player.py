"""Camera-only reference batter (shared by the single-player oracle and the duel's reference player).

It uses only what the prompt documents: the camera poses and intrinsics from `spec`, the frame times of each
observation, the release point and the published ball and swing-rig models. No simulator state, no seed.

  * detection: the ball is the small bright white sphere; a pixel is a ball pixel if it is near white and differs from
    a background tile of the same camera taken while the ball was still in the pitcher's hand (the scene is static
    apart from the ball and the bat). The largest such blob near the expected place is the ball;
  * fit: the flight from the release point (known) at t = 0 under gravity, drag and Magnus lift; unknowns the release
    velocity and the spin (6 numbers), fitted to all detections in both cameras by damped Gauss-Newton on the pixel
    reprojection error;
  * swing: if the predicted crossing is a strike (or close to one with two strikes), the rig's parameters that put the
    sweet spot at the ball when the bat is near square, with the ball centre DELTA above the bat axis (a line drive);
    otherwise take the pitch.
"""
from __future__ import annotations

import base64
import io
import math
import time

import numpy as np
from PIL import Image


G = 9.81
K_D, K_L0, R_BALL, SPIN_TAU = 0.00601, 0.01718, 0.0365, 30.0
REL = (-0.50, 16.80, 1.80)
ZONE_X, ZONE_LO, ZONE_HI = 0.216, 0.46, 1.07
PIVOT_X0, PIVOT_Y, S_SS = -0.66, 0.25, 0.69
TH0, TH1 = -math.pi, -math.pi / 6
T_SQUARE = (5 * math.pi / 3 + math.pi / 6) * S_SS          # time to square = T_SQUARE / SPEED
TILE_W, TILE_H = 480, 360
# the swing recipe (contact angle, ball centre above the bat axis, swing plane, sweet-spot speed)
THETA_C, DELTA, PLANE, SPEED = 4.0, 0.022, 4.0, 34.0


# ------------------------------------------------------------------------------------------------- ball model
def c_lift(S):
    return 1.5 * S if S < 0.1 else 0.09 + 0.6 * S


def acc(v, w):
    vx, vy, vz = v
    sp = math.sqrt(vx * vx + vy * vy + vz * vz)
    a = [-K_D * sp * vx, -K_D * sp * vy, -G - K_D * sp * vz]
    wm = math.sqrt(w[0] ** 2 + w[1] ** 2 + w[2] ** 2)
    if wm > 0 and sp > 0:
        k = K_L0 * c_lift(R_BALL * wm / sp) * sp / wm
        a[0] += k * (w[1] * vz - w[2] * vy)
        a[1] += k * (w[2] * vx - w[0] * vz)
        a[2] += k * (w[0] * vy - w[1] * vx)
    return a


def rk4(p, v, w, h):
    a1 = acc(v, w)
    v2 = [v[i] + 0.5 * h * a1[i] for i in range(3)]
    a2 = acc(v2, w)
    v3 = [v[i] + 0.5 * h * a2[i] for i in range(3)]
    a3 = acc(v3, w)
    v4 = [v[i] + h * a3[i] for i in range(3)]
    a4 = acc(v4, w)
    p = [p[i] + h / 6 * (v[i] + 2 * v2[i] + 2 * v3[i] + v4[i]) for i in range(3)]
    v = [v[i] + h / 6 * (a1[i] + 2 * a2[i] + 2 * a3[i] + a4[i]) for i in range(3)]
    d = math.exp(-h / SPIN_TAU)
    return p, v, [x * d for x in w]


def positions(params, ts, h=0.01):
    """Ball centre at the (sorted or not) times ts after release, for params = (v0, w0)."""
    v, w, p = list(params[:3]), list(params[3:]), list(REL)
    order = sorted(range(len(ts)), key=lambda i: ts[i])
    out = [None] * len(ts)
    t = 0.0
    for i in order:
        while t + h <= ts[i]:
            p, v, w = rk4(p, v, w, h)
            t += h
        q, _, _ = rk4(p, v, w, ts[i] - t) if ts[i] > t else (p, v, w)
        out[i] = q
    return out


def path(params, t_end=0.9, h=0.001):
    """Dense flight samples (t, x, y, z) until the ball is 1.5 m behind the plate."""
    v, w, p = list(params[:3]), list(params[3:]), list(REL)
    t, out = 0.0, [(0.0, *REL)]
    while t < t_end and p[1] > -1.5 and p[2] > 0:
        p, v, w = rk4(p, v, w, h)
        t += h
        out.append((t, *p))
    return np.array(out)


# ------------------------------------------------------------------------------------------------- cameras
class Cam:
    def __init__(self, c):
        self.name = c["name"]
        self.pos = np.array(c["position"], float)
        self.f, self.up, self.r = (np.array(c[k], float) for k in ("forward", "up", "right"))
        self.focal = float(c["focal_px"])
        self.cx, self.cy = (float(x) for x in c["principal_point_px"])

    def project(self, P):
        d = np.asarray(P, float) - self.pos
        z = d @ self.f
        return np.array([self.cx + self.focal * (d @ self.r) / z, self.cy - self.focal * (d @ self.up) / z])


def components(mask):
    """Connected components (8-neighbourhood) of a boolean image, as arrays of (row, col); largest first."""
    pts = set(zip(*np.nonzero(mask)))
    out = []
    while pts:
        stack = [pts.pop()]
        comp = []
        while stack:
            y, x = stack.pop()
            comp.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    q = (y + dy, x + dx)
                    if q in pts:
                        pts.remove(q)
                        stack.append(q)
        out.append(np.array(comp))
    return sorted(out, key=len, reverse=True)


def decode(b64):
    return np.asarray(Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")).astype(np.int16)


def tile(img, row, col):
    return img[row * TILE_H:(row + 1) * TILE_H, col * TILE_W:(col + 1) * TILE_W]


# ------------------------------------------------------------------------------------------------- the batter
class Batter:
    def __init__(self, cameras):
        self.cams = [Cam(c) for c in cameras]          # row 0: catcher, row 1: side (spec order)
        self.bg = [None] * len(self.cams)
        self.reset()

    def reset(self):
        self.dets = {}                                   # (cam, t) -> (u, v)
        self.params = None
        self.fit_n = 0

    # --- perception
    def ingest(self, img, view_times):
        """Add the frames of one observation (decoded image, each column's time since release)."""
        for col, t in enumerate(view_times):
            if t is None:
                continue
            for row, cam in enumerate(self.cams):
                tl = tile(img, row, col)
                if t < 0:
                    self.bg[row] = tl.copy()             # the ball is still in the hand: background
                    continue
                if t < 0.025 or self.bg[row] is None or (row, round(t, 3)) in self.dets:
                    continue
                uv = self.detect(tl, row, t)
                if uv is not None:
                    self.dets[(row, round(t, 3))] = uv

    def detect(self, tl, row, t):
        """The ball's centre in a tile: a near-white blob that differs from the background, refined by the centroid
        of its whole silhouette (lit and shaded side: brighter than the background) in a small window."""
        bg = self.bg[row]
        d = np.abs(tl - bg).sum(axis=2)
        m = (tl.min(axis=2) > 185) & (d > 90)
        m[:16, :200] = False                                # the time stamp
        if not m.any():
            return None
        guess = self.guess(row, t)
        best, best_score = None, None
        for pts in components(m):
            c = pts.mean(axis=0)[::-1]
            dist = 0.0 if guess is None else float(np.linalg.norm(c - guess))
            if guess is not None and dist > 150:
                continue
            score = len(pts) - 0.05 * dist
            if best_score is None or score > best_score:
                best, best_score, best_n = c, score, len(pts)
        if best is None:
            return None
        r = int(math.ceil(math.sqrt(best_n / math.pi))) + 4
        x0, y0 = max(0, int(best[0]) - r), max(0, int(best[1]) - r)
        x1, y1 = int(best[0]) + r + 1, int(best[1]) + r + 1
        brighter = (tl[y0:y1, x0:x1].sum(axis=2) - bg[y0:y1, x0:x1].sum(axis=2)) > 40
        seed = (min(int(best[1]) - y0, brighter.shape[0] - 1), min(int(best[0]) - x0, brighter.shape[1] - 1))
        for pts in components(brighter):
            if (pts == np.array(seed)).all(axis=1).any() or len(pts) >= 0.8 * best_n:
                cy, cx = pts.mean(axis=0)
                return np.array([x0 + cx, y0 + cy]) + 0.5          # pixel centres are at index + 0.5
        return best + 0.5

    def guess(self, row, t):
        """Where the ball should be: the current fit, else a nominal pitch to the middle of the zone."""
        p = self.params if self.params is not None else self.nominal()
        try:
            return self.cams[row].project(positions(p, [t])[0])
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def nominal(speed=36.0):
        d = np.array([0.0, 0.0, 1.0]) - np.array(REL)
        d /= np.linalg.norm(d)
        return np.concatenate([d * speed + np.array([0, 0, 1.6]), np.zeros(3)])

    # --- fit
    def fit(self, spins, iters=10):
        """Fit the release velocity for each candidate spin vector (the documented pitch types' spins); keep the
        candidate with the smallest reprojection error."""
        keys = sorted(self.dets, key=lambda k: k[1])
        if len(keys) < 4:
            return None
        ts = [k[1] for k in keys]
        meas = np.array([self.dets[k] for k in keys]).ravel()
        cams = [self.cams[k[0]] for k in keys]
        best = None
        for w in spins:
            w = np.asarray(w, float)

            def resid(v):
                P = positions(np.concatenate([v, w]), ts)
                return np.concatenate([c.project(x) for c, x in zip(cams, P)]) - meas

            v = np.array(self.params[:3] if self.params is not None else self.nominal()[:3], float)
            r = resid(v)
            lam = 1e-3
            for _ in range(iters):
                J = np.stack([(resid(v + 0.01 * np.eye(3)[i]) - r) / 0.01 for i in range(3)], axis=1)
                A, g = J.T @ J, J.T @ r
                ok = False
                while lam < 1e6:
                    step = -np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-9), g)
                    rq = resid(v + step)
                    if rq @ rq < r @ r:
                        v, r, lam, ok = v + step, rq, max(lam / 3, 1e-7), True
                        break
                    lam *= 5
                if not ok or np.abs(step).max() < 1e-4:
                    break
            cost = float(r @ r)
            if best is None or cost < best[0]:
                best = (cost, np.concatenate([v, w]))
        self.params, self.fit_n = best[1], len(keys)
        self.rms_px = float(math.sqrt(best[0] / len(meas)))
        return self.params

    # --- the swing
    def crossing(self):
        """(t, x, z) where the predicted ball centre crosses y = 0."""
        P = path(self.params)
        idx = np.nonzero(P[:, 2] <= 0.0)[0]
        if not len(idx):
            return None
        j = int(idx[0])
        a, b = P[j - 1], P[j]
        f = a[2] / (a[2] - b[2])
        return tuple(a[[0, 1, 3]] + f * (b[[0, 1, 3]] - a[[0, 1, 3]]))

    def swing(self, strikes=0):
        """The command for this pitch: None (take) or dict(start, plane, height, speed, reach) with the swing start in
        seconds since release."""
        c = self.crossing()
        if c is None:
            return None
        _, x, z = c
        m = -0.03 if strikes == 2 else 0.0                     # with two strikes, protect the edges
        if not (abs(x) <= ZONE_X + R_BALL - m and ZONE_LO - R_BALL + m <= z <= ZONE_HI + R_BALL - m):
            return None
        return self.geometry()

    def geometry(self, theta_c=THETA_C, delta=DELTA, plane=PLANE, speed=SPEED):
        P = path(self.params)
        a = math.radians(plane)
        ca, sa = math.cos(a), math.sin(a)
        th = math.radians(theta_c)
        px = PIVOT_X0
        # angle of the ball about the pivot: x along the bat at square, e2 = (0, cos a, sin a)
        for _ in range(6):
            ang = np.arctan2((P[:, 2] - PIVOT_Y) * ca, P[:, 1] - px)
            j = int(np.argmax(ang <= th)) if (ang <= th).any() else None
            if j is None or j == 0:  # noqa
                return None
            f = (ang[j - 1] - th) / (ang[j - 1] - ang[j])
            tc, bx, by, bz = P[j - 1] + f * (P[j] - P[j - 1])
            H = bz - (delta + sa * (by - PIVOT_Y)) / ca
            e2 = ca * (by - PIVOT_Y) + sa * (bz - H)
            px_new = bx - (S_SS - math.sin(th) * e2) / math.cos(th)
            px_new = min(max(px_new, PIVOT_X0 - 0.2), PIVOT_X0 + 0.2)
            done = abs(px_new - px) < 1e-5
            px = px_new
            if done:
                break
        w = speed / S_SS
        tau1 = 2 * (TH1 - TH0) / w
        start = tc - (tau1 + (th - TH1) / w)
        if not (0.30 <= H <= 1.40):
            return None
        return {"start": float(start), "plane": plane, "height": round(float(H), 4), "speed": speed,
                "reach": round(float(px - PIVOT_X0), 4)}


# ------------------------------------------------------------------------------------------------- live play
DT = 0.01


class Clock:
    """Where the world is now: a reference state (step index, its phase, time since release) and the wall time when
    it was reported; the world advances one step per `period` of wall time."""

    def __init__(self, period):
        self.period = period
        self.set(0, 0.5, 0.0)

    def set(self, k, phase, t_rel):
        self.k, self.phase, self.t_rel, self.mono = k, phase, t_rel, time.monotonic()

    def predict(self, lead_s=0.002):
        """(step, time since release) at which a command sent now takes effect."""
        k_cont = self.k + self.phase + (time.monotonic() - self.mono + lead_s) / self.period
        k = int(math.floor(k_cont))
        return k, self.t_rel + (k - self.k) * DT


def ended(r):
    return bool(r.get("done") or r.get("review_prompt") or r.get("error"))


def bat_pitch(api, B, spins, period, log=lambda **kw: None, t_fit=0.09, t_act=0.18):
    """Bat one pitch live: observe, fit, act (and refine) until the pitch is over. api.observe() returns (reply, the
    observation with the image as base64), api.act(body) and api.wait(dt) the service's replies. Returns the reply
    that ended the pitch. period = wall seconds per control step."""
    B.reset()
    clock = Clock(period)
    sent = None
    while True:
        r, ob = api.observe()
        if ob is None or ended(r):
            return r
        B.ingest(decode(ob.pop("image_png_b64")), ob["view_times"])
        t_now = ob.get("t_since_release")
        if t_now is None:                                   # the windup: keep watching
            continue
        strikes = int((ob.get("count") or {}).get("strikes", 0))
        k_reply = int(round(ob["t_sim_at_reply"] / DT))
        obs_cost = max(DT, (k_reply - int(ob["step"])) * DT)  # game time one observation costs
        clock.set(k_reply, 0.5, t_now + (k_reply - int(ob["step"])) * DT)
        if clock.t_rel > 0.6 or (sent and sent["start"] <= clock.t_rel):
            break                                           # the swing has started, or the ball is past the plate
        if len(B.dets) < 6 or t_now < t_fit:
            continue
        B.fit(spins)
        sw = B.swing(strikes)
        if sw is None:                                      # a ball (or out of reach): take it
            if t_now >= t_act or clock.t_rel + 2 * obs_cost > 0.25:
                if sent:
                    api.act({"type": "none"})
                log(take=True, t=t_now, crossing=B.crossing(), rms=B.rms_px)
                break
            continue
        urgent = sw["start"] - clock.t_rel < 3 * obs_cost + 0.03
        if sent is None and not (t_now >= t_act or urgent):
            continue
        if sent is None or abs(sw["start"] - sent["start"]) >= 0.002:
            tsq = T_SQUARE / sw["speed"]
            for attempt in range(6):
                k_eff, t_eff = clock.predict()
                if sw["start"] <= t_eff + 1e-6:
                    break
                T = sw["start"] + tsq - t_eff
                rr = api.act({"type": "swing", "t": round(T, 5), "plane": sw["plane"], "height": sw["height"],
                              "speed": sw["speed"], "reach": sw["reach"]})
                info = rr.get("swing") or {}
                log(act=dict(sw, T=T, attempt=attempt, took_effect=rr.get("took_effect"), swing=info,
                             rms=B.rms_px, n=B.fit_n))
                if ended(rr) or "now" not in rr:
                    return rr if ended(rr) else bat_finish(api)
                nw = rr["now"]
                if nw.get("t_since_release") is not None:
                    clock.set(int(nw["step"]), float(nw.get("step_phase", 0.5)), float(nw["t_since_release"]))
                if not info.get("accepted"):
                    break
                sent = dict(sw)
                got = info.get("swing_start_t_since_release")
                if got is None or info.get("swing_started") or abs(got - sw["start"]) < 0.0015:
                    break
        if urgent:
            break
    return bat_finish(api)


def bat_finish(api):
    while True:                                             # let the pitch finish
        r = api.wait(1.0)
        if ended(r):
            return r
