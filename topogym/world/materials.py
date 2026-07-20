"""Shared surface palette for TopoGym scenes (module A).

One place owns the semantic material roles so every task builds surfaces the
same way, instead of scattering inline ``gs.surfaces.Plastic(...)`` calls with
ad-hoc roughness values (the pre-unification code had 12 distinct values
between 0.5 and 0.95 across 35 call sites).

Colors stay caller/config-driven — this module only owns the per-role finish.

Rasterizer note (see docs/develop/visual/photorealism_workstream_zh.md): Genesis'
rasterizer honors only a surface's diffuse color/texture and opacity;
``roughness`` is raytracer-only and currently has no visual effect. The
per-role values are kept anyway so a future renderer upgrade inherits a
consistent finish for free.
"""

from __future__ import annotations

import genesis as gs

# Per-role finish. Values consolidate the sensible majority of the previous
# inline constants (matte boards/markers, slightly glossier rigid objects).
_ROLE_ROUGHNESS = {
    "table": 0.90,       # shared table top
    "stage": 0.95,       # optional staging pad
    "frame": 0.70,       # decorative table frame / apron
    "board": 0.90,       # task boards, workspaces, discard zones, substrates
    "marker": 0.95,      # flat visual indicators: holes, slots, cells, path dots
    "fixture": 0.80,     # static rigid posts, pegs, supports, axes
    "connector": 0.85,   # graspable endpoint handles / plugs
    "object": 0.80,      # manipulable rigid bodies: blocks, walls, plates, tabs
    "deformable": 0.75,  # PBD visual skins: ropes, cables, film
}


def plastic(role: str, color, *, vis_mode: str | None = None) -> gs.surfaces.Plastic:
    """Return the standard Plastic surface for a semantic ``role``.

    ``color`` is required (RGB tuple/list, usually straight from config).
    ``vis_mode`` is passed through for deformable visual skins.
    """

    if role not in _ROLE_ROUGHNESS:
        raise ValueError(
            f"Unknown material role {role!r}; expected one of {sorted(_ROLE_ROUGHNESS)}."
        )
    kwargs = {
        "color": tuple(float(channel) for channel in color),
        "roughness": _ROLE_ROUGHNESS[role],
    }
    if vis_mode is not None:
        kwargs["vis_mode"] = str(vis_mode)
    return gs.surfaces.Plastic(**kwargs)
