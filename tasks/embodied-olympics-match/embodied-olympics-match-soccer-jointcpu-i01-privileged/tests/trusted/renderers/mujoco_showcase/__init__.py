"""MuJoCo showcase: the same rasterizer with better lights, materials and anti-aliasing (real time; CPU with osmesa,
GPU optional). The scene is the default renderer's scene with visual changes only, checked by scene_check.same_scene
before the first frame (the renderer refuses to draw otherwise).

Look (Scene.look): None or {} = the generic showcase look below (shadow-casting key light, soft fill, satin materials
that keep every geom's colour, MSAA); {"preset": <name>} = a sport's look from scripts/olympiad/showcase/looks.py
(SHOWCASE[name], e.g. "tabletennis"), available when this checkout's showcase tools are present.
Options: ssaa (supersampling factor, default 1; 2 for re-renders), stamp (tag every frame with `label`, default False:
the tag is for re-rendered outputs, not for player images).

A presentation scene (Scene.match set, renderers/presentation.py): its added visual geoms keep their own materials
under any look, the kinematics check of the default renderer applies, and `label` says it is a presentation scene."""
from __future__ import annotations

import os
import sys

import numpy as np

from ..base import RendererUnavailable, Scene
from ..label import label_text, stamp
from ..mujoco import MujocoRenderer, compile_spec, load_spec
from ..scene_check import DEFAULT_RGBA, VISUAL_PREFIX, same_scene

SHOWCASE_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                              "scripts", "olympiad", "showcase")


def _material(spec, name, **kw):
    mt = spec.add_material(name=name)
    for k, v in kw.items():
        setattr(mt, k, v)
    return mt


def generic_look(spec, size):
    import mujoco as mj
    v = spec.visual
    v.global_.offwidth, v.global_.offheight = max(v.global_.offwidth, size[0]), max(v.global_.offheight, size[1])
    v.quality.offsamples = 8
    v.quality.shadowsize = 4096
    v.headlight.ambient = [0.18, 0.18, 0.2]
    v.headlight.diffuse = [0.25, 0.25, 0.25]
    v.headlight.specular = [0.1, 0.1, 0.1]
    for li in spec.lights:
        li.castshadow = True
    key = spec.worldbody.add_light(name="_showcase_key", pos=[4, -4, 8], dir=[-0.45, 0.45, -0.77],
                                   diffuse=[0.55, 0.53, 0.5], specular=[0.3, 0.3, 0.3], castshadow=True)
    fill = spec.worldbody.add_light(name="_showcase_fill", pos=[-4, 4, 6], dir=[0.5, -0.5, -0.7],
                                    diffuse=[0.22, 0.24, 0.28], specular=[0, 0, 0], castshadow=False)
    for li in (key, fill):
        if hasattr(li, "type"):                       # MuJoCo >= 3.3: light type enum
            li.type = mj.mjtLightType.mjLIGHT_DIRECTIONAL
        else:                                          # pragma: no cover
            li.directional = True
    _material(spec, "_showcase_satin", specular=0.45, shininess=0.55, reflectance=0.0)
    _material(spec, "_showcase_satin_default", specular=0.45, shininess=0.55, reflectance=0.0, rgba=list(DEFAULT_RGBA))
    for g in spec.geoms:
        if g.material:
            continue                                   # textured or already styled: keep it
        g.material = "_showcase_satin" if tuple(np.round(g.rgba, 6)) != DEFAULT_RGBA else "_showcase_satin_default"


def preset_look(name):
    if not os.path.isdir(SHOWCASE_TOOLS):
        raise RendererUnavailable("mujoco-showcase", f"look preset {name!r} needs scripts/olympiad/showcase/looks.py")
    if SHOWCASE_TOOLS not in sys.path:
        sys.path.insert(0, SHOWCASE_TOOLS)
    import looks
    if name not in looks.SHOWCASE:
        raise ValueError(f"unknown showcase look {name!r}; have {sorted(looks.SHOWCASE)}")
    return looks.SHOWCASE[name]


class ShowcaseRenderer(MujocoRenderer):
    name = "mujoco-showcase"
    title = "MuJoCo showcase"
    realtime = True
    needs_gpu = False
    label = label_text(title)

    def __init__(self, scene: Scene, ssaa: int = 1, stamp: bool = False, **opts):
        self.ssaa, self.stamp = max(1, int(ssaa)), bool(stamp)
        self.label = label_text(self.title, presentation=scene.match is not None and not scene.players)
        super().__init__(scene, **opts)

    def make_spec(self):
        spec = load_spec(self.scene)
        size = (self._size[0] * self.ssaa, self._size[1] * self.ssaa)
        look = self.scene.look or {}
        added = {g.name: g.material for g in spec.geoms if (g.name or "").startswith(VISUAL_PREFIX)}
        (preset_look(look["preset"]) if look.get("preset") else generic_look)(spec, size)
        for g in spec.geoms:                           # a presentation scene's own materials win over the look
            if g.name in added:
                g.material = added[g.name]
        return spec

    def _build(self):
        self._size = (max(self._size[0], 1), max(self._size[1], 1))
        super()._build()
        ref = compile_spec(load_spec(self.scene), self._n, self._size)        # what the default renderer draws
        bad = same_scene(ref, self.m)
        if bad:
            raise RuntimeError(f"{self.name}: not the same scene as the default renderer: {bad[:8]}")
        self.scene_diffs = bad

    def render(self, state, cameras):
        from ..base import as_cameras
        cams = as_cameras(cameras)
        s = self.ssaa
        big = [type(c)(c.name, c.pos, c.lookat, c.up, c.fovy_deg, c.width * s, c.height * s) for c in cams]
        imgs = super().render(state, big)
        out = []
        for img, c in zip(imgs, cams):
            if s > 1:                                  # box filter: same projection, anti-aliased
                img = img.reshape(c.height, s, c.width, s, 3).mean(axis=(1, 3)).round().astype(np.uint8)
            out.append(stamp(img, self.label) if self.stamp else img)
        return out


RENDERER = ShowcaseRenderer
