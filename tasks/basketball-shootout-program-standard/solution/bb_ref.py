"""Reference shooter (camera images and the documented physics only; no simulator internals).

* Hoop: the orange rim in the `shooter_zoom` tile; the image rows at its left and right ends give the rim centre's
  pixel, whose ray from the camera (pose in the shooter's frame from `game spec`) meets the rim plane z = 3.048 at the
  hoop's position in the shooter's frame: its bearing is the yaw, its distance the range.
* Flight: the documented ball model (release point turning with the yaw, gravity, drag -c_d |v| v, Magnus
  c_m (omega x v), backspin), integrated with RK4; the release speed is solved so the ball's centre comes down through
  the rim plane a little beyond the hoop's centre, at a fixed release angle.
* After a miss at a spot, the second attempt from it is 1 % slower if the ball touched the backboard (long), else
  0.6 % faster (short).
"""
import io
import math

import numpy as np
from PIL import Image

G = 9.81
DT = 0.002
ANGLE = 54.0
SPIN = 1.5
BEYOND = 0.0             # aim this far past the hoop centre (m)


def rim_mask(img):
    r, g, b = (img[..., i].astype(int) for i in range(3))
    return (r > 120) & (g > 0.26 * r) & (g < 0.46 * r) & (b < 0.12 * r)


class Shooter:
    def __init__(self, spec):
        cam = next(c for c in spec["cameras"] if c["name"] == "shooter_zoom")
        self.cam_pos = np.array(cam["pos_in_shooter_frame"], float)
        p = math.radians(cam["pitch_up_deg"])
        self.fwd = np.array([math.cos(p), 0.0, math.sin(p)])
        self.right = np.array([0.0, -1.0, 0.0])
        self.up = np.array([-math.sin(p), 0.0, math.cos(p)])
        self.focal = cam["focal_px"]
        self.pp = cam["principal_point_px"]
        self.tile = cam["tile_px"]
        self.col = cam["tile_offset_px"]                 # (x, y) of the zoom tile in the 2 x 2 image
        rel = spec["release"]
        self.rel_fwd, self.rel_h = rel["point_in_shooter_frame"][0], rel["point_in_shooter_frame"][2]
        b = spec["ball"]
        self.m, self.cd, self.cm = b["mass_kg"], b["drag_coef_n_s2_m2"], b["magnus_coef"]
        self.hoop_z = spec["court"]["hoop_centre"][2]
        self.speed_scale = {}                            # per spot: correction factor learned from its first shot

    def locate(self, png):
        """The hoop centre (x, y) in the shooter's frame, or None."""
        img = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))
        x0, y0 = self.col
        tile = img[y0:y0 + self.tile[1], x0:x0 + self.tile[0]]
        m = rim_mask(tile)
        ys, xs = np.nonzero(m)
        if len(xs) < 20:
            return None
        lo, hi = xs.min(), xs.max()
        left, right = ys[xs <= lo + 2].mean(), ys[xs >= hi - 2].mean()
        px, py = (lo + hi + 1) / 2.0, (left + right) / 2.0 + 0.5
        ray = self.fwd + (px - self.pp[0]) / self.focal * self.right - (py - self.pp[1]) / self.focal * self.up
        t = (self.hoop_z - self.cam_pos[2]) / ray[2]
        h = self.cam_pos + t * ray
        return float(h[0]), float(h[1])

    def flight(self, dist, angle, speed, spin):
        """Horizontal distance from the pedestal axis where the ball's centre comes down through the rim plane."""
        a = math.radians(angle)
        x, z = self.rel_fwd, self.rel_h
        vx, vz = speed * math.cos(a), speed * math.sin(a)
        w = 2 * math.pi * spin                           # backspin about the horizontal axis (dir x z)

        def acc(vx, vz):
            s = math.hypot(vx, vz)
            # omega = w * (d x z) with d the horizontal direction: omega x v = w * (vz * d_h... ) in the vertical plane
            fx = -self.cd * s * vx + self.cm * (-w * vz)
            fz = -self.cd * s * vz + self.cm * (w * vx)
            return fx / self.m, fz / self.m - G

        for _ in range(5000):
            ax1, az1 = acc(vx, vz)
            ax2, az2 = acc(vx + .5 * DT * ax1, vz + .5 * DT * az1)
            ax3, az3 = acc(vx + .5 * DT * ax2, vz + .5 * DT * az2)
            ax4, az4 = acc(vx + DT * ax3, vz + DT * az3)
            nx = x + DT * (vx + DT / 6 * (ax1 + ax2 + ax3))
            nz = z + DT * (vz + DT / 6 * (az1 + az2 + az3))
            nvx, nvz = vx + DT / 6 * (ax1 + 2 * ax2 + 2 * ax3 + ax4), vz + DT / 6 * (az1 + 2 * az2 + 2 * az3 + az4)
            if nvz < 0 and z >= self.hoop_z > nz:
                return x + (nx - x) * (z - self.hoop_z) / (z - nz)
            if nz < 0:
                return -1.0
            x, z, vx, vz = nx, nz, nvx, nvz
        return -1.0

    def speed_for(self, dist, angle=None, spin=None):
        angle, spin = ANGLE if angle is None else angle, SPIN if spin is None else spin
        lo, hi = 3.0, 14.0
        for _ in range(50):
            mid = (lo + hi) / 2
            if self.flight(dist, angle, mid, spin) < dist:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    def command(self, png, spot):
        h = self.locate(png)
        if h is None:
            return {"angle_deg": ANGLE, "speed": 8.0, "spin_hz": SPIN, "yaw_deg": 0.0}, None
        dist = math.hypot(*h)
        yaw = math.degrees(math.atan2(h[1], h[0]))
        v = self.speed_for(dist + BEYOND) * self.speed_scale.get(spot, 1.0)
        return {"angle_deg": ANGLE, "speed": round(v, 4), "spin_hz": SPIN, "yaw_deg": round(yaw, 4)}, (round(dist, 3), round(yaw, 3))

    def learn(self, spot, result):
        """After a miss, the next shot from this spot is a little shorter (backboard first) or longer (otherwise)."""
        if result.get("result") == "made":
            return
        long = "backboard" in (result.get("touched") or [])
        self.speed_scale[spot] = self.speed_scale.get(spot, 1.0) * (0.99 if long else 1.006)
