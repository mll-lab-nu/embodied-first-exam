"""Load a qualified instance into the task scene without drawing another seed.

This scene adapter is shared by future physical/data runners. The CLI only
checks asset loading and initialization, and never claims task success.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation
import trimesh

from .stability import array
from .variant_validation import frame
from .variants import load_instance, save


def build_scene(instance, *, cameras=False):
    """Genesis must be initialized by the caller; return scene + saved plan."""
    import genesis as gs
    from topogym.world import StandardTabletopSceneBuilder
    from topogym.utils.franka import initialize_franka_controller
    cfg, spec = load_instance(instance)
    folder = Path(cfg.run.output)
    assets = folder / "assets"
    if not cameras:
        cfg.env.cameras = {}
    builder = StandardTabletopSceneBuilder(cfg.env, cfg.robot_control,
        rigid_options=gs.options.RigidOptions(enable_collision=True, enable_self_collision=True,
            enable_joint_limit=True, max_collision_pairs=16384, iterations=100,
            constraint_timeconst=.0012, noslip_iterations=5))
    base = builder.create(show_viewer=False, include_robot=True,
                          robot_material=gs.materials.Rigid(gravity_compensation=1.))
    origin, rotation = frame(cfg)
    floor = float(cfg.env.frames.table_surface.origin[2])
    mount_r = Rotation.from_euler("z", float(cfg.task.mount_yaw_delta_deg), degrees=True)
    mount = base.manifest.add("hedgehog_mount", base.scene.add_entity(gs.morphs.Box(
        pos=(*cfg.task.center_xy_m, floor+.05), size=(.22, .22, .10),
        quat=mount_r.as_quat()[[3, 0, 1, 2]], fixed=True),
        surface=gs.surfaces.Plastic(color=(.16, .20, .24)), name="hedgehog_mount"))
    cage = base.manifest.add("hedgehog_cage", base.scene.add_entity(gs.morphs.URDF(
        file=str(assets / "cage.urdf"), pos=origin, quat=rotation.as_quat()[[3, 0, 1, 2]],
        fixed=True, convexify=True, decimate=False, merge_fixed_links=False),
        material=gs.materials.Rigid(friction=.3), name="hedgehog_cage"))
    bp = spec.layout.objects["hedgehog"]["position_m"]
    br = Rotation.from_quat(spec.layout.objects["hedgehog"]["quaternion_xyzw"])
    ball = base.manifest.add("hedgehog_ball", base.scene.add_entity(gs.morphs.URDF(
        file=str(assets / "hedgehog.urdf"), pos=bp, quat=br.as_quat()[[3, 0, 1, 2]],
        fixed=False, convexify=True, decimate=False, merge_fixed_links=False),
        material=gs.materials.Rigid(friction=.3), name="hedgehog_ball"))
    builder.finalize(base)
    loaded = []
    for name, entity, expected_p, expected_r in (("cage", cage, origin, rotation), ("hedgehog", ball, bp, br)):
        files = sorted(assets.glob(f"{name}_collision_*.obj"))
        if len(entity.geoms) != len(files):
            raise ValueError("Loaded compound collision count changed")
        user_r = Rotation.from_quat(array(entity.get_quat())[[1, 2, 3, 0]])
        position_error = float(np.linalg.norm(array(entity.get_pos()) - expected_p))
        rotation_error = float((user_r * expected_r.inv()).magnitude())
        if max(position_error, rotation_error) > 1e-7:
            raise ValueError("Scene loader ignored the sampled placement")
        solver_r = Rotation.from_quat(array(entity.get_quat(relative=False))[[1, 2, 3, 0]])
        anchor = np.eye(4)
        anchor[:3, :3] = user_r.as_matrix().T @ solver_r.as_matrix()
        anchor[:3, 3] = user_r.inv().apply(array(entity.get_pos(relative=False)) - array(entity.get_pos()))
        maximum = 0.
        for geom, file in zip(entity.geoms, files):
            source = trimesh.load(file, force="mesh")
            transform = np.eye(4)
            transform[:3, :3] = Rotation.from_quat(np.asarray(geom.init_quat)[[1, 2, 3, 0]]).as_matrix()
            transform[:3, 3] = geom.init_pos
            actual = geom.mesh.trimesh.copy().apply_transform(anchor @ transform)
            error = float(abs(actual.bounds-source.bounds).max())
            maximum = max(maximum, error)
            if not geom.is_convex or error > 1e-7:
                raise ValueError(f"Loaded collision differs: {name}, {error}")
        loaded.append(dict(name=name, cells=len(files), maximum_bounds_error_m=maximum,
                           position_error_m=position_error, rotation_error_rad=rotation_error, passed=True))
    motion = json.loads((folder / "robot_motion.json").read_text())
    controller = initialize_franka_controller(scene=base.scene, manifest=base.manifest,
                                              robot_cfg=cfg.robot_control, settle_steps=0)
    initial = np.array(motion["frames"][0]["qpos"])
    controller.robot.set_qpos(initial, zero_velocity=True)
    controller.robot.control_dofs_position(initial[:7], controller.arm_dofs)
    if np.max(abs(array(controller.robot.get_qpos()) - initial)) > 1e-7:
        raise ValueError("Robot initialization does not match the instance plan")
    return SimpleNamespace(scene=base.scene, manifest=base.manifest, cameras=base.cameras, ball=ball,
        cage=cage, mount=mount, controller=controller, origin=origin, rotation=rotation,
        loaded_audit=loaded, spec=spec, cfg=cfg, motion=motion)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise ValueError("Preserve existing report")
    import genesis as gs
    gs.init(backend=gs.cpu, precision="64", logging_level="warning", seed=0)
    task = build_scene(args.instance)
    report = dict(passed=True, episode_id=task.spec.stable_id(),
        instance_sha256=task.spec.resolved_config["instance_sha256"], loaded_collision_audit=task.loaded_audit,
        physics_steps=0, physical_execution="not_run", dataset_generated=False, h5_generated=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    save(args.report, report)
    print(json.dumps(report, indent=2))
