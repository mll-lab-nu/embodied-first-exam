"""curling's built-in players (the same action interface as a model's program; core/client.py plays them over HTTP).

  Reference  the legacy scripted camera-only player (Season 1's oracle): stones from the top-down house camera image
             (the house tile of the observation PNG), its documented pose and intrinsics (/spec cameras), and the ice
             model and sheet geometry of the rules. No simulator, no hidden state. It is also the task's oracle.
  Random     uniform random valid throws (the generic tests: no draw, whitelist, determinism).

perceive(): every stone has a grey granite body around its coloured top, so the grey pixels (filled) give one disc per
stone; its centre is back-projected to the body's top face, and the colour at the centre says whose stone it is.
plan(): a few candidate shots (takeouts of the opponent's stones in or near the house, draws to free spots around the
button, with both spins), each checked for a clear path along its curling trajectory; it takes out the opponent's
shot stone when it can, else draws for the button. During the first five stones of an end (the free guard zone rule)
it never plays through guards (curling-4: a takeout's path is checked against the protected guards all the way to
its target; the Season-1 check stopped 3-5 m short of it, so firm hits went through guards in front of the house). Since curling-3 it plays the hammer and the guards first (tactics(), from the
observation's score, end, hammer and stones left): last stone: draw for one more or throw it away to keep its points,
blank an empty house when the hammer is worth more than a point (wp(), the match's win chance), hit and stay on
their shot stone; with the hammer: keep the end clean (their stones in the house hit, their centre guards peeled once
the free guard zone allows; curling-4: while it holds and none of mine is in the house, come around their centre
guard into the house; corner guards while it holds and the house is empty); without it and trailing: centre guards
in the free guard zone, draws behind them.
aim(): the documented FCV1 single-stone law (deceleration, curl, spin decay) integrated once from 4 m/s; a slower
release follows the tail of that path, rotated to its heading, so a release speed and angle that pass a point at a
given speed are found by a search along it.
The ice (curling-3): the deceleration is kd times the documented law, kd hidden in a documented range. Scaling the
deceleration by kd scales the distance travelled between two speeds and the heading turned between them by 1/kd
(the curl rate depends on the speed only), so the path for any kd is the documented one transformed (Path.scaled).
IceFit learns kd online from the player's own throws: a throw that touched nothing rests where the ice put it, so kd is
the scale under which that release stops at the distance seen in the house camera (the reply image of the throw, taken
before the next stone; without it, the next observation if no later stone touched anything); the estimate is the mean
of these fits with the documented ice (kd = 1) as one prior observation.
No simulator import: this file runs in the player's container as the task's oracle (numpy and pillow only).
"""
import base64
import io
import math

import numpy as np
from PIL import Image

R = 0.145
TEE_Y, HOG_Y, BACK_Y, HOUSE_R, HALF_W = 38.405, 32.004, 40.234, 1.829, 2.375
BODY_TOP_Z = 0.107
TOP_R = 0.105                       # the coloured top's radius (inside the grey ring)
V_MAX = 4.0
DT = 0.001
G = 9.80665


def _accel(v):
    return (0.00200985 / (v + 0.06385782) + 0.00626286) * G


