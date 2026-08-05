"""Shared scene lighting for TopoGym scenes (module A companion to materials).

One place owns the scene-level lighting "craft" so every task builds through the
same rig, instead of every scene silently inheriting Genesis' bare default
(a single harsh directional key from ``(-1,-1,-1)`` with near-black ambient).

Rasterizer note (see docs/develop/visual/photorealism_workstream_zh.md): the
rasterizer honors ``VisOptions`` lights / ``ambient_light`` / ``background_color``
/ ``shadow`` / ``plane_reflection`` (but not per-surface ``roughness``), so this
scene-level rig is the effective lever for a nicer look. Colors/intensities are
overridable via the optional ``env.vis`` config block; defaults live here so the
rig is zero-config by default.
"""

from __future__ import annotations

import genesis as gs
from omegaconf import OmegaConf

# Neutral light-grey "studio" rig: a dominant key + a softer opposite fill so
# object faces read with gradient shading, lifted ambient so shadows aren't
# pure black, and a light neutral background.
_KEY_DIR = (-0.6, -0.5, -1.0)
_KEY_COLOR = (1.0, 0.98, 0.95)
_KEY_INTENSITY = 4.0
_FILL_DIR = (0.6, 0.4, -0.7)
_FILL_COLOR = (0.90, 0.93, 1.0)
_FILL_INTENSITY = 1.5
_AMBIENT_LIGHT = (0.35, 0.35, 0.38)
_BACKGROUND_COLOR = (0.55, 0.58, 0.62)
_SHADOW = True
_PLANE_REFLECTION = False


def _plain(value):
    if OmegaConf.is_config(value):
        return OmegaConf.to_container(value, resolve=True)
    return value


def _get(vis_cfg, name: str, default):
    if vis_cfg is None:
        return default
    value = getattr(vis_cfg, name, default)
    return default if value is None else value


def _vec3(value) -> tuple[float, float, float]:
    plain = _plain(value)
    return tuple(float(channel) for channel in plain)


def vis_options(env_cfg=None) -> gs.options.VisOptions:
    """Return the shared studio ``VisOptions`` rig.

    ``env_cfg`` is the ``env`` config node; an optional ``env.vis`` block
    overrides individual knobs (key/fill dir+color+intensity, ambient_light,
    background_color, shadow, plane_reflection). Absent block -> module defaults.
    """

    vis_cfg = getattr(env_cfg, "vis", None) if env_cfg is not None else None

    key = gs.options.vis.DirectionalLight(
        dir=_vec3(_get(vis_cfg, "key_dir", _KEY_DIR)),
        color=_vec3(_get(vis_cfg, "key_color", _KEY_COLOR)),
        intensity=float(_get(vis_cfg, "key_intensity", _KEY_INTENSITY)),
    )
    fill = gs.options.vis.DirectionalLight(
        dir=_vec3(_get(vis_cfg, "fill_dir", _FILL_DIR)),
        color=_vec3(_get(vis_cfg, "fill_color", _FILL_COLOR)),
        intensity=float(_get(vis_cfg, "fill_intensity", _FILL_INTENSITY)),
    )
    return gs.options.VisOptions(
        lights=[key, fill],
        ambient_light=_vec3(_get(vis_cfg, "ambient_light", _AMBIENT_LIGHT)),
        background_color=_vec3(_get(vis_cfg, "background_color", _BACKGROUND_COLOR)),
        shadow=bool(_get(vis_cfg, "shadow", _SHADOW)),
        plane_reflection=bool(_get(vis_cfg, "plane_reflection", _PLANE_REFLECTION)),
    )
