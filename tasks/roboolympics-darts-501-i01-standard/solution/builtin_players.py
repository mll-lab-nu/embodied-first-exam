"""darts' built-in players (the same action interface as a model's program; core/client.py plays them over HTTP).

  Reference  camera-only reference player. It models the documented flight (release point, gravity, quadratic drag
             with an unknown constant k), aims with the optimal-aim table for its own published scatter (minimum
             expected visits to check out, double-out and bust included; after Tibshirani, Price & Taylor 2011, "A
             statistician plays darts"), built from /spec when the player starts, and learns its landing offset from the
             images (darts-7: the unknown drag k and its release mechanism's calibration bias, D6/D7): after each of
             its darts it finds the dart (by its flight colour) in the board close-up of the reply (review(); with a
             client that does not review: its visit's earlier darts in the observation's close-up), turns the pixel
             into the landing point with the camera's pose and intrinsics, and adds the difference to the landing its
             model predicts for the sent command (k = the middle of the published range, no bias) to a shrunk running
             mean (a Gaussian prior from the published ranges); it aims at the table's point minus that offset.
             Proves the sport is winnable from the images alone.
  Rival      the reference with aim errors of its own (seeded by the seed and the seat; 1 sigma = the published
             execution scatter): the fairness policy (two references throw identical darts, see sport.toml).
  Random     uniform random throws towards the board (generic tests).
No simulator import: this file runs in the player's container as the task's oracle (numpy + Pillow only)."""
from __future__ import annotations

import base64
import io
import json
import math

import numpy as np

G = 9.81
DT = 0.002                   # the player's own integration step (RK4; the simulator uses a finer one)
SPEED = 7.0
FLIGHT_BACK = 0.135          # flight centre behind the tip (m), sport.toml dart_model
TIP_IN = 0.006               # tip inside the board (m)
LAND_SIGMA = 0.013           # landing scatter on the board (about 1.2 cm) and the image measurement, per axis
COLOURS = ("yellow", "cyan", "magenta")
_POLICIES: dict = {}


