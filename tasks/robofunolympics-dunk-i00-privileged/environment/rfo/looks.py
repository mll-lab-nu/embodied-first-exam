"""How a venue looks: sunlight with shadows, a painted sky, surfaces with a material instead of a flat colour (grass,
a rubber track, a wooden court, sand, an acrylic hard court), balls with their patterns, and perimeter boards and
grandstands round the venue (drawn only: no collision class). Looks only: nothing here touches a collision
class, a friction, a mass or a pose, so the physics and the state hash are what they were.

Two steps, both called by World: `dress(scene)` on the MJCF tree after the family has built its venue (lights, the
visual settings, one material per kind of surface, given to the venue's large flat boxes by their colour), and
`paint(model)` on the compiled model, which fills the materials' textures with procedural detail (numpy, seeded: the
same pixels in every process). The textures are luminance detail close to white; a geom keeps the colour its family
gave it (MuJoCo multiplies the two), so a family needs to know nothing about this module."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import numpy as np

# name -> (pixels, metres one repeat covers, specular, shininess, reflectance)
MATERIALS = {
    "rfo_grass": (1024, 6.0, 0.05, 0.05, 0.0),      # the open ground (in colour: the floor has none of its own)
    "rfo_turf": (512, 4.0, 0.05, 0.05, 0.0),        # a pitch, a green, a lawn
    "rfo_track": (512, 1.5, 0.10, 0.10, 0.0),       # a rubber track or runway
    "rfo_wood": (1024, 4.0, 0.45, 0.65, 0.0),      # a sprung wooden court, a lane, a platform
    "rfo_sand": (512, 2.0, 0.02, 0.02, 0.0),
    "rfo_hard": (512, 2.0, 0.15, 0.20, 0.0),        # an acrylic court, a mat, a wall
    "rfo_paving": (512, 2.0, 0.08, 0.10, 0.0),      # the open ground around a court or a gym floor (in colour)
    "rfo_boards": (1024, 16.0, 0.20, 0.30, 0.0),    # the perimeter boards: 16 m of panels (in colour)
    "rfo_seats": (512, 8.0, 0.05, 0.05, 0.0),       # a grandstand: ten rows of seats, some taken (in colour)
}
ARENA_MARGIN_M = 8.0         # the perimeter boards stand this far outside everything the venue has (cameras too)
ARENA_MIN_HALF_M = 14.0
BOARD_H_M, STAND_GAP_M, STAND_RUN_M, STAND_RISE_M = 1.0, 3.0, 10.0, 6.0
# a ball's pattern, by the plain colour scene.py gives its kind: name -> (that colour, specular, shininess)
BALLS = {
    "football": ((0.95, 0.95, 0.95), 0.35, 0.50), "basketball": ((0.90, 0.45, 0.12), 0.12, 0.20),
    "volleyball": ((0.98, 0.90, 0.25), 0.30, 0.45), "tennis": ((0.80, 0.95, 0.20), 0.02, 0.02),
    "baseball": ((0.97, 0.97, 0.94), 0.15, 0.20), "golf": ((1.0, 1.0, 1.0), 0.45, 0.60),
    "bowling": ((0.15, 0.2, 0.6), 0.85, 0.90),
}
BALL_PX = 128                                        # one face of a ball's cube
SKY_PX = 512                                         # one face of the sky's cube
SUN_DIR = (0.20, 0.13, -1.0)                         # the sunlight's direction (the sun stands opposite): a high
#                                                      sun, because under a lower one MuJoCo's shadow map speckles
#                                                      the ground with self-shadowing in some views
GRASS_RGB = (0.27, 0.44, 0.21)      # the open ground
TURF_RGB = (0.30, 0.46, 0.20)       # what a pitch's or a lawn's colour is drawn towards
MIN_AREA_M2 = 1.0            # smaller boxes (lines, marks, posts) keep their flat colour
_CACHE: dict[str, np.ndarray] = {}


# ---------------------------------------------------------------------- the scene (MJCF)
def _kind(name: str, rgba) -> str | None:
    """The material of a large flat surface, from its colour (and the word "sand")."""
    r, g, b, a = rgba
    if a < 0.99:
        return None
    if "sand" in name:
        return "rfo_sand"
    if min(r, g, b) > 0.9:
        return None                                  # painted white: a line or a zone
    if g > r and g > b:
        return "rfo_turf"
    if r > 0.55 and g < 0.36 and b < 0.36:
        return "rfo_track"
    if r > g > b and r >= 0.68 and g >= 0.5 and r - b >= 0.25:
        return "rfo_wood"
    return "rfo_hard"


def dress(sc) -> None:
    root, wb = sc.root, sc.wb
    vis = root.find("visual")
    for tag in ("headlight", "quality", "map", "rgba"):
        for el in vis.findall(tag):
            vis.remove(el)
    ET.SubElement(vis, "headlight", ambient="0.30 0.32 0.36", diffuse="0.12 0.12 0.12", specular="0 0 0")
    ET.SubElement(vis, "quality", shadowsize="2048", offsamples="4")   # (software GL: about twice the old frame time)
    # One visual scale for every venue (MuJoCo would take it from the venue's size): the clipping planes are 0.08 m and
    # 500 m, and the sun's shadows are drawn within 60 m of what a camera looks at (a shorter range speckles the
    # ground with self-shadowing, as a lower sun does).
    for el in root.findall("statistic"):
        root.remove(el)
    ET.SubElement(root, "statistic", extent="10")
    ET.SubElement(vis, "map", haze="0.5", shadowclip="6", znear="0.008", zfar="50")
    ET.SubElement(vis, "rgba", haze="0.58 0.69 0.66 1")
    asset = root.find("asset")
    for t in asset.findall("texture"):
        if t.get("name") == "sky":                   # painted by paint(): a sky with clouds over distant hills
            for k in ("rgb2", "mark", "markrgb", "random"):
                t.attrib.pop(k, None)
            t.set("builtin", "flat")
            t.set("rgb1", "0.5 0.7 0.9")
            t.set("width", str(SKY_PX))
            t.set("height", str(6 * SKY_PX))
    for name, (px, metres, spec, shin, refl) in MATERIALS.items():
        ET.SubElement(asset, "texture", name=name, type="2d", builtin="flat", rgb1="1 1 1", width=str(px),
                      height=str(px))
        ET.SubElement(asset, "material", name=name, texture=name, texuniform="true",
                      texrepeat=f"{1 / metres:.6g} {1 / metres:.6g}", specular=f"{spec:g}", shininess=f"{shin:g}",
                      reflectance=f"{refl:g}")
    for light in wb.findall("light"):
        if light.get("name") == "sun":               # an early-afternoon sun: warm, with shadows
            light.set("dir", " ".join(f"{x:g}" for x in SUN_DIR))
            light.set("diffuse", "0.78 0.75 0.68")
            light.set("specular", "0.30 0.30 0.28")
            light.set("castshadow", "true")
    for name, (_rgb, spec, shin) in BALLS.items():   # balls: a cube texture that turns with the ball
        ET.SubElement(asset, "texture", name=f"rfo_{name}", type="cube", builtin="flat", rgb1="1 1 1",
                      width=str(BALL_PX), height=str(6 * BALL_PX))
        ET.SubElement(asset, "material", name=f"rfo_{name}", texture=f"rfo_{name}", specular=f"{spec:g}",
                      shininess=f"{shin:g}")
    for g in wb.iter("geom"):
        if g.get("type") != "sphere" or g.get("material") or g.get("rgba") is None:
            continue
        rgba = [float(x) for x in g.get("rgba").split()]
        for name, (rgb, _s, _h) in BALLS.items():
            if rgba[3] >= 0.99 and max(abs(a - b) for a, b in zip(rgba, rgb)) < 0.005:
                g.set("material", f"rfo_{name}")
                g.set("rgba", "1 1 1 1")                     # the colour is in the texture now
                break
    kinds, ground = set(), None
    for g in wb.findall("geom"):                     # the venue's own geoms (not the bodies': balls, bars, pins)
        if g.get("material") == "ground":            # the open ground, to the horizon
            ground = g
            g.set("size", "0 0 0.05")
            continue
        if g.get("type") != "box" or g.get("material") or g.get("rgba") is None:
            continue
        hx, hy, hz = (float(x) for x in g.get("size").split())
        if hz > min(hx, hy) or 4 * hx * hy < MIN_AREA_M2:
            continue                                 # a wall or a post (the texture is laid in the box's x-y plane)
        kind = _kind(g.get("name", ""), [float(x) for x in g.get("rgba").split()])
        if kind:
            g.set("material", kind)
            kinds.add(kind)
            if kind == "rfo_turf":                   # paint-box greens towards the colour of grass in sunlight
                r, gr, b, a = (float(x) for x in g.get("rgba").split())
                g.set("rgba", f"{0.5 * r + 0.5 * TURF_RGB[0]:.3f} {0.5 * gr + 0.5 * TURF_RGB[1]:.3f} "
                              f"{0.5 * b + 0.5 * TURF_RGB[2]:.3f} {a:g}")
    if ground is not None:
        _arena(sc, ground)
    if ground is not None:                           # a lawn round a field, a track or a pit; paving round a court,
        outdoor = (not kinds or kinds & {"rfo_turf", "rfo_sand"}                 # a lane or a gym floor
                   or ("rfo_track" in kinds and "rfo_wood" not in kinds))
        ground.set("material", "rfo_grass" if outdoor else "rfo_paving")


def _quat(*rots) -> str:
    """The quaternion of rotations ("x" | "z", radians) applied in turn, each about the frame the last one left."""
    w, x, y, z = 1.0, 0.0, 0.0, 0.0
    for axis, a in rots:
        c, s_ = np.cos(a / 2), np.sin(a / 2)
        w2, x2, y2, z2 = (c, s_, 0.0, 0.0) if axis == "x" else (c, 0.0, 0.0, s_)
        w, x, y, z = (w * w2 - x * x2 - y * y2 - z * z2, w * x2 + x * w2 + y * z2 - z * y2,
                      w * y2 - x * z2 + y * w2 + z * x2, w * z2 + x * y2 - y * x2 + z * w2)
    return f"{w:.6g} {x:.6g} {y:.6g} {z:.6g}"


def _arena(sc, ground) -> None:
    """Perimeter boards and a grandstand on each side, round everything the venue has: they give the place an edge
    instead of a plain to the horizon. Drawn only (no collision class): a ball flies through them. Not built where
    the family has lowered the ground plane (a sand pit, a water jump)."""
    if abs(float((ground.get("pos") or "0 0 0").split()[2])) > 1e-9:
        return
    lo, hi = np.array([np.inf, np.inf]), np.array([-np.inf, -np.inf])

    def grow(pos, half):
        nonlocal lo, hi
        lo, hi = np.minimum(lo, np.asarray(pos[:2]) - half), np.maximum(hi, np.asarray(pos[:2]) + half)

    for el in sc.wb.iter():
        if el.tag in ("camera", "body") and el.get("pos"):
            grow([float(v) for v in el.get("pos").split()], 0.0)
        elif el.tag == "geom" and el is not ground and el.get("size") and el.get("type") in ("box", "cylinder", "sphere"):
            size = [float(v) for v in el.get("size").split()]
            pos = [float(v) for v in (el.get("pos") or "0 0 0").split()]
            grow(pos, max(size[:2]) if el.get("type") == "box" else size[0])
    if not np.all(np.isfinite(lo)):
        lo, hi = np.zeros(2), np.zeros(2)
    c = (lo + hi) / 2
    half = np.maximum((hi - lo) / 2 + ARENA_MARGIN_M, ARENA_MIN_HALF_M)
    th = float(np.arctan2(STAND_RISE_M, STAND_RUN_M))
    slope = float(np.hypot(STAND_RISE_M, STAND_RUN_M))
    quarter = np.pi / 2
    # side: (centre of the boards, their length, the turn about z that brings local +y to point outwards)
    sides = {"n": ((c[0], c[1] + half[1]), 2 * half[0], 0.0), "s": ((c[0], c[1] - half[1]), 2 * half[0], np.pi),
             "e": ((c[0] + half[0], c[1]), 2 * half[1], -quarter), "w": ((c[0] - half[0], c[1]), 2 * half[1], quarter)}
    for tag, ((x, y), length, turn) in sides.items():
        out = np.array([-np.sin(turn), np.cos(turn)])                       # the outward direction on the ground
        common = dict(type="box", contype="0", conaffinity="0", rgba="1 1 1 1")
        ET.SubElement(sc.wb, "geom", name=f"rfo_boards_{tag}", material="rfo_boards", pos=f"{x:.4g} {y:.4g} {BOARD_H_M / 2:g}",
                      size=f"{length / 2:.4g} {BOARD_H_M / 2:g} 0.05", quat=_quat(("z", turn), ("x", quarter)), **common)
        mid = np.array([x, y]) + out * (STAND_GAP_M + STAND_RUN_M / 2)
        ET.SubElement(sc.wb, "geom", name=f"rfo_stand_{tag}", material="rfo_seats",
                      pos=f"{mid[0]:.4g} {mid[1]:.4g} {BOARD_H_M + 0.2 + STAND_RISE_M / 2:.4g}",
                      size=f"{length / 2 + STAND_GAP_M:.4g} {slope / 2:.4g} 0.05", quat=_quat(("z", turn), ("x", th)), **common)


# ---------------------------------------------------------------------- the pixels
def _fbm(n: int, beta: float, seed: int, stretch: tuple[float, float] = (1.0, 1.0)) -> np.ndarray:
    """Tileable noise with a 1/f^beta spectrum (zero mean, unit deviation); stretch > 1 draws it out along that axis."""
    rs = np.random.RandomState(seed)
    F = np.fft.rfft2(rs.standard_normal((n, n)))
    fy = np.fft.fftfreq(n)[:, None] * stretch[0]
    fx = np.fft.rfftfreq(n)[None, :] * stretch[1]
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1.0
    F *= f ** (-beta / 2)
    F[0, 0] = 0.0
    x = np.fft.irfft2(F, (n, n))
    return x / x.std()


def _grey(lum: np.ndarray, tint=(1.0, 1.0, 1.0)) -> np.ndarray:
    return np.clip(lum[:, :, None] * np.asarray(tint)[None, None, :], 0.0, 1.0)


def _texture(name: str, n: int) -> np.ndarray:
    """(n, n, 3) in 0..1."""
    if name == "rfo_grass":                          # the blades' fine grain; little at long wavelengths, which
        lum = 0.90 + 0.03 * _fbm(n, 1.2, 11) + 0.05 * _fbm(n, 0.4, 12)    # would show the texture's repeat from afar
        rgb = _grey(lum, GRASS_RGB)
        rgb[:, :, 0] += 0.012 * np.clip(_fbm(n, 1.4, 13), -2, 2)          # drier, yellower patches
        return np.clip(rgb, 0.0, 1.0)
    if name == "rfo_turf":
        return _grey(0.90 + 0.03 * _fbm(n, 1.2, 21) + 0.05 * _fbm(n, 0.4, 22), (1.0, 1.0, 0.97))
    if name == "rfo_track":                          # rubber granules
        rs = np.random.RandomState(31)
        grains = (rs.random_sample((n, n)) < 0.10) * rs.uniform(-0.22, 0.10, (n, n))
        return _grey(0.90 + 0.04 * _fbm(n, 2.0, 32) + 0.04 * _fbm(n, 0.2, 33) + grains)
    if name == "rfo_sand":
        ripple = 0.03 * np.sin(np.arange(n)[:, None] * (2 * np.pi * 24 / n) + 2.0 * _fbm(n, 2.5, 41))
        return _grey(0.90 + 0.04 * _fbm(n, 1.8, 42) + 0.05 * _fbm(n, 0.2, 43) + ripple, (1.0, 0.99, 0.95))
    if name == "rfo_hard":
        return _grey(0.94 + 0.025 * _fbm(n, 2.0, 51) + 0.02 * _fbm(n, 0.2, 52))
    if name == "rfo_wood":                           # strip flooring: boards along x, 16 px (62 mm) wide
        rs = np.random.RandomState(61)
        w, rows = 16, n // 16
        lum = np.empty((n, n))
        seam = np.ones((n, n))
        for r in range(rows):
            cuts = np.sort(rs.choice(np.arange(8, n - 8), 3, replace=False))
            tone = 0.90 + rs.uniform(-0.07, 0.06, 4)
            col = np.searchsorted(cuts, np.arange(n))
            lum[r * w:(r + 1) * w, :] = tone[col % 4][None, :]
            seam[r * w, :] = 0.72
            seam[r * w:(r + 1) * w, cuts] = 0.75
        grain = _fbm(n, 1.6, 62, (8.0, 0.6))
        return _grey((lum + 0.035 * grain) * seam, (1.0, 0.985, 0.95))
    if name == "rfo_paving":                         # concrete flags 0.5 m square, weathered
        lum = 0.70 + 0.02 * _fbm(n, 1.6, 71) + 0.035 * _fbm(n, 0.3, 72)
        q = n // 4
        tone = np.random.RandomState(73).uniform(-0.03, 0.03, (4, 4))
        lum += np.kron(tone, np.ones((q, q)))
        lum[::q, :] *= 0.72
        lum[:, ::q] *= 0.72
        lum[1::q, :] *= 0.9
        lum[:, 1::q] *= 0.9
        return _grey(lum, (1.0, 0.99, 0.96))
    if name == "rfo_boards":                         # eight panels of 2 m, each a colour with a paler block on it
        rs = np.random.RandomState(101)
        palette = np.array([[0.93, 0.93, 0.93], [0.10, 0.25, 0.60], [0.75, 0.12, 0.12], [0.95, 0.78, 0.12],
                            [0.10, 0.45, 0.25], [0.12, 0.12, 0.14], [0.90, 0.45, 0.10], [0.20, 0.55, 0.75]])
        rgb = np.empty((n, n, 3))
        w = n // 8
        for k in range(8):
            col = palette[rs.permutation(8)[0] if k else 1]
            rgb[:, k * w:(k + 1) * w] = col
            a, b = k * w + w // 5, (k + 1) * w - w // 5
            rgb[n // 3:2 * n // 3, a:b] = 0.55 * col + 0.45
            rgb[:, k * w:k * w + 2] *= 0.6
        rgb[:6] *= 0.7
        rgb[-6:] *= 0.7
        return rgb
    if name == "rfo_seats":                          # rows of seats 0.5 m wide, 0.8 m apart; about a third are taken
        rs = np.random.RandomState(111)
        rgb = np.full((n, n, 3), 0.20)                                    # the steps between the rows
        rows, cols, rh, cw = 10, 16, n // 10, n // 16
        seat = np.array([0.12, 0.28, 0.60])
        clothes = np.array([[0.80, 0.15, 0.15], [0.95, 0.95, 0.95], [0.15, 0.15, 0.18], [0.95, 0.80, 0.20],
                            [0.20, 0.55, 0.30], [0.55, 0.35, 0.65], [0.30, 0.45, 0.75]])
        for r in range(rows):
            for k in range(cols):
                y0, x0 = r * rh + rh // 4, k * cw + 2
                rgb[y0:y0 + rh // 2, x0:x0 + cw - 4] = seat * rs.uniform(0.85, 1.1)
                if rs.random_sample() < 0.35:                             # somebody: a body and a head
                    rgb[y0 + 2:y0 + rh // 2 + 6, x0 + 4:x0 + cw - 8] = clothes[rs.randint(len(clothes))]
                    rgb[y0 + rh // 2 + 6:y0 + rh // 2 + 14, x0 + cw // 2 - 6:x0 + cw // 2 + 4] = (0.80, 0.62, 0.50)
        return rgb + 0.02 * _fbm(n, 0.3, 112)[:, :, None]
    raise KeyError(name)


def _cube_dirs(n: int) -> list:
    """The unit directions of a cube texture's texels, face by face, in the order and orientation MuJoCo reads a cube
    in (measured: faces +x, -x, +z, -z, -y, +y; rows run down from the top)."""
    u = ((np.arange(n) + 0.5 - n / 2) / (n / 2))[None, :] * np.ones((n, 1))
    v = ((np.arange(n) + 0.5 - n / 2) / (n / 2))[:, None] * np.ones((1, n))
    one = np.ones((n, n))
    out = []
    for x, y, z in [(one, u, -v), (-one, -u, -v), (u, -v, one), (u, v, -one), (u, -one, -v), (-u, one, -v)]:
        r = np.sqrt(x * x + y * y + z * z)
        out.append((x / r, y / r, z / r))
    return out


def _lines(d: np.ndarray, w: float) -> np.ndarray:
    """1 on a line of half-width w where d = 0, falling to 0 beside it."""
    return np.clip(1.5 - np.abs(d) / w, 0.0, 1.0)


def _ball(kind: str, n: int) -> np.ndarray:
    """(6 n, n, 3) in 0..1: a ball's pattern on its cube."""
    rs = np.random.RandomState(91)
    out = np.empty((6, n, n, 3))
    if kind == "football":                           # the 12 black pentagons and 20 white hexagons of the classic ball
        phi = (1 + 5 ** 0.5) / 2
        v = np.array([p for a in (-1, 1) for b in (-phi, phi) for p in ((0, a, b), (a, b, 0), (b, 0, a))], float)
        v /= np.linalg.norm(v[0])
        f = np.array([v[i] + v[j] + v[k] for i in range(12) for j in range(i) for k in range(j)
                      if min(v[i] @ v[j], v[j] @ v[k], v[i] @ v[k]) > 0.4])
        f /= np.linalg.norm(f, axis=1)[:, None]
        centres = np.r_[v, f]
        radius = np.r_[np.full(12, np.radians(16.5)), np.full(len(f), np.radians(20.9))]
    for i, (x, y, z) in enumerate(_cube_dirs(n)):
        grain = rs.uniform(-1.0, 1.0, (n, n))
        if kind == "football":
            d = np.stack([x, y, z], -1)
            score = np.arccos(np.clip(d @ centres.T, -1, 1)) - radius
            order = np.sort(score, axis=-1)
            seam = _lines(order[:, :, 1] - order[:, :, 0], 0.012)
            black = np.argmin(score, axis=-1) < 12
            lum = np.where(black, 0.08, 0.95) * (1 - 0.6 * seam) + 0.01 * grain
            rgb = np.repeat(lum[:, :, None], 3, 2)
        elif kind == "basketball":                   # pebbled orange leather, black channels
            seam = np.maximum.reduce([_lines(z, 0.022), _lines(y, 0.022), _lines(np.abs(x) - 0.62, 0.022)])
            rgb = np.array([0.86, 0.40, 0.10]) * (1 + 0.07 * grain)[:, :, None] * (1 - 0.92 * seam)[:, :, None]
        elif kind == "volleyball":                   # six groups of three panels, yellow and blue
            a = np.argmax(np.stack([np.abs(x), np.abs(y), np.abs(z)]), axis=0)
            comp = np.stack([x, y, z])
            major = np.take_along_axis(comp, a[None], 0)[0]
            other = np.take_along_axis(comp, ((a + 1) % 3)[None], 0)[0] / np.abs(major)
            strip = np.clip(((other + 1) * 1.5).astype(int), 0, 2)
            seam = np.maximum(_lines(np.abs(other) - 1 / 3, 0.02), _lines(1 - np.abs(other), 0.03))
            third = np.take_along_axis(comp, ((a + 2) % 3)[None], 0)[0] / np.abs(major)
            seam = np.maximum(seam, _lines(1 - np.abs(third), 0.03))
            rgb = np.where((strip == 1)[:, :, None], np.array([0.10, 0.25, 0.62]), np.array([0.97, 0.86, 0.20]))
            rgb = rgb * (1 - 0.55 * seam)[:, :, None] + 0.01 * grain[:, :, None]
        elif kind in ("tennis", "baseball"):         # one seam, the curve z = k (x^2 - y^2), round the ball
            c = z - 1.15 * (x * x - y * y)
            if kind == "tennis":
                rgb = np.array([0.78, 0.90, 0.18]) * (1 + 0.10 * grain)[:, :, None]
                s_ = _lines(c, 0.06)[:, :, None]
                rgb = rgb * (1 - s_) + s_ * np.array([0.96, 0.96, 0.92])
            else:
                rgb = np.array([0.95, 0.94, 0.90]) * (1 + 0.02 * grain)[:, :, None]
                dash = (np.floor(np.arctan2(y, x) * 28 / np.pi) % 2 == 0)
                s_ = (np.maximum(_lines(c - 0.07, 0.028), _lines(c + 0.07, 0.028)) * dash)[:, :, None]
                rgb = rgb * (1 - s_) + s_ * np.array([0.75, 0.08, 0.08])
        elif kind == "golf":                         # dimples
            dimple = (np.sin(38 * x + 3 * y) * np.sin(38 * y + 3 * z) * np.sin(38 * z + 3 * x)) > 0.25
            rgb = np.repeat((0.96 - 0.10 * dimple + 0.01 * grain)[:, :, None], 3, 2)
        elif kind == "bowling":                      # a swirled, polished shell
            swirl = 0.5 + 0.5 * np.sin(7 * x + 4 * np.sin(6 * y + 2 * np.sin(5 * z)))
            rgb = (np.array([0.06, 0.09, 0.32])[None, None, :] * (1 - swirl)[:, :, None]
                   + np.array([0.20, 0.32, 0.78])[None, None, :] * swirl[:, :, None])
        else:
            raise KeyError(kind)
        out[i] = rgb
    return np.clip(out, 0.0, 1.0).reshape(6 * n, n, 3)


