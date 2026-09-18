"""Two independent Keyhole rigid plates on the shared laboratory table."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import genesis as gs
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.world import StandardTabletopSceneBuilder
from .geometry import generate_assets


@dataclass
class KeyholeScene:
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


def build_scene(cfg, asset_dir, geometry_path=None, *, replay_only=False):
    folder = Path(asset_dir).resolve()
    if geometry_path is None:
        assembly, report = generate_assets(folder, scale=float(cfg.task.scale))
    else:
        from .variant_assets import generate_variant_assets
        assembly, report = generate_variant_assets(folder, geometry_path)
        if float(cfg.task.scale) != assembly.scale:
            raise ValueError("Variant scale does not match the scene")
    if cfg.task.variant != assembly.template["template_id"] or cfg.task.initial_relative_pose_id != assembly.template["initial_relative_pose_id"]:
        raise ValueError("Unknown Keyhole geometry or initial pose")
    xy = np.asarray(cfg.task.center_xy_m, dtype=float)
    if xy.shape != (2,) or not np.isfinite([*xy, cfg.task.yaw_deg, cfg.task.initial_floor_clearance_m]).all():
        raise ValueError("Invalid Keyhole layout")
    if cfg.task.initial_floor_clearance_m < 0:
        raise ValueError("Initial floor clearance must be nonnegative")
    builder = StandardTabletopSceneBuilder(cfg.env, cfg.robot_control,
        rigid_options=gs.options.RigidOptions(enable_collision=not replay_only, enable_self_collision=not replay_only,
            iterations=100, max_collision_pairs=1 if replay_only else 8192, constraint_timeconst=.001))
    base = builder.create(show_viewer=bool(cfg.run.viewer), include_robot=bool(cfg.run.include_robot),
        robot_material=gs.materials.Rigid(gravity_compensation=1.0))
    # Put both long axes along the tabletop, with each plate 45 degrees to it.
    rotation = (Rotation.from_euler("z", float(cfg.task.yaw_deg), degrees=True)
                * Rotation.from_euler("y", 90, degrees=True)
                * Rotation.from_euler("z", 45, degrees=True))
    vertices = np.concatenate([rotation.apply(b.visual.vertices) for b in assembly.bodies])
    mid = (vertices.min(axis=0)+vertices.max(axis=0))/2
    origin = np.r_[xy-mid[:2], base.frames.table_surface_origin[2]-vertices[:,2].min()+float(cfg.task.initial_floor_clearance_m)]
    bodies = {}
    for item in report["bodies"]:
        name = item["name"]
        body = base.scene.add_entity(gs.morphs.URDF(
            file=str(folder/name/f"{name}.urdf"), pos=origin+rotation.apply(item["origin_m"]),
            quat=rotation.as_quat()[[3,0,1,2]], fixed=False, align=False,
            # Each URDF collision is already a convex prism. Mark these
            # individually convex for GJK; never convexify the whole plate.
            convexify=True, decimate=False, merge_fixed_links=False),
            material=gs.materials.Rigid(friction=.35),
            surface=gs.surfaces.Default(smooth=False), name=name)
        bodies[name] = base.manifest.add(name, body)
    builder.finalize(base)
    if any(b.n_dofs != 6 or b.n_links != 1 for b in bodies.values()):
        raise RuntimeError("Each Keyhole plate must be one free six-DOF link")
    loaded_report = []
    for source, item in zip(assembly.bodies, report["bodies"]):
        geoms = bodies[source.name].geoms
        if len(geoms) != len(source.collision) or not all(g.is_convex for g in geoms):
            raise RuntimeError("Genesis merged or changed the Keyhole convex partition")
        bounds_error, volume_error = 0.0, 0.0
        for geom, expected in zip(geoms, source.collision):
            transform = np.eye(4)
            transform[:3,:3] = Rotation.from_quat(np.asarray(geom.init_quat)[[1,2,3,0]]).as_matrix()
            transform[:3,3] = geom.init_pos
            loaded = geom.mesh.trimesh.copy().apply_transform(transform)
            bounds_error = max(bounds_error, float(np.max(np.abs(
                loaded.bounds+item["origin_m"]-expected.bounds))))
            volume_error += abs(loaded.volume-expected.volume)
        if bounds_error > 1e-7 or volume_error > source.visual.volume*1e-5:
            raise RuntimeError("Loaded collision geometry differs from the authored solid")
        loaded_report.append(dict(name=source.name, loaded_convex_prisms=len(geoms),
            max_bounds_error_m=bounds_error, absolute_volume_error_m3=float(volume_error), passed=True))
    report["loaded_collision_audit"] = loaded_report
    return KeyholeScene(base, assembly, bodies, report, origin, rotation)
