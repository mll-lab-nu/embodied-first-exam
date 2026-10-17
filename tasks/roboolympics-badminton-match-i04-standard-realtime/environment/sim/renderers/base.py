"""The renderer plugin interface (docs/framework_zh.md §3.1, renderer rules §9): a renderer turns a sport's scene,
camera definitions and one world state into images. It never changes physics or the match state: it draws on its own
copy of the model.

    scene   = Scene(engine="mujoco", xml=MJCF text, assets={relative path: bytes}, look=None or a presentation look)
              a presentation scene (renderers/presentation.py, spectators only) also carries `match`, the match scene
              it dresses: same kinematics, extra visual-only geoms (scene_check.same_kinematics)
    cameras = [CameraDef(name, pos, lookat, up, fovy_deg, width, height), ...]     (what Match.cameras(seat) returns)
    state   = {"qpos": [...], optional "mocap_pos": [...], "mocap_quat": [...]}
    images  = Renderer(scene).render(state, cameras)      -> one H x W x 3 uint8 array per camera

The camera model is a pinhole that every renderer must reproduce (CameraDef.project): pixel (u, v) from the image's
top-left corner, u to the right, v down, vertical field of view fovy_deg. Only numpy is needed here; engines import
their own libraries inside their backend packages. Never put the renderers/ directory itself on sys.path (its
`mujoco` backend package would shadow the mujoco library); import it as the package `renderers`.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


class RendererUnavailable(RuntimeError):
    """The renderer cannot run here; `requirements` says what it needs (GPU, image, library ...)."""

    def __init__(self, name: str, why: str, requirements: str = ""):
        super().__init__(f"renderer {name!r} unavailable: {why}" + (f" (requires: {requirements})" if requirements else ""))
        self.name, self.why, self.requirements = name, why, requirements


def _unit(v):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    if not np.isfinite(n) or n < 1e-12:
        raise ValueError("degenerate camera direction")
    return v / n


@dataclass
class CameraDef:
    name: str
    pos: tuple
    lookat: tuple
    up: tuple = (0.0, 0.0, 1.0)
    fovy_deg: float = 45.0
    width: int = 320
    height: int = 240

    def __post_init__(self):
        self.pos = tuple(float(x) for x in self.pos)
        self.lookat = tuple(float(x) for x in self.lookat)
        self.up = tuple(float(x) for x in self.up)
        self.fovy_deg, self.width, self.height = float(self.fovy_deg), int(self.width), int(self.height)
        if len(self.pos) != 3 or len(self.lookat) != 3 or len(self.up) != 3:
            raise ValueError("pos, lookat and up are 3-vectors")
        if not 0 < self.fovy_deg < 180 or self.width <= 0 or self.height <= 0:
            raise ValueError("fovy_deg in (0, 180), positive width and height")
        self.basis()                                   # raises on a degenerate pose

    @staticmethod
    def from_dict(d: dict) -> "CameraDef":
        keys = ("name", "pos", "lookat", "up", "fovy_deg", "width", "height")
        return CameraDef(**{k: d[k] for k in keys if k in d})

    def to_dict(self) -> dict:
        return {"name": self.name, "pos": list(self.pos), "lookat": list(self.lookat), "up": list(self.up),
                "fovy_deg": self.fovy_deg, "width": self.width, "height": self.height}

    def focal_px(self) -> float:
        return (self.height / 2) / math.tan(math.radians(self.fovy_deg) / 2)

    def intrinsics(self) -> dict:
        return {"focal_px": self.focal_px(), "principal_point_px": [self.width / 2, self.height / 2],
                "width": self.width, "height": self.height}

    def basis(self):
        """(right, up, forward) unit vectors in the world frame."""
        fwd = _unit(np.subtract(self.lookat, self.pos))
        right = _unit(np.cross(fwd, self.up))
        up = np.cross(right, fwd)
        return right, up, fwd

    def project(self, point):
        """Pixel (u, v) of a world point (u right, v down, from the top-left corner; continuous coordinates, so the
        centre of pixel column i is u = i + 0.5). None if the point is behind the camera."""
        right, up, fwd = self.basis()
        d = np.subtract(point, self.pos)
        depth = float(d @ fwd)
        if depth <= 1e-9:
            return None
        f = self.focal_px()
        return (self.width / 2 + f * float(d @ right) / depth, self.height / 2 - f * float(d @ up) / depth)

    def spherical(self):
        """(lookat, distance, azimuth_deg, elevation_deg): the free-camera form the showcase exporters use."""
        d = np.subtract(self.lookat, self.pos)
        dist = float(np.linalg.norm(d))
        az = math.degrees(math.atan2(d[1], d[0]))
        el = math.degrees(math.asin(max(-1.0, min(1.0, d[2] / dist))))
        return list(self.lookat), dist, az, el


@dataclass
class Scene:
    engine: str = "mujoco"                       # the physics engine whose scene format `xml` is in
    xml: str = ""                                # MJCF text (engine "mujoco")
    assets: dict = field(default_factory=dict)   # {path as referenced by the xml (with meshdir/texturedir): bytes}
    look: dict | None = None                     # optional presentation appearance (showcase renderers only)
    match: "Scene | None" = None                 # set on a presentation scene only: the match scene it dresses
    credits: tuple = ()                          # presentation scene: what was added, with its source and licence
    players: bool = False                        # a presentation scene the sport declares for its players' images too

    @property
    def is_presentation(self) -> bool:
        """A presentation scene (renderers/presentation): drawn for the players' images only when `players` is set
        (the sport declares it, renderer rule 6), else for spectators only."""
        return self.match is not None

    @staticmethod
    def from_file(path, look=None) -> "Scene":
        """A scene file plus every other file below its directory as an asset (paths relative to that directory)."""
        p = Path(path)
        assets = {str(f.relative_to(p.parent)): f.read_bytes() for f in sorted(p.parent.rglob("*"))
                  if f.is_file() and f != p and "__pycache__" not in f.parts}
        return Scene(engine="mujoco", xml=p.read_text(), assets=assets, look=look)


class Renderer(ABC):
    name: str = ""
    realtime: bool = True          # fast enough for player images (still subject to the task's frame budget)
    needs_gpu: bool = False
    label: str | None = None       # the tag a re-rendered frame carries ("re-rendered: <engine>"); None = default

    def __init__(self, scene: Scene, **opts):
        self.scene, self.opts = scene, opts

    @abstractmethod
    def render(self, state: dict, cameras: list) -> list:
        """One H x W x 3 uint8 image per camera (CameraDef or its dict form), for the given world state."""

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def as_cameras(cameras) -> list:
    return [c if isinstance(c, CameraDef) else CameraDef.from_dict(c) for c in cameras]
