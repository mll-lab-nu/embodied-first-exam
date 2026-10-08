"""airhockey's built-in players (same action interface as a model's program; core/client.py plays them over HTTP).

  Reference  the camera-only reference player (rewritten 2026-10-07, review item B13; the legacy camera_player.py
             rarely scored: 0.05 goals per game against itself). It finds the red puck and the opponent's mallet by
             colour in its camera image (the camera definition of /spec) and fits the puck's velocity over the recent
             images. Defence: on the defence line where the puck will cross it (side-rail bounces predicted with the
             rails' restitution), at the near post when the puck will slide along the end rail towards the mouth,
             and a puck deep beside the own goal is pushed out from the goal side, never across the mouth. Attack:
             a puck in the own half is struck hard: wind-up behind it on the chosen line (straight or off a rail, at
             the part of the goal the opponent's mallet needs longest to reach), then a drive through it towards a
             target far beyond, so the mallet hits at the path's top speed.
  Random     uniform random targets in the own workspace (generic tests: no draw, whitelist, determinism).
No simulator import: this file runs in the player's container as the task's oracle (numpy + pillow only)."""
from __future__ import annotations

import base64
import io
import math

import numpy as np

X_NEAR, X_FAR, Y_MAX, REACH, BASE_X = .05, .92, .47, 1.45, 1.51     # the public workspace (game spec: workspace)
PUCK_R, MALLET_R = .03165, .04815                    # game spec: geometry
CONTACT = PUCK_R + MALLET_R
END = 1.948 / 2                                     # the end line (half length)
RAIL = .519 - PUCK_R                                # the puck centre's reach across the table (half width - radius)
MOUTH = .125 - PUCK_R                               # the puck centre scores within |y| < MOUTH
E_RAIL = .8                                         # the rails return about 80 % of the speed across them (spec)
GUARD = .80                                         # the defence line (local u)
WIND = .26                                          # the wind-up distance behind the puck before a strike
TOL = .07                                           # line-up tolerance (rad) before a strike
MALLET_Z = .005                                     # the mallet blob's centroid back-projects best onto this height


def image_of(view):
    """The seat's camera tile of the observation as an H x W x 3 float array (None without an image)."""
    from PIL import Image
    obs = view.get("observation") or {}
    if not obs.get("image_png_b64"):
        return None
    img = np.asarray(Image.open(io.BytesIO(base64.b64decode(obs["image_png_b64"]))).convert("RGB")).astype(float)
    tile = next((t for t in obs.get("tiles") or [] if t.get("camera") == "front"), None)
    if tile:
        img = img[tile["y"]:tile["y"] + tile["height"], tile["x"]:tile["x"] + tile["width"]]
    return img


def locate(a, cam, seat, what="puck"):
    """The table-plane position of the puck (red) or of the opponent's mallet top (B green, A blue): the centroid of
    the colour mask back-projected through the camera definition (pinhole, pixel centres at i + 0.5)."""
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    if what == "puck":
        mask = (R > 150) & (R > 2.5 * G) & (R > 2.5 * B)
    elif seat == "A":
        mask = (G > 100) & (G > 2 * R) & (G > 1.5 * B)      # B's green mallet
    else:
        mask = (B > 150) & (B > 2 * R) & (B > 1.3 * G)      # A's blue mallet
    rows, cols = np.nonzero(mask)
    if len(rows) < 3:
        return None
    pos, look = np.array(cam["pos"], float), np.array(cam["lookat"], float)
    fwd = (look - pos) / np.linalg.norm(look - pos)
    right = np.cross(fwd, np.array(cam.get("up", [0, 0, 1]), float))
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    f = cam["focal_px"]
    cx, cy = cam["principal_point_px"]
    ray = fwd + right * ((float(cols.mean()) + .5 - cx) / f) + up * ((cy - float(rows.mean()) - .5) / f)
    z = .012 if what == "puck" else MALLET_Z                # the puck's centre plane / the mallet blob (calibrated)
    return (pos + ray * ((z - pos[2]) / ray[2]))[:2]


