"""Free Cast Coil pieces in the shared laboratory tabletop scene."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import genesis as gs
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.world import StandardTabletopSceneBuilder
from .geometry import generate_assets, load_template


@dataclass
class CoilScene:
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


def build_scene(cfg, asset_dir, *, render_only=False):
    folder = Path(asset_dir).resolve()
    template_path = cfg.task.get('template_path')
    assembly, report = generate_assets(folder, scale=float(cfg.task.scale),
        template=load_template(template_path) if template_path else None)
    if cfg.task.variant != assembly.template["template_id"]:
        raise ValueError("Unknown Cast Coil variant")
    xy = np.asarray(cfg.task.center_xy_m, dtype=float)
    if xy.shape != (2,) or not np.isfinite([*xy, cfg.task.yaw_deg, cfg.task.initial_floor_clearance_m]).all():
        raise ValueError("Invalid Cast Coil layout")
    if cfg.task.initial_floor_clearance_m < 0:
        raise ValueError("Initial floor clearance must be nonnegative")
    builder = StandardTabletopSceneBuilder(cfg.env, cfg.robot_control,
        rigid_options=gs.options.RigidOptions(enable_collision=not render_only,
            enable_self_collision=not render_only,
            iterations=100, max_collision_pairs=32 if render_only else 4096, constraint_timeconst=.001,
            noslip_iterations=int(cfg.task.get('physics', {}).get('noslip_iterations', 0))))
    base = builder.create(show_viewer=bool(cfg.run.viewer), include_robot=bool(cfg.run.include_robot),
        robot_material=gs.materials.Rigid(gravity_compensation=1.0),
        robot_morph_options={"collision": False} if render_only else None)
    rotation = Rotation.from_euler("z", float(cfg.task.yaw_deg), degrees=True)
    bottom = min(b.visual.bounds[0, 2] for b in assembly.bodies)
    origin = np.r_[xy, base.frames.table_surface_origin[2]-bottom+float(cfg.task.initial_floor_clearance_m)]
    bodies = {}
    for item in report["bodies"]:
        name = item["name"]
        body = base.scene.add_entity(gs.morphs.URDF(
            file=str(folder/name/f"{name}.urdf"), pos=origin+rotation.apply(item["origin_m"]),
            quat=rotation.as_quat()[[3, 0, 1, 2]], fixed=False, align=False,
            convexify=False, decimate=False, merge_fixed_links=False,
            collision=not render_only),
            material=gs.materials.Rigid(friction=.35),
            surface=gs.surfaces.Default(smooth=False), name=name)
        bodies[name] = base.manifest.add(name, body)
    builder.finalize(base)
    if any(b.n_dofs != 6 or b.n_links != 1 for b in bodies.values()):
        raise RuntimeError("Each coil must load as one independent free rigid body")
    return CoilScene(base, assembly, bodies, report, origin, rotation)
