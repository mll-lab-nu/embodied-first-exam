"""Approved single-post and single-ring Orbits variants with a rigid link chain cord.

The cord is a chain of capsule links on ball joints, tied at both ends to the wooden handle (one MJCF entity, the loop
closed by a <connect> equality); the FEM+IPC cord was replaced (team decision, 2026-10-07): a pinch on the thin soft
cord could not hold it, and the IPC cost 3-5 s per control step. The fixture and the whole-target placement goal are
unchanged. Difficulty names describe design intent, not solver qualification.
"""
from dataclasses import replace
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.assets.geometry.orbits import OrbitsLayout, generate_assets, make_meshes
from topogym.assets.geometry.orbits_chain import chain_polyline, resample_links, write_cord_assembly
from topogym.assets.geometry.orbits_initial import natural_working_state, resample
from topogym.assets.scene_visuals import visual_collision_urdf
from topogym.evaluation.task_metrics import body_points, quiet_body, rigid_asset_vertices
from topogym.tasks.base import merge_parameters, EntitySpec, TaskSpec
from topogym.tasks.scene_presets import record_preset
from topogym.utils.geometry.regions import placement_measurements
from .common import CORD_PROFILES, OrbitsTask, profile_cord_length, profile_value


class OrbitsBelowEasyTask(OrbitsTask):
    variant_parameters = {
        'linear_scale': .85,
        'cord_profile': 'below_easy_stiff_loop_v1',
        'geometry': {
            'ring_count': 1,
            'ring_radius_m': .090,
            'post_spacing_m': .112,
            'lowest_ring_z_m': .100,
            'base_length_m': .360,
            'base_width_m': .230,
            # 2 mm after the 0.85 scale (was 20.4 mm): the very_easy oracle's lift dragged the handle along the
            # table into the base edge, which caught it and tore the cord from a gripper (2026-10-07).
            'base_height_m': .002/.85,
            # 35 mm after the 0.85 scale (was 23.8 mm): a stiff loop keeps this authored opening, and 23.8 mm left it
            # 0.4 mm around the ball (MuJoCo lift sweep, 2026-10-07).
            'bight_radius_m': .035/.85,
            'handle_bend_radius_m': .020,
        },
    }
    defaults = merge_parameters(OrbitsTask.defaults, variant_parameters)
    fixed_parameters = ('linear_scale', 'cord_profile', 'geometry')
    model_revision = 'below_easy_v10_stiff_chain_armature1e5_v1'
    physics_model = "rigid_articulated"
    placement_attachment_names = ()
    # The teammates' Orbits chain standard (2026-10-07), at this 0.85 layout: 16.5 mm capsule links (their 23.1 mm at
    # linear_scale 1.19) of the authored cord's 3.74 mm diameter, ball-joint damping 2e-4, one 2.5 ms
    # substep with the CG constraint solver. Before: 6 mm cord of 20 mm links, damping 1e-4, four substeps.
    CHAIN_RADIUS_M = .00187
    LINK_LENGTH_M = .0165
    JOINT_DAMPING = 2e-4
    # Armature 1e-5 for these two tiers (the teammates' 1e-6; user, 2026-10-08): Genesis' grasp weld and the middle
    # tie are soft constraints (time constant two substeps) scaled by the links' effective inertia, and the 0.18 g
    # links let about 1 N of cord tension pull the weld past its 10 mm limit and the tie past 2 mm while easier's
    # bight rose through the ring hole; at 1e-5 the weld stayed within 5 mm and the tie within 0.7 mm up to 0.19 m.
    JOINT_ARMATURE = 1e-5
    # Bending stiffness as a Young's modulus, k = E pi r^4 / (4 L) per ball joint, pulling each joint back to the
    # authored loop (a charging-cable cord; user, 2026-10-07). Two hands lifting a limp loop let it hang into their
    # vertical plane, one strand pressed on the post, which the ball then caught (very_easy run 17 tore the handle tie).
    # 100 MPa for these two tiers only (user, 2026-10-07; the teammates' cord is 50 kPa). MuJoCo two-point lift of this
    # chain (welds at the very_easy oracle's grips to 0.25 m, then 0.10 m toward the handle): 0.05, 3 and 10 MPa jammed
    # on the ball and tore the middle tie 24 mm; 30 MPa came off 1.0 mm from it; 50 / 100 / 170 MPa 7.6 / 8.8 / 8.2 mm,
    # the tie within 0.1 mm. easier's standard solution (MuJoCo reference run): carrying the loop off around the ring
    # tore the tie 19.2 / 19.6 / 11.6 / 11.2 mm at 0.05 / 3 / 10 / 30 MPa and kept it within 0.51 mm at 100 MPa.
    YOUNG_MODULUS_PA = 1e8
    # Placement speeds (user, 2026-10-06): every cord link and the handle at most 10 mm/s, the handle's rotation
    # at most 0.02 rad/s; the two chain halves joined at the middle within 2 mm.
    LINEAR_LIMIT_M_S = .01
    ANGULAR_LIMIT_RAD_S = .02
    TIE_LIMIT_M = .002

    def declare(self, asset_dir, table_height_m):
        self.table_height_m = float(table_height_m)
        preset = record_preset(self, asset_dir)
        layout, cord, roots = self.chain_roots()
        self.layout, report = generate_assets(asset_dir, layout, initial_cord=cord)
        folder = Path(asset_dir)
        xml, self.link_names, self.link_lengths, self.tie_link = write_cord_assembly(
            folder, self.layout, roots, radius_m=self.CHAIN_RADIUS_M, joint_damping=self.JOINT_DAMPING,
            young_modulus_pa=self.YOUNG_MODULUS_PA, armature=self.JOINT_ARMATURE)
        self.link_roots = roots
        parts, _ = make_meshes(self.layout, initial_cord=cord)
        yaw = float(self.config["yaw_deg"])
        if not np.isfinite(yaw):
            raise ValueError("Invalid Orbits yaw_deg")
        rotation = Rotation.from_euler("z", yaw, degrees=True)
        points = np.vstack([rotation.apply(mesh.vertices) for mesh in parts.values()])
        center = (points.min(0)+points.max(0))/2
        base_points = rotation.apply(parts["base"].vertices)
        base_center = (base_points.min(0)+base_points.max(0))/2
        anchor = self.config["placement_anchor"]
        if anchor == "base_center":
            coordinate_key, local_anchor = "base_center_xy_m", base_center
        elif anchor == "assembly_center":
            coordinate_key, local_anchor = "center_xy_m", center
        else:
            raise ValueError("Orbits placement_anchor must be base_center or assembly_center")
        xy = np.asarray(self.config[coordinate_key], dtype=float)
        if xy.shape != (2,) or not np.isfinite(xy).all():
            raise ValueError(f"Invalid Orbits {coordinate_key}")
        self.origin = np.r_[xy-local_anchor[:2], table_height_m]
        turn = tuple(rotation.as_quat()[[3, 0, 1, 2]])
        fixture = [name for name in parts if name not in {"cord", "handle"}]
        # Fixture friction 0.3 like the chain (teammate standard): Genesis takes the larger of two contact frictions,
        # and the URDF default of 1.0 made the easier legs drag over the ring rim hard enough to stretch the middle tie
        # to 2 mm while the bight rose (local easier run 3, 2026-10-08); the MuJoCo reference at 0.3 stretched it 0.7 mm.
        entities = [EntitySpec(name, "urdf", visual_collision_urdf(folder, name), tuple(self.origin), turn, fixed=True,
                               material={"friction": .3},
                               morph_options={"convexify": False, "decimate": False, "file_meshes_are_zup": True,
                                              "align": False, "merge_fixed_links": False})
                    for name in fixture]
        self.placement_vertices = {e.name: rigid_asset_vertices(e) for e in entities}
        entities.append(EntitySpec("cord", "mjcf", xml, tuple(self.origin), turn))
        self.handle_vertices = np.asarray(parts["handle"].vertices)
        self.placement_vertices["cord"] = np.vstack([self.handle_vertices, roots])
        self.placement_targets = ("cord",)
        self.placement_remainder = tuple(fixture)
        return TaskSpec(
            tuple(entities),
            {"rigid": {"enable_self_collision": True, "constraint_solver": "CG"}},
            dict(
                **preset, placement_anchor=anchor, placement_xy_m=xy.tolist(),
                assembly_center_xy_m=(center[:2]+self.origin[:2]).tolist(),
                base_center_xy_m=(base_center[:2]+self.origin[:2]).tolist(),
                base_long_axis_world=rotation.apply([1., 0., 0.]).tolist(),
                assembly_bounds_world_m=(np.array([points.min(0), points.max(0)])+self.origin).tolist(),
                yaw_deg=yaw, linear_scale=self.config["linear_scale"], origin_m=self.origin.tolist(),
                task_id=self.task_id,
                cord_chain=dict(links=len(self.link_names), radius_m=self.CHAIN_RADIUS_M,
                                link_lengths_m=[float(v) for v in self.link_lengths],
                                length_m=float(self.link_lengths.sum())),
                orbits_scene_contract=dict(
                    ring_count=self.layout.ring_count, post_count=self.layout.ring_count+1,
                    ring_ids=[f"ring_{i+1}" for i in range(self.layout.ring_count)],
                    ring_centers_world_m=(rotation.apply(np.column_stack([
                        self.layout.ring_x, np.zeros(self.layout.ring_count),
                        self.layout.ring_z]))+self.origin).tolist() if self.layout.ring_count else [],
                    trapped_post_id=f"post_{self.layout.ring_count+1}",
                    initial_winding_absolute=[0]*self.layout.ring_count+[1],
                    cord_profile=self.config["cord_profile"], cord_length_m=float(self.link_lengths.sum()),
                    handle_x_local_m=self.layout.handle_x_m,
                    difficulty_qualified=False, solution_verified=False, stability_qualified=False,
                ),
                geometry_report=report, geometry_report_frame="unrotated_template",
                permanent_connections=["each chain end to its handle eye (ball joint)",
                                       "the two chain halves at the middle (connect equality)"],
                goal_evaluation_complete=bool(self.goal_complete),
            ),
        )

    def chain_roots(self):
        """The authored layout and loop, and the chain's link roots (task-local), without writing assets."""
        layout = OrbitsLayout(**self.config["geometry"]).scaled(self.config["linear_scale"])
        profile = CORD_PROFILES[self.config["cord_profile"]]
        handle_x_m = profile_value(profile, "handle_x_m", layout.ring_count)
        cord, _ = natural_working_state(layout, handle_x_m=handle_x_m,
            cord_length_m=profile_cord_length(profile, layout.ring_count), spacing=.002)
        cord = resample(cord, spacing=.001)
        layout = replace(layout, handle_x_m=handle_x_m).validate()
        return layout, cord, resample_links(chain_polyline(layout, cord, self.CHAIN_RADIUS_M), self.LINK_LENGTH_M)

    def link_cover(self, length):
        """Capsule axis ends and their radial extremes, in the link frame."""
        r = self.CHAIN_RADIUS_M
        return np.array([[x, *offset] for x in (0., length) for offset in
                         ((0., 0.), (r, 0.), (-r, 0.), (0., r), (0., -r))])

    def cord_points(self, state):
        """Handle vertices and every link's cover in the world, plus the middle tie residual."""
        links = state["articulations"]["cord"]["links"]
        handle = links["handle"]
        clouds = [body_points(handle, self.handle_vertices)]
        clouds += [body_points(links[name], self.link_cover(length))
                   for name, length in zip(self.link_names, self.link_lengths)]
        m = self.tie_link
        tip = body_points(links[self.link_names[m-1]], [[self.link_lengths[m-1], 0., 0.]])[0]
        tie = float(np.linalg.norm(tip-body_points(links[self.link_names[m]], [[0., 0., 0.]])[0]))
        return np.vstack(clouds), tie

    def evaluate_goal_region(self, state, region):
        """The whole chain and handle inside the goal, the fixture on the system side, slow and tied."""
        links = state["articulations"]["cord"]["links"]
        points, tie = self.cord_points(state)
        remainder = {name: body_points(state["bodies"][name], self.placement_vertices[name])
                     for name in self.placement_remainder}
        metrics = placement_measurements(region, {"cord": points}, remainder)
        speeds = [float(np.linalg.norm(links[name]["linear_velocity_m_s"])) for name in self.link_names]
        quiet = (max(speeds) <= self.LINEAR_LIMIT_M_S
                 and quiet_body(links["handle"], self.LINEAR_LIMIT_M_S, self.ANGULAR_LIMIT_RAD_S))
        intact = tie <= self.TIE_LIMIT_M
        metrics.update(quiet=bool(quiet), maximum_link_speed_m_s=max(speeds), connections_intact=intact,
                       tie_residual_m=tie, evaluation_status="available", holding_allowed=True)
        reached = metrics["all_target_inside"] and metrics["remainder_on_system_side"] and quiet and intact
        return bool(reached), None if intact else "connection_invalid", metrics
