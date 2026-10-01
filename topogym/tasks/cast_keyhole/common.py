"""Cast Keyhole geometry and whole-piece placement qualification."""
from pathlib import Path
from topogym.tasks.placement import PlacementGoalMixin

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.assets.geometry.cast_keyhole import generate_assets
from topogym.tasks.base import EntitySpec, RigidTaskDefinition, TaskSpec


class CastKeyholeTask(PlacementGoalMixin, RigidTaskDefinition):
    task_id = "cast_keyhole"
    placement_description = 'the entire silver keyhole piece'
    goal_side = (1, 1)  # +y, the nominal scene's side; pose variation cannot flip it
    defaults = dict(scale=3., center_xy_m=[-.1356786, .05], yaw_deg=0.,
                    initial_floor_clearance_m=.0005, stable_duration_s=.5,
                    minimum_separation_m=.02, piece_tint=dict(gold=1., silver=1.))
    hash_when_changed = ("piece_tint",)

    geometry_resource = None

    terminal_revision = "cast_keyhole_placement_v3_default_success"

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
        if self.geometry_resource:
            from topogym.assets.geometry.cast_keyhole import generate_variant_assets
            return generate_variant_assets(folder, self.geometry_resource)
        return generate_assets(folder, scale=float(self.config["scale"]))

    def declare(self, asset_dir, table_height_m):
        self.table_height_m = float(table_height_m)
        cfg, folder = self.config, Path(asset_dir)
        assembly, report = self.build_assets(folder)
        if cfg["piece_tint"] != self.defaults["piece_tint"]:
            # Appearance only: rescale each piece's baked GLB colour after generation.
            from topogym.assets.scene_visuals import scale_glb_color
            for body in assembly.bodies:
                metal = "gold" if "gold" in body.name else "silver"
                for path in sorted((folder/body.name).glob("*.glb")):
                    scale_glb_color(path, cfg["piece_tint"][metal])
        xy = np.asarray(cfg["center_xy_m"], dtype=float)
        clearance = float(cfg["initial_floor_clearance_m"])
        if xy.shape != (2,) or not np.isfinite(xy).all() or not np.isfinite(clearance) or clearance < 0:
            raise ValueError("Invalid Keyhole layout")
        if not np.isfinite(cfg["minimum_separation_m"]) or cfg["minimum_separation_m"] <= 0:
            raise ValueError("minimum_separation_m must be finite and positive")
        rotation = (Rotation.from_euler("z", float(cfg["yaw_deg"]), degrees=True)
                    * Rotation.from_euler("y", 90, degrees=True)
                    * Rotation.from_euler("z", 45, degrees=True))
        vertices = np.concatenate([rotation.apply(b.visual.vertices) for b in assembly.bodies])
        midpoint = (vertices.min(0)+vertices.max(0))/2
        origin = np.r_[xy-midpoint[:2], self.table_height_m-vertices[:, 2].min()+clearance]
        entities, self.local_vertices = [], {}
        for body, item in zip(assembly.bodies, report["bodies"]):
            center = np.asarray(item["origin_m"])
            self.local_vertices[body.name] = body.visual.vertices-center
            entities.append(EntitySpec(body.name, "urdf", folder/body.name/f"{body.name}.urdf",
                tuple(origin+rotation.apply(center)), tuple(rotation.as_quat()[[3, 0, 1, 2]]),
                material={"friction": .35}, morph_options={"align": False, "convexify": True,
                "decimate": False, "merge_fixed_links": False}, surface={"smooth": False}))
        # Placement rule caches the union of collision and visible geometry.
        from topogym.evaluation.task_metrics import rigid_asset_vertices
        self.placement_vertices = {e.name: rigid_asset_vertices(e) for e in entities}
        self.placement_targets = ('keyhole_silver',)
        self.placement_remainder = tuple(e.name for e in entities if e.name not in self.placement_targets)
        return TaskSpec(tuple(entities), {"rigid": {"enable_self_collision": True,
            "iterations": 100, "max_collision_pairs": 8192, "constraint_timeconst": .001}},
            dict(task_id=self.task_id, instance_id=self.instance_id, asset_report=report,
                 separation_measure="whole target in fixed region; remainder behind separator"))

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
