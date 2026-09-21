"""Exact reference assembly and fixtures in the shared ALOHA laboratory."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import genesis as gs
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.robot import initialize_robot_controller
from topogym.world import StandardTabletopSceneBuilder
from .geometry import generate_assets, reference_body_poses


def as_numpy(value):
    return value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)


@dataclass
class ClawScene:
    tabletop: Any
    assembly: Any
    bodies: dict
    asset_report: dict
    world_offset: np.ndarray
    controller: Any
    loading_report: dict

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
    from .variants import assert_runtime_supported
    assert_runtime_supported(cfg.task)
    folder = Path(asset_dir).resolve()
    assembly, report = generate_assets(folder, render_variant=cfg.task.get("render_variant"))
    if cfg.task.variant != assembly.reference["asset_id"]:
        raise ValueError("Unknown Claw asset")
    if cfg.robot_control.robot.name != "aloha" or np.any(cfg.env.robot_mount.euler):
        raise ValueError("The reference start requires ALOHA with an unrotated mount")
    builder = StandardTabletopSceneBuilder(cfg.env, cfg.robot_control,
        rigid_options=gs.options.RigidOptions(enable_collision=True, enable_self_collision=True,
            iterations=100, max_collision_pairs=int(cfg.task.get("max_collision_pairs", 8192)), constraint_timeconst=.001))
    base = builder.create(show_viewer=bool(cfg.run.viewer), include_robot=bool(cfg.run.include_robot),
                          robot_material=gs.materials.Rigid(gravity_compensation=1.0))
    fixture_offset = np.asarray(cfg.env.robot_mount.pos, dtype=float)
    riser = float(cfg.robot_control.robot.get("base_riser_height_m", 0.))
    adapter_z = riser - .02
    offset = fixture_offset + np.array([0, 0, adapter_z])
    # Restore the source robot/table relationship for the recorded trajectory.
    # Physical mounting blocks fill the declared lift below each fixed base.
    if riser:
        for b in assembly.reference["bodies"]:
            if b["name"].endswith("/base_link"):
                p = reference_body_poses(assembly.reference)[b["id"]][:3, 3].copy()
                p[2] = riser/2
                name = b["name"].split("/")[0]+"_mounting_block"
                entity = base.scene.add_entity(gs.morphs.Box(size=(.14,.14,riser), pos=fixture_offset+p, fixed=True),
                    material=gs.materials.Rigid(), surface=gs.surfaces.Default(color=(.3,.33,.35)), name=name)
                base.manifest.add(name, entity)
    bodies = {}
    for b in assembly.bodies:
        quat = Rotation.from_matrix(b.pose[:3, :3]).as_quat()[[3, 0, 1, 2]]
        body = base.scene.add_entity(gs.morphs.URDF(
            file=str(folder / b.name / f"{b.name}.urdf"), pos=offset+b.pose[:3, 3], quat=quat,
            fixed=False, align=False, convexify=False, decimate=False, merge_fixed_links=False),
            material=gs.materials.Rigid(rho=assembly.reference["density_kg_m3"], friction=.3,
                sdf_cell_size=float(cfg.task.sdf_cell_size_m), sdf_min_res=32,
                sdf_max_res=int(cfg.task.sdf_max_res)),
            surface=gs.surfaces.Default(color=b.color, smooth=True,
                **(dict(metallic=assembly.metallic, roughness=assembly.roughness)
                   if cfg.task.get("render_variant") else {})), name=b.name)
        bodies[b.name] = base.manifest.add(b.name, body)
    fixtures = []
    for g in assembly.reference["fixtures"]["geoms"]:
        pose = np.asarray(g["T_world_geom"]).copy()
        size = np.asarray(g["size_m"]).copy()
        root = fixture_offset
        if cfg.task.get("fixture_mode", "tabletop_preview") == "reference_contacts":
            # Preserve all source support contact locations relative to the
            # lowered robot. Bases remain above the table; shorten posts 20 mm.
            root = offset
            if g["role"] == "base":
                pose[2, 3] -= adapter_z
            elif g["role"] == "post":
                pose[2, 3] -= adapter_z/2
                size[2] += adapter_z/2
                if size[2] <= 0:
                    raise ValueError("Reference support is too short for the shared tabletop")
        kwargs = dict(pos=root+pose[:3, 3], fixed=True,
                      quat=Rotation.from_matrix(pose[:3, :3]).as_quat()[[3, 0, 1, 2]])
        morph = (gs.morphs.Sphere(radius=size[0], **kwargs) if g["type"] == "sphere"
                 else gs.morphs.Box(size=2*size, **kwargs))
        color = (.80, .65, .42) if g["type"] == "sphere" else (.45, .51, .46)
        entity = base.scene.add_entity(morph, material=gs.materials.Rigid(friction=.3),
            surface=gs.surfaces.Default(color=color), name=g["name"])
        base.manifest.add(g["name"], entity)
        fixtures.append(g["name"])
    builder.finalize(base)
    loading = dict(fixtures=fixtures, fixture_count=len(fixtures), collision_meshes=[],
                   fixture_mode=str(cfg.task.get("fixture_mode", "tabletop_preview")),
                   fixture_reference_to_world_translation_m=fixture_offset.tolist(),
                   reference_robot_base_lift_removed_m=-adapter_z,
                   robot_mounting_block_height_m=riser,
                   grasp_constraints_installed=False, physics_steps=0)
    for b in assembly.bodies:
        entity = bodies[b.name]
        if entity.n_dofs != 6 or entity.n_links != 1 or len(entity.geoms) != 1:
            raise RuntimeError("Each Claw must load as one independent free nonconvex link")
        geom = entity.geoms[0]
        if geom.is_convex:
            raise RuntimeError("The Claw collision mesh was incorrectly convexified")
        local = np.eye(4)
        local[:3, :3] = Rotation.from_quat(np.asarray(geom.init_quat)[[1, 2, 3, 0]]).as_matrix()
        local[:3, 3] = geom.init_pos
        loaded = geom.mesh.trimesh.copy().apply_transform(local)
        # Vertex ordering may change on import, so compare the point sets.
        from scipy.spatial import cKDTree
        error = max(cKDTree(loaded.vertices).query(b.mesh.vertices)[0].max(),
                    cKDTree(b.mesh.vertices).query(loaded.vertices)[0].max())
        if len(loaded.faces) != len(b.mesh.faces) or error > 1e-7:
            raise RuntimeError("Genesis changed the reference collision geometry")
        loading["collision_meshes"].append(dict(name=b.name, triangles=len(loaded.faces),
            max_vertex_error_m=float(error), convex=False, free_dofs=entity.n_dofs))
    controller = None
    if cfg.run.include_robot:
        controller = initialize_robot_controller(scene=base.scene, manifest=base.manifest,
                                                 robot_cfg=cfg.robot_control, settle_steps=0)
        qpos = np.asarray(assembly.reference["initial_qpos"])
        # Address joints by the shared controller's named mapping, not raw order.
        for i, arm in enumerate(controller.arms.values()):
            q = qpos[8*i:8*(i+1)]
            controller.robot.set_dofs_position(q, arm.dofs_idx, zero_velocity=True)
            controller.robot.control_dofs_position(q[:7], arm.actuated_dofs)
        expected = reference_body_poses(assembly.reference)
        errors = []
        for source, arm in zip(assembly.reference["pieces"], controller.arms.values()):
            actual = np.eye(4)
            actual[:3, 3] = arm.hand_pos()-offset
            actual[:3, :3] = Rotation.from_quat(arm.hand_quat()[[1, 2, 3, 0]]).as_matrix()
            errors.append(float(np.max(np.abs(actual-expected[source["gripper_body"]]))))
        loading["robot_gripper_fk_max_error"] = max(errors)
        if max(errors) > 2e-5:
            raise RuntimeError(f"Local ALOHA differs from reference FK by {max(errors):.8g}")
    base.scene.visualizer.update_visual_states(force_render=True)
    return ClawScene(base, assembly, bodies, report, offset, controller, loading)
