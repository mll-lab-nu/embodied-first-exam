"""Free Cast Coil pieces in the shared laboratory tabletop scene."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf
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
    template = cfg.task.get('template')
    if template is not None:
        template = OmegaConf.to_container(template, resolve=True) if OmegaConf.is_config(template) else template
        if template_path and load_template(template_path) != template:
            raise ValueError("Inline instance and template file disagree")
    else:
        template = load_template(template_path) if template_path else None
    assembly, report = generate_assets(folder, scale=float(cfg.task.scale),
        template=template)
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
    poses = [(rotation, origin)] * 2
    if cfg.task.get("initial_body_poses") is not None:
        mount = np.asarray(cfg.env.robot_mount.pos)
        poses = [(Rotation.from_quat(p["r"]), mount + np.asarray(p["p"])) for p in cfg.task.initial_body_poses]
        if len(poses) != 2:
            raise ValueError("Expected two initial body poses")
    elif cfg.task.get("objective", "disassemble") == "assemble":
        from .assembly_task import DEFAULT_XY_OFFSET, initial_poses
        poses = initial_poses(assembly, origin, rotation, cfg.task.get("initial_xy_offset_m", DEFAULT_XY_OFFSET))
    bodies = {}
    for item, (body_rotation, body_origin) in zip(report["bodies"], poses):
        name = item["name"]
        body = base.scene.add_entity(gs.morphs.URDF(
            file=str(folder/name/f"{name}.urdf"), pos=body_origin+body_rotation.apply(item["origin_m"]),
            quat=body_rotation.as_quat()[[3, 0, 1, 2]], fixed=False, align=False,
            convexify=False, decimate=False, merge_fixed_links=False,
            collision=not render_only),
            material=gs.materials.Rigid(friction=.35),
            surface=gs.surfaces.Default(smooth=False), name=name)
        bodies[name] = base.manifest.add(name, body)
    builder.finalize(base)
    if any(b.n_dofs != 6 or b.n_links != 1 for b in bodies.values()):
        raise RuntimeError("Each coil must load as one independent free rigid body")
    return CoilScene(base, assembly, bodies, report, origin, rotation)
