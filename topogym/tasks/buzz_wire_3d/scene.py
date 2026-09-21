"""Complete tabletop scene with a fixed toy and one free six-DOF loop wand."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from .geometry import BuzzWireLayout, generate_assets
from .verification import verify_route


@dataclass
class BuzzWireScene:
    tabletop: Any
    wire: Any
    wand: Any
    base: Any
    route: Any
    origin: np.ndarray
    rotation: Rotation
    geometry_report: dict
    clearance_report: dict

    @property
    def scene(self):
        return self.tabletop.scene

    @property
    def manifest(self):
        return self.tabletop.manifest

    @property
    def cameras(self):
        return self.tabletop.cameras

    @property
    def bodies(self):
        return {"buzz_wand": self.wand}

    def reference_pose(self, progress):
        """Return the reference loop-link pose in world coordinates (wxyz)."""
        if not hasattr(self.route, "pose"):
            raise RuntimeError(
                "This episode has static geometry only, no reference pose guide"
            )
        p, q = self.route.pose(progress)
        orientation = self.rotation * Rotation.from_quat(q[[1, 2, 3, 0]])
        return self.origin + self.rotation.apply(p), orientation.as_quat()[[3, 0, 1, 2]]


class BuzzWireSceneBuilder:
    def __init__(self, env_cfg, task_cfg, robot_cfg):
        self.env_cfg, self.task_cfg, self.robot_cfg = env_cfg, task_cfg, robot_cfg

    def build(
        self,
        *,
        asset_dir,
        show_viewer=False,
        include_robot=False,
        constraint_timeconst=None,
        static_assets=None,
    ):
        import genesis as gs
        from topogym.world import StandardTabletopSceneBuilder

        if self.env_cfg.sim.n_envs != 0:
            raise ValueError(
                "Spatial buzz-wire preview currently requires an unbatched scene"
            )
        cfg = self.task_cfg
        if constraint_timeconst is None:
            constraint_timeconst = float(
                cfg.get("physics", {}).get("constraint_timeconst", 0.001)
            )
        if constraint_timeconst <= 0:
            raise ValueError("Contact time constant must be positive")
        folder = Path(asset_dir).resolve()
        if static_assets is None:
            layout = BuzzWireLayout(
                **OmegaConf.to_container(cfg.geometry, resolve=True)
            )
            route, geometry = generate_assets(folder, layout)
            clearance = verify_route(route)
            if not clearance["passed"]:
                raise ValueError(f"Unplayable reference route: {clearance}")
            p, q = route.pose(0.0)
        else:
            # Trusted operator loader supplies hash-checked URDFs and a single
            # initial pose. It does not construct or verify a solution route.
            route = static_assets(folder)
            layout, geometry = route.layout, route.geometry_report
            p, q = route.initial_position, route.initial_quaternion
            clearance = dict(
                passed=False,
                scope="Static episode; solution qualification not inherited",
            )
        if cfg.variant != layout.template_id:
            raise ValueError("Scene variant and geometry template differ")
        xy = np.asarray(cfg.origin_xy_m, dtype=float)
        rotation = Rotation.from_euler("z", float(cfg.yaw_deg), degrees=True)
        quaternion = rotation.as_quat()[[3, 0, 1, 2]]
        table_xy = np.asarray(self.env_cfg.world.table.pos[:2])
        table_half = np.asarray(self.env_cfg.world.table.size[:2]) / 2
        base_half_xy = np.abs(rotation.as_matrix()[:2, :2]) @ (
            np.asarray(layout.base_size_m[:2]) / 2
        )
        if np.any(np.abs(xy - table_xy) + base_half_xy > table_half):
            raise ValueError("Toy base extends beyond the table")
        builder = StandardTabletopSceneBuilder(
            self.env_cfg,
            self.robot_cfg,
            rigid_options=gs.options.RigidOptions(
                enable_collision=True,
                enable_self_collision=True,
                enable_neutral_collision=True,
                iterations=100,
                noslip_iterations=int(
                    cfg.get("physics", {}).get("noslip_iterations", 0)
                ),
                noslip_tolerance=float(
                    cfg.get("physics", {}).get("noslip_tolerance", 1e-6)
                ),
                max_collision_pairs=4096,
                max_contacts=int(cfg.get("physics", {}).get("max_contacts", 512)),
                constraint_timeconst=constraint_timeconst,
            ),
        )
        tabletop = builder.create(
            show_viewer=show_viewer,
            include_robot=include_robot,
            robot_material=gs.materials.Rigid(gravity_compensation=1.0),
        )
        scene, manifest = tabletop.scene, tabletop.manifest
        origin = np.r_[xy, tabletop.frames.table_surface_origin[2]]
        wood_finish = getattr(layout, "finish", "legacy") in {
            "wood_metal",
            "toy_wood_copper",
        }
        base_morph = (
            gs.morphs.Mesh(
                file=str(folder / "base_wood.glb"),
                pos=origin + [0, 0, layout.base_size_m[2] / 2],
                quat=quaternion,
                fixed=True,
                convexify=True,
                decimate=False,
                file_meshes_are_zup=True,
            )
            if wood_finish
            else gs.morphs.Box(
                pos=origin + [0, 0, layout.base_size_m[2] / 2],
                quat=quaternion,
                size=layout.base_size_m,
                fixed=True,
            )
        )
        if getattr(layout, "finish", "legacy") == "toy_wood_copper":
            base_morph = gs.morphs.URDF(
                file=str(folder / "base.urdf"),
                pos=origin + [0, 0, layout.base_size_m[2] / 2],
                quat=quaternion,
                fixed=True,
                merge_fixed_links=False,
                convexify=True,
                decimate=False,
            )
        base = manifest.add(
            "buzz_base",
            scene.add_entity(
                base_morph,
                surface=None
                if wood_finish
                else gs.surfaces.Plastic(color=(0.70, 0.50, 0.27)),
                name="buzz_base",
            ),
        )
        wire = manifest.add(
            "buzz_wire",
            scene.add_entity(
                gs.morphs.URDF(
                    file=str(folder / "wire.urdf"),
                    pos=origin,
                    quat=quaternion,
                    fixed=True,
                    merge_fixed_links=False,
                    convexify=True,
                    decimate=False,
                ),
                material=gs.materials.Rigid(friction=0.3),
                name="buzz_wire",
            ),
        )
        initial_rotation = rotation * Rotation.from_quat(q[[1, 2, 3, 0]])
        wand = manifest.add(
            "buzz_wand",
            scene.add_entity(
                gs.morphs.URDF(
                    file=str(folder / "wand.urdf"),
                    pos=origin + rotation.apply(p),
                    quat=initial_rotation.as_quat()[[3, 0, 1, 2]],
                    align=False,
                    fixed=False,
                    merge_fixed_links=False,
                    convexify=True,
                    decimate=False,
                ),
                material=gs.materials.Rigid(friction=0.3),
                name="buzz_wand",
            ),
        )
        if wood_finish:
            from .appearance import restore_renderer_materials

            for entity in (base, wire, wand):
                restore_renderer_materials(entity)
        builder.finalize(tabletop)
        return BuzzWireScene(
            tabletop, wire, wand, base, route, origin, rotation, geometry, clearance
        )