class Path:
    """A stone released at V_MAX along +y with the given spin, every step (the documented ice law, kd = 1); scaled(kd)
    gives the path on the ice of deceleration scale kd."""

    def __init__(self, spin: str):
        if spin is None:                               # an empty shell for scaled()
            return
        w = math.pi / 2 if spin == "ccw" else -math.pi / 2
        x = y = 0.0
        vx, vy = 0.0, V_MAX
        S, X, Y, H = [], [], [], []
        while True:
            v = math.hypot(vx, vy)
            S.append(v); X.append(x); Y.append(y); H.append(math.atan2(vx, vy))
            if v <= 0.0:
                break
            nv = v - _accel(v) * DT
            if nv <= 0.0:
                vx = vy = 0.0
            else:
                ex, ey = vx / v, vy / v
                yaw = (1.0 if w > 0 else -1.0) * 0.00820 * v ** -0.8 * DT
                lon, tr = nv * math.cos(yaw), nv * math.sin(yaw)
                vx, vy = lon * ex - tr * ey, lon * ey + tr * ex
            dw = 0.025 / max(v, 0.001) * DT
            w = w - dw * (1.0 if w > 0 else -1.0) if abs(w) > dw else w
            x += vx * DT; y += vy * DT
        # ascending speed: index 0 = at rest
        self.S, self.X, self.Y, self.H = (np.array(a[::-1]) for a in (S, X, Y, H))

    def scaled(self, kd: float) -> "Path":
        """The path on the ice of deceleration scale kd: between two speeds the stone travels 1/kd as far and its
        heading turns 1/kd as much (exact for the continuous law; the steps' own error is a few mm)."""
        if kd == 1.0:
            return self
        S, X, Y, H = self.S[::-1], self.X[::-1], self.Y[::-1], self.H[::-1]      # from the release at V_MAX
        dx, dy = np.diff(X), np.diff(Y)
        ds = np.hypot(dx, dy) / kd
        ph = np.arctan2(dx, dy) / kd                                           # each step's direction, turned 1/kd
        p = Path(None)
        Xs = np.concatenate([[0.0], np.cumsum(ds * np.sin(ph))])
        Ys = np.concatenate([[0.0], np.cumsum(ds * np.cos(ph))])
        p.S, p.X, p.Y, p.H = S[::-1].copy(), Xs[::-1].copy(), Ys[::-1].copy(), (H / kd)[::-1].copy()
        return p

    def rest(self, v0, angle_deg):
        """Where a lone stone released at (v0, angle) comes to rest."""
        k = min(int(np.searchsorted(self.S, v0)), len(self.S) - 1)
        lx, ly = self._local(k, 0)
        a = math.radians(angle_deg)
        return lx * math.cos(a) + ly * math.sin(a), -lx * math.sin(a) + ly * math.cos(a)

    def _local(self, k, j):
        """Displacement from state k to state j (speed index j <= k), in the frame where the heading at k is +y."""
        dx, dy = self.X[j] - self.X[k], self.Y[j] - self.Y[k]
        c, s = math.cos(self.H[k]), math.sin(self.H[k])
        return dx * c - dy * s, dx * s + dy * c

    def aim(self, tx, ty, v_at=0.0):
        """(release speed, angle deg) so that the stone passes (tx, ty) at speed v_at (0: comes to rest there)."""
        j = int(np.searchsorted(self.S, v_at)) if v_at > 0 else 0
        r = math.hypot(tx, ty)
        lo, hi = j + 1, len(self.S) - 1
        if math.hypot(*self._local(hi, j)) < r:
            return None
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if math.hypot(*self._local(mid, j)) < r:
                lo = mid
            else:
                hi = mid
        dx, dy = self._local(hi, j)
        return float(self.S[hi]), math.degrees(math.atan2(tx, ty) - math.atan2(dx, dy))

    def points(self, v0, angle_deg, v_end=0.0, every=50):
        """World points of the throw (release v0, angle) until its speed drops to v_end."""
        k = int(np.searchsorted(self.S, v0))
        j = int(np.searchsorted(self.S, v_end)) if v_end > 0 else 0
        idx = np.arange(k, j - 1, -every)
        dx, dy = self.X[idx] - self.X[k], self.Y[idx] - self.Y[k]
        c, s = math.cos(self.H[k]), math.sin(self.H[k])
        lx, ly = dx * c - dy * s, dx * s + dy * c
        a = math.radians(angle_deg)
        return np.stack([lx * math.cos(a) + ly * math.sin(a), -lx * math.sin(a) + ly * math.cos(a)], 1)


_PATHS = {}
KD_RANGE = (0.97, 1.03)              # the documented range of the ice's deceleration scale ([spec] ice)


def path(spin, kd=1.0):
    """The path of `spin` on the ice of deceleration scale kd (the documented law integrated once, then scaled)."""
    key = (spin, round(float(kd), 5))
    if key not in _PATHS:
        if (spin, 1.0) not in _PATHS:
            _PATHS[(spin, 1.0)] = Path(spin)
        if len(_PATHS) > 12:
            for k in [k for k in _PATHS if k[1] != 1.0][:4]:
                _PATHS.pop(k)
        _PATHS[key] = _PATHS[(spin, 1.0)].scaled(key[1])
    return _PATHS[key]


