"""Fixed cage, one free hedgehog rigid body, and the shared Panda/Robotiq rig."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import genesis as gs
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.world import StandardTabletopSceneBuilder
from .geometry import HedgehogLayout, generate_assets, load_template


@dataclass
class HedgehogScene:
    tabletop: Any
    layout: HedgehogLayout
    cage: Any
    hedgehog: Any
    asset_report: dict
    cage_origin: np.ndarray

    @property
    def scene(self):
        return self.tabletop.scene

    @property
    def manifest(self):
        return self.tabletop.manifest

    @property
    def cameras(self):
        return self.tabletop.cameras


class HedgehogSceneBuilder:
    def __init__(self, env_cfg, task_cfg, robot_cfg):
        self.env_cfg, self.task_cfg, self.robot_cfg = env_cfg, task_cfg, robot_cfg

    def build(self, *, asset_dir, show_viewer=False, reuse_assets=False):
        cfg = self.task_cfg
        folder = Path(asset_dir).resolve()
        if reuse_assets:
            template = load_template(folder / "template.json")
            report = json.loads((folder / "asset_report.json").read_text())
            if template != load_template() or report["scale"] != float(cfg.scale):
                raise ValueError("Cached assets differ from the requested geometry")
            if any(report[name]["visual_finish"] != str(cfg.get("finish", "wood"))
                   for name in ("cage", "hedgehog")):
                raise ValueError("Cached assets differ from the requested visual finish")
            for filename, digest in json.loads((folder / "sha256.json").read_text()).items():
                if hashlib.sha256((folder / filename).read_bytes()).hexdigest() != digest:
                    raise ValueError(f"Cached asset hash mismatch: {filename}")
            layout = HedgehogLayout(template, float(cfg.scale))
        else:
            layout, report = generate_assets(folder, float(cfg.scale), finish=str(cfg.get("finish", "wood")))
        physics = cfg.get("physics", {})
        rigid_options = dict(enable_collision=True, enable_self_collision=True,
            enable_joint_limit=True, max_collision_pairs=8192,
            iterations=int(physics.get("iterations", 100)))
        if "constraint_timeconst" in physics:
            rigid_options["constraint_timeconst"] = float(physics["constraint_timeconst"])
        if "noslip_iterations" in physics:
            rigid_options["noslip_iterations"] = int(physics["noslip_iterations"])
        builder = StandardTabletopSceneBuilder(self.env_cfg, self.robot_cfg,
            rigid_options=gs.options.RigidOptions(**rigid_options))
        base = builder.create(show_viewer=show_viewer, include_robot=True,
            robot_material=gs.materials.Rigid(gravity_compensation=1.0))
        scene, manifest = base.scene, base.manifest
        floor = base.frames.table_surface_origin[2]
        xy = np.asarray(cfg.center_xy_m, dtype=float)
        height = layout.template["cage"]["height"] * layout.unit
        pad_height = float(cfg.mount_height_m)
        cage_origin = np.r_[xy, floor+pad_height+height/2]
        rotation = Rotation.from_euler("z", float(cfg.yaw_deg), degrees=True)
        q = rotation.as_quat()[[3,0,1,2]]
        manifest.add("hedgehog_mount", scene.add_entity(gs.morphs.Box(
            pos=(*xy, floor+pad_height/2),
            size=(float(cfg.mount_width_m), float(cfg.mount_width_m), pad_height), fixed=True),
            surface=gs.surfaces.Plastic(color=(.16,.20,.24)), name="hedgehog_mount"))
        cage = manifest.add("hedgehog_cage", scene.add_entity(gs.morphs.URDF(
            file=str(folder/"cage.urdf"), pos=cage_origin, quat=q, fixed=True,
            convexify=True, decimate=False, merge_fixed_links=False),
            material=gs.materials.Rigid(friction=float(physics.get("friction", .3))), name="hedgehog_cage"))
        initial = cfg.get("initial_pose", report["initial_pose"])
        initial_q = np.asarray(initial["quaternion_wxyz"])
        ball_rotation = rotation * Rotation.from_quat(initial_q[[1,2,3,0]])
        position = cage_origin + rotation.apply(initial["position_m"])
        ball = manifest.add("hedgehog_ball", scene.add_entity(gs.morphs.URDF(
            file=str(folder/"hedgehog.urdf"), pos=position,
            quat=ball_rotation.as_quat()[[3,0,1,2]], fixed=False,
            convexify=True, decimate=False, merge_fixed_links=False),
            material=gs.materials.Rigid(friction=float(physics.get("friction", .3))), name="hedgehog_ball"))
        # Small fasteners make the fixed mounting visible. They do not occupy
        # any cage window or add hidden constraints to the hedgehog.
        for i, (x, y) in enumerate(((-1,-1),(-1,1),(1,-1),(1,1))):
            offset = float(cfg.mount_width_m)*.4
            manifest.add(f"hedgehog_mount_bolt_{i}", scene.add_entity(gs.morphs.Cylinder(
                pos=(xy[0]+x*offset, xy[1]+y*offset, floor+pad_height+.0015),
                radius=.005, height=.003, fixed=True),
                surface=gs.surfaces.Plastic(color=(.65,.67,.70)), name=f"hedgehog_mount_bolt_{i}"))
        builder.finalize(base)
        return HedgehogScene(base, layout, cage, ball, report, cage_origin)
