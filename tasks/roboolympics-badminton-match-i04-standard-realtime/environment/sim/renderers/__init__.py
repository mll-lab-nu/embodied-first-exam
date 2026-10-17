"""Renderer plugins (docs/framework_zh.md §3.1): a renderer draws a sport's scene, from its camera definitions, for
one world state. Sports never import a renderer; the core calls the task's observation renderer (task parameter
`renderer`, default DEFAULT) and the viewing tools any renderer for re-renders.

    from renderers import load, Scene, CameraDef
    R = load("mujoco")(Scene.from_file("scene.xml"))
    images = R.render({"qpos": qpos}, [CameraDef("behind", pos, lookat)])
"""
from __future__ import annotations

import importlib

from .base import CameraDef, Renderer, RendererUnavailable, Scene  # noqa: F401

DEFAULT = "mujoco"
REGISTRY = {   # name -> (module, realtime, needs_gpu, requires)
    "mujoco": ("renderers.mujoco", True, False, "mujoco; MUJOCO_GL=osmesa (CPU) or egl (GPU)"),
    "mujoco-showcase": ("renderers.mujoco_showcase", True, False, "as mujoco"),
    "cycles": ("renderers.cycles", False, True, "Docker, the rcb-showcase-blender image, an NVIDIA GPU (or device=CPU)"),
    "isaac": ("renderers.isaac", False, True, "Docker, the Isaac Sim 4.5 image, an NVIDIA RTX GPU"),
}


def load(name: str = DEFAULT):
    """The Renderer subclass registered under `name`."""
    if name not in REGISTRY:
        raise KeyError(f"unknown renderer {name!r}; have {sorted(REGISTRY)}")
    return importlib.import_module(REGISTRY[name][0]).RENDERER


def available() -> dict:
    return {n: {"realtime": rt, "needs_gpu": gpu, "requires": req} for n, (_, rt, gpu, req) in REGISTRY.items()}


def players_model(sport_dir, match: Scene):
    """For a sport that draws its own images (the renderers' interface for sports): the compiled MjModel of the
    players' presentation scene its presentation.toml declares (`players`, renderer rule 6; the same kinematics as
    `match` checked), or None when it declares none (draw the match model). See renderers/presentation."""
    from .presentation import players_model as _players_model
    return _players_model(sport_dir, match)
