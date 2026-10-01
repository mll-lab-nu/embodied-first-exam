"""Hedgehog cage/ball declarations; control capabilities belong to the registry."""
from pathlib import Path
from topogym.tasks.placement import PlacementGoalMixin

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.assets.geometry.hedgehog_in_cage import generate_assets, cage_meshes, hedgehog_meshes
from topogym.tasks.base import EntitySpec, RigidTaskDefinition, TaskSpec
from ..scene_presets import defaults, record_preset
from topogym.assets.scene_visuals import surface


class HedgehogInCageTask(PlacementGoalMixin, RigidTaskDefinition):
    task_id = "hedgehog_in_cage"
    placement_description = 'the hedgehog ball including every spike'
    goal_side = (1, -1)  # -y, the nominal scene's side; pose variation cannot flip it
    defaults = defaults(task_id, scale=3., center_xy_m=[-.1356786, .05], yaw_deg=0.,
                    mount_height_m=.04, mount_width_m=.25, stable_duration_s=2.,
                    minimum_separation_m=.01, wood_tint=1.)
    hash_when_changed = ("wood_tint",)

    asset_resource = None

    terminal_revision = "hedgehog_placement_v3_default_success"

    def terminal_metadata(self):
        from .qualification import placement_qualification
        metadata = super().terminal_metadata()
        qualification = placement_qualification(self)
        if qualification is not None:
            # A historical match describes evidence scope, not current-run
            # calibration/reachability or permission to report success.
            metadata.update(qualification=dict(qualification))
        return metadata

    def build_assets(self, folder):
        if not self.asset_resource:
            layout, report = generate_assets(folder, float(self.config["scale"]), finish=self.config["finish"])
            cage, _ = cage_meshes(layout)
            ball, _ = hedgehog_meshes(layout)
            return cage, ball, -layout.template["cage"]["height"]*layout.unit/2, report
        import json
        import trimesh
        from topogym.assets.variation_resources import read_json, unpack_assets
        unpack_assets(self.asset_resource, folder)
        prototype = read_json(self.prototype_resource)
        report = json.loads((folder/"asset_report.json").read_text())
        report.update(initial_pose=self.initial_ball_pose,
                      source_resource=self.asset_resource, spike_count=prototype["spike_count"],
                      historical_certificate_transferred=False)
        cage = trimesh.load(folder/"cage.obj", force="mesh", process=False)
        ball = trimesh.load(folder/"hedgehog.obj", force="mesh", process=False)
        return cage, ball, prototype["cage_bottom_m"], report

    def declare(self, asset_dir, table_height_m):
        self.table_height_m = float(table_height_m)
        cfg, folder = self.config, Path(asset_dir)
        preset = record_preset(self, folder)
        cage, ball, cage_bottom, report = self.build_assets(folder)
        if cfg["wood_tint"] != 1.:
            # Appearance only: darken the baked wood textures of cage and ball.
            from topogym.assets.scene_visuals import scale_glb_color
            for path in sorted(folder.glob("*.glb")):
                scale_glb_color(path, cfg["wood_tint"], materials=("wood",))
        xy = np.asarray(cfg["center_xy_m"], dtype=float)
        if xy.shape != (2,) or not np.isfinite(xy).all():
            raise ValueError("Invalid Hedgehog center_xy_m")
        pad = float(cfg["mount_height_m"])
        if pad <= 0 or not np.isfinite(pad) or cfg["mount_width_m"] <= 0:
            raise ValueError("Invalid cage mount dimensions")
        origin = np.r_[xy, self.table_height_m+pad-cage_bottom]
        rotation = Rotation.from_euler("z", float(cfg["yaw_deg"]), degrees=True)
        initial = report["initial_pose"]
        ball_rotation = rotation*Rotation.from_quat(np.asarray(initial["quaternion_wxyz"])[[1, 2, 3, 0]])
        position = origin+rotation.apply(initial["position_m"])
        self.local_vertices = {"hedgehog_cage": cage.vertices, "hedgehog_ball": ball.vertices}
        options = {"convexify": True, "decimate": False, "merge_fixed_links": False}
        entities = (
            EntitySpec("hedgehog_mount", "box", None,
                (*xy, self.table_height_m+pad/2), fixed=True,
                surface=surface("coated_metal"),
                morph_options={"size": (cfg["mount_width_m"], cfg["mount_width_m"], pad)}),
            EntitySpec("hedgehog_cage", "urdf", folder/"cage.urdf", tuple(origin),
                tuple(rotation.as_quat()[[3, 0, 1, 2]]), fixed=True,
                material={"friction": .3}, morph_options={**options,
                    "convexify": getattr(self, "cage_convexify", True)}),
            EntitySpec("hedgehog_ball", "urdf", folder/"hedgehog.urdf", tuple(position),
                tuple(ball_rotation.as_quat()[[3, 0, 1, 2]]), material={"friction": .3}, morph_options=options))
        # Placement rule caches the union of collision and visible geometry.
        from topogym.evaluation.task_metrics import rigid_asset_vertices
        self.placement_vertices = {e.name: rigid_asset_vertices(e) for e in entities}
        self.placement_targets = ('hedgehog_ball',)
        self.placement_remainder = tuple(e.name for e in entities if e.name not in self.placement_targets)
        return TaskSpec(entities, {"rigid": {"enable_self_collision": True, "iterations": 100,
            "max_collision_pairs": 8192, "constraint_timeconst": .00125}}, dict(**preset, task_id=self.task_id, instance_id=self.instance_id,
            asset_report=report, required_control_review="cage reachability and suitable gripper"))

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
