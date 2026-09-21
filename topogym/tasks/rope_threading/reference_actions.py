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
from .reference_ik import (MarginAwareThreadingIK, JOINT_MARGIN_RAD, ROLL_TRANSITION_RAD,
                           free_hand_clearance)


def ending_lift(time_s, start_s, lift_m=.03):
    """Raise the final placement path above the larger shared tabletop."""
    return np.array([0., 0., lift_m*float(smoothstep((time_s-start_s)/12.))])


class ReferenceThreadingActions(RobotGraspActions):
    def __init__(self, reference, *, speed=1., prefix=False, release_limits=None, settle_s=5.,
                 contact_distance_m=.0008):
        super().__init__()
        if not np.isfinite(contact_distance_m) or contact_distance_m <= 0:
            raise ValueError('Contact distance must be finite and positive')
        self.declared_contact_distance = float(contact_distance_m)
        folder = Path(reference)
        with np.load(folder/"reference_motion.npz") as source:
            self.reference = {key: source[key] for key in source.files}
        self.summary = json.loads((folder/"reference_summary.json").read_text())
        self.reference_sha256 = {name: hashlib.sha256((folder/name).read_bytes()).hexdigest()
                                 for name in ("reference_motion.npz", "reference_summary.json")}
        if not np.isfinite(speed) or speed <= 0:
            raise ValueError("Reference speed must be positive")
        self.speed, self.prefix = speed, prefix
        if not np.isfinite(settle_s) or settle_s < 5.:
            raise ValueError("Reference execution requires at least five seconds of final settling")
        self.settle_s = settle_s
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
        self.closure_targets = {}
        self.release_limits, self.release_checks = release_limits, []
        self.material_arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(self.reference["rope_nodes"][0], axis=0), axis=1))]

    def specification(self):
        return dict(kind="reference_pose_ik_with_contact_gated_assisted_grasp",
            prefix_only=self.prefix, source_duration_s=self.cutoff, reference_speed=self.speed,
            minimum_post_release_s=self.settle_s, source_pose_overwrites=False, fem_state_replay=False,
            bands_at_material_nodes=self.material_nodes, band_radius_m=.008, band_strength=100.,
            feedback="measured material-point correction during acquisitions; measured gripper transforms while held",
            grasp_gate="both native finger surfaces within the configured IPC contact distance",
            contact_distance_m=self.declared_contact_distance,
            maximum_wait_for_contact_s=6., grasp_events=self.schedule,
            joint_limit_planning=dict(safety_margin_rad=JOINT_MARGIN_RAD,
                tool_roll_transition_rad=ROLL_TRANSITION_RAD,
                relaxed_dof="local gripper X roll near wrist_rotate limits",
                preserve="hand origin and tool X axis; exact orientation of the modified target",
                actual_joint_limit_checks_unchanged=True),
            empty_hand_clearance=dict(side="left", phases=[40, 49], maximum_z_offset_m=.003,
                reason="avoid gripper-base grazing of R2 during empty-handed approach/withdrawal"),
            release_operating_limits=self.release_limits,
            final_table_clearance_adaptation=dict(side="right", start_phase=49,
                upward_offset_m=.03, ramp_source_seconds=12.,
                reason="reference gripper base descends outside the original table but inside the larger shared table"),
            reference_sha256=self.reference_sha256)

    def configure(self, task, controller, monitor):
        super().configure(task, controller, monitor)
        self.ik = MarginAwareThreadingIK(task, controller)
        if not np.isclose(self.contact_distance, self.declared_contact_distance, rtol=0., atol=1e-12):
            raise ValueError('Declared grasp gate differs from the native contact distance')

    def release(self, side, t, *, open_qpos=None):
        if self.release_limits:
            releasing = [band for band, owner in self.owners.items() if owner == side]
            remaining = [band for band, owner in self.owners.items() if owner != side]
            for band in releasing:
                height = float(self.monitor.last_centers[self.ring_indices[band], 2]
                               -self.monitor.floor-self.task.layout.radius)
                node = self.material_nodes[band]
                spans = [abs(float(self.material_arc[self.material_nodes[other]]-self.material_arc[node]))
                         for other in remaining]
                supported = bool(spans and min(spans) <= self.release_limits["max_supported_material_span_m"])
                passed = height <= self.release_limits["max_unsupported_height_m"] or supported
                self.release_checks.append(dict(time_s=t, owner=side, band=band,
                    height_above_table_m=height, nearby_support= supported,
                    nearest_support_material_span_m=min(spans) if spans else None, passed=passed))
                if not passed:
                    raise RuntimeError("Release exceeds the qualified height without a nearby supporting grasp")
        super().release(side, t, open_qpos=open_qpos)

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

    def _acquire(self, event, t, *, minimum_aperture=.002):
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
            arm.set_gripper(self.closed[side])
            self.adaptation_after_grasp[side] = (self.source_time, self.pending_correction.get(side, np.zeros(3)))
            self.events.append(dict(time_s=t, source_time_s=self.source_time, event="contact_then_assisted_grasp",
                band=band, material_node=event["node"], owner=side, native_finger_gaps_m=gaps))
            self.wait_start = None
            self.closure_targets.pop(side, None)
            return True
        if self.wait_start is None:
            self.wait_start = t
        # Integrate the commanded aperture while the source clock waits for
        # contact. Re-basing every command on the lagging measured aperture
        # made a 4 mm/s closure almost stationary under the position servo.
        target = self.closure_targets.get(side, float(arm.gripper_qpos()[0]))
        target = max(minimum_aperture, target-.004*self.control_dt)
        self.closure_targets[side] = target
        arm.set_gripper(target)
        if t-self.wait_start > 6.:
            raise RuntimeError(f"{side} acquisition of material node {event['node']} did not establish two-sided contact")
        return False

    def release_aperture(self, side, reference_q):
        """Optional task-specific aperture on the support-release frame."""
        return None

    def task_clearance(self, source_time, phase, side):
        return np.zeros(3)

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
        if self.completion_time is not None:
            self.stage = "final_settle"
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
            if side == "right" and phase >= 49:
                correction += ending_lift(self.source_time, self.summary["stages"][49]["start_s"])
            correction += free_hand_clearance(self.source_time, phase, self.summary["stages"], side)
            correction += self.task_clearance(self.source_time, phase, side)
            self.max_adaptation = max(self.max_adaptation, float(np.linalg.norm(correction)))
            if np.linalg.norm(correction) > .15:
                raise RuntimeError("Reference material point departed by more than 150 mm; replan required")
            position = self.task.layout.transform(hands[index, :3])+correction
            target_q = self.ik.solve_reference(side, position, hands[index, 3:], target_q)
            arm.set_arm_qpos(target_q)
            if self.completion_time is not None:
                arm.open_gripper()
            elif pending and event["kind"] == "release" and event["side"] == side:
                aperture = self.release_aperture(side, q)
                if aperture is None:
                    arm.open_gripper()
                else:
                    arm.set_gripper(aperture)
            elif side in self.owners.values():
                arm.set_gripper(self.closed[side])
            else:
                arm.set_gripper(float(np.clip(q[index*8+6], .002, .037)))
        if pending:
            if event["kind"] == "release":
                self.release(event["side"], t, open_qpos=self.release_aperture(event["side"], q))
                self.event_index += 1
            elif self._acquire(event, t):
                self.event_index += 1
        for band, side in self.owners.items():
            arm = self.controller.arms[side]
            self.bands[band]._handle.update_targets(arm.hand_pos()+rotation(arm.hand_quat()).apply(self.offsets[band]))

    def observe(self, t, monitor):
        super().observe(t, monitor)
        # Save centroid following alongside the inherited per-vertex audit.
        # Targets use measured hand transforms; no rope positions are overwritten.
        follow_errors = {}
        for band, side in self.owners.items():
            arm = self.controller.arms[side]
            expected = arm.hand_pos()+rotation(arm.hand_quat()).apply(self.offsets[band])
            actual = monitor.last_positions[self.bands[band].indices]
            error = float(np.linalg.norm(actual.mean(axis=0)-expected.mean(axis=0)))
            follow_errors[str(band)] = error
            self.max_follow_error = max(self.max_follow_error, error)
        self.samples[-1].update(source_time_s=self.source_time,
            grasp_band_center_errors_m=follow_errors,
            crossings=route_crossings(monitor.last_centers, self.task.layout.rings(), self.task.layout.radius))
        if self.max_follow_error > .002:
            raise RuntimeError("Assisted band departed from the measured gripper by more than 2 mm")

    def finished(self, t):
        return self.completion_time is not None and t-self.completion_time >= self.settle_s-1e-8

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
        if self.release_limits:
            checks["release_operating_limits"] = bool(self.release_checks and all(s["passed"] for s in self.release_checks))
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
            ik_joint_safety_margin_rad=self.ik.margin,
            ik_max_reference_roll_relaxation_rad=self.ik.max_reference_roll_relaxation,
            source_time_s=self.source_time, final_material_route=route,
            final_support=supported,
            release_operating_limits=self.release_limits, release_checks=self.release_checks,
            max_material_point_adaptation_m=self.max_adaptation,
            scope="new physical execution of public motion targets; contact-triggered assisted bands, not pure frictional grasps")
        return result
