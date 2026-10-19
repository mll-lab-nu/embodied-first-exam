"""An in-memory description of one asset (bodies, joints, geoms, sites, meshes) and its MJCF output.

Builders describe geometry in millimetres and dynamics in SI units; the writer converts lengths to metres and prints
every number with a fixed format, so the same asset always produces the same text.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Sequence

import numpy as np

from . import mesh as M

MM = 1e-3
IDENTITY = (1.0, 0.0, 0.0, 0.0)

# Shared default classes; every file the generator writes declares the same ones.
DEFAULTS = (
    '  <default>\n'
    '    <default class="ese_visual"><geom contype="0" conaffinity="0" group="2" density="0"/></default>\n'
    '    <default class="ese_solid"><geom group="2" condim="4" friction="0.9 0.005 0.0002" solref="0.005 1" solimp="0.9 0.999 0.0005 0.5 2"/></default>\n'
    '    <default class="ese_collision"><geom group="3" rgba="0.9 0.3 0.2 0.35" condim="4" friction="0.9 0.005 0.0002" solref="0.005 1" solimp="0.9 0.999 0.0005 0.5 2"/></default>\n'
    '    <default class="ese_site"><site group="4" size="0.0015" rgba="0.1 0.8 0.3 1"/></default>\n'
    '  </default>\n'
)

# name -> (rgba, specular, shininess, reflectance). Colours are our own choice; nothing here imitates a product.
MATERIALS: dict[str, tuple[tuple[float, float, float, float], float, float, float]] = {
    "plastic_white": ((0.93, 0.93, 0.91, 1.0), 0.3, 0.4, 0.0),
    "plastic_clear": ((0.82, 0.90, 0.95, 0.42), 0.6, 0.8, 0.0),
    "plastic_natural": ((0.86, 0.88, 0.86, 0.5), 0.4, 0.5, 0.0),
    "plastic_black": ((0.08, 0.08, 0.09, 1.0), 0.3, 0.4, 0.0),
    "plastic_blue": ((0.16, 0.38, 0.72, 1.0), 0.3, 0.4, 0.0),
    "plastic_teal": ((0.10, 0.55, 0.55, 1.0), 0.3, 0.4, 0.0),
    "plastic_orange": ((0.92, 0.50, 0.12, 1.0), 0.3, 0.4, 0.0),
    "plastic_yellow": ((0.93, 0.80, 0.20, 1.0), 0.3, 0.4, 0.0),
    "plastic_red": ((0.80, 0.14, 0.12, 1.0), 0.3, 0.4, 0.0),
    "plastic_green": ((0.18, 0.62, 0.30, 1.0), 0.3, 0.4, 0.0),
    "housing_light": ((0.85, 0.86, 0.87, 1.0), 0.2, 0.3, 0.0),
    "housing_mid": ((0.55, 0.58, 0.62, 1.0), 0.2, 0.3, 0.0),
    "housing_dark": ((0.20, 0.22, 0.25, 1.0), 0.2, 0.3, 0.0),
    "aluminium": ((0.74, 0.76, 0.78, 1.0), 0.8, 0.9, 0.08),
    "steel": ((0.62, 0.64, 0.66, 1.0), 0.9, 0.9, 0.15),
    "anodised": ((0.24, 0.26, 0.30, 1.0), 0.6, 0.7, 0.03),
    "rubber": ((0.06, 0.06, 0.06, 1.0), 0.05, 0.1, 0.0),
    "glass": ((0.75, 0.88, 0.92, 0.22), 0.9, 0.9, 0.0),
    "glass_clear": ((0.80, 0.90, 0.94, 0.26), 0.9, 0.95, 0.0),
    "glass_frosted": ((0.90, 0.93, 0.95, 0.55), 0.2, 0.2, 0.0),
    "enamel_white": ((0.97, 0.97, 0.95, 1.0), 0.1, 0.2, 0.0),
    "ink_black": ((0.05, 0.05, 0.06, 1.0), 0.1, 0.2, 0.0),
    "ink_blue": ((0.08, 0.14, 0.50, 1.0), 0.1, 0.2, 0.0),
    "brass": ((0.80, 0.62, 0.25, 1.0), 0.8, 0.8, 0.06),
    "wood": ((0.68, 0.50, 0.32, 1.0), 0.1, 0.2, 0.0),
    "string": ((0.15, 0.15, 0.17, 1.0), 0.1, 0.1, 0.0),
    "deck": ((0.30, 0.32, 0.35, 1.0), 0.4, 0.5, 0.02),
    "table": ((0.56, 0.58, 0.61, 1.0), 0.05, 0.1, 0.0),
    # surfaces for geoms that carry their own colour (the geom's rgba replaces the material's)
    "matte": ((0.5, 0.5, 0.5, 1.0), 0.05, 0.1, 0.0),
    "satin": ((0.5, 0.5, 0.5, 1.0), 0.3, 0.4, 0.0),
    "gloss": ((0.5, 0.5, 0.5, 1.0), 0.7, 0.8, 0.02),
    "metal": ((0.5, 0.5, 0.5, 1.0), 0.9, 0.9, 0.12),
    # lit from inside: a lamp, a glowing coil, a flame, a screen. A fifth number is the emission.
    "glow": ((0.5, 0.5, 0.5, 1.0), 0.0, 0.0, 0.0, 1.0),
}


def num(x: float) -> str:
    """Nine significant digits, no exponent noise, no negative zero."""
    x = float(x)
    if abs(x) < 1e-12:
        return "0"
    s = f"{x:.9g}"
    return s


def vec(xs: Sequence[float], scale: float = 1.0) -> str:
    return " ".join(num(float(x) * scale) for x in xs)


def quat_axis_angle(axis: Sequence[float], angle: float) -> tuple[float, float, float, float]:
    a = np.asarray(axis, dtype=np.float64)
    a = a / np.linalg.norm(a)
    s = math.sin(angle / 2.0)
    return (math.cos(angle / 2.0), a[0] * s, a[1] * s, a[2] * s)


def quat_mul(q: Sequence[float], r: Sequence[float]) -> tuple[float, float, float, float]:
    w0, x0, y0, z0 = q
    w1, x1, y1, z1 = r
    return (w0 * w1 - x0 * x1 - y0 * y1 - z0 * z1, w0 * x1 + x0 * w1 + y0 * z1 - z0 * y1,
            w0 * y1 - x0 * z1 + y0 * w1 + z0 * x1, w0 * z1 + x0 * y1 - y0 * x1 + z0 * w1)


def quat_to_mat(q: Sequence[float]) -> np.ndarray:
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def mat_to_quat(r: np.ndarray) -> tuple[float, float, float, float]:
    t = np.trace(r)
    if t > 0:
        k = math.sqrt(t + 1.0) * 2.0
        q = (0.25 * k, (r[2, 1] - r[1, 2]) / k, (r[0, 2] - r[2, 0]) / k, (r[1, 0] - r[0, 1]) / k)
    else:
        i = int(np.argmax(np.diag(r)))
        j, m = (i + 1) % 3, (i + 2) % 3
        k = math.sqrt(1.0 + r[i, i] - r[j, j] - r[m, m]) * 2.0
        v = [0.0, 0.0, 0.0]
        v[i] = 0.25 * k
        v[j] = (r[j, i] + r[i, j]) / k
        v[m] = (r[m, i] + r[i, m]) / k
        q = ((r[m, j] - r[j, m]) / k, v[0], v[1], v[2])
    n = math.sqrt(sum(c * c for c in q))
    q = tuple(c / n for c in q)
    return q if q[0] >= 0 else tuple(-c for c in q)


def quat_from_z(direction: Sequence[float]) -> tuple[float, float, float, float]:
    """A rotation that takes the local +z axis to `direction` (the turn about that axis is arbitrary but fixed)."""
    d = np.asarray(direction, dtype=np.float64)
    d = d / np.linalg.norm(d)
    ref = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    x = np.cross(ref, d)
    x /= np.linalg.norm(x)
    y = np.cross(d, x)
    return mat_to_quat(np.stack([x, y, d], axis=1))


def quat_z_to(axis: str) -> tuple[float, float, float, float]:
    """The rotation that takes the local +z axis to the named axis (`x`, `-x`, `y`, `-y`, `z`, `-z`)."""
    return {
        "z": IDENTITY,
        "-z": quat_axis_angle((1, 0, 0), math.pi),
        "x": quat_axis_angle((0, 1, 0), math.pi / 2),
        "-x": quat_axis_angle((0, 1, 0), -math.pi / 2),
        "y": quat_axis_angle((1, 0, 0), -math.pi / 2),
        "-y": quat_axis_angle((1, 0, 0), math.pi / 2),
    }[axis]


@dataclass
class Geom:
    type: str                                   # box | cylinder | sphere | capsule | ellipsoid | mesh
    size: tuple = ()                            # box: full sizes (x, y, z); cylinder/capsule: (radius, length); sphere: (radius,); ellipsoid: semi-axes
    pos: tuple = (0.0, 0.0, 0.0)
    quat: tuple = IDENTITY
    mesh: str | None = None
    role: str = "visual"                        # visual | collision | solid (drawn and collides)
    material: str | None = None
    rgba: tuple | None = None
    name: str | None = None
    mass: bool | None = None                    # counts towards the body's mass distribution (default: drawn geoms)
    friction: tuple | None = None
    condim: int | None = None
    margin_mm: float | None = None
    priority: int | None = None                 # contact parameters of this geom win over those of a lower priority

    def counts_for_mass(self) -> bool:
        return self.role != "collision" if self.mass is None else self.mass


@dataclass
class Joint:
    name: str
    type: str                                   # slide | hinge | ball | free
    axis: tuple = (0.0, 0.0, 1.0)
    pos: tuple = (0.0, 0.0, 0.0)
    range: tuple | None = None                  # mm for slides, radians for hinges and ball joints
    stiffness: float = 0.0                      # N/m or N m/rad
    springref: float = 0.0                      # mm or radians
    damping: float = 0.0
    frictionloss: float = 0.0
    armature: float = 0.0
    stiff_limit: bool = False                   # a hard end stop (short time constant), for parts held against it by a spring or by gravity
    role: str = ""                              # door | lid | tray | button | knob | axis | rotor | cap ... (goes to meta.json)


@dataclass
class Site:
    name: str
    pos: tuple = (0.0, 0.0, 0.0)
    quat: tuple = IDENTITY
    size_mm: float | None = None


@dataclass
class Body:
    name: str
    pos: tuple = (0.0, 0.0, 0.0)
    quat: tuple = IDENTITY
    mass_g: float | None = None
    joints: list[Joint] = field(default_factory=list)
    geoms: list[Geom] = field(default_factory=list)
    sites: list[Site] = field(default_factory=list)
    children: list["Body"] = field(default_factory=list)
    gravcomp: float = 0.0

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class Texture:
    name: str
    width: int
    height: int
    rgb: tuple = (0.03, 0.08, 0.05)
    emission: float = 0.7


@dataclass
class Asset:
    id: str
    kind: str                                   # labware | item | instrument
    root: Body
    meshes: dict[str, M.Mesh] = field(default_factory=dict)       # millimetres
    textures: dict[str, Texture] = field(default_factory=dict)    # repaintable 2-D textures (displays)
    images: dict[str, bytes] = field(default_factory=dict)        # printed textures (labels): name -> PNG bytes, written as <name>.png
    image_glow: dict[str, float] = field(default_factory=dict)    # emission of a printed texture that is lit from behind (a screen)
    equalities: list[dict] = field(default_factory=list)          # {"joint1", "joint2", "polycoef"}
    actuators: list[dict] = field(default_factory=list)           # {"name", "joint", "kind", "kp", "kv", "ctrlrange", "forcerange"}
    excludes: list[tuple[str, str]] = field(default_factory=list)
    tendons: list[dict] = field(default_factory=list)             # {"name", "joint", "stiffness", "springlength" (m), "damping"}
    numerics: dict[str, tuple] = field(default_factory=dict)      # custom numeric data the helpers read back from a model
    meta: dict = field(default_factory=dict)

    def materials(self) -> list[str]:
        used = {g.material for b in self.root.walk() for g in b.geoms
                if g.material and g.material in MATERIALS and g.role != "collision"}
        return sorted(used)


# ----------------------------------------------------------------------------------------------------------------------
# Mass properties
# ----------------------------------------------------------------------------------------------------------------------

def geom_mesh(asset: Asset, g: Geom) -> M.Mesh:
    """The geom as a closed mesh in the body frame (millimetres)."""
    if g.type == "box":
        m = M.box(g.size)
    elif g.type == "cylinder":
        m = M.cylinder(g.size[0], -g.size[1] / 2.0, g.size[1] / 2.0, 48)
    elif g.type == "capsule":
        r, half = g.size[0], g.size[1] / 2.0
        arc = [(r * math.cos(a), r * math.sin(a)) for a in np.linspace(-math.pi / 2, math.pi / 2, 9)[1:-1]]
        prof = [(0.0, -half - r)] + [(x, -half + z) for x, z in arc if z < 0] + [(r, -half), (r, half)] \
            + [(x, half + z) for x, z in arc if z > 0] + [(0.0, half + r)]
        m = M.revolve(prof, 32)
    elif g.type == "sphere":
        r = g.size[0]
        m = M.revolve([(r * math.cos(a), r * math.sin(a)) if 0 < i < 12 else (0.0, r * math.sin(a))
                       for i, a in enumerate(np.linspace(-math.pi / 2, math.pi / 2, 13))], 24)
    elif g.type == "ellipsoid":
        unit = M.revolve([(math.cos(a), math.sin(a)) if 0 < i < 12 else (0.0, math.sin(a))
                          for i, a in enumerate(np.linspace(-math.pi / 2, math.pi / 2, 13))], 24)
        m = M.Mesh(unit.v * np.asarray(g.size, dtype=np.float64), unit.f)
    elif g.type == "mesh":
        m = asset.meshes[g.mesh]
    else:
        raise ValueError(f"no mass model for geom type {g.type!r}")
    return m.transformed(quat_to_mat(g.quat), g.pos)


def body_inertial(asset: Asset, body: Body) -> dict | None:
    """Mass (kg), centre of mass (m) and inertia about it (kg m^2) of one body, from its mass-carrying geoms.

    The body's `mass_g` is spread uniformly over the union volume of those geoms (overlaps count twice).
    """
    parts = [geom_mesh(asset, g) for g in body.geoms if g.counts_for_mass()]
    if not parts or body.mass_g is None:
        return None
    vol, first, second = 0.0, np.zeros(3), np.zeros((3, 3))
    for p in parts:
        v, c, i = M.mass_properties(p)
        vol += v
        first += v * c
        # second moment about the body origin: I_origin = I_com + v * (|c|^2 1 - c c^T)
        second += i + v * (np.dot(c, c) * np.eye(3) - np.outer(c, c))
    com = first / vol
    inertia = second - vol * (np.dot(com, com) * np.eye(3) - np.outer(com, com))
    density = body.mass_g * 1e-3 / vol                                  # kg per mm^3
    return {"mass": body.mass_g * 1e-3, "com": com * MM, "inertia": inertia * density * MM * MM, "volume_mm3": vol}


# ----------------------------------------------------------------------------------------------------------------------
# MJCF
# ----------------------------------------------------------------------------------------------------------------------

def _attrs(pairs: list[tuple[str, str | None]]) -> str:
    return "".join(f' {k}="{v}"' for k, v in pairs if v is not None)


def _pose(pos: Sequence[float], quat: Sequence[float]) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    if any(abs(p) > 1e-12 for p in pos):
        out.append(("pos", vec(pos, MM)))
    if tuple(round(q, 12) for q in quat) != IDENTITY:
        out.append(("quat", vec(quat)))
    return out


def mesh_name(asset: Asset, name: str) -> str:
    return f"{asset.id}.{name}"


def asset_elements(asset: Asset, prefix: str = "", inline: bool = False, with_meshes: bool = True) -> list[str]:
    """`<asset>` children for the meshes and the display textures of one asset instance."""
    out = []
    if with_meshes:
        for name in sorted(asset.meshes):
            if inline:
                # an inline mesh carries one normal per vertex, so vertices are duplicated at sharp edges
                m, normals = M.split_for_drawing(asset.meshes[name].scaled(MM))
                a = [("name", mesh_name(asset, name)),
                     ("vertex", " ".join(M._num(x, 6) for x in m.v.reshape(-1))),
                     ("normal", " ".join(M._num(x, 5) for x in normals.reshape(-1))),
                     ("face", " ".join(str(int(i)) for i in m.f.reshape(-1)))]
                if m.uv is not None:
                    a.append(("texcoord", " ".join(M._num(x, 6) for x in m.uv.reshape(-1))))
            else:
                a = [("name", mesh_name(asset, name)), ("file", f"{name}.obj")]
            out.append(f"<mesh{_attrs(a)}/>")
    for name in sorted(asset.textures):
        t = asset.textures[name]
        out.append(f'<texture name="{prefix}{name}" type="2d" builtin="flat" width="{t.width}" height="{t.height}" '
                   f'rgb1="{vec(t.rgb)}" rgb2="{vec(t.rgb)}"/>')
        out.append(f'<material name="{prefix}{name}" texture="{prefix}{name}" emission="{num(t.emission)}" specular="0" shininess="0"/>')
    for name in sorted(asset.images):
        full = mesh_name(asset, name)
        out.append(f'<texture name="{full}" type="2d" file="{name}.png"/>')
        glow = f' emission="{num(asset.image_glow[name])}"' if name in asset.image_glow else ""
        out.append(f'<material name="{full}" texture="{full}" specular="0.05" shininess="0.1"{glow}/>')
    return out


def material_elements(names: Sequence[str]) -> list[str]:
    out = []
    for n in sorted(set(names)):
        rgba, spec, shin, refl = MATERIALS[n][:4]
        glow = f' emission="{num(MATERIALS[n][4])}"' if len(MATERIALS[n]) > 4 else ""
        out.append(f'<material name="{n}" rgba="{vec(rgba)}" specular="{num(spec)}" shininess="{num(shin)}" '
                   f'reflectance="{num(refl)}"{glow}/>')
    return out


def _geom(asset: Asset, g: Geom, prefix: str, overrides: dict | None = None) -> str:
    if overrides and g.name in overrides:                   # per-instance changes (e.g. a liquid level set when a scene is built)
        g = replace(g, **overrides[g.name])
    a: list[tuple[str, str | None]] = []
    if g.name:
        a.append(("name", prefix + g.name))
    a.append(("class", {"visual": "ese_visual", "collision": "ese_collision", "solid": "ese_solid"}[g.role]))
    a.append(("type", g.type))
    if g.type == "box":
        a.append(("size", vec([s / 2.0 for s in g.size], MM)))
    elif g.type in ("cylinder", "capsule"):
        a.append(("size", vec([g.size[0], g.size[1] / 2.0], MM)))
    elif g.type == "sphere":
        a.append(("size", vec([g.size[0]], MM)))
    elif g.type == "ellipsoid":
        a.append(("size", vec(g.size, MM)))
    elif g.type == "mesh":
        a.append(("mesh", mesh_name(asset, g.mesh)))
    a += _pose(g.pos, g.quat)
    if g.role != "collision":
        if g.material in asset.textures:
            a.append(("material", prefix + g.material))
        elif g.material in asset.images:
            a.append(("material", mesh_name(asset, g.material)))
        elif g.material:
            a.append(("material", g.material))
        if g.rgba is not None:
            a.append(("rgba", vec(g.rgba)))
    if g.friction is not None:
        a.append(("friction", vec(g.friction)))
    if g.condim is not None:
        a.append(("condim", str(g.condim)))
    if g.margin_mm is not None:
        a.append(("margin", num(g.margin_mm * MM)))
    if g.priority is not None:
        a.append(("priority", str(int(g.priority))))
    return f"<geom{_attrs(a)}/>"


def _joint(j: Joint, prefix: str) -> str:
    if j.type == "free":
        return f'<freejoint name="{prefix}{j.name}"/>'
    s = MM if j.type == "slide" else 1.0
    a: list[tuple[str, str | None]] = [("name", prefix + j.name), ("type", j.type)]
    if j.type != "ball":
        a.append(("axis", vec(j.axis)))
    if any(abs(p) > 1e-12 for p in j.pos):
        a.append(("pos", vec(j.pos, MM)))
    if j.range is not None:
        a.append(("range", vec(j.range, s)))
    if j.stiffness:
        a.append(("stiffness", num(j.stiffness)))
        a.append(("springref", num(j.springref * s)))
    if j.damping:
        a.append(("damping", num(j.damping)))
    if j.frictionloss:
        a.append(("frictionloss", num(j.frictionloss)))
    if j.armature:
        a.append(("armature", num(j.armature)))
    if j.stiff_limit:
        a.append(("solreflimit", "0.004 1"))
    return f"<joint{_attrs(a)}/>"


def body_element(asset: Asset, prefix: str = "", name: str | None = None, pos: Sequence[float] = (0, 0, 0),
                 quat: Sequence[float] = IDENTITY, free: bool = False, indent: str = "    ", overrides: dict | None = None,
                 guide: dict | None = None) -> str:
    """The `<body>` tree of an asset instance. `pos` (mm) and `quat` place the root body in its parent."""

    def emit(b: Body, ind: str, root: bool) -> list[str]:
        a: list[tuple[str, str | None]] = [("name", (name or asset.id) if root else prefix + b.name)]
        a += _pose(np.asarray(b.pos) + np.asarray(pos) if root else b.pos, quat_mul(quat, b.quat) if root else b.quat)
        if b.gravcomp or (root and guide):
            a.append(("gravcomp", num(1.0 if (root and guide) else b.gravcomp)))
        lines = [f"{ind}<body{_attrs(a)}>"]
        if root and guide:                                   # held on one axis instead of free: a hand, a rail, a test rig
            lines.append(f'{ind}  <joint name="{prefix}{guide.get("name", "guide")}" type="{guide.get("type", "slide")}" '
                         f'axis="{vec(guide.get("axis", (0.0, 0.0, 1.0)))}" damping="{num(guide.get("damping", 1.0))}"/>')
        elif root and free:
            lines.append(f'{ind}  <freejoint name="{prefix}free"/>')
        inert = body_inertial(asset, b)
        if inert is not None:
            i = inert["inertia"]
            full = [i[0, 0], i[1, 1], i[2, 2], i[0, 1], i[0, 2], i[1, 2]]
            lines.append(f'{ind}  <inertial pos="{vec(inert["com"])}" mass="{num(inert["mass"])}" fullinertia="{vec(full)}"/>')
        lines += [f"{ind}  {_joint(j, prefix)}" for j in b.joints]
        lines += [f"{ind}  {_geom(asset, g, prefix, overrides)}" for g in b.geoms]
        for s in b.sites:
            sa: list[tuple[str, str | None]] = [("name", prefix + s.name), ("class", "ese_site")] + _pose(s.pos, s.quat)
            if s.size_mm is not None:
                sa.append(("size", num(s.size_mm * MM)))
            lines.append(f"{ind}  <site{_attrs(sa)}/>")
        for c in b.children:
            lines += emit(c, ind + "  ", False)
        lines.append(f"{ind}</body>")
        return lines

    return "\n".join(emit(asset.root, indent, True))


def extra_elements(asset: Asset, prefix: str = "", root_name: str | None = None) -> dict[str, list[str]]:
    """`<equality>`, `<actuator>` and `<contact>` children of an asset instance."""
    def body_ref(n: str) -> str:
        return (root_name or asset.id) if n == asset.root.name else prefix + n

    # MuJoCo sizes the softness of a joint coupling from the inverse inertias of both joints, without the gear ratio
    # between them. For a thread (metres per radian) that makes the coupling far too soft, hence the near-rigid
    # impedance and the short time constant.
    eq = [f'<joint name="{prefix}{e["name"]}" joint1="{prefix}{e["joint1"]}" joint2="{prefix}{e["joint2"]}" '
          f'polycoef="{vec(e["polycoef"])}" solref="0.004 1" solimp="0.9999 0.9999 0.001 0.5 2"/>' for e in asset.equalities]
    act = []
    for a in asset.actuators:
        attrs: list[tuple[str, str | None]] = [("name", prefix + a["name"]), ("joint", prefix + a["joint"])]
        if a.get("kind", "position") == "position":
            attrs += [("kp", num(a["kp"])), ("kv", num(a["kv"]))]
        else:
            attrs += [("kv", num(a["kv"]))]
        if "ctrlrange" in a:
            attrs.append(("ctrlrange", vec(a["ctrlrange"])))
        if "forcerange" in a:
            attrs.append(("forcerange", vec(a["forcerange"])))
        act.append(f'<{a.get("kind", "position")}{_attrs(attrs)}/>')
    # A moving part never collides with the body it is mounted on. MuJoCo applies that rule by itself only when the
    # parent can move, and instruments are fixed to the world, so every parent-child pair is excluded explicitly.
    pairs = [(b.name, c.name) for b in asset.root.walk() for c in b.children]
    pairs += [p for p in asset.excludes if p not in pairs and (p[1], p[0]) not in pairs]
    con = [f'<exclude body1="{body_ref(b1)}" body2="{body_ref(b2)}"/>' for b1, b2 in pairs]
    ten = []
    for t in asset.tendons:
        lo, hi = t["springlength"]
        ten.append(f'<fixed name="{prefix}{t["name"]}" stiffness="{num(t["stiffness"])}" springlength="{num(lo)} {num(hi)}" '
                   f'damping="{num(t.get("damping", 0.0))}"><joint joint="{prefix}{t["joint"]}" coef="1"/></fixed>')
    cus = [f'<numeric name="{prefix}{n}" data="{vec(asset.numerics[n])}"/>' for n in sorted(asset.numerics)]
    return {"contact": con, "equality": eq, "tendon": ten, "actuator": act, "custom": cus}


def standalone_xml(asset: Asset) -> str:
    """A complete MJCF file for one asset, with its meshes as OBJ files next to it."""
    return document_xml(asset)


def document_xml(asset: Asset, root_name: str | None = None) -> str:
    """The same, with the top-level body called `root_name` (default: the asset's id)."""
    out = [f'<mujoco model="{asset.id}">', '  <compiler angle="radian" autolimits="true" meshdir="." texturedir="."/>',
           DEFAULTS.rstrip("\n")]
    assets = material_elements(asset.materials()) + asset_elements(asset)
    if assets:
        out.append("  <asset>")
        out += [f"    {a}" for a in assets]
        out.append("  </asset>")
    out.append("  <worldbody>")
    out.append(body_element(asset, name=root_name))
    out.append("  </worldbody>")
    for tag, items in extra_elements(asset, root_name=root_name).items():
        if items:
            out.append(f"  <{tag}>")
            out += [f"    {i}" for i in items]
            out.append(f"  </{tag}>")
    out.append("</mujoco>")
    return "\n".join(out) + "\n"
