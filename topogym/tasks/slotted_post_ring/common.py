"""Slotted post, mobile ring/beads/discs and FEM cord with attached end stops."""

from pathlib import Path
from topogym.tasks.placement import PlacementGoalMixin
import numpy as np
from topogym.assets.geometry.slotted_post_ring import (
    SlottedPostLayout,
    generate_assets,
    make_meshes,
    centerline,
)
from topogym.assets.materials import rope_fem_parameters, rope_ipc_parameters
from topogym.assets.geometry.rope_volume import write_rope_volume
from ..base import TaskDefinition, EntitySpec, TaskSpec, AttachmentSpec
from ..scene_presets import defaults, record_preset
from topogym.assets.scene_visuals import surface, visual_collision_urdf
from topogym.evaluation.task_metrics import placement_candidate, rigid_asset_vertices, ipc_integrity


class SlottedPostRingTask(PlacementGoalMixin, TaskDefinition):
    task_id = "slotted_post_ring"
    placement_description = 'the entire removable metal ring'
    goal_side = (1, 1)  # +y, the nominal scene's side; pose variation cannot flip it
    placement_attachment_names = ('cord_disc_left', 'cord_disc_right')
    physics_model = "fem_ipc"
    defaults = defaults(task_id, geometry={}, stable_duration_s=0.5, cord_finish="hemp")
    hash_when_changed = ("cord_finish",)

    def declare(self, asset_dir, table_height_m):
        self.table_height_m = float(table_height_m)
        preset = record_preset(self, asset_dir)
        xy = np.asarray(self.config["center_xy_m"], dtype=float)
        if xy.shape != (2,) or not np.isfinite(xy).all():
            raise ValueError("Invalid Slotted Post Ring center_xy_m")
        origin = tuple(np.r_[xy, table_height_m])
        self.layout, report = generate_assets(
            asset_dir, SlottedPostLayout(**self.config["geometry"])
        )
        parts, _ = make_meshes(self.layout)
        folder = Path(asset_dir)
        volume = write_rope_volume(folder / "cord_volume.npz", centerline(self.layout),
                                   self.layout.rope_radius_m, end_stops=True)
        entities = []
        for name in parts:
            if name.startswith("stop_knot"):
                continue  # Must become part of the same FEM cord, not free rigid decorations.
            soft = name == "cord"
            entities.append(
                EntitySpec(
                    name,
                    "mesh" if soft else "urdf",
                    folder / f"{name}.obj" if soft else visual_collision_urdf(folder, name),
                    origin,
                    fixed=name in {"base", "post"},
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
        self.placement_targets = ("target_ring",)
        self.placement_remainder = tuple(e.name for e in entities if e.name != "target_ring")
        return TaskSpec(
            tuple(entities),
            {"fem": {}, "ipc": rope_ipc_parameters()},
            dict(
                **preset,
                assembly_origin_m=list(origin),
                task_id=self.task_id,
                fem_rope_profile="v13_material_mesh",
                geometry_report=report,
                permanent_connections=[
                    "cord endpoint to disc",
                    "FEM end stops",
                    "mobile bead/cord contact",
                ],
                goal_evaluation_complete=bool(self.goal_complete),
            ),
            attachments=tuple(AttachmentSpec(f"cord_disc_{side}", "cord", f"disc_{side}", end, self.layout.rope_radius_m) for side, end in (("left", "start"), ("right", "end"))),
        )

    def evaluate_state(self, state):
        return self.evaluate_placement(state)

    def evaluate_goal_region(self, state, region):
        """Measure whole-ring placement and permanent-connection integrity."""
        return placement_candidate(state, region, self.placement_vertices,
            self.placement_targets, self.placement_remainder, soft_names=("cord",),
            attachment_names=("cord_disc_left", "cord_disc_right"))

    def goal_region_observation(self, region):
        return region.observation(self.placement_targets, self.placement_remainder)
