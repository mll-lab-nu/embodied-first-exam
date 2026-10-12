"""How a venue looks: sunlight with shadows, a hazy horizon, and surfaces with a material instead of a flat colour
(grass, a rubber track, a wooden court, sand, an acrylic hard court). Looks only: nothing here touches a collision
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
}
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
    if ground is not None:                           # a lawn round a field, a track or a pit; paving round a court,
        outdoor = (not kinds or kinds & {"rfo_turf", "rfo_sand"}                 # a lane or a gym floor
                   or ("rfo_track" in kinds and "rfo_wood" not in kinds))
        ground.set("material", "rfo_grass" if outdoor else "rfo_paving")


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
    raise KeyError(name)


def _sky(n: int) -> np.ndarray:
    """(6 n, n, 3) in 0..1: the cube MuJoCo's skybox reads (faces +x, -x, +z, -z, -y, +y; rows run down from the top):
    a sky that pales to the horizon, the sun's glow, clouds, and two ranges of hazy wooded hills on the horizon."""
    u = ((np.arange(n) + 0.5 - n / 2) / (n / 2))[None, :] * np.ones((n, 1))
    v = ((np.arange(n) + 0.5 - n / 2) / (n / 2))[:, None] * np.ones((1, n))
    one = np.ones((n, n))
    faces = [(one, u, -v), (-one, -u, -v), (u, -v, one), (u, v, -one), (u, -one, -v), (-u, one, -v)]
    zenith, horizon = np.array([0.20, 0.42, 0.78]), np.array([0.76, 0.85, 0.94])
    sun = -np.asarray(SUN_DIR) / np.linalg.norm(SUN_DIR)
    cloud_map, ridge = _fbm(1024, 2.6, 81), _fbm(2048, 2.6, 82)[0]
    ridge2 = _fbm(2048, 1.7, 83)[0]
    out = np.empty((6, n, n, 3))
    for i, (x, y, z) in enumerate(faces):
        r = np.sqrt(x * x + y * y + z * z)
        x, y, z = x / r, y / r, z / r
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
    for name, (px, *_rest) in MATERIALS.items():
        i = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_TEXTURE, name)
        if i < 0:
            continue
        if name not in _CACHE:
            _CACHE[name] = (np.clip(_texture(name, px), 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
        h, w, c = int(m.tex_height[i]), int(m.tex_width[i]), int(m.tex_nchannel[i])
        a = int(m.tex_adr[i])
        m.tex_data[a:a + h * w * c] = _CACHE[name].reshape(-1)