def _sky(n: int) -> np.ndarray:
    """(6 n, n, 3) in 0..1: the cube MuJoCo's skybox reads: a sky that pales to the horizon, the sun's glow, clouds,
    and two ranges of hazy wooded hills on the horizon."""
    faces = _cube_dirs(n)
    zenith, horizon = np.array([0.20, 0.42, 0.78]), np.array([0.76, 0.85, 0.94])
    sun = -np.asarray(SUN_DIR) / np.linalg.norm(SUN_DIR)
    cloud_map, ridge = _fbm(1024, 2.6, 81), _fbm(2048, 2.6, 82)[0]
    ridge2 = _fbm(2048, 1.7, 83)[0]
    out = np.empty((6, n, n, 3))
    for i, (x, y, z) in enumerate(faces):
        el = np.arcsin(np.clip(z, -1, 1))
        t = np.exp(-np.clip(el, 0, None) / 0.30)[:, :, None]
        rgb = zenith * (1 - t) + horizon * t
        c = np.clip(x * sun[0] + y * sun[1] + z * sun[2], 0, 1)
        rgb += (0.25 * c ** 24 + 0.9 * c ** 2500)[:, :, None] * np.array([1.0, 0.95, 0.85])
        zz = np.clip(z, 0.02, None)                                       # clouds: a layer overhead, seen in perspective
        cu = ((x / zz * 0.11 + 0.5) % 1.0 * 1024).astype(int) % 1024
        cv = ((y / zz * 0.11 + 0.5) % 1.0 * 1024).astype(int) % 1024
        dens = np.clip((cloud_map[cv, cu] - 0.35) * 0.9, 0, 1) * np.clip((el - 0.05) / 0.12, 0, 1)
        rgb = rgb * (1 - 0.85 * dens[:, :, None]) + 0.85 * dens[:, :, None] * np.array([0.98, 0.98, 0.99])
        az = ((np.arctan2(y, x) / (2 * np.pi) + 0.5) * 2048).astype(int) % 2048
        far = el < 0.030 + 0.010 * ridge[az]                              # hills: the far range paler than the near one
        near = el < 0.016 + 0.007 * ridge2[az]
        rgb[far] = [0.50, 0.63, 0.66]
        rgb[near] = [0.33, 0.47, 0.40]
        rgb[el < 0.0] = [0.33, 0.47, 0.40]
        out[i] = rgb
    return np.clip(out, 0.0, 1.0).reshape(6 * n, n, 3)


