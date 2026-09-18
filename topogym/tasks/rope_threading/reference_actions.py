"""Reference-guided force-driven ALOHA motion with contact-gated band grasps.

Public poses are controller targets only. FEM states are never replayed into
the solver; assisted targets follow the measured physical gripper transforms.
"""
import json
import hashlib
from pathlib import Path

import numpy as np

from topogym.tasks.knot_untying.robot_probe import RobotGraspActions, rotation
from topogym.tasks.knot_untying.probe_actions import smoothstep
from .geometry import route_crossings


class ReferenceThreadingActions(RobotGraspActions):
    def __init__(self, reference, *, speed=1., prefix=False):
        super().__init__()
        folder = Path(reference)
        with np.load(folder/"reference_motion.npz") as source:
            self.reference = {key: source[key] for key in source.files}
        self.summary = json.loads((folder/"reference_summary.json").read_text())
        self.reference_sha256 = {name: hashlib.sha256((folder/name).read_bytes()).hexdigest()
                                 for name in ("reference_motion.npz", "reference_summary.json")}
        if not np.isfinite(speed) or speed <= 0:
            raise ValueError("Reference speed must be positive")
        self.speed, self.prefix = speed, prefix
        self.material_nodes = [0, 75, 77, 80]
        self.node_to_band = {node: i for i, node in enumerate(self.material_nodes)}
        self.schedule = []
        for event in self.summary["equality_changes"]:
            phase = event["phase"]
            for grasp in self.summary["grasp_material_nodes"]:
                for kind, key in (("acquire", "acquire_phase"), ("release", "release_phase")):
                    if grasp[key] == phase:
                        self.schedule.append(dict(time=event["time_s"], kind=kind, side=grasp["side"], node=grasp["node"]))
        self.schedule.sort(key=lambda event: event["time"])
        if prefix:
            self.schedule = [event for event in self.schedule if event["time"] <= 25.]
        self.source_time, self.last_time, self.event_index = 0., 0., 0
        self.wait_start = self.completion_time = None
        self.cutoff = 25. if prefix else float(self.reference["time"][-1])
        self.max_adaptation = 0.
        self.adaptation_after_grasp = {}
        self.pending_correction = {}

    def specification(self):
        return dict(kind="reference_joint_targets_with_contact_gated_assisted_grasp",
            prefix_only=self.prefix, source_duration_s=self.cutoff, reference_speed=self.speed,
            minimum_post_release_s=5., source_pose_overwrites=False, fem_state_replay=False,
            bands_at_material_nodes=self.material_nodes, band_radius_m=.008, band_strength=100.,
            feedback="measured material-point correction during acquisitions; measured gripper transforms while held",
            grasp_gate="both native finger surfaces within the 0.8 mm IPC contact distance",
            maximum_wait_for_contact_s=6., grasp_events=self.schedule,
            reference_sha256=self.reference_sha256)

    def declare(self, base, rope, centerline, backend):
        from topogym.primitives.fem_attachment import FEMRopeAttachment
        subdivisions = (len(centerline)-1)//80
        self.ring_indices = [node*subdivisions for node in self.material_nodes]
        for index in self.ring_indices:
            self.bands.append(FEMRopeAttachment(rope, centerline[index], radius=.008, strength=100.))

    def _sample(self, time):
        times = self.reference["time"]
        i = min(len(times)-2, max(0, int(np.searchsorted(times, time, side="right"))-1))
        f = float(np.clip((time-times[i])/(times[i+1]-times[i]), 0, 1))
        q = self.reference["qpos"][i]*(1-f)+self.reference["qpos"][i+1]*f
        hands = self.reference["hands"][i].copy()
        hands[:, :3] = hands[:, :3]*(1-f)+self.reference["hands"][i+1, :, :3]*f
        for side in (0, 1):
            a, b = hands[side, 3:], self.reference["hands"][i+1, side, 3:]
            if a@b < 0:
                b = -b
            hands[side, 3:] = a*(1-f)+b*f
            hands[side, 3:] /= np.linalg.norm(hands[side, 3:])
        rope = self.reference["rope_nodes"][i]*(1-f)+self.reference["rope_nodes"][i+1]*f
        phase = int(self.reference["phase"][i])
        return q, hands, rope, phase

    def _acquire(self, event, t):
        side, band = event["side"], self.node_to_band[event["node"]]
        arm = self.controller.arms[side]
        gaps = self.gaps(side, band)
        self.finger_gaps[side] = [gap if np.isfinite(gap) else None for gap in gaps]
        if max(gaps) <= self.contact_distance+1e-6:
            positions = self.monitor.last_positions[self.bands[band].indices]
            self.offsets[band] = rotation(arm.hand_quat()).inv().apply(positions-arm.hand_pos())
            self.bands[band]._handle.engage(positions)
            self.bands[band].active = True
            self.owners[band] = side
            self.closed[side] = float(arm.gripper_qpos()[0])
            self.adaptation_after_grasp[side] = (self.source_time, self.pending_correction.get(side, np.zeros(3)))
            self.events.append(dict(time_s=t, source_time_s=self.source_time, event="contact_then_assisted_grasp",
                band=band, material_node=event["node"], owner=side, native_finger_gaps_m=gaps))
            self.wait_start = None
            return True
        if self.wait_start is None:
            self.wait_start = t
        arm.set_gripper(max(.002, float(arm.gripper_qpos()[0])-.004*self.control_dt))
        if t-self.wait_start > 6.:
            raise RuntimeError(f"{side} acquisition of material node {event['node']} did not establish two-sided contact")
        return False

    def update(self, t):
        self.control_dt = max(0., t-self.last_time)
        self.last_time = t
        desired = min(self.cutoff, self.source_time+self.control_dt*self.speed)
        event = self.schedule[self.event_index] if self.event_index < len(self.schedule) else None
        pending = event is not None and desired >= event["time"]
        self.source_time = event["time"] if pending else desired
        q, hands, reference_rope, phase = self._sample(self.source_time)
        self.stage = f"reference_{phase:02d}"
        if self.source_time >= self.cutoff-1e-8 and self.completion_time is None:
            self.completion_time = t
            if self.prefix:
                for side in ("left", "right"):
                    self.release(side, t)
        acquisition_phases = {1: ("right", 80), 2: ("right", 80), 5: ("left", 0), 6: ("left", 0),
            19: ("left", 77), 20: ("left", 77), 32: ("right", 80), 33: ("right", 80),
            40: ("left", 75), 41: ("left", 75), 45: ("right", 80), 46: ("right", 80)}
        for index, side in enumerate(("left", "right")):
            arm = self.controller.arms[side]
            target_q = q[index*8:index*8+6].copy()
            correction = np.zeros(3)
            acquisition = acquisition_phases.get(phase)
            if acquisition and acquisition[0] == side and side not in self.owners.values() and hasattr(self.monitor, "last_centers"):
                node = acquisition[1]
                actual = self.monitor.last_centers[self.ring_indices[self.node_to_band[node]]]
                expected = self.task.layout.transform(reference_rope[node])
                first_phase = phase if phase in (1, 5, 19, 32, 40, 45) else phase-1
                start = self.summary["stages"][first_phase]["start_s"]
                correction = (actual-expected)*smoothstep((self.source_time-start)/3.)
                self.pending_correction[side] = correction.copy()
            elif side in self.adaptation_after_grasp:
                start, delta = self.adaptation_after_grasp[side]
                correction = delta*(1-smoothstep((self.source_time-start)/5.))
            self.max_adaptation = max(self.max_adaptation, float(np.linalg.norm(correction)))
            if np.linalg.norm(correction) > .15:
                raise RuntimeError("Reference material point departed by more than 150 mm; replan required")
            if np.linalg.norm(correction) > 1e-7:
                position = self.task.layout.transform(hands[index, :3])+correction
                target_q = self.ik.solve(side, position, hands[index, 3:], seed=target_q)
            arm.set_arm_qpos(target_q)
            if self.completion_time is not None or (pending and event["kind"] == "release" and event["side"] == side):
                arm.open_gripper()
            elif side in self.owners.values():
                arm.set_gripper(self.closed[side])
            else:
                arm.set_gripper(float(np.clip(q[index*8+6], .002, .037)))
        if pending:
            if event["kind"] == "release":
                self.release(event["side"], t)
                self.event_index += 1
            elif self._acquire(event, t):
                self.event_index += 1
        for band, side in self.owners.items():
            arm = self.controller.arms[side]
            self.bands[band]._handle.update_targets(arm.hand_pos()+rotation(arm.hand_quat()).apply(self.offsets[band]))

    def observe(self, t, monitor):
        super().observe(t, monitor)
        self.samples[-1].update(source_time_s=self.source_time,
            crossings=route_crossings(monitor.last_centers, self.task.layout.rings(), self.task.layout.radius))

    def finished(self, t):
        return self.completion_time is not None and t-self.completion_time >= 5.-1e-8

    def report(self):
        result = super().report()
        crossings = self.samples[-1].get("crossings", []) if self.samples else []
        route = [hit["ring"]+("+" if hit["sign"] > 0 else "-") for hit in crossings]
        acquired = sum(event["event"] == "contact_then_assisted_grasp" for event in self.events)
        checks = dict(result["checks"])
        checks.pop("two_physical_grasps")
        checks.pop("transfer_observed")
        checks["all_reference_acquisitions"] = acquired == (1 if self.prefix else 6)
        checks["post_release_observed"] = bool(self.samples and self.finished(self.samples[-1]["time_s"]))
        checks["source_sequence_complete"] = self.source_time >= self.cutoff-1e-8
        checks["final_material_route"] = not route if self.prefix else route == ["R1-", "R2+", "R3+"]
        supported = None
        if not self.prefix and hasattr(self, "monitor") and hasattr(self.monitor, "last_centers"):
            ends = self.monitor.last_centers[[0, -1]]
            heights = ends[:, 2]-self.monitor.floor-self.task.layout.radius
            supported = dict(endpoint_clearance_above_table_m=heights.tolist(), tolerance_m=.003)
            checks["both_ends_returned_to_table"] = bool(np.all(heights <= .003) and np.all(heights >= -.00005))
            # A withdrawn hand must be outside the nominal ring aperture.
            from .geometry import surface_intersects_ring_disk
            obstructed = [dict(link=part["name"], ring=ring["name"])
                for part, _ in self.native_robot_parts for ring in self.task.layout.rings()
                if surface_intersects_ring_disk(part["previous"], part["faces"], ring)]
            checks["robot_withdrawn_from_ring_apertures"] = not obstructed
            supported["robot_aperture_intersections"] = obstructed
        elif not self.prefix:
            checks["both_ends_returned_to_table"] = False
            checks["robot_withdrawn_from_ring_apertures"] = False
        result.update(checks=checks, passed=all(checks.values()), prefix_only=self.prefix,
            source_time_s=self.source_time, final_material_route=route,
            final_support=supported,
            max_material_point_adaptation_m=self.max_adaptation,
            scope="new physical execution of public motion targets; contact-triggered assisted bands, not pure frictional grasps")
        return result