def clip(u, v):
    """Local coordinates (u > 0 into the own half): the nearest workspace point."""
    u, v = min(max(u, X_NEAR), X_FAR), min(max(v, -Y_MAX), Y_MAX)
    d = math.hypot(BASE_X - u, v)
    if d > REACH - 1e-3:
        u, v = BASE_X - (BASE_X - u) * (REACH - 1e-3) / d, v * (REACH - 1e-3) / d
    return u, v


def inside(u, v):
    return X_NEAR <= u <= X_FAR and abs(v) <= Y_MAX and math.hypot(BASE_X - u, v) <= REACH


def seg_dist(q, a, b):
    ab = b - a
    t = float(np.clip((q - a) @ ab / max(1e-9, ab @ ab), 0, 1))
    return float(np.linalg.norm(q - (a + t * ab)))


def cross(p, w, line, bounces=4):
    """Where (v), after how long (s, at constant speed) and with what velocity across (wv) a puck at p moving with w
    (local coordinates) crosses u = line, bouncing off the side rails (the speed across a rail scales by E_RAIL);
    None if it moves away."""
    pu, pv = float(p[0]), float(p[1])
    wu, wv = float(w[0]), float(w[1])
    if (line - pu) * wu <= 1e-9:
        return None
    t = 0.
    for _ in range(bounces + 1):
        tu = (line - pu) / wu
        tv = (RAIL - pv) / wv if wv > 1e-9 else ((-RAIL - pv) / wv if wv < -1e-9 else math.inf)
        if tu <= tv:
            return pv + wv * tu, t + tu, wv
        pu, pv, t, wv = pu + wu * tv, pv + wv * tv, t + tv, -E_RAIL * wv
    return None


def shots(p, mouth=MOUTH):
    """Candidate strikes of a puck at p (local): (unit direction, path points), straight at the other goal or off
    one side rail (aimed with the rail's restitution), at five points of the goal mouth."""
    out = []
    x = END + p[0]                                           # the distance to the other end line along -u
    for gy in (-.7 * mouth, -.35 * mouth, 0., .35 * mouth, .7 * mouth):
        out.append((0, gy, np.array([-x, gy - p[1]]), [p, np.array([-END, gy])]))
        for b in (1, -1):
            k = ((b * RAIL - p[1]) + (b * RAIL - gy) / E_RAIL) / x
            if abs(k) < 1e-6:
                continue
            x1 = (b * RAIL - p[1]) / k
            if not 0 < x1 < x:
                continue
            out.append((b, gy, np.array([-1., k]), [p, np.array([p[0] - x1, b * RAIL]), np.array([-END, gy])]))
    return [(b, gy, d / np.linalg.norm(d), path) for b, gy, d, path in out]


def defender_time(dist):
    """Seconds an opponent's mallet needs to move `dist` (a 10 m/s^2 path from rest, plus a reaction)."""
    return .12 + 2 * math.sqrt(max(dist, 0.) / 10.)


def choose(p, opp, speed=1.8, wind=WIND, mouth=MOUTH):
    """The strike direction for a puck at p: the candidate the opponent's mallet `opp` (local) is least likely to
    reach in time, among those whose wind-up point behind the puck lies in the workspace."""
    best = None
    for b, gy, d, path in shots(p, mouth):
        w = p - d * wind
        if not inside(*w):
            continue
        if opp is None:
            score = -.02 * abs(b) + .1 * abs(gy)
        else:
            clear, s = 9., 0.
            for i in range(len(path) - 1):
                a_, b_ = path[i], path[i + 1]
                seg = float(np.linalg.norm(b_ - a_))
                ab = b_ - a_
                tt = float(np.clip((opp - a_) @ ab / max(1e-9, ab @ ab), 0, 1))
                dd = float(np.linalg.norm(opp - (a_ + tt * ab)))
                if dd < clear:
                    clear, s_at = dd, s + tt * seg
                s += seg
            t_puck = s_at / (speed * (E_RAIL if b and s_at > float(np.linalg.norm(path[1] - path[0])) else 1.))
            score = min(defender_time(clear - CONTACT + .01) - t_puck, .3) - .03 * abs(b)
        if best is None or score > best[0]:
            best = (score, d)
    return None if best is None else best[1]