def paint(m) -> None:
    """Fill the materials' textures and the sky of a compiled model (they were declared flat)."""
    import mujoco

    i = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_TEXTURE, "sky")
    if i >= 0 and int(m.tex_height[i]) == 6 * int(m.tex_width[i]) == 6 * SKY_PX:
        if "sky" not in _CACHE:
            _CACHE["sky"] = (_sky(SKY_PX) * 255.0 + 0.5).astype(np.uint8)
        a = int(m.tex_adr[i])
        m.tex_data[a:a + _CACHE["sky"].size] = _CACHE["sky"].reshape(-1)
    for kind in BALLS:
        i = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_TEXTURE, f"rfo_{kind}")
        if i < 0 or not np.any(m.mat_texid == i) or not np.any(np.isin(m.geom_matid, np.flatnonzero(np.any(m.mat_texid == i, axis=-1)))):
            continue                                 # no ball of this kind in this venue
        key = f"ball_{kind}"
        if key not in _CACHE:
            _CACHE[key] = (_ball(kind, BALL_PX) * 255.0 + 0.5).astype(np.uint8)
        a = int(m.tex_adr[i])
        m.tex_data[a:a + _CACHE[key].size] = _CACHE[key].reshape(-1)
    for name, (px, *_rest) in MATERIALS.items():
        i = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_TEXTURE, name)
        if i < 0:
            continue
        if name not in _CACHE:
            _CACHE[name] = (np.clip(_texture(name, px), 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
        h, w, c = int(m.tex_height[i]), int(m.tex_width[i]), int(m.tex_nchannel[i])
        a = int(m.tex_adr[i])
        m.tex_data[a:a + h * w * c] = _CACHE[name].reshape(-1)
