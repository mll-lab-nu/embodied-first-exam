"""The builder the catalogue kinds are written with.

A kind is a function that takes a `Kit` and its parameters and adds shapes, sites, zones, labels and controls to it.
Geometry is given in millimetres and grams (as in `model.py`); what goes into `meta` is in metres and kilograms.

Conventions every kind follows:
- origin at the centre of the footprint on the underside, `+z` up, the front (label, door, controls) towards `-y`;
- drawn shapes (`shape`, `vis`) do not collide; collision shapes (`col`, `solid`, `ring`, `foot`) are primitives;
- what stands on the table stands on boxes (box-box contacts keep still; a cylinder face on a box does not);
- the mass of a body is spread over its collision shapes.
"""
from __future__ import annotations

import json
import math
from typing import Sequence

import numpy as np

from . import labels as L
from . import mesh as M
from .model import (IDENTITY, MATERIALS, Asset, Body, Geom, Joint, Site, document_xml, geom_mesh, mat_to_quat,
                    quat_axis_angle, quat_from_z, quat_mul, quat_to_mat)

MM = 1e-3
# Paper and card on a table top: sliding friction about 0.4 (the default of the generated solids, 0.9, is that of rubber
# or of a rough surface). Given with priority 1, so that it is what such a thing has against the table, while the
# finger pads (priority 1 too, friction 1.0) still grip it with theirs: of two equal priorities MuJoCo takes the larger.
PAPER_FRICTION = {"friction": (0.4, 0.005, 0.0001), "priority": 1}
# zones with these beginnings are places where a thing can be put down (the same list as
# `robosafebench.hazard.state.PLACE_NAMES`); every zone built here says so explicitly in its `place` entry
PLACE_NAMES = ("surface", "slot", "inside", "top", "cavity", "socket", "drum", "bin", "tray", "shelf", "rack", "drain",
               "hopper", "nest", "day", "above")

# colour of the drawn fill of a vessel, by substance
SUBSTANCES = {
    "water": (0.55, 0.75, 0.92, 0.45), "juice": (0.96, 0.62, 0.10, 0.85), "milk": (0.97, 0.97, 0.94, 0.95),
    "coffee": (0.24, 0.14, 0.08, 0.92), "tea": (0.62, 0.36, 0.12, 0.75), "soup": (0.82, 0.36, 0.14, 0.95),
    "oil": (0.90, 0.78, 0.22, 0.70), "bleach": (0.88, 0.92, 0.70, 0.55), "ammonia": (0.75, 0.86, 0.92, 0.5),
    "cleaner": (0.35, 0.65, 0.95, 0.65), "detergent": (0.25, 0.55, 0.90, 0.85), "acid": (0.93, 0.93, 0.70, 0.45),
    "solvent": (0.85, 0.90, 0.93, 0.35), "ethanol": (0.85, 0.90, 0.93, 0.35), "wine": (0.45, 0.05, 0.12, 0.85),
    "soda": (0.30, 0.16, 0.08, 0.8), "waste": (0.45, 0.40, 0.25, 0.8), "pills": (0.95, 0.95, 0.90, 1.0),
    "salt": (0.96, 0.96, 0.96, 1.0), "sugar": (0.97, 0.96, 0.92, 1.0), "kibble": (0.50, 0.33, 0.18, 1.0),
    "copper": (0.10, 0.45, 0.88, 0.80),          # copper sulfate solution: clear blue
    "soil": (0.28, 0.20, 0.14, 1.0), "sodium": (0.80, 0.80, 0.78, 1.0), "sample": (0.75, 0.15, 0.15, 0.8),
    "paper": (0.93, 0.92, 0.88, 1.0),
    "blocking_buffer": (0.95, 0.94, 0.90, 0.96),  # 0.5.4: skimmed milk in buffer (the blocking step of a western blot): milky, opaque
}


def rot_x(deg: float) -> np.ndarray:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def rot_y(deg: float) -> np.ndarray:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def rot_z(deg: float) -> np.ndarray:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def qz(deg: float) -> tuple:
    return quat_axis_angle((0, 0, 1), math.radians(deg))


def qy(deg: float) -> tuple:
    return quat_axis_angle((0, 1, 0), math.radians(deg))


def qx(deg: float) -> tuple:
    return quat_axis_angle((1, 0, 0), math.radians(deg))


def rounded_rect(sx: float, sy: float, r: float, n: int = 5, center=(0.0, 0.0)) -> np.ndarray:
    """A counter-clockwise rectangle with rounded corners."""
    r = min(r, sx / 2.0 - 1e-6, sy / 2.0 - 1e-6)
    if r <= 0:
        return M.rect(sx, sy, center)
    pts = []
    for (cx, cy), a0 in (((sx / 2 - r, sy / 2 - r), 0.0), ((-sx / 2 + r, sy / 2 - r), 90.0),
                         ((-sx / 2 + r, -sy / 2 + r), 180.0), ((sx / 2 - r, -sy / 2 + r), 270.0)):
        for k in range(n + 1):
            a = math.radians(a0 + 90.0 * k / n)
            pts.append((center[0] + cx + r * math.cos(a), center[1] + cy + r * math.sin(a)))
    return np.array(pts)


def rbox(sx: float, sy: float, sz: float, r: float = 3.0, center=(0.0, 0.0, 0.0), n: int = 4) -> M.Mesh:
    """A box with its vertical edges rounded, centred at `center`."""
    return M.extrude(rounded_rect(sx, sy, r, n, center[:2]), center[2] - sz / 2.0, center[2] + sz / 2.0)


