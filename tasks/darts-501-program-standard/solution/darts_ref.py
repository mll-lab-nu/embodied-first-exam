"""Reference darts player (camera images and the documented physics only; no simulator internals).

* Flight: the documented model (release point, gravity, quadratic drag a = -k |v| v), integrated with RK4.
* Drag: k is unknown (0.02-0.05 1/m). After each of its darts the player finds the dart in the board close-up (the
  flight colour of that dart: yellow, cyan, magenta), turns the pixel into the tip's board position with the board
  camera's pose and intrinsics from `game spec` (the flight sits 13.5 cm behind the tip, along the arrival
  direction), and refits k by least squares on the vertical landing errors of all its darts so far (prior 0.035).
* Aim: the optimal-aim table for its own scatter (policy_player.json: minimum expected visits to check out,
  double-out, after Tibshirani et al. 2011), at 7 m/s.
"""
import io
import json
import math
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
G = 9.81
DT = 0.0005
SPEED = 7.0
FLIGHT_BACK = 0.135          # flight centre behind the tip (m)
TIP_IN = 0.006               # tip inside the board (m)
COLOURS = ("yellow", "cyan", "magenta")


def fly(release, x_board, z_bull, yaw, pitch, speed, k):
    """(u, v, unit arrival direction) where the tip reaches the board plane; None if it never does."""
    y, p = math.radians(yaw), math.radians(pitch)
    x, yy, z = release
    vx, vy, vz = speed * math.cos(p) * math.cos(y), speed * math.cos(p) * math.sin(y), speed * math.sin(p)

    def acc(a, b, c):
        s = math.sqrt(a * a + b * b + c * c)
        return -k * s * a, -k * s * b, -G - k * s * c

    for _ in range(40000):
        a1 = acc(vx, vy, vz)
        v2 = (vx + .5 * DT * a1[0], vy + .5 * DT * a1[1], vz + .5 * DT * a1[2]); a2 = acc(*v2)
        v3 = (vx + .5 * DT * a2[0], vy + .5 * DT * a2[1], vz + .5 * DT * a2[2]); a3 = acc(*v3)
        v4 = (vx + DT * a3[0], vy + DT * a3[1], vz + DT * a3[2]); a4 = acc(*v4)
        nx = x + DT / 6 * (vx + 2 * v2[0] + 2 * v3[0] + v4[0])
        ny = yy + DT / 6 * (vy + 2 * v2[1] + 2 * v3[1] + v4[1])
        nz = z + DT / 6 * (vz + 2 * v2[2] + 2 * v3[2] + v4[2])
        nv = (vx + DT / 6 * (a1[0] + 2 * a2[0] + 2 * a3[0] + a4[0]), vy + DT / 6 * (a1[1] + 2 * a2[1] + 2 * a3[1] + a4[1]),
              vz + DT / 6 * (a1[2] + 2 * a2[2] + 2 * a3[2] + a4[2]))
        if nx >= x_board:
            f = (x_board - x) / (nx - x)
            hy, hz = yy + f * (ny - yy), z + f * (nz - z)
            d = np.array(nv) / np.linalg.norm(nv)
            return -hy, hz - z_bull, d
        if nz <= 0 or nv[0] <= 0:
            return None
        x, yy, z, (vx, vy, vz) = nx, ny, nz, nv
    return None


def colour_mask(img, name):
    """Pixels of a flight colour, lit or shaded (hue test, not brightness)."""
    r, g, b = (img[..., i].astype(int) for i in range(3))
    if name == "yellow":
        return (r > 50) & (g > 0.6 * r) & (g < 1.2 * r) & (b < 0.4 * r)
    if name == "cyan":
        return (b > 50) & (g > 0.6 * b) & (g < 1.3 * b) & (r < 0.4 * b)
    return (r > 50) & (b > 0.6 * r) & (b < 1.3 * r) & (g < 0.4 * r)     # magenta