class Reference:
    """Works in local coordinates: u = own * x (own half u > 0, own goal at u = +END), v = y.

    Defence: while the puck is in the other half or coming at the own goal, the mallet stands on the defence line
    (u = GUARD) where the puck will cross it (the side-rail bounces predicted with the rails' restitution), or, while
    the puck goes away or rests over there, on the line from the puck to the goal centre. Attack: a puck resting or
    moving slowly in the own half is struck hard: the mallet winds up WIND behind the puck on the chosen line
    (choose(): straight or off a rail, where the opponent's mallet has to travel farthest in the time the puck takes),
    then drives through it towards a target far beyond, so it reaches the path's top speed at the impact."""

    def __init__(self, spec, seat, seed=0):
        self.seat, self.own = seat, (-1. if seat == "A" else 1.)
        self.cam = next(c for c in spec["cameras"] if c["name"] == "front")
        self.mouth = float((spec.get("geometry") or {}).get("goal_width_m", 2 * (MOUTH + PUCK_R))) / 2 - PUCK_R
        self.rally = None
        self.reset()

    def reset(self):
        self.until, self.stroke, self.hist, self.w, self.p, self.t_side = -1., None, [], np.zeros(2), None, None
        self.deep_stroke = False

    def world(self, u, v):
        u, v = clip(u, v)
        return [round(self.own * u, 4), round(v, 4)]

    def track(self, p, t):
        """The puck's velocity: a straight-line fit over the recent images, restarted at a hit or a rail bounce
        (an image off the fitted line by more than 1.2 cm)."""
        if self.hist and t <= self.hist[-1][0] + 1e-6:
            return
        if len(self.hist) >= 2:
            t0, p0 = self.hist[-1]
            if float(np.linalg.norm(p0 + self.w * (t - t0) - p)) > .012:
                self.hist = self.hist[-1:]
        self.hist = (self.hist + [(t, p.copy())])[-5:]
        if len(self.hist) >= 2:
            ts = np.array([h[0] for h in self.hist])
            ps = np.array([h[1] for h in self.hist])
            tc = ts - ts.mean()
            self.w = (tc[:, None] * (ps - ps.mean(0))).sum(0) / max(1e-9, float((tc * tc).sum()))
        else:
            self.w = np.zeros(2)

    def guard(self, p, w):
        c = cross(p, w, GUARD) if w[0] > .05 else None
        e = cross(p, w, END) if w[0] > .05 else None
        if e is not None and self.mouth - .01 < abs(e[0]) < .34 and e[0] * e[2] < 0 and e[1] < 3.:
            # it will hit the end rail beside the goal and slide on towards the mouth: block the near post
            return self.world(X_FAR - .02, float(np.sign(e[0])) * .05)
        if c is not None and c[1] < 3.:
            y = c[0]
        else:                                            # between the puck and the goal centre
            y = p[1] * (END - GUARD) / max(.2, END - p[0])
        return self.world(GUARD, float(np.clip(y, -.22, .22)))

    def clear_deep(self, p, w, m, t):
        """A puck deep beside the own goal: block the near post while it slides towards the goal mouth; else get to
        its goal side (round the front, never through it) and push it outwards, away from the mouth."""
        sg = 1. if p[1] >= 0 else -1.                   # the outer side of the puck
        if w[1] * sg < -.15 and abs(p[1]) > .1:          # sliding along the end rail towards the mouth
            return self.world(X_FAR, sg * .05)
        stage = np.array([min(X_FAR, p[0] + .04), p[1] - sg * .075])
        if float(np.linalg.norm(m - stage)) < .03:
            q = p - stage
            self.stroke, self.until = self.world(*(p + q / float(np.linalg.norm(q)) * .25)), t + .3
            return self.stroke
        if (m[1] - p[1]) * sg < -.05 and abs(m[0] - p[0]) < .1:      # on the goal side: close in
            return self.world(*stage)
        beside = np.array([p[0], p[1] - sg * .095])
        if seg_dist(p, m, beside) > CONTACT + .015:
            return self.world(*beside)
        return self.world(p[0] - .13, p[1] - sg * .095)             # first in front of the puck

    def decide(self, puck, own_xyz, t, opp=None):
        m = np.array([self.own * own_xyz[0], own_xyz[1]])
        if puck is None:
            if self.p is None or not self.hist or t > self.hist[-1][0] + .25:
                return self.world(GUARD, 0.)
            p = self.p + self.w * (t - self.hist[-1][0])
        else:
            p = np.array([self.own * puck[0], puck[1]])
            self.track(p, t)
            self.p = p
        w = self.w
        o = None if opp is None else np.array([self.own * opp[0], opp[1]])
        if p[0] > PUCK_R:                                # seven-second clock: time the puck has spent in the own half
            self.t_side = t if self.t_side is None else self.t_side
        else:
            self.t_side = None
        deep = p[0] > .86 and abs(p[1]) < .26 and w[0] > -.6
        if t < self.until:                               # a stroke in progress: drive through until the puck has gone
            if w[0] < -.4 or p[0] < 0 or (deep and not self.deep_stroke):
                self.until = -1.
            else:
                return self.stroke
        self.deep_stroke = deep
        if deep:                                         # deep beside the own goal
            return self.clear_deep(p + w * .05, w, m, t)
        if p[0] < -.02 or w[0] > .35 or (w[0] < -.3 and p[0] < .3) or (w[0] > .12 and m[0] < p[0] + .05):
            return self.guard(p, w)                      # (also: coming at the goal while the mallet is not behind it)
        pp = p + w * .1                                  # where the puck will be when the mallet gets there
        hurry = self.t_side is not None and t - self.t_side > 4.
        d, wind = None, WIND
        for wind in (WIND, .2, .14):
            d = choose(pp, o, wind=wind, mouth=self.mouth)
            if d is not None:
                break
        if d is None:                                    # no line-up possible (a corner): push it out past the mallet
            q = pp - m
            q = q / max(1e-9, float(np.linalg.norm(q)))
            self.stroke, self.until = self.world(*(pp + q * .25)), t + .3
            return self.stroke
        wpt = pp - d * wind
        rel = pp - m
        dist = float(np.linalg.norm(rel))
        tol = TOL * (2.5 if hurry else 1.)
        if (float(np.linalg.norm(m - wpt)) < .06 or hurry) and CONTACT + .02 < dist < wind + .12 \
                and float(rel @ d) / dist > math.cos(tol):      # lined up: drive through the puck
            reach = .1
            for L in (.5, .4, .3, .2):
                if inside(*(pp + d * L)):
                    reach = L
                    break
            self.stroke = self.world(*(pp + d * reach))
            self.until = t + .35
            return self.stroke
        if seg_dist(pp, m, wpt) < CONTACT + .03 and float((m - pp) @ d) > -wind + .06:
            n = np.array([-d[1], d[0]])                  # the way to the wind-up point runs through the puck:
            s = 1. if float(n @ (m - pp)) >= 0 else -1.  # first beside it, on the mallet's side
            q = pp + n * s * .17
            if not inside(*q):
                q = pp - d * .12 + n * s * .14
            if not inside(*q):
                q = pp - d * .12 - n * s * .14
            return self.world(*q)
        return self.world(*wpt)

    def act(self, view):
        st = view.get("state") or {}
        if st.get("rally") != self.rally:                # a new rally
            self.rally = st.get("rally")
            self.reset()
        img = image_of(view)
        if img is None or "own" not in st:
            return None
        puck = locate(img, self.cam, self.seat)
        opp = locate(img, self.cam, self.seat, "opponent")
        x, y = self.decide(puck, st["own"]["mallet_xyz"], float(st.get("t_play", st.get("t_sim", 0.0))), opp)
        return {"type": "target", "x": x, "y": y}

    def review(self, reply):
        self.reset()
        return "A goal, foul or dead puck ended the rally.", "Guard the crossing point; wind up and strike hard at the open side."


class Random:
    def __init__(self, spec, seat, seed=0):
        self.own = -1. if seat == "A" else 1.
        self.g = np.random.default_rng(int(seed) * 7919 + 17)        # by seed, not by seat

    def act(self, view):
        if self.g.random() < .2:
            return {"type": "none"}
        u, v = clip(float(self.g.uniform(X_NEAR, X_FAR)), float(self.g.uniform(-Y_MAX, Y_MAX)))
        return {"type": "target", "x": round(self.own * u, 4), "y": round(v, 4)}
