"""Complete free-body horseshoe assembly in the shared tabletop world."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import genesis as gs
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.world import StandardTabletopSceneBuilder
from .geometry import generate_assets, load_template


@dataclass
class HorseshoeScene:
    tabletop: Any
    assembly: Any
    bodies: dict
    asset_report: dict
    origin: np.ndarray
    rotation: Rotation

    @property
    def scene(self):
        return self.tabletop.scene

    @property
    def cameras(self):
        return self.tabletop.cameras

    @property
    def manifest(self):
        return self.tabletop.manifest


def build_scene(cfg, asset_dir):
    folder = Path(asset_dir).resolve()
    template = load_template(cfg.task.get("template_path"))
    assembly, report = generate_assets(folder, template=template, scale=float(cfg.task.scale))
    if cfg.task.variant != assembly.template["template_id"]:
        raise ValueError("Unknown horseshoe assembly variant")
    builder = StandardTabletopSceneBuilder(cfg.env, cfg.robot_control,
        rigid_options=gs.options.RigidOptions(enable_collision=True, enable_self_collision=True,
            iterations=100, max_collision_pairs=4096, constraint_timeconst=.001))
    base = builder.create(show_viewer=bool(cfg.run.viewer), include_robot=bool(cfg.run.include_robot),
        robot_material=gs.materials.Rigid(gravity_compensation=1.0))
    rotation = Rotation.from_euler("z", float(cfg.task.yaw_deg), degrees=True)
    bottom = min(rotation.apply(body.visual.vertices)[:, 2].min() for body in assembly.bodies)
    origin = np.r_[np.asarray(cfg.task.center_xy_m, dtype=float),
                   base.frames.table_surface_origin[2]-bottom+float(cfg.task.initial_floor_clearance_m)
                   +float(cfg.task.get("initial_lift_m", 0.))]
    bodies = {}
    for item in report["bodies"]:
        name = item["name"]
        entity = base.scene.add_entity(gs.morphs.URDF(
            file=str(folder/name/f"{name}.urdf"), pos=origin+rotation.apply(item["origin_m"]),
            quat=rotation.as_quat()[[3, 0, 1, 2]], fixed=False, align=False,
            convexify=True, decimate=False, merge_fixed_links=False),
            material=gs.materials.Rigid(friction=.3), name=name)
        bodies[name] = base.manifest.add(name, entity)
    builder.finalize(base)
    if any(entity.n_dofs != 6 or entity.n_links != 1 for entity in bodies.values()):
        raise RuntimeError("Every puzzle part must be a single free rigid body")
    return HorseshoeScene(base, assembly, bodies, report, origin, rotation)
