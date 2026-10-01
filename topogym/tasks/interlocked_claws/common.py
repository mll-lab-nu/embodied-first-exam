"""Exact Claw mesh entities with a tabletop initial assembly and separation goal."""
from pathlib import Path
from dataclasses import replace
from topogym.tasks.placement import PlacementGoalMixin

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.assets.geometry.interlocked_claws import generate_assets
from topogym.tasks.base import EntitySpec, RigidTaskDefinition, TaskSpec


class InterlockedClawsTask(PlacementGoalMixin, RigidTaskDefinition):
    terminal_revision = "placement_region_v3_grasp_contact_2mm"
    task_id = "interlocked_claws"
    placement_description = 'the entire brown claw piece'
    goal_side = (1, 1)  # +y, the nominal scene's side; pose variation cannot flip it
    defaults = dict(center_xy_m=[-.1356786, .05], initial_floor_clearance_m=.001,
                    stable_duration_s=.5, minimum_separation_m=.01,
                    sdf_cell_size_m=.001, sdf_max_res=128,
                    initial_finger_position_m=None, target_shade=1., other_rgb=None)
    # Appearance only: brightness of the brown target piece; colour of the other piece (None keeps it).
    hash_when_changed = ("target_shade", "other_rgb")

    geometry_family = None
    gate_extra_m = (0., 0.)
    claw_scale = 1.
    # Pure-friction pregrasp holds slip (release probe 2026-09-29). All three
    # shipped tiers request contact_weld_v1 through recommended_grasp_assist();
    # the owner's SimulatorConfig still decides whether assistance is enabled.
    pregrasp_weld = False

    def build_assets(self, folder):
        if self.geometry_family == 'acute_windows_opposed':
            from topogym.assets.geometry.claws_opposed import build_opposed_windows
            assembly, report, self.initial_robot_q = build_opposed_windows(folder, self.gate_extra_m)
            return assembly, report
        if not self.geometry_family:
            assembly, report = generate_assets(folder, scale=self.claw_scale)
            from topogym.assets.geometry.claws_grip import add_grip_blocks
            from topogym.assets.geometry.interlocked_claws import geometry_report
            add_grip_blocks(assembly, folder)
            report = geometry_report(assembly)
            report.update(grip_blocks_m=[.030,.028,.024], claw_scale=assembly.scale,
                initial_robot_qpos=assembly.initial_qpos.tolist(),
                triangle_positions_preserved=False, original_collision_triangles_preserved=True,
                collision_representation='original nonconvex triangles plus native flat grip boxes',
                historical_certificate_transferred=False)
            import json
            import trimesh
            (folder/'geometry_report.json').write_text(json.dumps(report,indent=2)+'\n')
            scene = trimesh.Scene()
            for body in assembly.bodies:
                scene.add_geometry(body.mesh,node_name=body.name,transform=body.pose)
            scene.export(folder/'assembly.glb')
            self.initial_robot_q = assembly.initial_qpos.copy()
            self.initial_robot_q[[6,7,14,15]] = .0222
            return assembly, report
        from types import SimpleNamespace
        from topogym.assets.geometry.interlocked_claws import FamilyModel, DENSITY, COLORS
        model = FamilyModel(self.geometry_family)
        # FamilyModel writes compound URDFs preserving each box's orientation.
        root = folder / "family"
        report = model.save(root)
        bodies = [SimpleNamespace(name=part.name, mesh=part.mesh,
                                  pose=pose, color=color,
                                  asset_path=root/f"{part.name}.urdf")
                  for part, pose, color in zip(model.parts, model.initial, COLORS)]
        if self.geometry_family == 'helical_claws_balanced_v2':
            # Rotate the assembled pair together: preserve its actual interlock.
            # Square handles admit an upright opposed grasp on both sides.
            transform = np.eye(4)
            transform[:3, :3] = Rotation.from_euler('y', 90, degrees=True).as_matrix()
            transform[:3, 3] = [0., -.019, .30528805]
            for body in bodies:
                body.pose = transform@body.pose
            self.initial_robot_q = self.opposed_q(.13, .30528805, .0172)
        return SimpleNamespace(bodies=bodies, reference={"density_kg_m3": DENSITY}), report

    @staticmethod
    def opposed_q(half_gap, height, finger):
        from scipy.optimize import least_squares
        from topogym.assets.geometry.interlocked_claws import load_reference, reference_body_poses
        reference = load_reference()
        def residual(angles):
            arm = [0., angles[0], angles[1], 0., -sum(angles), 0., finger, finger]
            frame = reference_body_poses(reference, np.tile(arm, 2))[7]
            tcp = (frame@np.array([.13, 0., -.003, 1.]))[:3]
            return tcp[[0, 2]]-[-half_gap, height]
        result = least_squares(residual, [-.96, 1.16], bounds=([-1.85005, -1.76278], [1.25664, 1.6057]),
                               xtol=1e-12, ftol=1e-12, gtol=1e-12)
        if np.linalg.norm(result.fun) > 1e-6:
            raise ValueError('Opposed claw grasp is unreachable')
        a, b = result.x
        return np.tile([0., a, b, 0., -a-b, 0., finger, finger], 2)

    def finalize_spec(self, spec, *, asset_dir, scene_config):
        # Task-owned segment0 configuration; no robot mesh or common home edit.
        if scene_config.robot_control.robot.name != 'aloha':
            raise ValueError('Claw pregrasp initialization requires original ALOHA')
        q = np.asarray(self.initial_robot_q).reshape(2, 8).copy()
        finger = self.config["initial_finger_position_m"]
        if finger is not None:
            gripper = scene_config.robot_control.gripper
            if (isinstance(finger, (bool, np.bool_)) or not np.isfinite(finger)
                    or not float(gripper.closed_qpos) <= finger <= float(gripper.open_qpos)):
                raise ValueError("initial_finger_position_m must lie inside the original ALOHA joint limits")
            q[:, 6:] = finger
        scene_config.robot_control.home.left = q[0].tolist()
        scene_config.robot_control.home.right = q[1].tolist()
        mount = scene_config.env.robot_mount
        rotation = Rotation.from_euler('xyz', mount.euler, degrees=True)
        offset = np.asarray(mount.pos, dtype=float) + rotation.apply([0., 0.,
            float(scene_config.robot_control.robot.get('base_riser_height_m', 0.))-.02])
        entities = tuple(replace(e, position_m=tuple(offset+rotation.apply(e.position_m)),
            quaternion_wxyz=tuple((rotation*Rotation.from_quat(np.asarray(e.quaternion_wxyz)[[1,2,3,0]])).as_quat()[[3,0,1,2]]))
            for e in spec.entities)
        targets = {side: {'gripper_position_m': float(scene_config.robot_control.gripper.closed_qpos)}
                   for i,side in enumerate(('left','right'))}
        spec = replace(spec, entities=entities, initial_robot_targets=targets, metadata={**spec.metadata,
            'initial_robot_qpos': q.tolist(), 'robot_geometry_modified': False,
            'initial_robot_targets': targets,
            'initial_grasp_model': 'physical_finger_contact_no_weld',
            'initial_state': 'segment0 pregrasp; original ALOHA; independent interlocked pieces'})
        return super().finalize_spec(spec, asset_dir=asset_dir, scene_config=scene_config)

    def declare(self, asset_dir, table_height_m):
        self.table_height_m = float(table_height_m)
        cfg, folder = self.config, Path(asset_dir)
        assembly, report = self.build_assets(folder)
        transformed = [b.mesh.vertices@b.pose[:3, :3].T+b.pose[:3, 3] for b in assembly.bodies]
        points = np.concatenate(transformed)
        center = np.asarray(cfg["center_xy_m"], dtype=float)
        if center.shape != (2,) or not np.isfinite(center).all() or cfg["initial_floor_clearance_m"] < 0:
            raise ValueError("Invalid Claw tabletop layout")
        offset = np.zeros(3)  # Assembly is declared in source robot-mount coordinates.
        self.local_vertices = {b.name: b.mesh.vertices for b in assembly.bodies}
        colors = self.paint_pieces(assembly, folder)
        entities = tuple(EntitySpec(body.name, "urdf", getattr(body, "asset_path", folder/body.name/f"{body.name}.urdf"),
            tuple(offset+body.pose[:3, 3]),
            tuple(Rotation.from_matrix(body.pose[:3, :3]).as_quat()[[3, 0, 1, 2]]),
            material={"rho": assembly.reference["density_kg_m3"], "friction": .3,
                      "sdf_cell_size": float(cfg["sdf_cell_size_m"]), "sdf_min_res": 32,
                      "sdf_max_res": int(cfg["sdf_max_res"])},
            morph_options={"align": False, "convexify": False, "decimate": False,
                           "merge_fixed_links": False}, surface={"color": color})
            for body, color in zip(assembly.bodies, colors))
        # Placement rule caches the union of collision and visible geometry.
        from topogym.evaluation.task_metrics import rigid_asset_vertices
        self.placement_vertices = {e.name: rigid_asset_vertices(e) for e in entities}
        self.placement_targets = (assembly.bodies[0].name,)
        self.placement_remainder = tuple(e.name for e in entities if e.name not in self.placement_targets)
        self.weld_targets = self.pregrasp_targets(assembly, entities, transformed) if self.pregrasp_weld else ()
        return TaskSpec(entities, {"rigid": {"enable_self_collision": True, "iterations": 100,
            "max_collision_pairs": 8192, "constraint_timeconst": .001}},
            dict(task_id=self.task_id, instance_id=self.instance_id, asset_report=report,
                 initial_state="tabletop-translated reference relative assembly; robot remains at home",
                 holding_allowed=True, recommended_grasp_assist=dict(
                     model="contact_weld_v1", initial_intent="close", targets=list(self.weld_targets))
                 if self.pregrasp_weld else None))

    def pregrasp_targets(self, assembly, entities, transformed):
        """Each hand's grasp centre in the frame of the piece whose surface is nearest its TCP."""
        import xml.etree.ElementTree as ET
        from topogym.assets.geometry.interlocked_claws import load_reference, tcp_frames
        paths = {e.name: e.asset_path for e in entities}
        targets = []
        for tcp in tcp_frames(load_reference(), self.initial_robot_q):
            i = min(range(len(assembly.bodies)), key=lambda k: np.linalg.norm(transformed[k]-tcp[:3, 3], axis=1).min())
            body = assembly.bodies[i]
            center = (np.linalg.inv(body.pose)@np.r_[tcp[:3, 3], 1.])[:3]
            link = ET.parse(paths[body.name]).getroot().find("link").get("name")
            targets.append(dict(entity=body.name, link=link, center_m=center.tolist(), radius_m=.03))
        if len({t["entity"] for t in targets}) != 2:
            raise ValueError("Each hand must hold a different claw piece")
        return tuple(targets)

    def evaluate_goal_region(self, state, region):
        """Measure the fixed placement rule; physical qualification is separate."""
        from topogym.evaluation.task_metrics import placement_candidate
        result = placement_candidate(state, region, self.placement_vertices,
            self.placement_targets, self.placement_remainder)
        return result

    def goal_region_observation(self, region):
        return region.observation(self.placement_targets, self.placement_remainder)

    def evaluate_state(self, state):
        return self.evaluate_placement(state)

    def paint_pieces(self, assembly, folder):
        """Per-piece RGBA; non-default appearance also rewrites the piece's URDF and GLB colours."""
        import xml.etree.ElementTree as ET
        from topogym.assets.scene_visuals import scale_glb_color
        shade, other = float(self.config["target_shade"]), self.config["other_rgb"]
        colors = []
        for index, body in enumerate(assembly.bodies):
            if index == 0 and shade != 1.:
                paint = lambda rgba: [*(min(1., float(c)*shade) for c in rgba[:3]), float(rgba[3])]
            elif index > 0 and other is not None:
                paint = lambda rgba: [*(float(c) for c in other), float(rgba[3])]
            else:
                colors.append(body.color)
                continue
            urdf = Path(getattr(body, "asset_path", folder/body.name/f"{body.name}.urdf"))
            tree = ET.parse(urdf)
            for node in tree.findall(".//visual/material/color"):
                node.set("rgba", " ".join(map(str, paint([float(v) for v in node.get("rgba").split()]))))
            for mesh in tree.findall(".//visual/geometry/mesh"):
                if mesh.get("filename").endswith(".glb"):
                    scale_glb_color(urdf.parent/mesh.get("filename"), shade if index == 0 else 1.,
                                    color=None if index == 0 else [*paint([0, 0, 0, 1])])
            tree.write(urdf, encoding="unicode", xml_declaration=True)
            colors.append(tuple(paint(body.color)))
        return colors


def recommended_grasp_assist(variation_id, seed=0, *, task_parameters=None):
    """Recommended contact_weld_v1 config, or None for a non-assisted definition.

    All three shipped tiers opt in. initial_intent="close" lets the already-closed
    hands acquire after bilateral-contact qualification, without another close command.
    """
    import tempfile
    from topogym.config.registry import task_definition
    from topogym.utils.grasp import GraspAssistConfig, GraspTarget
    task = task_definition("interlocked_claws", variation_id, seed)(task_parameters, seed=seed)
    if not task.pregrasp_weld:
        return None
    with tempfile.TemporaryDirectory() as folder:
        task.declare(Path(folder), 0.)
    return GraspAssistConfig("contact_weld_v1", tuple(GraspTarget(t["entity"], t["link"], tuple(t["center_m"]), t["radius_m"])
                                                      for t in task.weld_targets), initial_intent="close")