_path = path


class IceFit:
    """The ice's deceleration scale kd, learnt from the player's own uncontacted throws: each one gives the kd under
    which its release stops at the distance (from the hack) where it was seen at rest; kd = the mean of those fits
    and of one prior fit at the documented kd = 1."""

    def __init__(self, prior_weight=1.0):
        self.fits = []
        self.n0 = prior_weight
        self.kd = 1.0

    @staticmethod
    def fit(v0, angle_deg, spin, rest):
        """kd under which (v0, angle, spin) comes to rest at the distance of `rest` from the hack (None: no kd in
        0.85-1.15 does)."""
        target = math.hypot(rest[0], rest[1])
        base = path(spin, 1.0)

        def dist(kd):
            return math.hypot(*base.scaled(kd).rest(v0, angle_deg))

        lo, hi = 0.85, 1.15
        if not dist(hi) <= target <= dist(lo):
            return None
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            if dist(mid) > target:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    def observe(self, v0, angle_deg, spin, rest):
        k = self.fit(v0, angle_deg, spin, rest)
        if k is None:
            return None
        self.fits.append(k)
        self.kd = round((self.n0 * 1.0 + sum(self.fits)) / (self.n0 + len(self.fits)), 5)
        return k


def house_image(obs: dict) -> np.ndarray:
    """The house camera's tile of the observation PNG (RGB, float)."""
    img = np.asarray(Image.open(io.BytesIO(base64.b64decode(obs["image_png_b64"]))).convert("RGB"), dtype=float)
    t = next(t for t in obs["tiles"] if t["camera"] == "house")
    return img[t["y"]:t["y"] + t["height"], t["x"]:t["x"] + t["width"]]


