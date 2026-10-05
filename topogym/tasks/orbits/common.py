"""Orbits FEM cord, rigid fixtures and permanent material endpoints on the handle."""

from pathlib import Path
from topogym.tasks.placement import PlacementGoalMixin
import hashlib
import json
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation
from topogym.assets.geometry.orbits import OrbitsLayout, generate_assets, make_meshes
from topogym.assets.materials import rope_fem_parameters, rope_ipc_parameters
from topogym.assets.geometry.rope_volume import write_rope_volume
from ..base import TaskDefinition, EntitySpec, TaskSpec, AttachmentSpec
from ..scene_presets import defaults, record_preset
from topogym.assets.scene_visuals import surface, visual_collision_urdf
from topogym.evaluation.task_metrics import placement_candidate, rigid_asset_vertices, ipc_integrity


# Shared with development planners; these are the existing local task values,
# in metres after linear_scale. Imported oracle geometry does not replace them.
CORD_PROFILES = {
    "compact_external_handle_v1": dict(handle_x_m=.41, cord_length_m=.80),
    "below_easy_external_handle_v1": dict(handle_x_m=.32, cord_length_m=.80),
}


def profile_value(profile, key, ring_count):
    value = profile[key]
    return float(value[ring_count] if isinstance(value, dict) else value)


def profile_cord_length(profile, ring_count):
    return profile_value(profile, "cord_length_m", ring_count)