def arc_points(r: float, a0: float, a1: float, n: int, center=(0.0, 0.0)) -> list[tuple[float, float]]:
    return [(center[0] + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
             center[1] + r * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(n + 1)]


def shell_profile(outer: Sequence[Sequence[float]], wall: float, floor: float) -> tuple[list, list]:
    """The closed (r, z) outline of an open vessel and its inner outline.

    `outer` runs from the edge of the base up to the rim. The wall is `wall` thick measured radially and the bottom
    `floor` thick. Returns `(profile for revolve, inner outline from the floor up to the rim)`.
    """
    outer = [(float(r), float(z)) for r, z in outer]
    zb, zf = outer[0][1], outer[0][1] + floor

    def r_at(z: float) -> float:
        for (r0, z0), (r1, z1) in zip(outer, outer[1:]):
            if z0 <= z <= z1 and z1 > z0:
                return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
        return outer[-1][0]

    inner = [(max(r_at(zf) - wall, 1.0), zf)] + [(max(r - wall, 1.0), z) for r, z in outer if z > zf + 1e-6]
    profile = [(0.0, zb)] + outer + inner[::-1] + [(0.0, zf)]
    return profile, inner


def profile_volume(inner: Sequence[Sequence[float]], level: float | None = None) -> float:
    """Volume (mm^3) inside an inner outline up to height `level` above its lowest point (default: to the rim)."""
    vol = 0.0
    z_base = inner[0][1]
    top = inner[-1][1] if level is None else z_base + level
    for (r0, z0), (r1, z1) in zip(inner, inner[1:]):
        if z0 >= top:
            break
        if z1 > top:
            r1 = r0 + (r1 - r0) * (top - z0) / (z1 - z0)
            z1 = top
        vol += math.pi * (z1 - z0) * (r0 * r0 + r0 * r1 + r1 * r1) / 3.0
    return vol


def level_for_volume(inner: Sequence[Sequence[float]], volume: float) -> float:
    """Height of the surface above the inside bottom for a volume in mm^3 (clamped to the rim)."""
    depth = inner[-1][1] - inner[0][1]
    if volume <= 0:
        return 0.0
    if volume >= profile_volume(inner):
        return depth
    lo, hi = 0.0, depth
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if profile_volume(inner, mid) < volume:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def radius_at(inner: Sequence[Sequence[float]], level: float) -> float:
    z = inner[0][1] + level
    for (r0, z0), (r1, z1) in zip(inner, inner[1:]):
        if z0 <= z <= z1 and z1 > z0:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return inner[-1][0]


class Kit:
    def __init__(self, kind: str):
        self.kind = kind
        self.root = Body("body")
        self.asset = Asset(id=kind, kind="prop", root=self.root)
        self.bodies: dict[str, Body] = {"body": self.root}
        self.parents: dict[str, str] = {}
        self.total_g: float | None = None
        self.fixed = False
        self.tags: list[str] = []
        self.zones: dict[str, dict] = {}
        self.grasps: list[dict] = []
        self.controls: dict[str, dict] = {}
        self.looks: dict[str, dict] = {}
        self.labels: list[dict] = []
        self.doors: dict[str, dict] = {}
        self.vessel: dict | None = None
        self.contents: dict[str, float] = {}
        self.extra: dict = {}
        self._decor: set[int] = set()
        self._named: dict[str, Geom] = {}
        self._count = {"mesh": 0, "label": 0, "geom": 0}

    # ---- colours -------------------------------------------------------------------------------------------------------
    @staticmethod
    def paint(color, finish: str = "satin", alpha: float | None = None) -> tuple[str, tuple | None]:
        """(material, rgba) for a colour: a material name of `model.MATERIALS`, a colour name, or numbers."""
        if isinstance(color, str) and color in MATERIALS and color not in ("matte", "satin", "gloss", "metal", "glow"):
            if alpha is None:
                return color, None
            return color, MATERIALS[color][0][:3] + (float(alpha),)
        rgba = L.rgba01(color)
        if alpha is not None:
            rgba = rgba[:3] + (float(alpha),)
        if rgba[:3] == (0.5, 0.5, 0.5) and rgba[3] == 1.0:      # MuJoCo reads exactly this as "no colour given"
            rgba = (0.502, 0.5, 0.5, 1.0)
        return finish, rgba

    # ---- bodies --------------------------------------------------------------------------------------------------------
    def body(self, name: str | Body | None) -> Body:
        if isinstance(name, Body):
            return name
        return self.bodies[name or "body"]

    def part(self, name: str, pos=(0.0, 0.0, 0.0), quat=IDENTITY, mass_g: float = 10.0, parent: str | None = None) -> Body:
        """A moving part (door, drawer, button): a child body. Add joints to `part.joints`."""
        b = Body(name, tuple(float(v) for v in pos), tuple(quat), mass_g=float(mass_g))
        self.body(parent).children.append(b)
        self.bodies[name] = b
        self.parents[name] = parent or "body"
        return b

    def mass(self, grams: float) -> None:
        """Total mass of the object, moving parts included."""
        self.total_g = float(grams)

    # ---- shapes --------------------------------------------------------------------------------------------------------
    def _add(self, g: Geom, body, decor: bool) -> Geom:
        self.body(body).geoms.append(g)
        if decor:
            self._decor.add(id(g))
        if g.name:
            if g.name in self._named:
                raise ValueError(f"{self.kind}: two geoms called {g.name!r}")
            self._named[g.name] = g
        return g

    def shape(self, mesh: M.Mesh, color="grey", *, name: str | None = None, body=None, pos=(0.0, 0.0, 0.0), quat=IDENTITY,
              finish: str = "satin", alpha: float | None = None, decor: bool = False) -> Geom:
        """A drawn mesh (no collision, no mass)."""
        mname = f"m{self._count['mesh']}"
        self._count["mesh"] += 1
        self.asset.meshes[mname] = mesh
        material, rgba = self.paint(color, finish, alpha)
        return self._add(Geom("mesh", mesh=mname, pos=tuple(pos), quat=tuple(quat), role="visual", material=material,
                              rgba=rgba, name=name, mass=False), body, decor)

    def vis(self, type: str, size, pos=(0.0, 0.0, 0.0), color="grey", *, quat=IDENTITY, name: str | None = None, body=None,
            finish: str = "satin", alpha: float | None = None, decor: bool = False) -> Geom:
        """A drawn primitive (no collision, no mass)."""
        material, rgba = self.paint(color, finish, alpha)
        return self._add(Geom(type, tuple(size), tuple(pos), tuple(quat), role="visual", material=material, rgba=rgba,
                              name=name, mass=False), body, decor)

    def col(self, type: str, size, pos=(0.0, 0.0, 0.0), *, quat=IDENTITY, name: str | None = None, body=None,
            friction: tuple | None = None, mass: bool = True, priority: int | None = None) -> Geom:
        """A collision primitive that is not drawn."""
        return self._add(Geom(type, tuple(size), tuple(pos), tuple(quat), role="collision", name=name, mass=mass,
                              friction=friction, priority=priority), body, False)

    def solid(self, type: str, size, pos=(0.0, 0.0, 0.0), color="grey", *, quat=IDENTITY, name: str | None = None,
              body=None, finish: str = "satin", alpha: float | None = None, friction: tuple | None = None,
              mass: bool = True, priority: int | None = None) -> Geom:
        """A primitive that is drawn and collides."""
        material, rgba = self.paint(color, finish, alpha)
        return self._add(Geom(type, tuple(size), tuple(pos), tuple(quat), role="solid", material=material, rgba=rgba,
                              name=name, mass=mass, friction=friction, priority=priority), body, False)

    def foot(self, radius: float, z0: float = 0.0, height: float = 3.0, *, body=None, name: str | None = None) -> None:
        """What a round thing stands on: two square plates turned 45 degrees to each other, corners on the circle."""
        side = radius * math.sqrt(2.0)
        for k in range(2):
            self.col("box", (side, side, height), (0.0, 0.0, z0 + height / 2.0), quat=qz(45.0 * k), body=body,
                     name=None if name is None else f"{name}_{k}")

    def round_body(self, radius: float, z0: float, z1: float, *, body=None, name: str | None = None) -> None:
        """Collision of a closed round container: a cylinder that stops half a millimetre above its feet."""
        self.foot(radius, z0, min(3.0, (z1 - z0) / 2.0), body=body)
        self.col("cylinder", (radius, z1 - z0 - 0.5), (0.0, 0.0, (z0 + z1 + 0.5) / 2.0), body=body, name=name)

    def ring(self, r0: float, r1: float, z0: float, z1: float, wall: float, n: int = 12, *, body=None,
             name: str | None = None, center=(0.0, 0.0)) -> None:
        """Collision of a round wall: `n` boxes around the axis, outer radius `r0` at `z0` and `r1` at `z1`."""
        tilt = math.atan2(r1 - r0, z1 - z0)
        slant = math.hypot(r1 - r0, z1 - z0)
        width = 2.0 * max(r0, r1) * math.tan(math.pi / n) * 1.02
        rc = (r0 + r1) / 2.0 - wall / 2.0 * math.cos(tilt)
        zc = (z0 + z1) / 2.0 + wall / 2.0 * math.sin(tilt)
        for i in range(n):
            a = 360.0 * i / n
            q = quat_mul(qz(a), qy(math.degrees(tilt)))
            self.col("box", (wall, width, slant), (center[0] + rc * math.cos(math.radians(a)),
                                                   center[1] + rc * math.sin(math.radians(a)), zc), quat=q, body=body,
                     name=None if name is None else f"{name}_{i}")

    def tube(self, points: Sequence[Sequence[float]], radius: float, color="black", *, solid: bool = False, body=None,
             finish: str = "satin", decor: bool = False, name: str | None = None) -> None:
        """Capsules joining consecutive points: a cord, a wire handle, a limb."""
        pts = [np.asarray(p, dtype=np.float64) for p in points]
        for i, (a, b) in enumerate(zip(pts, pts[1:])):
            d = b - a
            length = float(np.linalg.norm(d))
            if length < 1e-6:
                continue
            args = dict(quat=quat_from_z(d), body=body, finish=finish, name=None if name is None else f"{name}_{i}")
            if solid:
                self.solid("capsule", (radius, length), tuple((a + b) / 2.0), color, **args)
            else:
                self.vis("capsule", (radius, length), tuple((a + b) / 2.0), color, decor=decor, **args)

    def cord(self, start: Sequence[float], end: Sequence[float] | None = None, *, radius: float = 3.0, color="black",
             plug: bool | str = True, socket_yaw: float = 0.0, socket_terminal=None) -> None:
        """A power cord lying on the table from `start` (on the appliance) to a plug. A picture only: it does not
        collide and is left out of the asset's metadata bounding box. `plug="grommet"` (0.5.4): the cord runs into a cable grommet in
        the table top at its end, to a socket under the table: the appliance is plugged in. It is drawn with as many
        shapes as the loose plug (three), so that a scene's other shapes keep their indices. `plug="socket"` seats
        the terminal in a receptacle whose top face is `socket_terminal` (or `end`); `socket_yaw` aligns its prongs. These are visual
        connections; physical insertion is modelled separately by `State.add_plug`."""
        if plug not in (True, False, "grommet", "socket"):
            raise ValueError("plug: grommet, socket, True (loose plug), or False")
        s = np.asarray(start, dtype=np.float64)
        e = np.asarray(end if end is not None else (s[0] + 90.0, s[1] + 160.0, radius), dtype=np.float64)
        z = radius
        mid1 = np.array([s[0], s[1] + 25.0, z])
        mid2 = np.array([(s[0] + e[0]) / 2.0 + 30.0, (s[1] + e[1]) / 2.0, z])
        self.tube([s, mid1, mid2, e], radius, color, decor=True, finish="matte")
        terminal = np.asarray(socket_terminal, dtype=float) if socket_terminal is not None else e
        path = [s, mid1, mid2, e]
        if plug == "socket":
            # Rise at the existing endpoint before crossing above the supply;
            # do not lay new wire across additional tabletop spill regions.
            path.extend([np.array([e[0], e[1], max(e[2], terminal[2] + 18.0)]), terminal + [0, 0, 18.0]])
        self.extra["power_connection"] = {
            "kind": "fixed_supply" if plug == "grommet" else "socket" if plug == "socket" else "loose" if plug else "unshown",
            "disconnectable": False,
            "path": [[round(float(v) * MM, 6) for v in p] for p in path],
            "terminal": [round(float(v) * MM, 6) for v in terminal],
        }
        if plug == "grommet":
            self.vis("cylinder", (radius + 13.0, 1.0), (e[0], e[1], 1.0), "dark_grey", decor=True, finish="satin")
            self.vis("cylinder", (radius + 6.0, 0.6), (e[0], e[1], 2.2), "black", decor=True, finish="matte")
            self.vis("capsule", (radius, 6.0), (e[0], e[1], z - 3.0), color, decor=True, finish="matte")
        elif plug == "socket":
            # The endpoint is the receptacle's top face. Prongs enter it; the
            # insulated housing remains above it. Keep the original three geoms.
            q = qz(socket_yaw)
            rotation = quat_to_mat(q)
            # Keep the original cord arc. Only its terminal stub goes up into
            # the receptacle, in the housing's visual geom (no extra geom ids).
            pieces = [M.box((30.0, 26.0, 16.0), (0, 0, 10.0)).transformed(rotation, terminal)]
            for a, b in zip(path[3:], path[4:]):
                delta = b - a
                length = float(np.linalg.norm(delta))
                if length > 1e-6:
                    pieces.append(M.cylinder(radius, 0, length, 12).transformed(quat_to_mat(quat_from_z(delta)), a))
            self.shape(M.merge(pieces), color, decor=True, finish="matte")
            for sy in (-9.5, 9.5):
                self.vis("box", (1.5, 2.0, 6.0), tuple(terminal + rotation @ [0, sy, -1.0]), "steel", quat=q, decor=True)
        elif plug:
            d = e - mid2
            yaw = math.degrees(math.atan2(d[1], d[0]))
            q = qz(yaw)
            r = quat_to_mat(q)
            self.vis("box", (30.0, 22.0, 16.0), tuple(e + r @ np.array([15.0, 0.0, 8.0 - z])), color, quat=q, decor=True,
                     finish="matte")
            for sy in (-6.0, 6.0):
                self.vis("box", (16.0, 1.5, 6.0), tuple(e + r @ np.array([38.0, sy, 8.0 - z])), "steel", quat=q, decor=True)

    # ---- named points and volumes --------------------------------------------------------------------------------------
    def site(self, name: str, pos, quat=IDENTITY, body=None) -> None:
        b = self.body(body)
        if any(s.name == name for bb in self.bodies.values() for s in bb.sites):
            raise ValueError(f"{self.kind}: two sites called {name!r}")
        b.sites.append(Site(name, tuple(float(v) for v in pos), tuple(quat)))

    def zone(self, name: str, pos, shape: str, size, quat=IDENTITY, body=None, place: bool | None = None,
             open: bool = False) -> None:
        """A named volume centred on a site of the same name. `size` in millimetres: box (x, y, z) full extents;
        cylinder (radius, height) along the site's z; sphere (radius,). `place`: a thing can be put down there, on the
        zone's lower face (default: by the zone's name, see `PLACE_NAMES`). `open`: the place is made of bars with
        gaps between them (the rails of a rack), so that what is seen through it from above is not what is meant."""
        if shape not in ("box", "cylinder", "sphere"):
            raise ValueError(shape)
        self.site(name, pos, quat, body)
        self.zones[name] = {"site": name, "shape": shape, "size": [round(float(v) * MM, 6) for v in size],
                            "place": name.startswith(PLACE_NAMES) if place is None else bool(place)}
        if open:
            self.zones[name]["open"] = True

    def grasp(self, name: str, type: str, pos, width: float, yaw_deg: float = 0.0, quat=None) -> None:
        """Where a parallel gripper may hold the object. The frame's +y is the closing direction; for a top grasp its
        +z is the object's up, for a side grasp +z is the axis the hand keeps square to. `yaw_deg` turns the frame
        about z (0: the fingers close along y)."""
        if type not in ("top", "side"):
            raise ValueError(type)
        q = tuple(quat) if quat is not None else qz(yaw_deg)
        site = f"grip_{len(self.grasps)}"
        self.site(site, pos, q)
        self.grasps.append({"name": name, "type": type, "pos": [round(float(v) * MM, 6) for v in pos],
                            "quat": [round(float(v), 9) for v in q], "width": round(float(width) * MM, 6), "site": site})

    def tag(self, *tags: str) -> None:
        for t in tags:
            if t and t not in self.tags:
                self.tags.append(t)

    # ---- appearances ---------------------------------------------------------------------------------------------------
    def look(self, look: str, geom: str, color, alpha: float | None = None) -> None:
        rgba = L.rgba01(color)
        if alpha is not None:
            rgba = rgba[:3] + (float(alpha),)
        self.looks.setdefault(look, {})[geom] = [round(float(v), 4) for v in rgba]

    def lamp(self, name: str, pos, axis=(0.0, -1.0, 0.0), radius: float = 3.5, *, on="red", off=(0.25, 0.05, 0.05),
             looks: tuple[str, str] = ("on", "off"), body=None) -> None:
        """A small indicator lamp: a glowing disc whose colour the looks switch."""
        self.vis("cylinder", (radius, 2.0), pos, off, quat=quat_from_z(axis), name=name, body=body, finish="glow")
        self.look(looks[0], name, on)
        self.look(looks[1], name, off)

    def set_look(self, look: str) -> None:
        """Start in this appearance."""
        if look not in self.looks:
            raise KeyError(f"{self.kind}: no look {look!r}; it has {sorted(self.looks)}")
        for geom, rgba in self.looks[look].items():
            self._named[geom].rgba = tuple(rgba)
        self.extra["look"] = look

    # ---- controls and doors --------------------------------------------------------------------------------------------
    def button(self, name: str, pos, axis=(0.0, -1.0, 0.0), *, size=(14.0, 14.0), round: bool = False, travel: float = 4.0,
               proud: float = 3.0, color="red", kind: str = "button", up=None, stiffness: float = 400.0,
               parent: str | None = None, finish: str = "satin") -> Body:
        """A sprung push control. `pos` is the point of the housing surface it comes out of, `axis` points out of the
        surface; pressing moves the cap by up to `travel` against the spring. The control's site (same name) is at the
        centre of the cap's face with +z pointing out."""
        axis = np.asarray(axis, dtype=np.float64)
        if up is None:
            up = (0.0, 1.0, 0.0) if abs(axis[2]) > 0.9 else (0.0, 0.0, 1.0)
        q = mat_to_quat(L.panel_rotation(axis, up))
        b = self.part(name, pos, q, mass_g=4.0, parent=parent)
        preload = 2.0
        b.joints.append(Joint(f"{name}_joint", "slide", axis=(0.0, 0.0, 1.0), range=(-travel, 0.0), stiffness=stiffness,
                              springref=preload, damping=0.6, armature=0.0005, stiff_limit=True, role="button"))
        depth = proud + travel + 2.0
        material, rgba = self.paint(color, finish)
        if round:
            g = Geom("cylinder", (size[0] / 2.0, depth), (0.0, 0.0, proud - depth / 2.0), role="solid", material=material,
                     rgba=rgba, name=f"{name}_cap", mass=True)
        else:
            g = Geom("box", (size[0], size[1], depth), (0.0, 0.0, proud - depth / 2.0), role="solid", material=material,
                     rgba=rgba, name=f"{name}_cap", mass=True)
        self._add(g, b, False)
        self.site(name, (0.0, 0.0, proud), body=b)
        self.controls[name] = {"site": name, "kind": kind, "joint": f"{name}_joint", "travel": round_(travel * MM),
                               "force": round_(stiffness * (travel + preload) * MM)}
        return b

    def door(self, name: str, joint: str, open: float, closed: float = 0.0, *, kp: float = 2.0, kv: float = 0.4,
             force: float = 3.0, actuator: bool = True) -> None:
        """Register a door, lid or drawer that moves on `joint` (radians, or metres for a slide). With `actuator` a
        position servo of the same name holds it where its control says (0 = closed at the start)."""
        self.doors[name] = {"joint": joint, "open": float(open), "closed": float(closed)}
        if actuator:
            lo, hi = sorted((float(open), float(closed)))
            self.asset.actuators.append({"name": joint, "joint": joint, "kind": "position", "kp": kp, "kv": kv,
                                         "ctrlrange": (lo, hi), "forcerange": (-force, force)})
            self.doors[name]["actuator"] = joint

    # ---- labels --------------------------------------------------------------------------------------------------------
    def _label_meta(self, lines, pictograms, size_mm, lay, site, extra) -> dict:
        ls = L._lines(lines)
        px_per_mm = lay["size"][0] / size_mm[0] if lay else 0.0
        if extra.get("px_per_mm"):
            px_per_mm = extra.pop("px_per_mm")
        cap = (lay["min_cap_px"] / px_per_mm) if lay and px_per_mm else 0.0
        entry = {"site": site, "text": " ".join(ln["text"] for ln in ls if not ln.get("fine")),
                 "lines": [ln["text"] for ln in ls], "pictograms": [L._resolve(p) for p in pictograms],
                 "size": [round_(size_mm[0] * MM), round_(size_mm[1] * MM)], "cap_height": round_(cap * MM)}
        # The actual authored text layout, in the front print panel's UV coordinates (u right, v down).
        # Retain individual principal lines: a small secondary line must not hide a readable product name.
        # These fields describe existing pixels; they do not change the texture, geometry or physics.
        if lay and px_per_mm:
            W, H = lay["size"]
            regions = []
            for placed in lay["lines"]:
                if placed["line"].get("fine") or not placed["line"]["text"].strip():
                    continue
                box = placed["box"]
                ox, oy = L.text_origin(placed)
                x0, x1 = (ox + box[0]) / W, (ox + box[2]) / W
                y0, y1 = (oy + box[1]) / H, (oy + box[3]) / H
                uv_box = [x0, y0, x1, y1]
                axis = "up"
                if extra.get("reads") == "bottom_to_top":
                    uv_box, axis = [y0, 1.0 - x1, y1, 1.0 - x0], "across"
                region = {"text": placed["line"]["text"], "uv_box": [round_(v) for v in uv_box],
                          "cap_height": round_(placed["cap_px"] / px_per_mm * MM), "cap_axis": axis}
                if placed["line"].get("text_group"):
                    region["text_group"] = str(placed["line"]["text_group"])
                # Character cells describe the existing raster, rather than nominal font cap height. They let
                # the evidence check measure resolved ink in the delivered native image without recognising text.
                # The exact same font/layout/origin draw this line; no image or physical dimension changes here.
                text, font = placed["line"]["text"], placed["font"]
                glyphs = []
                for i, character in enumerate(text):
                    if character.isspace():
                        continue
                    left = ox + float(font.getlength(text[:i]))
                    right = ox + float(font.getlength(text[:i + 1]))
                    cell = [left / W, y0, right / W, y1]
                    if axis == "across":
                        cell = [cell[1], 1.0 - cell[2], cell[3], 1.0 - cell[0]]
                    glyphs.append([round_(v) for v in cell])
                st, ln = lay["style"], placed["line"]
                background, foreground = st["bg"], ln.get("fg", st["fg"])
                if "band" in placed:
                    background, foreground = st.get("header") or ("ghs_red", "white")
                    background, foreground = ln.get("bg", background), ln.get("fg", foreground)
                elif ln.get("bg"):
                    background = ln["bg"]
                region["native_ink"] = {"glyph_cells": glyphs, "foreground": list(L.rgb(foreground)),
                                        "background": list(L.rgb(background))}
                regions.append(region)
            entry["text_regions"] = regions
        entry.update(extra)
        self.labels.append(entry)
        return entry

    def _label_names(self, name: str | None) -> tuple[str, str]:
        k = self._count["label"]
        self._count["label"] += 1
        return (name or ("label" if k == 0 else f"label_{k}")), f"label_{k}"

    def decal(self, image: np.ndarray, *, size, pos, normal=(0.0, -1.0, 0.0), up=None, body=None, thick: float = 0.4,
              name: str | None = None, glow: float | None = None, rgba=None) -> tuple[np.ndarray, tuple]:
        """A picture on a flat face (no label entry): `size` (width, height) in millimetres centred at `pos`, facing
        `normal`, its top towards `up`. Returns the panel's rotation matrix and quaternion."""
        normal = np.asarray(normal, dtype=np.float64)
        if up is None:
            up = (0.0, 1.0, 0.0) if abs(normal[2]) > 0.9 else (0.0, 0.0, 1.0)
        tex = f"tex_{len(self.asset.images)}"
        self._last_texture = tex
        self.asset.images[tex] = L._png.encode(np.ascontiguousarray(np.asarray(image)[:, :, :3]))
        if glow is not None:
            self.asset.image_glow[tex] = float(glow)
        rot = L.panel_rotation(normal, up)
        q = mat_to_quat(rot)
        mname = f"m{self._count['mesh']}"
        self._count["mesh"] += 1
        self.asset.meshes[mname] = L.flat_panel(size[0], size[1], thick)
        centre = np.asarray(pos, dtype=np.float64) + rot[:, 2] * (thick / 2.0 - 0.05)
        self._add(Geom("mesh", mesh=mname, pos=tuple(centre), quat=q, role="visual", material=tex, name=name, mass=False,
                       rgba=None if rgba is None else tuple(rgba)), body, False)
        return rot, q

    def label_flat(self, lines, pictograms=(), *, size, pos, normal=(0.0, -1.0, 0.0), up=None, style=None,
                   name: str | None = None, body=None, image: np.ndarray | None = None, thick: float = 0.4,
                   px_per_mm: float = L.PX_PER_MM, geom: str | None = None, glow: float | None = None,
                   cap_mm: float | None = None, wear=None, text_regions: Sequence[dict] | None = None) -> dict:
        """A printed panel on a flat face: `size` (width, height) in millimetres centred at `pos`, facing `normal`,
        with the top of the text towards `up`. `image` replaces the automatic layout (text and pictograms then only
        describe what is on it). Its author can supply `text_regions` in panel UV coordinates, with cap heights in
        metres and the actual font's native glyph cells/colours; these describe existing pixels, not OCR results.
        `wear` (0.5.0): a spec of `robosafebench.assets.wear` applied to the print."""
        if text_regions is not None and image is None:
            raise ValueError("explicit text_regions require an authored image")
        site, _ = self._label_names(name)
        px = L.texture_size(size[0], size[1], px_per_mm)
        lay = None
        if image is None:
            lay = L.layout(lines, pictograms, px, style)
            image = L.label_image(lines, pictograms, px, style)
        if wear:
            from . import wear as _wear
            if lay is not None:
                wear = _wear.resolve(wear, lines, pictograms, px, style)
            image = _wear.apply(image, wear, L._style(style)["bg"] if lay is not None else None)
        rot, q = self.decal(image, size=size, pos=pos, normal=normal, up=up, body=body, thick=thick, name=geom, glow=glow)
        self.site(site, tuple(np.asarray(pos, dtype=np.float64) + rot[:, 2] * thick), q, body)
        extra = {"px_per_mm": np.asarray(image).shape[1] / size[0]} if lay is None else {}
        extra["texture"] = f"{self._last_texture}.png"
        extra["uv"] = [0.0, 1.0]
        if wear:
            extra["wear"] = _wear.describe(wear)
            if lay is not None:                                    # what of the print is left (`wear.text_kept`)
                extra["kept"] = _wear.summary(_wear.text_kept(lines, pictograms, px, style, wear, px[0] / size[0]))
        entry = self._label_meta(lines, pictograms, size, lay, site, extra)
        if text_regions is not None:
            entry["text_regions"] = json.loads(json.dumps(text_regions))
        if cap_mm is not None:
            entry["cap_height"] = round_(cap_mm * MM)
        return entry

    def label_wrap(self, lines, pictograms=(), *, radius: float, z0: float, z1: float, arc_deg: float = 120.0,
                   center_deg: float = -90.0, style=None, r_top: float | None = None, band=None, name: str | None = None,
                   body=None, panels: Sequence[dict] = (), px_per_mm: float = L.PX_PER_MM, upright: bool = True,
                   torn: float = 0.0, wear=None) -> dict:
        """A printed label around a round body between `z0` and `z1`. The text panel covers `arc_deg` centred at azimuth
        `center_deg` (-90 is the front). With `band` (a colour) the label goes all the way round in that colour, like
        the sleeve of a can; `panels` adds more printed panels on it: dicts with `at_deg` (azimuth relative to the
        front panel), `arc_deg`, `lines`, `pictograms`, `style`."""
        r1 = radius if r_top is None else r_top
        rm = (radius + r1) / 2.0
        height = math.hypot(z1 - z0, r1 - radius)
        site, tex = self._label_names(name)
        arc_mm = rm * math.radians(arc_deg)
        full = band is not None
        scale = min(px_per_mm, L.MAX_TEXTURE / max(2 * math.pi * rm if full else arc_mm, height))
        ph = max(16, int(round(height * scale)))
        pw = max(16, int(round(arc_mm * scale)))
        style = dict(L._style(style))
        if wear:                                                   # (0.5.0) worn print, in reading orientation
            from . import wear as _wear
        if upright:
            style.setdefault("inset_x", 0.03 + 0.07 * max(0.0, (arc_deg - 60.0) / 60.0))   # keep the text off the receding edges
            lay = L.layout(lines, pictograms, (pw, ph), style)
            front = L.label_image(lines, pictograms, (pw, ph), style)
            if wear:
                front = _wear.apply(front, _wear.resolve(wear, lines, pictograms, (pw, ph), style), L._style(style)["bg"])
        else:                                                      # written along the axis, to be read bottom to top
            lay = L.layout(lines, pictograms, (ph, pw), style)
            front = L.label_image(lines, pictograms, (ph, pw), style)
            if wear:
                front = _wear.apply(front, _wear.resolve(wear, lines, pictograms, (ph, pw), style), L._style(style)["bg"])
            front = np.ascontiguousarray(np.rot90(front))
        if torn:                                                   # a part of the front panel torn off (`labels.tear`)
            front = L.tear(front, float(torn))
        if full:
            tw = max(pw, int(round(2 * math.pi * rm * scale)))
            parts = [(front, ((tw - pw) // 2, 0))]
            for p in panels:
                w2 = max(16, int(round(rm * math.radians(p.get("arc_deg", 90.0)) * scale)))
                img = L.label_image(p.get("lines", ()), p.get("pictograms", ()), (w2, ph), p.get("style", style))
                x = int(round(tw * (0.5 + p.get("at_deg", 120.0) / 360.0))) - w2 // 2
                parts.append((img, (x % tw, 0)))
                if x % tw + w2 > tw:                                   # the panel runs over the seam
                    parts.append((img[:, tw - (x % tw):], (0, 0)))
            image = L.compose((tw, ph), band, parts)
            shell_arc = 360.0
            uv = [(tw - pw) / 2.0 / tw, (tw + pw) / 2.0 / tw]
        else:
            image = front
            shell_arc = arc_deg
            uv = [0.0, 1.0]
        tex = f"tex_{len(self.asset.images)}"
        self.asset.images[tex] = L._png.encode(image)
        mname = f"m{self._count['mesh']}"
        self._count["mesh"] += 1
        self.asset.meshes[mname] = L.wrap_shell(radius, r1, z0, z1, shell_arc, center_deg)
        self._add(Geom("mesh", mesh=mname, role="visual", material=tex, mass=False), body, False)
        a = math.radians(center_deg)
        out = np.array([math.cos(a), math.sin(a), 0.0])
        q = mat_to_quat(L.panel_rotation(out, (0.0, 0.0, 1.0)))
        self.site(site, tuple(out * (rm + 0.4) + np.array([0.0, 0.0, (z0 + z1) / 2.0])), q, body)
        extra = {"wrap": {"radius": round_(rm * MM), "arc_deg": float(arc_deg),
                          "r_bottom": round_(radius * MM), "r_top": round_(r1 * MM), "height": round_((z1 - z0) * MM)}, "texture": f"{tex}.png", "uv": uv,
                 "px_per_mm": scale}
        if not upright:
            extra["reads"] = "bottom_to_top"
        if torn:
            extra["torn"] = float(torn)
        if wear:
            size_px = (pw, ph) if upright else (ph, pw)
            extra["wear"] = _wear.describe(_wear.resolve(wear, lines, pictograms, size_px, style))
            extra["kept"] = _wear.summary(_wear.text_kept(lines, pictograms, size_px, style, wear, scale))
        for p in panels:
            extra.setdefault("more", []).append({"at_deg": p.get("at_deg", 120.0),
                                                 "text": " ".join(ln["text"] for ln in L._lines(p.get("lines", ()))),
                                                 "pictograms": [L._resolve(x) for x in p.get("pictograms", ())]})
        return self._label_meta(lines, pictograms, (arc_mm, height), lay, site, extra)

    # ---- round open vessels --------------------------------------------------------------------------------------------
    def round_vessel(self, outer: Sequence[Sequence[float]], *, wall: float = 2.5, floor: float = 3.0, color="white",
                     finish: str = "gloss", alpha: float | None = None, n: int = 12, body=None, name: str = "shell",
                     contents: dict | None = None, liquid: bool = True, closed: bool = False, segments: int = 40,
                     rings: Sequence[int] | None = None, register: bool = True, wall_collision: bool = True,
                     draw: bool = True) -> dict:
        """An open round vessel from its outer outline `[(r, z), ...]` (base edge first, rim last).

        Draws the shell, gives it a bottom and a ring wall to collide with, the sites `inside_bottom` and `mouth`, the
        zone `inside`, the `vessel` entry and a drawn fill (geom `liquid`) for `contents` ({substance: ml}).
        `rings` picks the outline points between which wall rings are built (default: all of them).
        """
        outer = [(float(r), float(z)) for r, z in outer]
        profile, inner = shell_profile(outer, wall, floor)
        if draw:
            self.shape(M.revolve(profile, segments), color, name=name, body=body, finish=finish, alpha=alpha)
        zb = outer[0][1]
        self.foot(outer[0][0], zb, floor, body=body)
        idx = list(rings) if rings is not None else list(range(len(outer)))
        if wall_collision:
            for a, b in zip(idx, idx[1:]):
                (r0, z0), (r1, z1) = outer[a], outer[b]
                z0 = max(z0, zb + 0.5)
                if z1 - z0 > 1.0:
                    self.ring(r0, r1, z0, z1, max(wall, 2.0), n, body=body)
        depth = inner[-1][1] - inner[0][1]
        cap_mm3 = profile_volume(inner)
        r_mouth = inner[-1][0]
        info = {"inner": inner, "depth": depth, "capacity_ml": cap_mm3 / 1000.0, "mouth_radius": r_mouth}
        if not register:
            return info
        prefix = "" if self.vessel is None else f"{name}_"
        self.site(prefix + "inside_bottom", (0.0, 0.0, inner[0][1]), body=body)
        self.site(prefix + "mouth", (0.0, 0.0, inner[-1][1]), body=body)
        r_mean = math.sqrt(cap_mm3 / (math.pi * depth))
        self.zone(prefix + "inside", (0.0, 0.0, inner[0][1] + depth / 2.0), "cylinder", (r_mean, depth), body=body)
        vessel = {"capacity_ml": round(cap_mm3 / 1000.0, 1), "inner_radius": round_(r_mean * MM),
                  "inner_depth": round_(depth * MM), "bottom_site": prefix + "inside_bottom",
                  "mouth_site": prefix + "mouth", "closed": bool(closed), "shape": "cyl", "bottom_offset": 0.0,
                  "rim_site": prefix + "mouth", "mouth_radius": round_(r_mouth * MM)}
        if self.vessel is None:
            self.vessel = vessel
        else:
            self.extra.setdefault("vessels", {})[name] = vessel
        if liquid:
            self.fill(inner, contents or {}, body=body, name=prefix + "liquid")
        if contents and self.vessel is vessel:
            self.contents = {k: float(v) for k, v in contents.items()}
        return info

    # ---- rectangular open containers and blocks with holes ---------------------------------------------------------------
    def box_vessel(self, sx: float, sy: float, sz: float, *, wall: float = 3.0, floor: float = 3.0, color="white",
                   finish: str = "satin", alpha: float | None = None, corner: float = 8.0, center=(0.0, 0.0),
                   z0: float = 0.0, body=None, name: str = "shell", register: bool = True, contents: dict | None = None,
                   liquid: bool = True, closed: bool = False, draw: bool = True) -> dict:
        """An open rectangular container (tray, tub, bin, drawer): drawn as one shell, colliding as a floor and four
        walls. With `register` it gets the sites `inside_bottom` and `mouth`, the zone `inside` and the `vessel` entry."""
        cx, cy = center
        ix, iy, depth = sx - 2 * wall, sy - 2 * wall, sz - floor
        if draw:
            cell = M.Cell(rounded_rect(sx, sy, corner, 4, center),
                          M.Pocket(rounded_rect(ix, iy, max(corner - wall, 0.5), 4, center), floor_z=z0 + floor))
            self.shape(M.pocket_prism([cell], z0, z0 + sz), color, name=name, body=body, finish=finish, alpha=alpha)
        self.col("box", (sx, sy, floor), (cx, cy, z0 + floor / 2.0), body=body)
        zc = z0 + floor + depth / 2.0
        for sgn in (-1.0, 1.0):
            self.col("box", (wall, sy, depth), (cx + sgn * (sx - wall) / 2.0, cy, zc), body=body)
            self.col("box", (ix, wall, depth), (cx, cy + sgn * (sy - wall) / 2.0, zc), body=body)
        info = {"inner": (ix, iy, depth), "capacity_ml": ix * iy * depth / 1000.0}
        if not register:
            return info
        prefix = "" if self.vessel is None else f"{name}_"
        self.site(prefix + "inside_bottom", (cx, cy, z0 + floor), body=body)
        self.site(prefix + "mouth", (cx, cy, z0 + sz), body=body)
        self.zone(prefix + "inside", (cx, cy, zc), "box", (ix, iy, depth), body=body)
        vessel = {"capacity_ml": round(info["capacity_ml"], 1), "inner_radius": round_(min(ix, iy) / 2.0 * MM),
                  "inner_depth": round_(depth * MM), "bottom_site": prefix + "inside_bottom", "mouth_site": prefix + "mouth",
                  "closed": bool(closed), "shape": "box", "inner_size": [round_(ix * MM), round_(iy * MM)],
                  "bottom_offset": 0.0, "rim_site": prefix + "mouth"}
        if self.vessel is None:
            self.vessel = vessel
            if contents:
                self.contents = {k: float(v) for k, v in contents.items()}
        else:
            self.extra.setdefault("vessels", {})[name] = vessel
        if liquid:
            ml = float(sum((contents or {}).values()))
            level = min(depth, ml * 1000.0 / (ix * iy))
            substance = max(contents, key=contents.get) if contents else "water"
            rgba = SUBSTANCES.get(substance, SUBSTANCES["water"])
            shown = max(level, 1.0)
            lname = prefix + "liquid"
            # the surface only: a thin slab with the tub's rounded outline, moved up and down with the level
            slab = M.extrude(rounded_rect(ix - 0.6, iy - 0.6, max(corner - wall, 0.5), 4), -1.0, 0.0)
            self.shape(slab, rgba[:3], alpha=min(1.0, rgba[3] + 0.25) if ml > 0 else 0.0, name=lname, body=body, finish="gloss",
                       pos=(cx, cy, z0 + floor + shown))
            self.extra.setdefault("liquid", {})[lname] = {"geom": lname, "level": round_(level * MM),
                                                          "substance": substance if ml > 0 else None,
                                                          "box": [round_(ix * MM), round_(iy * MM), round_(depth * MM)]}
            self.asset.numerics[lname] = ((z0 + floor) * MM, 0.0, ix * MM, iy * MM, depth * MM)
        return info

    def holed_block(self, sx: float, sy: float, z0: float, z1: float, holes: Sequence[Sequence[float]], *,
                    floor: float = 5.0, color="wood", finish: str = "satin", name: str = "block", body=None) -> list:
        """A block with rectangular holes from the top, in one row along x. `holes`: `(cx, half_x, half_y)` or
        `(cx, half_x, half_y, cy)` each. Returns the centres of the hole floors."""
        hs = sorted([tuple(float(v) for v in h) + ((0.0,) if len(h) == 3 else ()) for h in holes])
        xs = [-sx / 2.0] + [(a[0] + a[1] + b[0] - b[1]) / 2.0 for a, b in zip(hs, hs[1:])] + [sx / 2.0]
        zf = z0 + floor
        cells = []
        for i, (cx, hx, hy, cy) in enumerate(hs):
            cells.append(M.Cell(np.array([[xs[i], -sy / 2], [xs[i + 1], -sy / 2], [xs[i + 1], sy / 2], [xs[i], sy / 2]]),
                                M.Pocket(M.rect(2 * hx, 2 * hy, (cx, cy)), floor_z=zf)))
            zc, hz = (zf + z1) / 2.0, z1 - zf
            self.col("box", (xs[i + 1] - xs[i], sy / 2 + cy - hy, hz), ((xs[i] + xs[i + 1]) / 2.0, (-sy / 2 + cy - hy) / 2.0, zc), body=body)
            self.col("box", (xs[i + 1] - xs[i], sy / 2 - cy - hy, hz), ((xs[i] + xs[i + 1]) / 2.0, (sy / 2 + cy + hy) / 2.0, zc), body=body)
            self.col("box", (cx - hx - xs[i], 2 * hy, hz), ((xs[i] + cx - hx) / 2.0, cy, zc), body=body)
            self.col("box", (xs[i + 1] - cx - hx, 2 * hy, hz), ((xs[i + 1] + cx + hx) / 2.0, cy, zc), body=body)
        self.shape(M.pocket_prism(cells, z0, z1), color, name=name, body=body, finish=finish)
        self.col("box", (sx, sy, floor), (0.0, 0.0, z0 + floor / 2.0), body=body)
        return [(cx, cy, zf) for cx, hx, hy, cy in hs]

    def fill(self, inner: Sequence[Sequence[float]], contents: dict, *, body=None, name: str = "liquid") -> None:
        """The drawn fill of a vessel: a disc from the inside bottom up to the level its contents reach. Present (and
        invisible) when empty, so that the level can be redrawn while the simulation runs."""
        ml = float(sum(contents.values())) if contents else 0.0
        level = level_for_volume(inner, ml * 1000.0)
        substance = max(contents, key=contents.get) if contents else "water"
        rgba = SUBSTANCES.get(substance, SUBSTANCES["water"])
        shown = max(level, 0.5)
        r = radius_at(inner, shown / 2.0) - 0.3
        self.vis("cylinder", (r, shown), (0.0, 0.0, inner[0][1] + shown / 2.0), rgba[:3], alpha=rgba[3] if ml > 0 else 0.0,
                 name=name, body=body, finish="gloss")
        self.extra.setdefault("liquid", {})[name] = {
            "geom": name, "level": round_(level * MM), "substance": substance if ml > 0 else None,
            "inner": [[round_(r * MM), round_((z - inner[0][1]) * MM)] for r, z in inner]}
        self.asset.numerics[name] = tuple([inner[0][1] * MM, float(len(inner))]
                                          + [v * MM for r, z in inner for v in (r, z - inner[0][1])])

    def case(self, W: float, D: float, H: float, t: float = 12.0, color="white", *, z0: float = 0.0, finish: str = "satin",
             name: str = "case", body=None, center=(0.0, 0.0), back: bool = True) -> tuple[float, float, float]:
        """A rectangular housing open to the front (-y): floor, roof, two sides and a back, each drawn and colliding.
        Returns the inner size (width, depth, height)."""
        cx, cy = center
        self.solid("box", (W, D, t), (cx, cy, z0 + t / 2.0), color, name=f"{name}_floor", body=body, finish=finish)
        self.solid("box", (W, D, t), (cx, cy, z0 + H - t / 2.0), color, name=f"{name}_roof", body=body, finish=finish)
        for sgn, nm in ((-1.0, "left"), (1.0, "right")):
            self.solid("box", (t, D, H - 2 * t), (cx + sgn * (W - t) / 2.0, cy, z0 + H / 2.0), color, name=f"{name}_{nm}", body=body,
                       finish=finish)
        if back:
            self.solid("box", (W - 2 * t, t, H - 2 * t), (cx, cy + (D - t) / 2.0, z0 + H / 2.0), color, name=f"{name}_back", body=body,
                       finish=finish)
        return (W - 2 * t, D - (t if back else 0.0), H - 2 * t)

    def hinged_door(self, name: str, hinge, width: float, height: float, thick: float = 18.0, color="white", *,
                    side: str = "left", open_angle: float = 1.6, mass_g: float = 1500.0, finish: str = "satin",
                    kp: float = 3.0, force: float = 4.0, parent: str | None = None, limit: float = 1.9) -> Body:
        """A door leaf on a vertical hinge at `hinge` (x, y of the front face, z of its lower edge), swinging out towards
        -y. The joint is called `name`, 0 when closed and positive when open; the leaf body is `<name>_leaf`."""
        leaf = self.part(f"{name}_leaf", hinge, mass_g=mass_g, parent=parent)
        sgn = 1.0 if side == "left" else -1.0
        leaf.joints.append(Joint(name, "hinge", axis=(0.0, 0.0, -sgn), range=(0.0, limit), damping=0.2, frictionloss=0.05,
                                 armature=0.003, role="door"))
        self.solid("box", (width, thick, height), (sgn * width / 2.0, -thick / 2.0, height / 2.0), color, body=leaf,
                   name=f"{name}_panel", finish=finish)
        self.door(name, name, open=open_angle, closed=0.0, kp=kp, kv=kp / 6.0, force=force)
        return leaf

    def reframe(self, rot: np.ndarray, origin: Sequence[float] = (0.0, 0.0, 0.0)) -> None:
        """Re-express everything added to the root body so far in a new frame: a point p becomes `rot @ (p - origin)`.
        Used for things that have two natural poses (a knife lying on the table, or standing tip down in a block)."""
        rot = np.asarray(rot, dtype=np.float64)
        origin = np.asarray(origin, dtype=np.float64)
        q = mat_to_quat(rot)
        for item in list(self.root.geoms) + list(self.root.sites):
            item.pos = tuple(rot @ (np.asarray(item.pos, dtype=np.float64) - origin))
            item.quat = quat_mul(q, item.quat)
        for child in self.root.children:
            child.pos = tuple(rot @ (np.asarray(child.pos, dtype=np.float64) - origin))
            child.quat = quat_mul(q, child.quat)
        for g in self.grasps:
            g["pos"] = [round_(float(v)) for v in rot @ (np.asarray(g["pos"]) - origin * MM)]
            g["quat"] = [round(float(v), 9) for v in quat_mul(q, g["quat"])]

    # ---- output --------------------------------------------------------------------------------------------------------
    def _world_pose(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        chain = []
        while name != "body":
            chain.append(self.bodies[name])
            name = self.parents[name]
        rot, pos = np.eye(3), np.zeros(3)
        for b in reversed(chain):
            pos = pos + rot @ np.asarray(b.pos, dtype=np.float64)
            rot = rot @ quat_to_mat(b.quat)
        return rot, pos

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
        for bname, b in self.bodies.items():
            rot, pos = self._world_pose(bname)
            for g in b.geoms:
                if id(g) in self._decor:
                    continue
                v = geom_mesh(self.asset, g).v @ rot.T + pos
                lo, hi = np.minimum(lo, v.min(axis=0)), np.maximum(hi, v.max(axis=0))
        return lo, hi

    def finish(self) -> tuple[dict[str, bytes], dict]:
        """The files of the asset (`<kind>.xml`, meshes, textures, `meta.json`) and its meta."""
        if self.total_g is None:
            raise ValueError(f"{self.kind}: no mass given")
        child_g = sum(b.mass_g or 0.0 for n, b in self.bodies.items() if n != "body")
        self.root.mass_g = self.total_g - child_g
        if self.root.mass_g <= 0:
            raise ValueError(f"{self.kind}: moving parts weigh more than the whole")
        for b in self.bodies.values():                      # a body without collision shapes spreads its mass over what is drawn
            if not any(g.counts_for_mass() for g in b.geoms):
                for g in b.geoms:
                    if g.material not in self.asset.images:
                        g.mass = True
            if not b.geoms:
                raise ValueError(f"{self.kind}: body {b.name!r} has no shapes")
        lo, hi = self.bounds()
        names = {s.name for b in self.bodies.values() for s in b.sites}
        if "top" not in names:
            self.site("top", (0.0, 0.0, float(hi[2])))
        if "bottom" not in names:
            self.site("bottom", (0.0, 0.0, 0.0))
        sites = {}
        for bname, b in self.bodies.items():
            rot, pos = self._world_pose(bname)
            for s in b.sites:
                p = rot @ np.asarray(s.pos, dtype=np.float64) + pos
                sites[s.name] = [round_(float(v) * MM) for v in p]
        meta = {
            "kind": self.kind,
            "size": [round_(float(v) * MM) for v in (hi - lo)],
            "bbox": [[round_(float(v) * MM) for v in lo], [round_(float(v) * MM) for v in hi]],
            "mass": round(self.total_g * 1e-3, 6),
            "fixed": bool(self.fixed),
            "grasps": self.grasps,
            "grips": {g["site"]: {"type": g["type"], "width": g["width"], "pos": g["pos"], "quat": g["quat"],
                                  "name": g["name"]} for g in self.grasps},
            "tags": list(self.tags),
            "sites": dict(sorted(sites.items())),
            "zones": self.zones,
            "vessel": self.vessel,
            "contents": self.contents,
            "controls": self.controls,
            "looks": self.looks,
            "labels": self.labels,
            "doors": self.doors,
        }
        if self.vessel is None:
            del meta["vessel"]
        meta.update(self.extra)
        files: dict[str, bytes] = {f"{self.kind}.xml": document_xml(self.asset, root_name="body").encode("utf8")}
        for name in sorted(self.asset.meshes):
            files[f"{name}.obj"] = M.to_obj(self.asset.meshes[name].scaled(MM)).encode("ascii")
        for name in sorted(self.asset.images):
            files[f"{name}.png"] = self.asset.images[name]
        files["meta.json"] = (json.dumps(meta, indent=1, sort_keys=True) + "\n").encode("utf8")
        return files, meta


def round_(x: float, digits: int = 6) -> float:
    v = round(float(x), digits)
    return 0.0 if v == 0 else v


def mm(*xs: float):
    """Metres (the unit of catalogue parameters) to millimetres (the unit builders draw in)."""
    out = [float(x) * 1000.0 for x in xs]
    return out[0] if len(out) == 1 else out
