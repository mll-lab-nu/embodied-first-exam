"""Ordered fiber passage with complete per-substep gripper contact evidence."""

from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from scipy.spatial.transform import Rotation
from topogym.assets.geometry.fiber_bundling import FiberLayout
from topogym.assets.geometry.fiber_bundling import (
    AnchoredLayout,
    generate_anchored_assets,
)
from topogym.assets.geometry.fiber_bundling import RingMount
from ..base import TaskDefinition, EntitySpec, TaskSpec
from ..scene_presets import defaults, record_preset
from topogym.evaluation.task_metrics import body_points
from topogym.utils.geometry.passage import passage_initial, advance_passage


class FiberBundlingTask(TaskDefinition):
    task_id = "fiber_bundling"
    instruction = ('Manipulate only the thick sheath. Pass every fiber tip first through the copper ring '
                   'in material order, without sharp bends, until the roots and front sheath have passed. '
                   'Any gripper contact with a fine strand fails the task; keep the rear terminal anchored.')
    terminal_revision = "terminal_v3_fiber_contacts"
    physics_model = "rigid_articulated"
    goal_complete = True
    defaults = defaults(task_id,
        geometry={}, anchor={}, center_xy_m=[-0.1, -0.25], stable_duration_s=0.5,
        terminal=dict(maximum_bend_deg=60., aperture_margin_m=.0001)
    )

    def declare(self, asset_dir, table_height_m):
        preset = record_preset(self, asset_dir)
        self.table_height_m = float(table_height_m)
        layout = FiberLayout(**{**self.config["geometry"], "seed": self.seed})
        anchor = AnchoredLayout(**self.config["anchor"])
        self.layout, report = generate_anchored_assets(asset_dir, layout, anchor)
        self.origin = np.r_[
            self.config["center_xy_m"], table_height_m + anchor.axis_height_m
        ]
        center = np.array(
            [layout.trunk_length_m + anchor.ring_distance_from_roots_m, 0, 0]
        )
        self.ring_center = self.origin+center
        folder = Path(asset_dir)
        # Declare authored collision roles; the World matches local geometry.
        # Native mesh metadata names may be reused by Genesis' primitive cache.
        contact_roles = {}
        root = ET.parse(folder / "bundle.xml").getroot()
        for body in root.findall(".//worldbody//body"):
            for geom in body.findall("geom"):
                if not (int(geom.get("contype", "1")) or int(geom.get("conaffinity", "1"))):
                    continue
                name = geom.get("name")
                if not name or name in contact_roles:
                    raise ValueError("Fiber collision geometries require unique names")
                contact_roles[name] = ("fiber_strand" if body.get("name", "").startswith("fiber_")
                                       else "fiber_sheath")
        expected = {f"fiber_surface_{i:02d}_{j:02d}" for i in range(layout.fiber_count)
                    for j in range(layout.fiber_segments)}
        if {name for name, role in contact_roles.items() if role == "fiber_strand"} != expected:
            raise ValueError("Incomplete declared fiber collision geometry")
        entities = [
            EntitySpec(
                "fiber_bundle",
                "mjcf",
                folder / "bundle.xml",
                tuple(self.origin),
                material={"gravity_compensation": 1.0},
                contact_roles=contact_roles,
            ),
            EntitySpec(
                "bundling_ring",
                "urdf",
                folder / "ring.urdf",
                tuple(self.origin + center),
                tuple(
                    Rotation.from_euler("y", 90, degrees=True).as_quat()[[3, 0, 1, 2]]
                ),
                fixed=True,
            ),
        ]
        for name, pos, size, color in anchor.cradle_parts(layout):
            entities.append(
                EntitySpec(
                    name,
                    "box",
                    None,
                    tuple(self.origin + pos),
                    fixed=True,
                    morph_options={"size": size},
                    surface={"color": color},
                )
            )
        for name, kind, pos, size, color in RingMount().parts(
            layout, center, -anchor.axis_height_m
        ):
            options = (
                {"size": size}
                if kind == "box"
                else {"radius": size[0], "height": size[1]}
            )
            entities.append(
                EntitySpec(
                    name,
                    kind,
                    None,
                    tuple(self.origin + pos),
                    fixed=True,
                    morph_options=options,
                    surface={"color": color},
                )
            )
        return TaskSpec(
            tuple(entities),
            {"rigid": {"enable_self_collision": True}},
            dict(
                **preset,
                task_id=self.task_id,
                geometry_report=report,
                goal_evaluation_complete=self.goal_complete,
            ),
        )

    def _strand_points(self, state):
        links = state["articulations"]["fiber_bundle"]["links"]
        length = self.layout.fiber_length_m/self.layout.fiber_segments
        paths = []
        for strand in range(self.layout.fiber_count):
            segments = [body_points(links[f"fiber_{strand:02d}_{segment:02d}"], [[0,0,0], [length,0,0]])
                        for segment in range(self.layout.fiber_segments)]
            # Link origins are capsule roots; include the final tip explicitly.
            paths.append(np.vstack([s[0] for s in segments]+[segments[-1][1]])[::-1].copy())
        return paths

    def initial_task_state(self, world_state):
        paths = self._strand_points(world_state)
        _, covered = self._contact_evidence(world_state)
        return dict(strands=[passage_initial(p) for p in paths],
                    front=passage_initial([self._front_point(world_state)]),
                    contact_coverage_complete=covered)

    @staticmethod
    def _contact_evidence(state):
        summary = state.get("contact_events")
        if summary is None:
            return [], False
        if summary["schema_version"] != 1 or summary["physics_step"] != state["physics_step"]:
            raise ValueError("Stale or unsupported fiber contact summary")
        expected, sampled = summary["expected_substeps"], summary["sampled_substeps"]
        if (type(expected) is not int or type(sampled) is not int
                or expected < 0 or not 0 <= sampled <= expected):
            raise ValueError("Invalid fiber contact substep counts")
        birth = state["physics_step"] == 0 and summary.get("sampling_scope") == "initial_pose"
        covered = bool(summary["substeps_complete"] is True
                       and summary["geometry_roles_complete"] is True
                       and summary["robot_geometry_complete"] is True
                       and sampled == expected and (expected > 0 or birth))
        hits = []
        for event in summary["events"]:
            if event["touching"] is not True:
                continue
            for robot_side, fiber_side in (("a", "b"), ("b", "a")):
                if (event[f"role_{robot_side}"] == "robot"
                        and event[f"role_{fiber_side}"] == "fiber_strand"):
                    part = event.get(f"robot_part_{robot_side}")
                    if part not in {"gripper", "arm"}:
                        covered = False
                    if part == "gripper":
                        hits.append(dict(event))
        return hits, covered

    def _front_point(self, state):
        link = state["articulations"]["fiber_bundle"]["links"][f"trunk_{self.layout.trunk_segments-1:02d}"]
        return body_points(link, [[self.layout.trunk_length_m/self.layout.trunk_segments,0,0]])[0]

    def validate_task_state(self, state):
        super().validate_task_state(state)
        if not state:
            return
        count = self.layout.fiber_count
        stations = self.layout.fiber_segments+1
        if set(state) != {"strands", "front", "contact_coverage_complete"} or len(state["strands"]) != count:
            raise ValueError("Invalid fiber history strand count")
        if not isinstance(state["contact_coverage_complete"], bool):
            raise ValueError("Invalid fiber contact coverage history")
        for strand in state["strands"]:
            stages = np.asarray(strand["stages"])
            if (np.asarray(strand["previous"]).shape != (stations, 3) or stages.shape != (stations,)
                    or stages.dtype.kind not in "iu" or np.any((stages < 0) | (stages > 2))
                    or np.any(np.diff(stages) > 0)):
                raise ValueError("Invalid fiber material history")
        front = state["front"]
        if (np.asarray(front["previous"]).shape != (1,3) or np.asarray(front["stages"]).shape != (1,)
                or np.asarray(front["stages"]).dtype.kind not in "iu" or not 0 <= front["stages"][0] <= 2):
            raise ValueError("Invalid front sheath passage history")

    def evaluate_state(self, state):
        return self.evaluate_transition(state, self.task_state)[0:3]

    def evaluate_transition(self, state, task_state):
        hits, covered = self._contact_evidence(state)
        if hits:
            # The base Task result locks this failure and restores it on rewind.
            return False, "fiber_gripper_contact", dict(contact_events=hits,
                first_touch_step=int(state["physics_step"]), evaluation_status="available"), task_state
        links = state["articulations"]["fiber_bundle"]["links"]
        points = np.array([x["position_m"] for x in links.values()])
        if not np.isfinite(points).all():
            return False, "Non-finite fiber link state", {}, task_state
        if points[:, 2].min() < self.table_height_m - 0.1:
            return False, "Fiber below table", {}, task_state
        paths = self._strand_points(state)
        history = task_state or self.initial_task_state(state)
        contact_coverage = bool(history["contact_coverage_complete"] and covered)
        ring = state["bodies"]["bundling_ring"]
        center = np.asarray(ring["position_m"], float)
        q = np.asarray(ring["quaternion_wxyz"], float)
        normal = Rotation.from_quat(q[[1,2,3,0]]).apply([0.,0.,1.])
        cfg = self.config["terminal"]
        radius = self.layout.minimum_aperture_radius-self.layout.fiber_radius_m-cfg["aperture_margin_m"]
        half = self.layout.ring_tube_radius_m+self.layout.fiber_radius_m
        completed, next_strands, bends = [], [], []
        for path, old in zip(paths, history["strands"]):
            done, new, _ = advance_passage(path, old, center, normal, radius, half)
            completed.append(done)
            next_strands.append(new)
            tangents = np.diff(path, axis=0)
            lengths = np.linalg.norm(tangents, axis=1)
            if np.any(lengths < 1e-10):
                raise ValueError("Degenerate fiber segment")
            tangents /= lengths[:,None]
            bends.extend(np.degrees(np.arccos(np.clip(np.sum(tangents[:-1]*tangents[1:], axis=1), -1, 1))))
        maximum = float(max(bends, default=0.))
        # Front sheath (the branching face) must also clear the exit, not the fixed terminal.
        front = self._front_point(state)
        front_clear = np.dot(front-center, normal)-self.layout.trunk_radius_m > self.layout.ring_tube_radius_m
        front_passed, front_history, _ = advance_passage([front], history["front"], center, normal,
            self.layout.minimum_aperture_radius-self.layout.trunk_radius_m-cfg["aperture_margin_m"],
            self.layout.ring_tube_radius_m+self.layout.trunk_radius_m)
        reached = (contact_coverage and all(completed) and front_passed and front_clear
                   and maximum <= cfg["maximum_bend_deg"])
        return bool(reached), None, dict(strands_complete=completed, maximum_bend_deg=maximum,
            front_sheath_clear=bool(front_clear), thresholds_calibrated=False,
            episode_contact_coverage_complete=contact_coverage,
            evaluation_status="available" if contact_coverage else "unavailable",
            goal_evaluation_complete=self.goal_complete), dict(strands=next_strands, front=front_history,
                contact_coverage_complete=contact_coverage)