class OrbitsTask(PlacementGoalMixin, TaskDefinition):
    task_id = "orbits"
    placement_description = 'the entire cord and wooden handle'
    goal_side = (1, -1)  # -y, the nominal scene's side; pose variation cannot flip it
    placement_attachment_names = ('cord_handle_start', 'cord_handle_end')
    physics_model = "fem_ipc"
    defaults = defaults(task_id, geometry={}, stable_duration_s=0.5, cord_profile="reference",
                        cord_finish="golden_rope")
    hash_when_changed = ("cord_finish",)

    def __init__(self, config=None, seed=0):
        supplied = dict(config or {})
        if "center_xy_m" in supplied and "placement_anchor" not in supplied:
            if "base_center_xy_m" in supplied:
                raise ValueError("Specify placement_anchor when supplying both Orbits centers")
            supplied["placement_anchor"] = "assembly_center"
        super().__init__(supplied, seed)

    def declare(self, asset_dir, table_height_m):
        self.table_height_m = float(table_height_m)
        preset = record_preset(self, asset_dir)
        layout = OrbitsLayout(**self.config["geometry"]).scaled(self.config["linear_scale"])
        initial_cord = None
        if self.config["cord_profile"] == "video_solution_v2":
            from dataclasses import replace
            from topogym.assets.geometry.orbits_initial import natural_working_state, resample
            initial_cord, _ = natural_working_state(layout, handle_x_m=.60, spacing=.0075)
            # Preserve the recorded polyline while providing a conservative
            # clearance cover and adequate FEM tube sampling.
            initial_cord = resample(initial_cord, spacing=.001)
            layout = replace(layout, handle_x_m=.60)
        elif self.config["cord_profile"] in CORD_PROFILES:
            from dataclasses import replace
            from topogym.assets.geometry.orbits_initial import natural_working_state, resample
            # Read the same profile as the development planner.
            # Both legs stop at the near-side eyes;
            # the handle's centre lies beyond the entire open bight, never inside it.
            profile = CORD_PROFILES[self.config["cord_profile"]]
            handle_x_m = profile_value(profile, "handle_x_m", layout.ring_count)
            initial_cord, _ = natural_working_state(layout, handle_x_m=handle_x_m,
                cord_length_m=profile_cord_length(profile, layout.ring_count), spacing=.002)
            initial_cord = resample(initial_cord, spacing=.001)
            layout = replace(layout, handle_x_m=handle_x_m)
        elif self.config["cord_profile"] != "reference":
            raise ValueError("Unknown Orbits cord_profile")
        self.layout, report = generate_assets(
            asset_dir, layout, initial_cord=initial_cord
        )
        parts, centerline = make_meshes(self.layout, initial_cord=initial_cord)
        report.update(handle_outside_bight=bool(self.layout.handle_x_m > centerline[:, 0].max()),
            cord_length_m=float(np.linalg.norm(np.diff(centerline, axis=0), axis=1).sum()),
            full_solution_length_qualified=False, material_rest_shape='straight',
            initialization_stress_free=False)
        folder = Path(asset_dir)
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
        # Bake the same rigid rotation into every visual, collider and FEM spawn.
        # FEM factory keeps identity orientation; endpoint identities do not change.
        if yaw:
            matrix = np.eye(4); matrix[:3, :3] = rotation.as_matrix()
            for name in parts:
                for suffix in ("obj", "glb"):
                    path = folder / f"{name}.{suffix}"
                    mesh = trimesh.load(path, force="mesh", process=False)
                    mesh.apply_transform(matrix); mesh.export(path)
            scene = trimesh.load(folder / "scene.glb", force="scene", process=False)
            scene.apply_transform(matrix)
            scene.export(folder / "scene.glb")
            np.save(folder / "cord_centerline.npy", rotation.apply(centerline))
        volume = write_rope_volume(folder / "cord_volume.npz", centerline,
                                   self.layout.cord_radius_m, end_stops=False)
        if yaw:
            # Pose the existing tube; rebuilding frames after rotation can twist
            # cross-sections. Material rest coordinates and endpoint IDs stay fixed.
            with np.load(volume) as source:
                data = {key: source[key] for key in source.files}
            for key in ("spawn", "centerline"):
                data[key] = rotation.apply(data[key])
            np.savez_compressed(volume, **data)
        entities = []
        for name in parts:
            soft = name == "cord"
            fixed = name not in {"cord", "handle"}
            entities.append(
                EntitySpec(
                    name,
                    "mesh" if soft else "urdf",
                    folder / f"{name}.obj" if soft else visual_collision_urdf(folder, name),
                    tuple(self.origin),
                    fixed=fixed,
                    physics_model="fem_elastic" if soft else "rigid",
                    volume_path=volume if soft else None,
                    material=rope_fem_parameters()
                    if soft
                    else {"coup_type": "ipc_only"},
                    surface=surface(self.config["cord_finish"]) if soft else {},
                    morph_options={"convexify": False, "decimate": False,
                                   **({"file_meshes_are_zup": True, "align": False,
                                       "merge_fixed_links": False} if not soft else {})},
                )
            )
        self.placement_vertices = {e.name: rigid_asset_vertices(e) for e in entities if e.name != "cord"}
        self.placement_targets = ("cord", "handle")
        self.placement_remainder = tuple(e.name for e in entities if e.name not in self.placement_targets)
        # The generator hashes its original files before the task poses them.
        # Refresh the manifest after all runtime meshes and volumes are final.
        (folder / "sha256.json").write_text(json.dumps({
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(folder.iterdir()) if path.is_file() and path.name != "sha256.json"
        }, sort_keys=True, indent=2) + "\n")
        return TaskSpec(
            tuple(entities),
            {"fem": {}, "ipc": rope_ipc_parameters()},
            dict(
                **preset, placement_anchor=anchor, placement_xy_m=xy.tolist(),
                assembly_center_xy_m=(center[:2]+self.origin[:2]).tolist(),
                base_center_xy_m=(base_center[:2]+self.origin[:2]).tolist(),
                base_long_axis_world=rotation.apply([1., 0., 0.]).tolist(),
                assembly_bounds_world_m=(np.array([points.min(0), points.max(0)])+self.origin).tolist(),
                yaw_deg=yaw,
                linear_scale=self.config["linear_scale"], origin_m=self.origin.tolist(),
                task_id=self.task_id,
                fem_rope_profile="v13_material_mesh",
                orbits_scene_contract=dict(
                    ring_count=self.layout.ring_count,
                    post_count=self.layout.ring_count + 1,
                    ring_ids=[f"ring_{i+1}" for i in range(self.layout.ring_count)],
                    ring_centers_world_m=(rotation.apply(np.column_stack([
                        self.layout.ring_x, np.zeros(self.layout.ring_count),
                        self.layout.ring_z])) + self.origin).tolist() if self.layout.ring_count else [],
                    trapped_post_id=f"post_{self.layout.ring_count+1}",
                    initial_winding_absolute=[0]*self.layout.ring_count + [1],
                    cord_profile=self.config["cord_profile"],
                    cord_length_m=report["cord_length_m"],
                    handle_x_local_m=self.layout.handle_x_m,
                    difficulty_qualified=False, solution_verified=False,
                    stability_qualified=False,
                ),
                geometry_report=report, geometry_report_frame="unrotated_template",
                permanent_connections=["cord endpoints to handle eyes"],
                goal_evaluation_complete=bool(self.goal_complete),
            ),
            attachments=tuple(AttachmentSpec(f"cord_handle_{end}", "cord", "handle", end, self.layout.cord_radius_m) for end in ("start", "end")),
        )

    def evaluate_state(self, state):
        return self.evaluate_placement(state)

    def evaluate_goal_region(self, state, region):
        """All cord vertices and the whole handle; no arbitrary loop closure."""
        return placement_candidate(state, region, self.placement_vertices,
            self.placement_targets, self.placement_remainder, soft_names=("cord",),
            attachment_names=("cord_handle_start", "cord_handle_end"))

    def goal_region_observation(self, region):
        return region.observation(self.placement_targets, self.placement_remainder)
