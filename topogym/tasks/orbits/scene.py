"""Shared Nyx laboratory with an explicitly frozen puzzle reconstruction."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from .geometry import OrbitsLayout, generate_assets


@dataclass
class OrbitsScene:
    tabletop: Any
    layout: OrbitsLayout
    asset_report: dict
    entities: dict
    import_audit: dict | None = None
    inspection_only: bool = True

    @property
    def scene(self):
        return self.tabletop.scene

    @property
    def cameras(self):
        return self.tabletop.cameras

    @property
    def manifest(self):
        return self.tabletop.manifest

    def step(self, *args, **kwargs):
        raise RuntimeError("Static reconstruction only: cord dynamics and handle coupling are not implemented")


class OrbitsSceneBuilder:
    def __init__(self, env_cfg, task_cfg, robot_cfg):
        self.env_cfg, self.task_cfg, self.robot_cfg = env_cfg, task_cfg, robot_cfg

    def build(self, *, asset_dir, show_viewer=False, include_robot=True):
        import genesis as gs
        from topogym.world import StandardTabletopSceneBuilder

        cfg = self.task_cfg
        if cfg.variant != "video_reconstruction_v1" or cfg.mode != "static_inspection":
            raise ValueError("Only video_reconstruction_v1/static_inspection is implemented")
        if self.env_cfg.sim.n_envs != 0:
            raise ValueError("Initial inspection requires a single unbatched scene")
        folder = Path(asset_dir).resolve()
        layout, report = generate_assets(folder, OrbitsLayout(
            **OmegaConf.to_container(cfg.geometry, resolve=True)).scaled(float(cfg.get("scale", 1.))))
        rotation = Rotation.from_euler("z", float(cfg.yaw_deg), degrees=True)
        xy = np.asarray(cfg.origin_xy_m, dtype=float)
        # The complete fixture, cord tails and pull handle must fit on the table.
        import trimesh
        assembly = trimesh.load(folder/"scene.glb", force="scene")
        corners = trimesh.bounds.corners(assembly.bounds)
        points = rotation.apply(corners)[:, :2]+xy
        table_xy = np.asarray(self.env_cfg.world.table.pos[:2])
        half = np.asarray(self.env_cfg.world.table.size[:2])/2
        if np.any(points < table_xy-half) or np.any(points > table_xy+half):
            raise ValueError("Reconstruction extends beyond the shared table")
        builder = StandardTabletopSceneBuilder(self.env_cfg, self.robot_cfg)
        base = builder.create(show_viewer=show_viewer, include_robot=include_robot,
                              robot_material=gs.materials.Rigid(gravity_compensation=1.))
        origin = [*xy, base.frames.table_surface_origin[2]]
        q = rotation.as_quat()[[3, 0, 1, 2]]
        entities = {}
        for name in report["meshes"]:
            key = f"orbits_{name}"
            # This stage is visual inspection, explicitly fixed and collision
            # disabled. No convex hull may fill the ring or handle holes.
            entities[name] = base.manifest.add(key, base.scene.add_entity(
                gs.morphs.Mesh(file=str(folder/f"{name}.glb"), pos=origin, quat=q,
                               fixed=True, collision=False, convexify=False, decimate=False,
                               file_meshes_are_zup=True),
                material=gs.materials.Rigid(), name=key))
        builder.finalize(base)
        bounds_errors = {}
        for name, entity in entities.items():
            actual = np.concatenate([g.get_vverts().detach().cpu().numpy() for g in entity.vgeoms])
            source = trimesh.load(folder/f"{name}.obj", force="mesh")
            expected = rotation.apply(source.vertices)+origin
            bounds_errors[name] = float(np.max(np.abs(
                np.array([actual.min(axis=0), actual.max(axis=0)])
                - np.array([expected.min(axis=0), expected.max(axis=0)]))))
        if max(bounds_errors.values()) > 1e-5:
            raise RuntimeError(f"Imported visuals differ from authored coordinates: {bounds_errors}")
        return OrbitsScene(base, layout, report, entities,
                           dict(world_bounds_error_m=bounds_errors, passed=True))