def _correlate(mask: np.ndarray, ker: np.ndarray) -> np.ndarray:
    """sum over the kernel window centred on each pixel (FFT correlation; same size as mask)."""
    H, W = mask.shape
    kh, kw = ker.shape
    sh = (H + kh - 1, W + kw - 1)
    full = np.fft.irfft2(np.fft.rfft2(mask, sh) * np.fft.rfft2(ker[::-1, ::-1], sh), sh)
    return full[kh // 2:kh // 2 + H, kw // 2:kw // 2 + W]


def perceive(img: np.ndarray, cam: dict):
    """[(x, y, team)] with team 'yellow' or 'red' (img: the house camera image, RGB float). Seen from above, every
    stone is a grey granite ring (radius 0.105-0.145 m) around its coloured top: the ring is found by correlating the
    grey pixels with a ring of the stone's size in pixels, refined to the centroid of its grey pixels, back-projected
    to the body's top face; the colour inside says whose stone it is. numpy only."""
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    f = cam["focal_px"]; cx, cy = cam["principal_point_px"]; cz = cam["pos"][2]; cy_w = cam["pos"][1]
    depth = cz - BODY_TOP_Z
    rp, ri = f * R / depth, f * TOP_R / depth
    grey = (np.abs(r - g) < 12) & (b - r > 3) & (b - r < 30) & (r > 140) & (r < 225)
    H, W = grey.shape
    x_of_u = (np.arange(W)[None, :] + 0.5 - cx) * depth / f
    grey &= np.abs(x_of_u) < HALF_W - 0.02
    n = int(math.ceil(rp)) + 1
    kv, ku = np.mgrid[-n:n + 1, -n:n + 1]
    kd = np.hypot(kv, ku)
    ring = ((kd >= ri + 0.5) & (kd <= rp - 0.5)).astype(float)
    resp = _correlate(grey.astype(float), ring) / ring.sum()
    vv, uu = np.mgrid[0:H, 0:W]
    centres = []
    while len(centres) < 2 * 5 + 2:
        k = int(np.argmax(resp))
        a, c = divmod(k, W)
        if resp[a, c] < 0.5:
            break
        centres.append([float(a), float(c)])
        v0, v1, u0, u1 = max(a - 2 * n, 0), min(a + 2 * n + 1, H), max(c - 2 * n, 0), min(c + 2 * n + 1, W)
        near = (vv[v0:v1, u0:u1] - a) ** 2 + (uu[v0:v1, u0:u1] - c) ** 2 < (1.5 * rp) ** 2
        resp[v0:v1, u0:u1][near] = 0.0
    for _ in range(2):                    # refine: the centroid of the ring's grey pixels nearer to it than to others
        new = []
        for i, (a, c) in enumerate(centres):
            v0, v1, u0, u1 = int(a - rp - 3), int(a + rp + 4), int(c - rp - 3), int(c + rp + 4)
            gv, gu = np.mgrid[max(v0, 0):min(v1, H), max(u0, 0):min(u1, W)]
            d2 = (gv - a) ** 2 + (gu - c) ** 2
            sel = grey[gv, gu] & (d2 <= (rp + 1.5) ** 2) & (d2 >= (ri - 1.5) ** 2)
            for j, (p, q) in enumerate(centres):
                if j != i:
                    sel &= d2 < (gv - p) ** 2 + (gu - q) ** 2
            new.append([float(gv[sel].mean()), float(gu[sel].mean())] if sel.sum() > 30 else [a, c])
        centres = new
    out = []
    for a, c in centres:
        gv, gu = np.mgrid[int(a - 0.5 * rp):int(a + 0.5 * rp) + 1, int(c - 0.5 * rp):int(c + 0.5 * rp) + 1]
        gv, gu = np.clip(gv, 0, H - 1), np.clip(gu, 0, W - 1)
        med = np.median(img[gv, gu].reshape(-1, 3), axis=0)
        team = "yellow" if med[1] > 170 and med[2] < 150 else "red" if med[0] > 170 and med[1] < 150 else None
        if team is None:
            continue
        x = (c + 0.5 - cx) * depth / f
        y = cy_w - (a + 0.5 - cy) * depth / f
        out.append((float(x), float(y), team))
    return out


def dist_tee(x, y):
    return math.hypot(x, y - TEE_Y)


def _protected(stones, mine, fgz):
    """The opposition guards the free guard zone protects now (one of the end's first five stones): theirs, in front
    of the tee line and outside the house (taking one out removes my stone and puts everything back)."""
    if not fgz:
        return []
    return [j for j, (x, y, t) in enumerate(stones) if t != mine and y < TEE_Y and dist_tee(x, y) >= HOUSE_R + R]


def _hit_clear(p, a, v_at, x, y, stones, i, guards=()):
    """A takeout path (release a on path p, at v_at at the target i at (x, y)) is clear: no stone within reach of its
    path up to where the stone is 0.15 m/s faster than at the target (the Season-1 check: the stones close to the
    target may be struck too, a double), and (curling-4) no protected guard anywhere on its way to the target: the
    Season-1 check stopped 3-5 m short of the target, so a firm hit through a guard in front of the house was a free
    guard zone violation (step-5 review, 2026-10-12)."""
    if not _clear(p.points(a[0], a[1], v_end=v_at + 0.15), stones, skip=i):
        return False
    g = [stones[j] for j in guards if j != i]
    if not g:
        return True
    pts = p.points(a[0], a[1], v_end=v_at)
    return _clear(pts[np.hypot(pts[:, 0] - x, pts[:, 1] - y) > 2 * R], g)


def _clear(pts, stones, skip=None, margin=0.03):
    for i, (x, y, _) in enumerate(stones):
        if i == skip:
            continue
        if np.min(np.hypot(pts[:, 0] - x, pts[:, 1] - y)) < 2 * R + margin:
            return False
    return True


FGZ_STONES = 5
# the end's points for the team with the hammer (>= 3 pooled), a rough model (as curling.py's level 3)
HAMMER_END = {3: 0.20, 2: 0.17, 1: 0.43, 0: 0.05, -1: 0.12, -2: 0.02, -3: 0.01}
_WP = {}


def wp(d, end_next, hammer, ends=4, extra=3, tie=0.0):
    """My chance to win from the start of end `end_next` (0-based) with lead d and the hammer (1) or not (0): `ends`
    regulation ends, extra ends while tied (at most `extra`), then `tie` (match format: the scripted team wins a tie,
    0; duel: the clocks decide, 0.5). The team that scores gives the hammer away; a blank end keeps it."""
    d = max(-12, min(12, int(d)))
    key = (d, end_next, hammer, ends, extra, tie)
    if key not in _WP:
        if end_next >= ends and d != 0:
            r = 1.0 if d > 0 else 0.0
        elif end_next >= ends + extra:
            r = tie
        else:
            r = 0.0
            for j, p in HAMMER_END.items():
                r += p * wp(d + (j if hammer else -j), end_next + 1, (1 - hammer) if j > 0 else hammer, ends, extra, tie)
        _WP[key] = r
    return _WP[key]


def centre_guard(x, y):
    """A stone in front of the house near the centre line (it covers the button)."""
    return HOG_Y + 0.5 < y < TEE_Y - HOUSE_R - R and abs(x) < 0.75


def plan(stones, mine: str, fgz: bool = False, kd: float = 1.0, ctx: dict | None = None):
    """(speed, angle, spin, description) for the next throw. stones: [(x, y, team)]; mine: my team colour; fgz: the
    free guard zone rule is in force (one of the first five stones of the end), so no blind takeouts through guards;
    kd: the ice's deceleration scale it believes (IceFit); ctx (curling-3, the hammer and guard tactics, tactics()):
    {"hammer": I throw the end's last stone, "k": the throw's index in the end (0-based), "left_me", "left_opp": stones
    left to throw (this one included), "d": my lead, "end": the end (0-based), "ends": regulation ends, "tie": my
    chance in a tie after the last extra end}. Without ctx: the Season-1 plan (basic)."""
    if ctx is not None:
        out = tactics(stones, mine, fgz, kd, ctx)
        if out is not None:
            return out
    return basic(stones, mine, fgz, kd)


def _draw(stones, spot, kd, gap=0.04):
    """A draw to `spot` (free, along a clear curling path, either spin) or None."""
    sx, sy = spot
    if any(math.hypot(sx - x, sy - y) < 2 * R + gap for x, y, _ in stones) or abs(sx) + R > HALF_W - 0.2:
        return None
    for spin in ("ccw", "cw"):
        a = _path(spin, kd).aim(sx, sy, 0.0)
        if a is None or abs(a[1]) > 5.0:
            continue
        if _clear(_path(spin, kd).points(a[0], a[1]), stones):
            return a[0], a[1], spin
    return None


def _hit(stones, i, kd, v_ats=(2.2, 1.6), guards=()):
    """A takeout of stone i along a clear path (no other stone touched on the way) or None."""
    x, y, _ = stones[i]
    for v_at in v_ats:
        for spin in ("ccw", "cw"):
            a = _path(spin, kd).aim(x, y, v_at)
            if a is None or abs(a[1]) > 5.0:
                continue
            if _hit_clear(_path(spin, kd), a, v_at, x, y, stones, i, guards):
                return min(a[0], V_MAX), a[1], spin
    return None


GUARD_LEAD = -1                                     # centre guards without the hammer when my lead <= this
THROW_AWAY = (1.0, 0.0, "ccw")                      # stops ~6 m out, short of the hog line: removed, touches nothing


def tactics(stones, mine, fgz, kd, ctx):
    """The hammer and the guards. Last stone (the hammer): keep the points I have (throw it away); with the house
    empty blank the end (throw away) when keeping the hammer is worth more than one point (wp), else draw; when they
    sit shot, draw closer if a spot is open, else hit and stay. With the hammer before that: keep the end clean (hit
    their stones in the house, peel their centre guards once the free guard zone allows, corner guards while it
    holds and the house is empty). Without it: centre guards in the free guard zone, then draws around them (the
    basic plan's clear-path draws), their shot stone hit when the path is clear. None: the basic plan."""
    hammer, k, d, end = bool(ctx["hammer"]), int(ctx["k"]), int(ctx["d"]), int(ctx["end"])
    ends, tie = int(ctx.get("ends", 4)), float(ctx.get("tie", 0.0))
    house = sorted((dist_tee(x, y), i) for i, (x, y, t) in enumerate(stones) if dist_tee(x, y) < HOUSE_R + R)
    guards = _protected(stones, mine, fgz)
    mine_h = [i for _, i in house if stones[i][2] == mine]
    theirs_h = [i for _, i in house if stones[i][2] != mine]
    count = 0
    if house:
        first = stones[house[0][1]][2]
        other = [dd for dd, i in house if stones[i][2] != first]
        lim = other[0] if other else 1e9
        n = sum(1 for dd, i in house if stones[i][2] == first and dd < lim)
        count = n if first == mine else -n
    my_cg = [i for i, (x, y, t) in enumerate(stones) if t == mine and centre_guard(x, y)]
    their_cg = [i for i, (x, y, t) in enumerate(stones) if t != mine and centre_guard(x, y)]
    last = ctx["left_me"] == 1 and ctx["left_opp"] == 0
    if last:
        if count > 0:                                  # one more: a draw inside their best stone along a clear path
            lim = min((dd for dd, i in house if stones[i][2] != mine), default=HOUSE_R + R) - 0.05
            for spot in SPOTS:
                if dist_tee(*spot) < lim:
                    a = _draw(stones, spot, kd)
                    if a is not None:
                        return (*a, f"draw for one more to ({spot[0]:.2f}, {spot[1]:.2f})")
            return (*THROW_AWAY, f"throw away: keep the {count} point(s)")
        if count == 0:
            if wp(d, end + 1, 1, ends, tie=tie) >= wp(d + 1, end + 1, 0, ends, tie=tie):
                return (*THROW_AWAY, "throw away: blank the end, keep the hammer")
            return None                                       # draw for one (basic)
        a = _hit(stones, house[0][1], kd, (1.6, 2.2), guards)
        if a is not None:
            return (*a, "hit and stay on their shot stone")
        best = house[0][0]
        for spot in SPOTS:
            if dist_tee(*spot) < best - 0.05:
                a = _draw(stones, spot, kd)
                if a is not None:
                    return (*a, f"draw inside their shot stone to ({spot[0]:.2f}, {spot[1]:.2f})")
        return None
    if hammer:
        for i in theirs_h:
            a = _hit(stones, i, kd, guards=guards)
            if a is not None:
                return (*a, "keep it clean: takeout")
        if not fgz:
            for i in their_cg:
                a = _hit(stones, i, kd, (2.6,))
                if a is not None:
                    return (*a, "keep it clean: peel their guard")
        if their_cg and not mine_h:                    # their centre guard (the free guard zone keeps it): use it as
            for i in their_cg:                         # cover, come around it into the house (curling-4)
                gx = stones[i][0]
                for spot in ((gx, TEE_Y - 0.2), (gx + 0.3, TEE_Y), (gx - 0.3, TEE_Y), (gx, TEE_Y + 0.4)):
                    a = _draw(stones, spot, kd)
                    if a is not None:
                        return (*a, f"come around their guard to ({spot[0]:.2f}, {spot[1]:.2f})")
        if fgz and not house and not their_cg:
            for gx in (0.9, -0.9):
                if not any(t != mine and abs(x - gx) < 0.5 for x, y, t in stones):
                    a = _draw(stones, (gx, TEE_Y - HOUSE_R - 0.6), kd)
                    if a is not None:
                        return (*a, "corner guard")
        return None
    if theirs_h and theirs_h[0] == house[0][1]:
        a = _hit(stones, theirs_h[0], kd, guards=guards)
        if a is not None:
            return (*a, "takeout of their shot stone")
    want = 0 if d > GUARD_LEAD else (2 if k < 2 else 1)  # guards only when trailing (GUARD_LEAD = -1)
    if k < FGZ_STONES and len(my_cg) < want:
        for gx, gy in ((0.0, TEE_Y - HOUSE_R - 1.2), (0.25, TEE_Y - HOUSE_R - 0.7), (-0.25, TEE_Y - HOUSE_R - 0.7),
                       (0.0, TEE_Y - HOUSE_R - 2.0)):
            a = _draw(stones, (gx, gy), kd)
            if a is not None:
                return (*a, f"centre guard at ({gx:.2f}, {gy:.2f})")
    if my_cg:
        for i in my_cg:
            gx = stones[i][0]
            for spot in ((gx, TEE_Y - 0.2), (gx + 0.3, TEE_Y), (gx - 0.3, TEE_Y), (gx, TEE_Y + 0.4)):
                a = _draw(stones, spot, kd)
                if a is not None:
                    return (*a, f"draw behind my guard to ({spot[0]:.2f}, {spot[1]:.2f})")
    return None


SPOTS = [(0.0, TEE_Y), (0.0, TEE_Y + 0.35), (-0.35, TEE_Y), (0.35, TEE_Y), (0.0, TEE_Y - 0.4), (-0.45, TEE_Y + 0.3),
         (0.45, TEE_Y + 0.3), (-0.6, TEE_Y - 0.3), (0.6, TEE_Y - 0.3), (0.0, TEE_Y + 0.8), (-0.9, TEE_Y), (0.9, TEE_Y)]


def basic(stones, mine: str, fgz: bool = False, kd: float = 1.0):
    """The Season-1 plan: their shot stone taken out along a clear path, else a draw to the free spot nearest the
    button, else a takeout through traffic or a draw to the button."""

    def path(spin):
        return _path(spin, kd)

    house = sorted((dist_tee(x, y), i) for i, (x, y, t) in enumerate(stones) if dist_tee(x, y) < HOUSE_R + R)
    shot_is_theirs = bool(house) and stones[house[0][1]][2] != mine
    guards = _protected(stones, mine, fgz)
    # 1. their shot stone (and their other stones near the house, closest first): a firm takeout with a clear path
    if shot_is_theirs:
        targets = [i for _, i in house if stones[i][2] != mine]
        for i in targets[:3]:
            x, y, _ = stones[i]
            for spin in ("ccw", "cw"):
                for v_at in (2.2, 1.6):
                    a = path(spin).aim(x, y - 0.0, v_at)
                    if a is None:
                        continue
                    if _hit_clear(path(spin), a, v_at, x, y, stones, i, guards):
                        return a[0], a[1], spin, f"takeout of the stone at ({x:.2f}, {y:.2f})"
    # 2. a draw to the free spot nearest the button
    for sx, sy in SPOTS:
        if any(math.hypot(sx - x, sy - y) < 2 * R + 0.04 for x, y, _ in stones):
            continue
        for spin in ("ccw", "cw"):
            a = path(spin).aim(sx, sy, 0.0)
            if a is None or abs(a[1]) > 5.0:
                continue
            pts = path(spin).points(a[0], a[1])
            if _clear(pts, stones):
                return a[0], a[1], spin, f"draw to ({sx:.2f}, {sy:.2f})"
    # 3. nothing clear: a takeout of the stone nearest the tee (or a plain draw to the button)
    if house and not fgz:
        x, y, _ = stones[house[0][1]]
        a = path("ccw").aim(x, y, 2.4)
        if a is not None:
            return a[0], a[1], "ccw", "takeout through traffic"
    a = path("ccw").aim(0.0, TEE_Y, 0.0)
    return a[0], a[1], "ccw", "draw to the button"


def clean(me):
    """My throw (as heard) touched nothing and stayed in play."""
    return bool(me) and "pass" not in me and not (me.get("collisions_heard") or any(
        (me.get("stones_removed") or {}).values()) or me.get("free_guard_zone_violation"))


def new_stone(before, stones, mine):
    """The one stone of my colour in `stones` that was not in `before` (None if not exactly one)."""
    new = [(x, y) for x, y, t in stones if t == mine
           and all(math.hypot(x - bx, y - by) > 0.05 for bx, by, bt in before if bt == mine)]
    return new[0] if len(new) == 1 else None


def own_rest(heard, end, before, stones, mine):
    """Where my last throw came to rest, if the next observation still shows it: `heard` = its throws since my last
    one (mine first): my stone touched nothing and stayed in play, no later stone touched anything, the end is still
    `end`, and exactly one stone of my colour is new against `before` (the stones I saw before throwing)."""
    if not heard or heard[0].get("by") != "you" or not clean(heard[0]) or heard[0].get("end") != end:
        return None
    if heard[0].get("end_finished") or any(h.get("collisions_heard") or h.get("end_finished") for h in heard[1:]):
        return None
    return new_stone(before, stones, mine)


def context(st, tie=0.0):
    """plan()'s ctx from the observation (the public state of the turn), None if it lacks a field."""
    try:
        left, score = st["stones_left_to_throw"], st["score"]
        return {"hammer": st["hammer"] == "you", "k": int(st["throw_in_end"]) - 1, "left_me": int(left["you"]),
                "left_opp": int(left["opponent"]), "d": int(score["you"]) - int(score["opponent"]),
                "end": int(st["end"]) - 1, "ends": int(st.get("regulation_ends", 4)), "tie": tie}
    except (KeyError, TypeError, ValueError):
        return None


class Reference:
    """The reference player: plan() on the stones perceived in the house image, on the ice it has learnt (IceFit)."""

    def __init__(self, spec, seat, seed=0):
        self.cam = next(c for c in spec["cameras"] if c["name"] == "house")
        self.mine = (spec.get("match") or {}).get("your_colour", "yellow")
        self.tie = 0.0 if spec.get("format", (spec.get("match") or {}).get("format")) == "match" else 0.5
        self.last = ""
        self.ice = IceFit()
        self.pending = None
        path("ccw")
        path("cw")                                   # integrate the ice law once

    def see(self, obs):
        """The stones [(x, y, colour)] in an image (the observation's, or a reply's) with a house tile (the reply's
        "observation": the house camera right after my throw came to rest, Match.reply_views; the live service and
        tools/screen's turn loop pass it to review())."""
        return perceive(house_image(obs), self.cam)

    def act(self, view):
        st, obs = view["state"], view["observation"]
        stones = self.see(obs)
        p, self.pending = self.pending, None
        if p is not None:                            # no reply image of my last throw: the observation, if it can
            rest = own_rest(st.get("throws_since_your_last"), p["end"], p["before"], stones, self.mine)
            if rest is not None:
                self.ice.observe(*p["cmd"], rest)
        v, a, spin, self.last = plan(stones, self.mine, fgz=(st.get("throw_in_end") or 99) <= 5, kd=self.ice.kd,
                                     ctx=context(st, self.tie))
        cmd = (round(v, 6), round(a, 6), spin)
        self.pending = {"cmd": cmd, "end": st.get("end"), "before": stones}
        return {"type": "throw", "speed": cmd[0], "angle": cmd[1], "spin": spin}

    def review(self, reply):
        p = self.pending
        img = (reply.get("observation") or {}) if isinstance(reply, dict) else {}
        if p is not None and "your_throw" in reply and img.get("image_png_b64") and any(
                t.get("camera") == "house" for t in img.get("tiles") or []):
            self.pending = None                      # the reply image of my throw at rest (before the next stone)
            if clean(reply["your_throw"]):
                rest = new_stone(p["before"], self.see(img), self.mine)
                if rest is not None:
                    self.ice.observe(*p["cmd"], rest)
        return ("reference player: " + (self.last or "throw recorded"),
                f"reference player: same policy, ice kd = {self.ice.kd:.4f} from {len(self.ice.fits)} throw(s)")


class Random:
    """Uniform random valid throws, by seed only (not by seat)."""

    def __init__(self, spec, seat, seed=0):
        self.g = np.random.default_rng(int(seed) * 7919 + 23)

    def act(self, view):
        return {"type": "throw", "speed": round(float(self.g.uniform(2.0, 3.4)), 6),
                "angle": round(float(self.g.uniform(-4.0, 4.0)), 6), "spin": ["ccw", "cw"][int(self.g.integers(2))]}