class Player:
    def __init__(self, spec, policy_file=os.path.join(HERE, "policy_player.json")):
        self.pol = json.load(open(policy_file))["policy"]
        self.release = tuple(spec["throw"]["release_point_m"])
        self.x_board = spec["board"]["face_plane_x_m"]
        self.z_bull = spec["board"]["bull_centre_m"][2]
        self.cam = next(c for c in spec["cameras"] if c["name"] == "board")
        self.k = 0.035
        self.obs = []                 # (command, observed v)

    def aim(self, u, v, speed, k):
        yaw = math.degrees(math.atan2(-u, self.x_board - self.release[0]))
        pitch = 10.0
        for _ in range(30):
            f = fly(self.release, self.x_board, self.z_bull, yaw, pitch, speed, k)
            eu, ev = u - f[0], v - f[1]
            if abs(eu) < 1e-6 and abs(ev) < 1e-6:
                break
            h = 1e-3
            fy = fly(self.release, self.x_board, self.z_bull, yaw + h, pitch, speed, k)
            fp = fly(self.release, self.x_board, self.z_bull, yaw, pitch + h, speed, k)
            j = np.array([[(fy[0] - f[0]) / h, (fp[0] - f[0]) / h], [(fy[1] - f[1]) / h, (fp[1] - f[1]) / h]])
            dy, dp = np.linalg.solve(j, [eu, ev])
            yaw, pitch = yaw + dy, pitch + dp
        return yaw, pitch

    def command(self, remaining, darts_left):
        u, v = self.pol[f"{remaining},{darts_left}"]
        yaw, pitch = self.aim(u, v, SPEED, self.k)
        return round(yaw, 4), round(pitch, 4), SPEED

    def locate(self, png, dart, cmd):
        """The board position (u, v) of the tip of this visit's dart number `dart` in the board close-up, or None."""
        img = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))
        m = colour_mask(img, COLOURS[dart - 1])
        if m.sum() < 15:
            return None
        ys, xs = np.nonzero(m)
        px, py = xs.mean() + 0.5, ys.mean() + 0.5
        c = self.cam
        ax = c["axes_world"]
        right, up, fwd = (np.array(ax[k]) for k in ("image_right", "image_up", "optical_axis_forward"))
        cx, cy = c["principal_point_px"]
        ray = fwd + (px - cx) / c["focal_px"] * right - (py - cy) / c["focal_px"] * up
        pred = fly(self.release, self.x_board, self.z_bull, *cmd, self.k)
        d = pred[2] if pred else np.array([1.0, 0.0, 0.0])
        x_flight = self.x_board + TIP_IN - FLIGHT_BACK * d[0]
        pos = np.array(c["pos"])
        p = pos + ray * (x_flight - pos[0]) / ray[0]
        hit = p + FLIGHT_BACK * d                           # where the dart crossed the board plane
        return -hit[1], hit[2] - self.z_bull

    def learn(self, png, dart, cmd):
        """Record where this dart landed and refit the drag constant."""
        uv = self.locate(png, dart, cmd)
        if uv is None:
            return None
        self.obs.append((cmd, uv[1]))
        for _ in range(2):                                  # Gauss-Newton on k with a weak prior at 0.035
            a, b = 1.0 / 0.01 ** 2, (0.035 - self.k) / 0.01 ** 2
            for c, v in self.obs:
                f0 = fly(self.release, self.x_board, self.z_bull, *c, self.k)
                f1 = fly(self.release, self.x_board, self.z_bull, *c, self.k + 1e-3)
                if not f0 or not f1:
                    continue
                j = (f1[1] - f0[1]) / 1e-3
                w = 1.0 / 0.013 ** 2                        # landing scatter, about 1.3 cm
                a += w * j * j
                b += w * j * (v - f0[1])
            self.k = float(min(0.06, max(0.01, self.k + b / a)))
        return uv
