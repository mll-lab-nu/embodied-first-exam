"""Horseshoe assembly entities and a conservative free-ring goal."""
from pathlib import Path
from topogym.tasks.placement import PlacementGoalMixin
from dataclasses import replace

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.assets.geometry.horseshoe_ring import generate_assets
from topogym.assets.scene_visuals import finish_generated_urdf
from topogym.tasks.base import EntitySpec, RigidTaskDefinition, TaskSpec
from ..scene_presets import defaults, record_preset


class HorseshoeRingTask(PlacementGoalMixin, RigidTaskDefinition):
    task_id = "horseshoe_ring"
    placement_description = 'the entire removable ring'
    goal_side = (1, -1)  # -y, the nominal scene's side; pose variation cannot flip it
    defaults = defaults(task_id, scale=2., center_xy_m=[-.1356786, .05], yaw_deg=0.,
                    initial_floor_clearance_m=.001, stable_duration_s=.5,
                    minimum_separation_m=.02)

    template_resource = None
    layout_resource = None

    def declare(self, asset_dir, table_height_m):
        self.table_height_m = float(table_height_m)
        cfg, folder = self.config, Path(asset_dir)
        preset = record_preset(self, folder)
        from topogym.assets.variation_resources import read_json
        template = read_json(self.template_resource) if self.template_resource else None
        assembly, report = generate_assets(folder, scale=float(cfg["scale"]), template=template)
        ring_finish = finish_generated_urdf(
            folder / "target_ring" / "target_ring.urdf", cfg["target_ring_finish"]
        )
        self.assembly = assembly
        self.body_origins = {item["name"]: np.asarray(item["origin_m"]) for item in report["bodies"]}
        rotation = Rotation.from_euler("z", float(cfg["yaw_deg"]), degrees=True)
        xy = np.asarray(cfg["center_xy_m"], dtype=float)
        clearance = float(cfg["initial_floor_clearance_m"])
        if xy.shape != (2,) or not np.isfinite(xy).all() or not np.isfinite(clearance) or clearance < 0:
            raise ValueError("Invalid Horseshoe initial layout")
        bottom = min(rotation.apply(body.visual.vertices)[:, 2].min() for body in assembly.bodies)
        origin = np.r_[xy, self.table_height_m-bottom+clearance]
        entities, self.local_vertices = [], {}
        for body, item in zip(assembly.bodies, report["bodies"]):
            center = np.asarray(item["origin_m"])
            self.local_vertices[body.name] = body.visual.vertices-center
            entities.append(EntitySpec(body.name, "urdf", folder/body.name/f"{body.name}.urdf",
                tuple(origin+rotation.apply(center)), tuple(rotation.as_quat()[[3, 0, 1, 2]]),
                material={"friction": .3, "gravity_compensation": 0.},
                morph_options={"align": False, "convexify": True, "decimate": False,
                               "merge_fixed_links": False}))
        if self.layout_resource:
            # Physically settled rest poses: the template assembly spawned on the
            # table drops ~66 mm and its ring slides off 1.5-2.5 s later.
            rest = read_json(self.layout_resource)["poses"]
            anchor = np.r_[xy, self.table_height_m]
            entities = [replace(e, position_m=tuple(anchor+rotation.apply(rest[e.name]["position_m"])),
                                quaternion_wxyz=tuple((rotation*Rotation.from_quat(np.roll(
                                    rest[e.name]["quaternion_wxyz"], -1))).as_quat()[[3, 0, 1, 2]]))
                        for e in entities]
        # Placement rule caches the union of collision and visible geometry.
        from topogym.evaluation.task_metrics import rigid_asset_vertices
        self.placement_vertices = {e.name: rigid_asset_vertices(e) for e in entities}
        self.placement_targets = ('target_ring',)
        self.placement_remainder = tuple(e.name for e in entities if e.name not in self.placement_targets)
        return TaskSpec(tuple(entities), {"rigid": {"enable_self_collision": True, "iterations": 100,
            "max_collision_pairs": 4096, "constraint_timeconst": .001}},
            dict(**preset, task_id=self.task_id, instance_id=self.instance_id, asset_report=report,
                 target_ring_visual=ring_finish,
                 target_ring_free=True, target_ring_gravity_compensation=0.,
                 goal_measure="whole ring in fixed region; remainder behind separator; holding allowed"))

    def evaluate_goal_region(self, state, region):
        """Measure the fixed placement rule; physical qualification is separate."""
        from topogym.evaluation.task_metrics import placement_candidate
        result = placement_candidate(state, region, self.placement_vertices,
            self.placement_targets, self.placement_remainder)
        from topogym.evaluation.task_metrics import body_points
        loops = {}
        for name, loop in self.assembly.loops.items():
            body = state["bodies"][loop.body]
            q = np.asarray(body["quaternion_wxyz"])
            rotation = Rotation.from_quat(q[[1,2,3,0]])
            center = body_points(body, [loop.center-self.body_origins[loop.body]])[0]
            loops[name] = replace(loop, center=center, rotation=rotation*loop.rotation)
        intact = all(abs(loops[a].linking(loops[b])) == 1 for a, b in self.assembly.edges)
        if not intact:
            return False, "Physical chain/eye connection lost", dict(result[2], connections_intact=False)
        return result

    def goal_region_observation(self, region):
        return region.observation(self.placement_targets, self.placement_remainder)

    def evaluate_state(self, state):
        return self.evaluate_placement(state)
