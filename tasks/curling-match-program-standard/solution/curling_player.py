"""Scripted curling player from public information only: the house camera image, its documented pose and intrinsics,
and the ice model and sheet geometry from the prompt. No simulator, no hidden state.

perceive(): stones from the top-down house image. Every stone has a grey granite body around its coloured top, so the
grey pixels (filled) give one disc per stone; its centre is back-projected to the body's top face, and the colour at
the centre says whose stone it is.
plan(): a few candidate shots (takeouts of the opponent's stones in or near the house, draws to free spots around the
button, with both spins), each checked for a clear path along its curling trajectory; it takes out the opponent's
shot stone when it can, else draws for the button. During the first five stones of an end (the free guard zone rule)
it never plays through guards.
aim(): the documented FCV1 single-stone law (deceleration, curl, spin decay) integrated once from 4 m/s; a slower
release follows the tail of that path, rotated to its heading, so a release speed and angle that pass a point at a
given speed are found by a search along it.
"""
import io
import math

import numpy as np
from PIL import Image
from scipy import ndimage

R = 0.145
TEE_Y, HOG_Y, BACK_Y, HOUSE_R, HALF_W = 38.405, 32.004, 40.234, 1.829, 2.375
BODY_TOP_Z = 0.107
V_MAX = 4.0
DT = 0.001
G = 9.80665


def _accel(v):
    return (0.00200985 / (v + 0.06385782) + 0.00626286) * G


class Path:
    """A stone released at V_MAX along +y with the given spin, every step (the documented ice law)."""

    def __init__(self, spin: str):
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


def path(spin):
    if spin not in _PATHS:
        _PATHS[spin] = Path(spin)
    return _PATHS[spin]


def perceive(png: bytes, cam: dict):
    """[(x, y, team)] with team 'yellow' or 'red'."""
    img = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), dtype=float)
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    f = cam["focal_px"]; cx, cy = cam["principal_point_px"]; cz = cam["pos"][2]; cy_w = cam["pos"][1]
    depth = cz - BODY_TOP_Z
    rp = f * R / depth
    grey = (np.abs(r - g) < 12) & (b - r > 3) & (b - r < 30) & (r > 140) & (r < 225)
    H, W = grey.shape
    uu = np.arange(W)[None, :]
    x_of_u = (uu + 0.5 - cx) * depth / f
    grey &= np.abs(x_of_u) < HALF_W - 0.02
    disc = ndimage.binary_fill_holes(ndimage.binary_closing(grey, iterations=1))
    dt = ndimage.distance_transform_edt(disc)
    peaks = (dt >= 0.75 * rp) & (dt == ndimage.maximum_filter(dt, size=int(rp)))
    lab, n = ndimage.label(peaks)
    cands = ndimage.center_of_mass(peaks, lab, range(1, n + 1)) if n else []
    cands = sorted(((dt[int(round(a)), int(round(c))], a, c) for a, c in cands), reverse=True)
    centres = []
    for _, a, c in cands:
        if all((a - p[0]) ** 2 + (c - p[1]) ** 2 > (1.4 * rp) ** 2 for p in centres):
            centres.append([a, c])
    for _ in range(3):                    # refine: centroid of the disc pixels nearer to this centre than to others
        new = []
        for i, (a, c) in enumerate(centres):
            v0, v1, u0, u1 = int(a - rp - 2), int(a + rp + 3), int(c - rp - 2), int(c + rp + 3)
            gv, gu = np.mgrid[max(v0, 0):min(v1, H), max(u0, 0):min(u1, W)]
            sel = disc[gv, gu] & ((gv - a) ** 2 + (gu - c) ** 2 <= rp ** 2)
            for j, (p, q) in enumerate(centres):
                if j != i:
                    sel &= (gv - a) ** 2 + (gu - c) ** 2 < (gv - p) ** 2 + (gu - q) ** 2
            new.append([float(gv[sel].mean()), float(gu[sel].mean())] if sel.sum() > 30 else [a, c])
        centres = new
    out = []
    for a, c in centres:
        gv, gu = np.mgrid[int(a - 0.5 * rp):int(a + 0.5 * rp) + 1, int(c - 0.5 * rp):int(c + 0.5 * rp) + 1]
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


def _clear(pts, stones, skip=None, margin=0.03):
    for i, (x, y, _) in enumerate(stones):
        if i == skip:
            continue
        if np.min(np.hypot(pts[:, 0] - x, pts[:, 1] - y)) < 2 * R + margin:
            return False
    return True


def plan(stones, mine: str, fgz: bool = False):
    """(speed, angle, spin, description) for the next throw. stones: [(x, y, team)]; mine: my team colour; fgz: the
    free guard zone rule is in force (one of the first five stones of the end), so no blind takeouts through guards."""
    house = sorted((dist_tee(x, y), i) for i, (x, y, t) in enumerate(stones) if dist_tee(x, y) < HOUSE_R + R)
    shot_is_theirs = bool(house) and stones[house[0][1]][2] != mine
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
                    pts = path(spin).points(a[0], a[1], v_end=v_at + 0.15)
                    if _clear(pts, stones, skip=i):
                        return a[0], a[1], spin, f"takeout of the stone at ({x:.2f}, {y:.2f})"
    # 2. a draw to the free spot nearest the button
    spots = [(0.0, TEE_Y), (0.0, TEE_Y + 0.35), (-0.35, TEE_Y), (0.35, TEE_Y), (0.0, TEE_Y - 0.4), (-0.45, TEE_Y + 0.3),
             (0.45, TEE_Y + 0.3), (-0.6, TEE_Y - 0.3), (0.6, TEE_Y - 0.3), (0.0, TEE_Y + 0.8), (-0.9, TEE_Y), (0.9, TEE_Y)]
    for sx, sy in spots:
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
