"""Buzz Wire traversal, substep metal contact failure and released deck finish."""

from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from dataclasses import asdict
from topogym.assets.geometry.buzz_wire_3d import BuzzWireLayout, generate_assets, endpoint_pose
from ..base import TaskDefinition, TaskSpec, EntitySpec
from ..scene_presets import defaults, record_preset
from topogym.evaluation.task_metrics import contact_role_hits, quiet_body
from topogym.evaluation.terminal import SettlingSpec
from topogym.utils.geometry.passage import aperture_crossings


def recommended_grasp_assist(variation_id, seed=0, *, task_parameters=None):
    """The oracle's handle region, resolved from this instance's tool dimensions."""
    from topogym.config.registry import task_definition
    from topogym.utils.grasp import GraspAssistConfig, GraspTarget
    task = task_definition("buzz_wire_3d", variation_id, seed)(task_parameters, seed=seed)
    layout = task.build_layout()
    center = (layout.loop_radius_m + layout.stem_length_m + .55*layout.grip_length_m, 0., 0.)
    return GraspAssistConfig("contact_weld_v1", (GraspTarget("wand", "wand", center, .025),))


class BuzzWireTask(TaskDefinition):
    task_id = "buzz_wire_3d"
    instruction = 'Guide the metal loop along the entire wire without touching it, then release the tool on the finish support and let it settle.'
    terminal_revision = "terminal_v4_traversal_then_deck_release"
    goal_complete = True
    # Fit the maze beside the Panda home pose, with its plinth on the table.
    # The previous full-size layout crossed the upper arm and robot pedestal.
    defaults = defaults(task_id,
        geometry=dict(horizontal_scale=0.7, depth_scale=0.7, height_scale=0.7,
                      base_size_m=(0.826, 0.574, 0.045)),
        center_xy_m=[-0.02, -0.32], stable_duration_s=1.0,
        terminal=dict(finish_position_tolerance_m=.005, finish_angle_tolerance_deg=10.,
                      maximum_speed_m_s=.001, maximum_angular_speed_rad_s=.02,
                      start_route_tolerance_m=.01, route_progress_tolerance_m=.003),
        wood_tint=1., rail_rgb=[.72, .33, .16],
    )
    hash_when_changed = ("wood_tint", "rail_rgb")

    layout_resource = None

    def final_settling_spec(self):
        cfg = self.config["terminal"]
        return SettlingSpec(rigid_targets=("wand",), maximum_speed_m_s=cfg["maximum_speed_m_s"],
            maximum_angular_speed_rad_s=cfg["maximum_angular_speed_rad_s"])

    def build_layout(self):
        if self.layout_resource:
            from topogym.assets.variation_resources import read_json
            values = read_json(self.layout_resource)
            # Apply the deck lift to frozen routes too. route_elevation_m is
            # added once by Route; authored controls and offset knots stay local.
            lift = float(self.config["base_elevation_m"]) - values.get("base_elevation_m", 0.)
            values["base_elevation_m"] = float(self.config["base_elevation_m"])
            values["route_elevation_m"] = values.get("route_elevation_m", 0.) + lift
            # Current three tiers use thin, non-captive endpoint connectors and
            # rest the complete tool directly on the raised deck. The archived
            # layouts remain untouched as provenance for the historical demos.
            values.update(endpoint_support_part="deck", supported_endpoints=True,
                          mount_size_m=(.008, .008, .012), end_stop_radius_m=.009,
                          grip_flat_roll_deg=0., rest_handle_pitch_deg=0.,
                          rest_finish_quaternion_wxyz=(), rest_finish_yaw_deg=0.)
            return BuzzWireLayout(**values)
        values = {**dict(horizontal_scale=.7, depth_scale=.7, height_scale=.7,
                        base_size_m=(.826, .574, .045)), **self.config["geometry"]}
        base = BuzzWireLayout(**values)
        scale = float(self.config["linear_scale"])
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError("linear_scale must be positive and finite")
        values = asdict(base)
        for name in ("horizontal_scale", "depth_scale", "height_scale", "wire_radius_m",
                     "loop_radius_m", "loop_tube_radius_m", "stem_length_m", "grip_length_m",
                     "grip_radius_m", "grip_half_thickness_m", "end_stop_radius_m",
                     "end_stop_thickness_m", "rail_segment_m", "witness_step_m", "end_reserve_m",
                     "clearance_cover_m", "vertical_valley_lift_m", "post_radius_m", "post_height_m",
                     "route_elevation_m", "finish_cradle_mount_clearance_m"):
            values[name] *= scale
        for name in ("base_size_m", "mount_size_m"):
            values[name] = tuple(np.asarray(values[name])*scale)
        values.update(finish="toy_wood_copper", supported_endpoints=True,
                      endpoint_support_part="stem",
                      end_stop_shape="block_mount", grip_shape="box",
                      mount_size_m=(.032, .032, .016), end_stop_radius_m=.026,
                      base_elevation_m=float(self.config["base_elevation_m"]))
        # Preserve template sections and orientation witnesses while lifting the
        # entire scaled route with its deck. Authored coordinates are metric.
        if values["authored_controls_m"]:
            values["authored_controls_m"] = tuple(map(tuple,
                np.asarray(values["authored_controls_m"])*scale))
        if values["center_offset_knots_m"]:
            knots = np.asarray(values["center_offset_knots_m"], dtype=float)
            knots[:, 1:] *= scale
            values["center_offset_knots_m"] = tuple(map(tuple, knots))
        values["route_elevation_m"] += values["base_elevation_m"]
        return BuzzWireLayout(**values)

    def declare(self, asset_dir, table_height_m):
        from topogym.assets.geometry.buzz_wire_3d import collision_roles
        self.table_height_m = float(table_height_m)
        preset = record_preset(self, asset_dir)
        layout = self.layout = self.build_layout()
        scale = float(self.config["linear_scale"])
        self.route, report = generate_assets(asset_dir, layout)
        # Appearance only: rescale the baked wood and recolour the rail after generation.
        from topogym.assets.scene_visuals import scale_glb_color
        for path in sorted(Path(asset_dir).glob("*.glb")):
            if self.config["wood_tint"] != 1.:
                scale_glb_color(path, self.config["wood_tint"], materials=("wood",))
            if self.config["rail_rgb"] != self.defaults["rail_rgb"]:
                scale_glb_color(path, 1., materials=("rail_metal", "brushed_copper"),
                                color=[*self.config["rail_rgb"], 1.])
        self.origin = np.r_[
            self.config["center_xy_m"], table_height_m
        ]
        self.rail = self.route.rail + self.origin
        position, rotation = endpoint_pose(self.route, 0)
        quaternion = rotation.as_quat()[[3, 0, 1, 2]]
        folder = Path(asset_dir)
        entities = (
            EntitySpec(
                "wire_base",
                "urdf",
                folder / "base.urdf",
                tuple(self.origin + [0, 0, layout.base_size_m[2] / 2]),
                fixed=True,
                morph_options={"convexify": True, "decimate": False},
                contact_roles=collision_roles(folder / "base.urdf"),
            ),
            EntitySpec(
                "wire",
                "urdf",
                folder / "wire.urdf",
                tuple(self.origin),
                fixed=True,
                contact_roles=collision_roles(folder / "wire.urdf"),
            ),
            EntitySpec(
                "wand",
                "urdf",
                folder / "wand.urdf",
                tuple(self.origin + position),
                tuple(quaternion),
                material={"friction": 0.3},
                contact_roles=collision_roles(folder / "wand.urdf"),
            ),
        )
        return TaskSpec(
            entities,
            {"rigid": {"enable_self_collision": True,
                       # Dense capsule compounds need more AABB candidates,
                       # independently of the much smaller actual contact set.
                       "multiplier_collision_broad_phase": 64,
                       "constraint_timeconst": 0.00125}},
            dict(
                **preset, linear_scale=scale,
                supported_endpoints=True,
                task_id=self.task_id,
                geometry_report=report,
                goal_evaluation_complete=self.goal_complete,
            ),
        )

    def initial_task_state(self, world_state):
        summary = world_state.get("contact_events")
        coverage = bool(summary and summary["substeps_complete"] is True and summary["geometry_roles_complete"] is True)
        return dict(cursor_m=0., started=False, traversal_complete=False, coverage_complete=coverage,
                    previous_position_m=np.asarray(world_state["bodies"]["wand"]["position_m"], float).copy(),
                    previous_quaternion_wxyz=np.asarray(world_state["bodies"]["wand"]["quaternion_wxyz"], float).copy())

    def validate_task_state(self, state):
        super().validate_task_state(state)
        if not state:
            return
        if (set(state) != {"cursor_m", "started", "traversal_complete", "coverage_complete", "previous_position_m", "previous_quaternion_wxyz"}
                or not isinstance(state["started"], bool) or state["cursor_m"] < 0
                or not isinstance(state["traversal_complete"], bool)
                or not isinstance(state["coverage_complete"], bool)
                or np.asarray(state["previous_position_m"]).shape != (3,)
                or np.asarray(state["previous_quaternion_wxyz"]).shape != (4,)
                or np.linalg.norm(state["previous_quaternion_wxyz"]) < 1e-12):
            raise ValueError("Invalid Buzz traversal history")

    def evaluate_state(self, state):
        return self.evaluate_transition(state, self.task_state)[0:3]

    def evaluate_transition(self, state, task_state):
        body = state["bodies"]["wand"]
        p = np.asarray(body["position_m"])
        if not np.isfinite(p).all():
            return False, "Non-finite wand state", {}, task_state
        if p[2] < self.table_height_m - 0.1:
            return False, "Wand fell below table", {}, task_state
        cfg = self.config["terminal"]
        summary = state.get("contact_events")
        events, covered = [], False
        if summary is not None:
            if summary["schema_version"] != 1 or summary["physics_step"] != state["physics_step"]:
                raise ValueError("Stale or unsupported contact event summary")
            events = summary["events"]
            covered = summary["substeps_complete"] is True and summary["geometry_roles_complete"] is True
        hits = contact_role_hits(events, {"wand_metal"}, {"wire_metal"})
        if hits:
            return False, "wire_touched", dict(touch_now=True, first_touch_step=int(state["physics_step"]),
                                               contact_events=hits, evaluation_status="available"), task_state
        q = np.asarray(body["quaternion_wxyz"], float)
        r = Rotation.from_quat(q[[1, 2, 3, 0]])
        history = task_state or self.initial_task_state(state)
        coverage_complete = bool(history["coverage_complete"] and covered)
        aperture = self.layout.loop_radius_m-self.layout.loop_tube_radius_m-self.layout.wire_radius_m
        hits, ambiguous = aperture_crossings(self.rail, p, r.apply([0., 0., 1.]), aperture)
        arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(self.rail, axis=0), axis=1))]
        cursor, started = history["cursor_m"], history["started"]
        tracking = len(hits) == 1 and not ambiguous
        if tracking:
            candidate = float(np.interp(hits[0]["material_coordinate"], np.arange(len(arc)), arc))
            if not started:
                started = candidate <= cfg["start_route_tolerance_m"]+1e-12
                if started:
                    cursor = candidate
            else:
                old_r = Rotation.from_quat(np.asarray(history["previous_quaternion_wxyz"])[[1,2,3,0]])
                movement = np.linalg.norm(p-history["previous_position_m"])+aperture*(r*old_r.inv()).magnitude()
                tracking = abs(candidate-cursor) <= 2*movement+cfg["route_progress_tolerance_m"]
                if tracking:
                    cursor = candidate
                else:
                    started = False  # Ambiguous branch jump needs a fresh traversal from start.
        else:
            started = False
        # The current deck is below the metal rail endpoint: lowering the ring
        # onto it necessarily removes the last aperture crossing. Preserve only
        # an already observed complete traversal, never merely a finish pose.
        complete = bool(history["traversal_complete"] or (coverage_complete and started and tracking
                        and cursor >= arc[-1]-cfg["start_route_tolerance_m"]-1e-12))
        next_state = dict(cursor_m=cursor, started=bool(started), traversal_complete=complete,
                          coverage_complete=coverage_complete,
                          previous_position_m=p.copy(), previous_quaternion_wxyz=q.copy())
        end_p, end_r = endpoint_pose(self.route, 1)
        distance = float(np.linalg.norm(p-(end_p+self.origin)))
        # Ring, stem and rectangular handle are invariant under a half turn
        # about the handle axis. Following a returning wire reverses the ring
        # normal; that is the same physical resting pose, not a 180-degree error.
        symmetry = Rotation.from_euler("x", 180, degrees=True)
        angle = float(np.degrees(min((r*end_r.inv()).magnitude(),
                                    (r*(end_r*symmetry).inv()).magnitude())))
        supported = bool(contact_role_hits(events, {"wand_metal", "wand_handle"}, {"finish_support"}))
        held = bool(contact_role_hits(events, {"wand_metal", "wand_handle"}, {"robot"}))
        released = covered and not held and state.get("assist_active") is False
        quiet = quiet_body(body, cfg["maximum_speed_m_s"], cfg["maximum_angular_speed_rad_s"])
        reached = (coverage_complete and complete
                   and distance <= cfg["finish_position_tolerance_m"] and angle <= cfg["finish_angle_tolerance_deg"]
                   and supported and released and quiet)
        return bool(reached), None, dict(touch_now=False, route_cursor_m=cursor, traversal_tracked=bool(started and tracking),
            traversal_complete=complete, episode_contact_coverage_complete=coverage_complete,
            distance_to_finish_m=distance, finish_angle_deg=angle, supported=supported, released=bool(released), quiet=quiet,
            evaluation_status="available" if coverage_complete and "assist_active" in state else "unavailable",
            goal_evaluation_complete=self.goal_complete, thresholds_calibrated=False), next_state
