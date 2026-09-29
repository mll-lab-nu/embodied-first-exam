"""Cast Coil entities and assembly/disassembly goals for the shared Env."""
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.assets.geometry.cast_coil import generate_assets
from topogym.tasks.base import EntitySpec, RigidTaskDefinition, TaskSpec
from topogym.evaluation.terminal import SettlingSpec


class CastCoilTask(RigidTaskDefinition):
    task_id = "cast_coil"
    terminal_revision = "release_settling_v1"
    defaults = dict(scale=3., center_xy_m=[-.1356786, .05], yaw_deg=90.,
                    initial_floor_clearance_m=.0005, objective="assemble",
                    initial_xy_offset_m=[-.12, .18], stable_duration_s=.5,
                    terminal=dict(release_clearance_m=.005, maximum_drift_m=.001,
                                  table_clearance_m=.003),
                    piece_tint=dict(gold=1., silver=1.))
    hash_when_changed = ("piece_tint",)

    template_resource = None

    def final_settling_spec(self):
        return SettlingSpec(rigid_targets=("coil_gold", "coil_silver"),
            clearance_m=self.config["terminal"]["release_clearance_m"],
            maximum_drift_m=self.config["terminal"]["maximum_drift_m"])

    def finalize_spec(self, spec, *, asset_dir, scene_config):
        table = scene_config.env.world.table
        center, half = np.asarray(table.pos[:2]), np.asarray(table.size[:2])/2
        self.table_xy_bounds = (center-half, center+half)
        return spec

    def build_assets(self, folder):
        from topogym.assets.variation_resources import read_json
        template = read_json(self.template_resource) if self.template_resource else None
        return generate_assets(folder, scale=float(self.config["scale"]), template=template)

    def declare(self, asset_dir, table_height_m):
        self.table_height_m = float(table_height_m)
        cfg, folder = self.config, Path(asset_dir)
        if cfg["objective"] not in ("assemble", "disassemble"):
            raise ValueError("Cast Coil objective must be assemble or disassemble")
        xy = np.asarray(cfg["center_xy_m"], dtype=float)
        clearance = float(cfg["initial_floor_clearance_m"])
        if xy.shape != (2,) or not np.isfinite(xy).all() or not np.isfinite(clearance) or clearance < 0:
            raise ValueError("Invalid Cast Coil initial position")
        assembly, report = self.build_assets(folder)
        if cfg["piece_tint"] != self.defaults["piece_tint"]:
            # Appearance only: rescale each piece's baked GLB colour after generation.
            from topogym.assets.scene_visuals import scale_glb_color
            for body in assembly.bodies:
                metal = "gold" if "gold" in body.name else "silver"
                for path in sorted((folder/body.name).glob("*.glb")):
                    scale_glb_color(path, cfg["piece_tint"][metal])
        rotation = Rotation.from_euler("z", float(cfg["yaw_deg"]), degrees=True)
        origin = np.r_[xy, self.table_height_m-min(rotation.apply(b.visual.vertices)[:, 2].min()
                                                  for b in assembly.bodies)+clearance]
        poses = [(rotation, origin), (rotation, origin.copy())]
        if cfg["objective"] == "assemble":
            offset = np.asarray(cfg["initial_xy_offset_m"], dtype=float)
            if offset.shape != (2,) or not np.isfinite(offset).all():
                raise ValueError("initial_xy_offset_m must be a finite XY offset")
            silver_rotation = rotation * Rotation.from_euler("y", -90, degrees=True)
            silver_bottom = silver_rotation.apply(assembly.bodies[1].visual.vertices)[:, 2].min()
            poses[1] = (silver_rotation, np.r_[xy+offset, self.table_height_m-silver_bottom+clearance])
            world_bounds = [(r.apply(b.visual.vertices)+p) for b, (r, p) in zip(assembly.bodies, poses)]
            gap = np.maximum(world_bounds[1].min(0)-world_bounds[0].max(0),
                             world_bounds[0].min(0)-world_bounds[1].max(0))
            if np.max(gap[:2]) < .01:
                raise ValueError("Assembly initial bodies must be separated by at least 10 mm")
        self.local_vertices, self.body_origins = {}, {}
        entities = []
        for body, item, (turn, position) in zip(assembly.bodies, report["bodies"], poses):
            center = np.asarray(item["origin_m"])
            self.local_vertices[body.name] = body.visual.vertices-center
            self.body_origins[body.name] = center
            entities.append(EntitySpec(body.name, "urdf", folder/body.name/f"{body.name}.urdf",
                tuple(position+turn.apply(center)), tuple(turn.as_quat()[[3, 0, 1, 2]]),
                material={"friction": .35}, morph_options={"align": False, "convexify": False,
                "decimate": False, "merge_fixed_links": False}, surface={"smooth": False}))
        return TaskSpec(tuple(entities), {"rigid": {"enable_self_collision": True, "iterations": 100,
            "max_collision_pairs": 4096, "constraint_timeconst": .001, "noslip_iterations": 5}},
            dict(task_id=self.task_id, instance_id=self.instance_id, objective=cfg["objective"],
                 asset_report=report, goal_requires_release=True))

    def evaluate_state(self, state):
        poses, bounds, quiet, failure = self.rigid_measurements(state)
        if failure:
            return False, failure, {}
        gold, silver = "coil_gold", "coil_silver"
        pg, rg = poses[gold]; ps, rs = poses[silver]
        pg = pg-rg.apply(self.body_origins[gold])
        ps = ps-rs.apply(self.body_origins[silver])
        position_error = float(np.linalg.norm(ps-pg))
        rotation_error = float((rg.inv()*rs).magnitude())
        separation = float(np.max(np.maximum(bounds[silver][0]-bounds[gold][1],
                                             bounds[gold][0]-bounds[silver][1])))
        reached = (position_error < .001 and rotation_error < .02) if self.config["objective"] == "assemble" else separation > .01
        released = self.released(state)
        bottoms = [bounds[name][0][2]-self.table_height_m for name in (gold, silver)]
        near_table = (min(bottoms) if self.config["objective"] == "assemble" else max(bottoms)) <= self.config["terminal"]["table_clearance_m"]
        on_table = near_table and min(bottoms) >= -.001
        if hasattr(self, "table_xy_bounds"):
            lo, hi = self.table_xy_bounds
            on_table &= all(np.all(bounds[n][1][:2] >= lo) and np.all(bounds[n][0][:2] <= hi) for n in (gold, silver))
        return bool(reached and quiet and released and on_table), None, dict(
            relative_position_error_m=position_error, relative_rotation_error_rad=rotation_error,
            conservative_separation_m=separation, released=released, quiet=quiet,
            near_table=bool(on_table), minimum_table_gap_m=float(min(bottoms)))
