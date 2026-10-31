"""Scene of a dough / plug task from the ``task`` block of its ``cfg.yaml``.

Two things are built from the same numbers (the task block ``p``, anchored frame = origin at ``p["anchor"]``):

* :func:`build_dough_scene` - the sidecar world description, particles and success grid (``softbody_geom.dough_task.DoughScene``),
  pure numpy, used by the task and by the scripted policy (which derives its waypoints from ``scene.info``);
* :func:`fixtures` / :func:`build_scene` - the Isaac Lab scene: the same plate / tray / hole plate as static (kinematic) cuboids,
  the tool rack and the scraper tool, plus collision-free *visual* boxes (the trough rails, the lead-in ramps) that exist in the
  sidecar world only.

Isaac Lab is imported lazily inside :func:`build_scene` / :func:`spawn_visual_boxes`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..core import math as m
from ..core.types import TABLE_TOP_Z
from ..softbody_geom import dough_pinch as dp
from ..softbody_geom import dough_task as dt
from ..softbody_geom import plug_pad_scene as pps
from ..softbody_geom import plug_scene as ps
from ..softbody_geom.dough_task import DoughScene

PLATE_COLOR = (0.20, 0.22, 0.26)
WALL_COLOR = (0.35, 0.35, 0.38)
RACK_COLOR = (0.55, 0.45, 0.35)
HOLE_PLATE_COLOR = (0.55, 0.55, 0.60)
RAMP_COLOR = (0.45, 0.45, 0.50)
TOOL_USD = "objects/dough/scraper_tool.usd"


@dataclass
class VisualBox:
    """A collision-free box (env frame): decoration of geometry that lives in the sidecar world."""

    name: str
    pos: Tuple[float, float, float]
    size: Tuple[float, float, float]
    quat: Tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    color: Tuple[float, float, float] = WALL_COLOR


# ----------------------------------------------------------------------------- sidecar scene


def build_dough_scene(p: Dict[str, Any], seed: int = 0) -> DoughScene:
    """The sidecar world of the task block ``p`` (``kind`` = ``pinch`` | ``fill`` | ``plug_pads``), nominal layout.

    The pinch scenes take their pad collider box from ``p["colliders"]``; ``dough_target_shape`` names its pinched slots
    (``pinch_offsets``) and the slots that must stay thick (``keep_offsets``) explicitly instead of drawing them."""
    kind = str(p.get("kind", "pinch"))
    anchor = np.asarray(p["anchor"], dtype=np.float64)
    rng = np.random.default_rng(int(seed))
    q = dict(p)
    cols = p.get("colliders")
    if cols:
        q["pad_half"] = tuple(float(v) for v in cols[0]["half"])
        if kind == "pinch":  # the plug world sets its own (larger) pad friction
            q["pad_mu"] = float(cols[0].get("mu", dp.PAD_MU))
    if kind == "pinch":
        q.pop("slots", None)  # no random slot draw: the pattern is fixed by the config
        sc = dp.make_pinch_scene(q, anchor, rng)
        if "pinch_offsets" in p:
            sc.extra["pinch_offsets"] = [float(v) for v in p["pinch_offsets"]]
        if "keep_offsets" in p:
            sc.extra["keep_offsets"] = [float(v) for v in p["keep_offsets"]]
        return sc
    if kind == "fill":
        return dt.make_fill_scene(q, anchor, rng)
    if kind == "plug_pads":
        return pps.make_plug_pad_scene(q, anchor, rng)
    raise ValueError(f"unknown dough task kind {kind!r}")


# ----------------------------------------------------------------------------- Isaac fixtures


def tool_start_pose(p: Dict[str, Any]) -> np.ndarray:
    """Env-frame pose7 of the scraper standing in its rack groove (blade bottom edge ``tool_rest_gap`` above the groove floor)."""
    r = p["rack"]
    x, y = (float(v) for v in r["xy"])
    z = TABLE_TOP_Z + float(r["base_size"][2]) + float(p.get("tool_rest_gap", 0.0005))
    return m.pose_from_pos_euler_deg((x, y, z), (0.0, 0.0, float(p.get("tool_yaw_deg", 0.0))))


def fixtures(p: Dict[str, Any]) -> Tuple[list, List[VisualBox]]:
    """``(objects, visuals)``: the :class:`ObjectCfg` list (static cuboids + the tool) and the visual-only boxes of the task block."""
    from ..backends.isaaclab_scene import ObjectCfg

    kind = str(p.get("kind", "pinch"))
    anchor = np.asarray(p["anchor"], dtype=np.float64)
    objects: list = []
    visuals: List[VisualBox] = []

    def static_box(name, center_anchored, half, color, friction):
        c = anchor + np.asarray(center_anchored, dtype=np.float64)
        objects.append(
            ObjectCfg(
                name,
                pos=tuple(float(v) for v in c),
                shape="cuboid",
                dims=tuple(2.0 * float(h) for h in half),
                kinematic=True,
                color=color,
                friction=float(friction),
            )
        )

    if kind == "pinch":
        half = [float(v) for v in p.get("plate_half", [0.12, 0.12])]
        thick = max(float(anchor[2] - TABLE_TOP_Z), 0.004)  # the plate stands on the table, its top at the anchor
        static_box(
            "plate",
            [0.0, 0.0, -0.5 * thick],
            [half[0], half[1], 0.5 * thick],
            PLATE_COLOR,
            p.get("plate_friction", 0.05),
        )
        th = float(p.get("trough_h", 0.0))
        if th > 0.0:  # the two low rails of the sidecar world (dough_pinch.make_pinch_scene), drawn only
            w, L, tt = float(p.get("ridge_w", 0.018)), float(p.get("ridge_len", 0.07)), float(p.get("trough_t", 0.004))
            cx, cy = (float(v) for v in p.get("blob_center", [0.0, 0.0]))
            for k, sgn in enumerate((-1.0, 1.0)):
                c = anchor + np.array([cx + sgn * (0.5 * w + 0.5 * tt + 0.0005), cy, 0.5 * th])
                visuals.append(VisualBox(f"trough_rail_{k}", tuple(c), (tt, L + 0.01, th), color=WALL_COLOR))
    elif kind == "fill":
        inner = [float(v) for v in p.get("tray_inner", [0.16, 0.10])]
        boxes = dt.tray_boxes(inner, float(p.get("wall_h", 0.02)), float(p.get("wall_t", 0.006)))
        names = ["tray_floor", "tray_wall_px", "tray_wall_nx", "tray_wall_py", "tray_wall_ny"]
        for name, b in zip(names, boxes):
            static_box(
                name,
                b["center"],
                b["half"],
                PLATE_COLOR if name == "tray_floor" else WALL_COLOR,
                p.get("tray_friction", 0.85),
            )
        r = p["rack"]
        x, y = (float(v) for v in r["xy"])
        bs, rs = [float(v) for v in r["base_size"]], [float(v) for v in r["rail_size"]]
        groove = float(r.get("groove_w", 0.006))
        mu = float(r.get("friction", 0.85))
        base_c = np.array([x, y, TABLE_TOP_Z + 0.5 * bs[2]])
        objects.append(
            ObjectCfg(
                "rack_base",
                pos=tuple(base_c),
                shape="cuboid",
                dims=tuple(bs),
                kinematic=True,
                color=RACK_COLOR,
                friction=mu,
            )
        )
        for k, sgn in enumerate((-1.0, 1.0)):
            c = np.array([x + sgn * (0.5 * groove + 0.5 * rs[0]), y, TABLE_TOP_Z + bs[2] + 0.5 * rs[2]])
            objects.append(
                ObjectCfg(
                    f"rack_rail_{k}",
                    pos=tuple(c),
                    shape="cuboid",
                    dims=tuple(rs),
                    kinematic=True,
                    color=RACK_COLOR,
                    friction=mu,
                )
            )
        from ..assets.resolve import resolve_asset

        start = tool_start_pose(p)
        objects.append(
            ObjectCfg(
                str(p.get("tool_name", "scraper_tool")),
                usd_path=resolve_asset(str(p.get("tool_usd", TOOL_USD))),
                pos=tuple(float(v) for v in start[:3]),
                ori_deg=(0.0, 0.0, float(p.get("tool_yaw_deg", 0.0))),
                mass=float(p.get("tool_mass", 0.04)),
                friction=float(p.get("tool_friction", 0.8)),
            )
        )
    elif kind == "plug_pads":
        specs = pps.specs_from_params(p)
        pick_xy = (float(p.get("pick_x", pps.PICK_X)), 0.0)
        tgt_xy = (float(p.get("target_x", pps.TARGET_X)), 0.0)
        mu = float(p.get("plate_mu", 0.05))
        for tag, xy, sp in (("pick", pick_xy, specs["pick"]), ("hole", tgt_xy, specs["plug"])):
            for b in ps.fixture_boxes(xy, 0.0, sp):
                static_box(f"{tag}_{b['name']}", b["pos"], b["half"], HOLE_PLATE_COLOR, mu)
        L = float(p.get("lead_in", 0.0))
        if L > 0.0:  # the 45 degree lead-in funnel of the sidecar world (sidecar/worlds/fem.py), drawn only
            sp = specs["plug"]
            hx_, hy_ = 0.5 * sp.hole[0], 0.5 * sp.hole[1]
            c45 = 0.5 * np.sqrt(2.0)
            for k, (ax, sgn) in enumerate(((0, 1.0), (0, -1.0), (1, 1.0), (1, -1.0))):
                half_in = (hx_, hy_)[ax]
                half_cross = (hy_, hx_)[ax] + L * c45 + 0.002
                centre = np.array([tgt_xy[0], tgt_xy[1], 0.5 * L * c45])
                centre[ax] += sgn * (half_in + 0.5 * L * c45)
                ang = -sgn * np.pi / 4.0
                if ax == 0:
                    q = m.quat_from_axis_angle([0.0, 1.0, 0.0], ang)
                    size = (L, 2.0 * half_cross, 0.001)
                else:
                    q = m.quat_from_axis_angle([1.0, 0.0, 0.0], -ang)
                    size = (2.0 * half_cross, L, 0.001)
                visuals.append(
                    VisualBox(f"leadin_ramp_{k}", tuple(anchor + centre), size, tuple(float(v) for v in q), RAMP_COLOR)
                )
    else:
        raise ValueError(f"unknown dough task kind {kind!r}")
    return objects, visuals


def spawn_visual_boxes(visuals: Sequence[VisualBox], root: str = "/World/Visuals") -> None:
    """Author the collision-free boxes (after the scene is built; pure geometry, PhysX ignores them)."""
    if not visuals:
        return
    import isaaclab.sim as sim_utils

    for v in visuals:
        cfg = sim_utils.CuboidCfg(
            size=tuple(v.size), visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=tuple(v.color))
        )
        cfg.func(f"{root}/{v.name}", cfg, translation=tuple(v.pos), orientation=tuple(float(x) for x in v.quat))


def make_scene(cfg: Dict[str, Any], cameras: bool = True, device: str = "cuda:0"):
    """The (unbuilt) Isaac Lab scene of a dough task configuration: call ``build()`` inside a running app."""
    from ..backends.isaaclab_scene import SceneCfg
    from ..backends.robot import RobotCfg
    from ..rigid.scene import RigidTaskScene

    class DoughTaskScene(RigidTaskScene):
        """``RigidTaskScene`` (USD tool with bound material) that also authors the visual-only boxes after the build."""

        visuals: List[VisualBox] = []

        def build(self) -> None:
            super().build()
            spawn_visual_boxes(self.visuals)

    p = cfg["task"]
    scene_cfg = cfg.get("scene") or {}
    gel = scene_cfg.get("gel") or {}
    robot = RobotCfg(
        gel_stiffness=float(gel.get("stiffness", 650.0)),
        gel_damping=float(gel.get("damping", 0.5)),
        gel_friction=float(gel.get("friction", 1.5)),
        close_magnitude=float((scene_cfg.get("robot") or {}).get("gripper_close", 0.038)),
    )
    objects, visuals = fixtures(p)
    scene = DoughTaskScene(SceneCfg(robot=robot, objects=objects, cameras=cameras, device=device))
    scene.visuals = visuals
    return scene


def build_scene(cfg: Dict[str, Any], cameras: bool = True, device: str = "cuda:0"):
    """:func:`make_scene` + ``build()``."""
    scene = make_scene(cfg, cameras=cameras, device=device)
    scene.build()
    return scene


__all__ = [
    "VisualBox",
    "build_dough_scene",
    "fixtures",
    "tool_start_pose",
    "spawn_visual_boxes",
    "make_scene",
    "build_scene",
    "TOOL_USD",
]