class Board:
    """The documented geometry and flight (from /spec)."""

    def __init__(self, spec):
        self.release = tuple(float(x) for x in spec["release_point_m"])
        self.x = float(spec["board_face_plane_x_m"])
        self.z = float(spec["bull_centre_m"][2])
        r = spec["radii_mm"]
        self.r_bull, self.r_obull = r["bull"] / 1000, r["outer_bull"] / 1000
        self.r_tri = [x / 1000 for x in r["treble_ring"]]
        self.r_dbl = [x / 1000 for x in r["double_ring"]]
        self.seg = np.array(spec["segments_clockwise_from_top"])

    def fly(self, yaw, pitch, speed, k):
        """(u, v, unit arrival direction) where the tip reaches the board plane, or None."""
        y, p = math.radians(yaw), math.radians(pitch)
        x, yy, z = self.release
        vx, vy, vz = speed * math.cos(p) * math.cos(y), speed * math.cos(p) * math.sin(y), speed * math.sin(p)

        def acc(a, b, c):
            s = math.sqrt(a * a + b * b + c * c)
            return -k * s * a, -k * s * b, -G - k * s * c
        for _ in range(5000):
            a1 = acc(vx, vy, vz)
            v2 = (vx + .5 * DT * a1[0], vy + .5 * DT * a1[1], vz + .5 * DT * a1[2])
            a2 = acc(*v2)
            v3 = (vx + .5 * DT * a2[0], vy + .5 * DT * a2[1], vz + .5 * DT * a2[2])
            a3 = acc(*v3)
            v4 = (vx + DT * a3[0], vy + DT * a3[1], vz + DT * a3[2])
            a4 = acc(*v4)
            nx = x + DT / 6 * (vx + 2 * v2[0] + 2 * v3[0] + v4[0])
            ny = yy + DT / 6 * (vy + 2 * v2[1] + 2 * v3[1] + v4[1])
            nz = z + DT / 6 * (vz + 2 * v2[2] + 2 * v3[2] + v4[2])
            nv = (vx + DT / 6 * (a1[0] + 2 * a2[0] + 2 * a3[0] + a4[0]),
                  vy + DT / 6 * (a1[1] + 2 * a2[1] + 2 * a3[1] + a4[1]),
                  vz + DT / 6 * (a1[2] + 2 * a2[2] + 2 * a3[2] + a4[2]))
            if nx >= self.x:
                f = (self.x - x) / (nx - x)
                d = np.array(nv) / np.linalg.norm(nv)
                return -(yy + f * (ny - yy)), z + f * (nz - z) - self.z, d
            if nz <= 0 or nv[0] <= 0:
                return None
            x, yy, z, (vx, vy, vz) = nx, ny, nz, nv
        return None

    def aim(self, u, v, speed, k, start=None):
        """(yaw, pitch) that land a dart released at `speed` on board point (u, v) (noise-free; Newton)."""
        yaw, pitch = start or (math.degrees(math.atan2(-u, self.x - self.release[0])), 10.0)
        for _ in range(30):
            f = self.fly(yaw, pitch, speed, k)
            eu, ev = u - f[0], v - f[1]
            if abs(eu) < 1e-6 and abs(ev) < 1e-6:
                break
            h = 1e-3
            fy, fp = self.fly(yaw + h, pitch, speed, k), self.fly(yaw, pitch + h, speed, k)
            j = np.array([[(fy[0] - f[0]) / h, (fp[0] - f[0]) / h], [(fy[1] - f[1]) / h, (fp[1] - f[1]) / h]])
            dy, dp = np.linalg.solve(j, [eu, ev])
            yaw, pitch = yaw + dy, pitch + dp
        return yaw, pitch

    # ------------------------------------------------------------------------ the optimal-aim table
    def outcomes(self, u, v):
        """Outcome class of board points: 0 miss, 1..20 singles, 21..40 doubles, 41..60 trebles, 61 25, 62 bull."""
        r = np.hypot(u, v)
        n = self.seg[(((np.degrees(np.arctan2(u, v)) % 360.0 + 9.0) % 360.0) // 18.0).astype(int) % 20]
        o = n.copy()
        o = np.where((r >= self.r_tri[0]) & (r <= self.r_tri[1]), 40 + n, o)
        o = np.where((r >= self.r_dbl[0]) & (r <= self.r_dbl[1]), 20 + n, o)
        o = np.where(r > self.r_dbl[1], 0, o)
        o = np.where(r <= self.r_obull, 61, o)
        return np.where(r <= self.r_bull, 62, o)

    def cov(self, scatter, speed, k):
        """Linearised covariance of the landing point for the execution scatter (aim at the bull)."""
        y0, p0 = self.aim(0.0, 0.0, speed, k)
        f0 = self.fly(y0, p0, speed, k)
        J = np.zeros((2, 3))
        for i, (dy, dp, dv) in enumerate(((1e-3, 0, 0), (0, 1e-3, 0), (0, 0, 1e-4 * speed))):
            f = self.fly(y0 + dy, p0 + dp, speed + dv, k)
            h = dy or dp or dv
            J[:, i] = (f[0] - f0[0]) / h, (f[1] - f0[1]) / h
        S = np.diag([scatter["yaw_deg"] ** 2, scatter["pitch_deg"] ** 2, (scatter["speed_rel"] * speed) ** 2])
        return J @ S @ J.T

    def policy(self, cov, grid_mm=4.0, n_samples=3000, start=501):
        """Aim point (u, v) for every (remaining, darts left in the visit) that minimises the expected number of
        visits to check out (double-out; a bust returns to the score at the start of the visit, approximated as
        the current score). Deterministic (a fixed sample set)."""
        val = np.array([0] + list(range(1, 21)) + [2 * n for n in range(1, 21)] + [3 * n for n in range(1, 21)]
                       + [25, 50])
        dbl = np.array([False] * 21 + [True] * 20 + [False] * 21 + [True])
        off = np.random.default_rng(12345).standard_normal((n_samples, 2)) @ np.linalg.cholesky(cov).T
        g = np.arange(-0.180, 0.180 + 1e-9, grid_mm / 1000.0)
        A = np.array([(a, b) for a in g for b in g if math.hypot(a, b) <= 0.180])
        P = np.zeros((len(A), 63))
        for i0 in range(0, len(A), 256):
            a = A[i0:i0 + 256]
            o = self.outcomes(a[:, None, 0] + off[None, :, 0], a[:, None, 1] + off[None, :, 1])
            for j in range(len(a)):
                P[i0 + j] = np.bincount(o[j], minlength=63) / n_samples
        W, Gd, pol = np.zeros(start + 1), np.zeros((start + 1, 4)), {}
        for r in range(2, start + 1):
            nr = r - val
            fin = (nr == 0) & dbl
            bust = (nr < 2) & ~fin
            ok = ~fin & ~bust
            nrc = np.where(ok, nr, 0)
            w, best = W[r - 1] + 1.0 if r > 2 else 5.0, {}
            for _ in range(200):
                W[r] = w
                for d in (1, 2, 3):
                    c = np.where(fin, 0.0, np.where(bust, w, W[nrc] if d == 1 else Gd[nrc, d - 1]))
                    if d > 1:
                        c = np.where(ok & (nr == r), Gd[r, d - 1], c)
                    ev = P @ c
                    best[d] = int(np.argmin(ev))
                    Gd[r, d] = ev[best[d]]
                w_new = 1.0 + Gd[r, 3]
                if abs(w_new - w) < 1e-10:
                    w = w_new
                    break
                w = w_new
            W[r] = w
            for d in (1, 2, 3):
                pol[r, d] = (float(A[best[d]][0]), float(A[best[d]][1]))
        return pol


def camera_basis(cam):
    pos, look = np.array(cam["pos"], float), np.array(cam["lookat"], float)
    fwd = (look - pos) / np.linalg.norm(look - pos)
    right = np.cross(fwd, np.array(cam.get("up", [0, 0, 1]), float))
    right /= np.linalg.norm(right)
    return pos, right, np.cross(right, fwd), fwd


def colour_mask(img, name):
    """Pixels of a flight colour, lit or shaded (a hue test, not brightness)."""
    r, g, b = (img[..., i].astype(int) for i in range(3))
    if name == "yellow":
        return (r > 50) & (g > 0.6 * r) & (g < 1.2 * r) & (b < 0.4 * r)
    if name == "cyan":
        return (b > 50) & (g > 0.6 * b) & (g < 1.3 * b) & (r < 0.4 * b)
    return (r > 50) & (b > 0.6 * r) & (b < 1.3 * r) & (g < 0.4 * r)


class Reference:
    def __init__(self, spec, seat, seed=0):
        self.B = Board(spec)
        self.cam = next(c for c in spec["cameras"] if c["name"] == "board")
        lo, hi = spec["drag_k_range_per_m"]
        self.kp = 0.5 * (float(lo) + float(hi))       # the middle of the published drag range
        key = json.dumps([spec["execution_scatter_1sigma"], spec["release_point_m"], spec["bull_centre_m"],
                          spec["radii_mm"], spec["segments_clockwise_from_top"], spec["drag_k_range_per_m"],
                          spec["calibration_bias_halfwidth"]], sort_keys=True)
        if key not in _POLICIES:                      # once per process: the table takes a few seconds
            _POLICIES[key] = (self.B.policy(self.B.cov(spec["execution_scatter_1sigma"], SPEED, self.kp)),
                              self.offset_sigma(spec))
        self.pol, sig = _POLICIES[key]
        self.n0 = (LAND_SIGMA / sig) ** 2             # the prior's weight in darts, per axis
        self.sum, self.n, self.seen, self.aims = np.zeros(2), 0, set(), {}

    def offset_sigma(self, spec):
        """Prior std (u, v) of the landing offset of a throw at the bull, from the published bias and drag ranges
        (uniform: half-width / sqrt 3)."""
        hw = spec["calibration_bias_halfwidth"]
        lo, hi = spec["drag_k_range_per_m"]
        y0, p0 = self.B.aim(0.0, 0.0, SPEED, self.kp)
        f0 = self.B.fly(y0, p0, SPEED, self.kp)
        var = np.zeros(2)
        for d, sd in (((1e-2, 0, 0, 0), hw["yaw_deg"] / math.sqrt(3)), ((0, 1e-2, 0, 0), hw["pitch_deg"] / math.sqrt(3)),
                      ((0, 0, 1e-3, 0), hw["speed_rel"] * SPEED / math.sqrt(3)),
                      ((0, 0, 0, 1e-3), (float(hi) - float(lo)) / math.sqrt(12))):
            f = self.B.fly(y0 + d[0], p0 + d[1], SPEED + d[2], self.kp + d[3])
            var += (np.array([f[0] - f0[0], f[1] - f0[1]]) / sum(d) * sd) ** 2
        return np.sqrt(var) + 1e-4

    def offset(self):
        """The learnt systematic landing offset (u, v), metres."""
        return self.sum / (self.n + self.n0)

    def throw(self, remaining, darts_left):
        u, v = self.pol[remaining, darts_left]
        if (u, v) not in self.aims:                   # the aim and its Jacobian at the table's point (k prior)
            y, p = self.B.aim(u, v, SPEED, self.kp)
            f0, h = self.B.fly(y, p, SPEED, self.kp), 1e-3
            fy, fp = self.B.fly(y + h, p, SPEED, self.kp), self.B.fly(y, p + h, SPEED, self.kp)
            J = np.array([[(fy[0] - f0[0]) / h, (fp[0] - f0[0]) / h], [(fy[1] - f0[1]) / h, (fp[1] - f0[1]) / h]])
            self.aims[u, v] = (y, p, np.linalg.inv(J))
        y, p, Ji = self.aims[u, v]
        dy, dp = Ji @ (-self.offset())                # aim off by minus the learnt offset (linear: offsets of cm)
        return round(y + float(dy), 4), round(p + float(dp), 4), SPEED

    def act(self, view):
        st = view["state"]
        self.learn(view)
        y, p, s = self.throw(st["remaining"]["you"], st["darts_left_in_visit"])
        return {"type": "throw", "yaw": y, "pitch": p, "speed": s}

    # ------------------------------------------------------------------------ learning the offset from the images
    def update(self, cmd, uv):
        """One measured landing (u, v) of a dart sent with cmd: its difference to the model's landing."""
        f = self.B.fly(*cmd, self.kp)
        if f is None:
            return
        r = np.array([uv[0] - f[0], uv[1] - f[1]])
        if math.hypot(r[0], r[1]) > 0.08:            # not this dart (a mis-detection): far beyond bias + scatter
            return
        self.sum += r
        self.n += 1

    def learn(self, view):
        """When my previous dart is on the board (an earlier dart of my current visit) and I have not measured it yet
        (a client that does not review), find it in the observation's board close-up and learn."""
        st, last = view["state"], view["state"].get("your_last_dart")
        if not last or st.get("visit_by") != "you" or (last["leg"], last["visit"]) != (st["leg"], st["visit"]) \
                or last["dart"] != st["dart_in_visit"] - 1:
            return
        self.measure(view["observation"], last)

    def measure(self, obs, last):
        """Find my dart `last` (state your_last_dart) in a board close-up and learn from it, once per dart."""
        tag = (last["leg"], last["visit"], last["dart"])
        if tag in self.seen:
            return
        self.seen.add(tag)
        cmd = (last["sent"]["yaw"], last["sent"]["pitch"], last["sent"]["speed"])
        uv = self.locate(obs or {}, last["dart"], cmd)
        if uv is not None:
            self.update(cmd, uv)

    def locate(self, obs, dart, cmd):
        """The board position (u, v) where this visit's dart number `dart` crossed the board plane, or None."""
        from PIL import Image
        tile = next((t for t in obs.get("tiles", []) if t["camera"] == "board"), None)
        if tile is None or "image_png_b64" not in obs:
            return None
        img = np.asarray(Image.open(io.BytesIO(base64.b64decode(obs["image_png_b64"]))).convert("RGB"))
        img = img[tile["y"]:tile["y"] + tile["height"], tile["x"]:tile["x"] + tile["width"]]
        m = colour_mask(img, COLOURS[dart - 1])
        if m.sum() < 15:
            return None
        ys, xs = np.nonzero(m)
        px, py = xs.mean() + 0.5, ys.mean() + 0.5
        pos, right, up, fwd = camera_basis(self.cam)
        cx, cy = self.cam["principal_point_px"]
        f = self.cam["focal_px"]
        ray = fwd + (px - cx) / f * right - (py - cy) / f * up
        pred = self.B.fly(*cmd, self.kp)
        d = pred[2] if pred else np.array([1.0, 0.0, 0.0])
        x_flight = self.B.x + TIP_IN - FLIGHT_BACK * d[0]
        p = pos + ray * (x_flight - pos[0]) / ray[0]
        hit = p + FLIGHT_BACK * d
        return -hit[1], hit[2] - self.B.z

    def review(self, reply):
        """The reply to each dart (the turn protocol) shows the board close-up with the darts of my current visit, the
        one just thrown included (its third dart too, which the next observation no longer shows): learn from it."""
        last = (reply.get("state") or {}).get("your_last_dart")
        if last and "image_png_b64" in (reply.get("observation") or {}) and all(
                reply.get(k, last[k]) == last[k] for k in ("leg", "visit", "dart")):
            self.measure(reply["observation"], last)
        o = self.offset() * 1000
        return ("measured my last dart in the board close-up",
                f"aim by the table, corrected by my landing offset ({o[0]:+.1f}, {o[1]:+.1f}) mm from {self.n} darts")


class Rival(Reference):
    def __init__(self, spec, seat, seed=0):
        super().__init__(spec, seat, seed)
        self.sc = spec["execution_scatter_1sigma"]
        self.g = np.random.default_rng([int(seed), 9, sum(map(ord, str(seat)))])

    def act(self, view):
        body = super().act(view)
        z = self.g.standard_normal(2)
        body["yaw"] = round(body["yaw"] + self.sc["yaw_deg"] * float(z[0]), 4)
        body["pitch"] = round(body["pitch"] + self.sc["pitch_deg"] * float(z[1]), 4)
        return body


class Random:
    def __init__(self, spec, seat, seed=0):
        self.g = np.random.default_rng(int(seed) * 7919 + 17)        # by seed, not by seat: mirror runs match

    def act(self, view):
        return {"type": "throw", "yaw": round(float(self.g.uniform(-4, 4)), 4),
                "pitch": round(float(self.g.uniform(8, 24)), 4), "speed": round(float(self.g.uniform(5.5, 7.0)), 4)}
