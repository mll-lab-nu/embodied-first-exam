"""Reference execution with an observed, contact-gated R2 handoff replacement."""
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from .feedback_ik_plan import GRASP_OFFSET, JOIN_SOURCE_S
from .feedback_paths import ARM, MeasuredHandoffPlanner
from .geometry import route_crossings
from .reference_actions import ReferenceThreadingActions
from .robot_mesh_guard import MeasuredRobotMeshGuard


class FeedbackThreadingActions(ReferenceThreadingActions):
    trigger_source_s = 195.

    def __init__(self, *args, cfg, output, **kwargs):
        super().__init__(*args, **kwargs)
        if self.prefix:
            raise ValueError("The R2 replacement requires a complete reference sequence")
        self.feedback_cfg = cfg
        self.feedback_output = Path(output)/"feedback_handoff"
        self.feedback_log = []
        self.local_stage = None
        self.local_path = None
        self.handoff_done = False
        self.first_handoff_done = False
        self.first_join_source_s = float(self.summary["stages"][27]["start_s"])
        self.path_counter = self.approach_retries = self.unpinch_retries = 0
        self.selected_angle = 28.

    def specification(self):
        result = super().specification()
        result["feedback_handoff"] = dict(trigger_source_s=self.trigger_source_s,
            resume_source_s=JOIN_SOURCE_S, left_pivot_deg=6.,
            source_clock_paused_during_replacement=True,
            observations=["before pivot", "after pivot", "after transit", "before closing", "after capture before carry"],
            closure_minimum_qpos_m=.010, native_contact_gate_unchanged=True,
            left_release_requires_confirmed_right_attachment=True,
            narrow_left_unpinch_step_m=.0003, maximum_unpinch_steps=3,
            after_handoff_release_aperture="follow reference fingers; fully open after final withdrawal",
            planner="measured-state bounded IK and 5 ms fixture/self-collision screening",
            fem_state_replay=False)
        result["first_handoff"] = dict(trigger="before right node-80 release in phase 24",
            hold_left="measured joint pose during narrow release and immediate right withdrawal",
            right_withdrawal_m=.08, resume_source_s=self.first_join_source_s,
            reason="avoid observed triangle-mesh finger intersection while left settles after right release")
        result["additional_robot_geometry_audit"] = "measured-joint collision triangles every control frame"
        result["early_left_clearance"] = dict(maximum_positive_x_m=.01, source_center_s=41.2,
                                              source_halfwidth_s=3., zero_at_capture=True)
        return result

    def release_aperture(self, side, reference_q):
        if self.handoff_done:
            # The source opens gradually while leaving R3. A one-frame .037 m
            # impulse is not part of the screened reference finger trajectory.
            return float(np.clip(reference_q[6 if side == "left" else 14], .002, .037))
        return None

    def task_clearance(self, source_time, phase, side):
        if side == "left" and phase in (5, 6):
            u = (source_time-41.2)/3.
            return self.ik.mount_rotation.apply([.01*max(0., 1.-u*u)**3, 0., 0.])
        return np.zeros(3)

    def configure(self, task, controller, monitor):
        super().configure(task, controller, monitor)
        self.planner = MeasuredHandoffPlanner(self.feedback_cfg, self._qpos())
        self.robot_mesh_guard = MeasuredRobotMeshGuard(self.planner.model)

    def _qpos(self):
        return np.concatenate([np.r_[self.controller.arms[side].arm_qpos(),
                                     self.controller.arms[side].gripper_qpos()]
                               for side in ("left", "right")])

    def _model_point(self, world):
        return self.ik.mount_rotation.inv().apply(np.asarray(world)-self.ik.mount_position)

    def _snapshot(self):
        centers = self._model_point(self.monitor.last_centers)
        subdivisions = (len(centers)-1)//80
        tangent = centers[-1]-centers[-1-subdivisions]
        tangent /= np.linalg.norm(tangent)
        snapshot = dict(qpos=self._qpos().tolist(), anchor=centers[77*subdivisions].tolist(),
                        tip=centers[-1].tolist(), tangent=tangent.tolist(),
                        source_time_s=self.source_time,
                        input_kind="current physical robot and FEM material centers; not predicted")
        return snapshot

    def _record(self, event, t, **fields):
        self.feedback_log.append(dict(event=event, physics_time_s=float(t),
                                      source_time_s=self.source_time, **fields))
        self.feedback_output.mkdir(parents=True, exist_ok=True)
        path = self.feedback_output/"events.json"
        temporary = path.with_suffix(".tmp.json")
        temporary.write_text(json.dumps(self.feedback_log, indent=2)+"\n")
        temporary.replace(path)

    def _begin_path(self, stage, path, t, snapshot):
        if not path.audit or not path.audit["passed"]:
            raise ValueError("Refusing an unscreened local robot path")
        self.path_counter += 1
        directory = self.feedback_output/f"{self.path_counter:03d}_{stage}"
        directory.mkdir(parents=True, exist_ok=False)
        np.savez_compressed(directory/"path.npz", time_s=path.time, qpos=path.qpos, stage=path.stage)
        (directory/"audit.json").write_text(json.dumps(path.audit, indent=2)+"\n")
        (directory/"observation.json").write_text(json.dumps(snapshot, indent=2)+"\n")
        self.local_stage, self.local_path, self.local_start = stage, path, t
        self._record("screened_path_started", t, stage=stage, directory=str(directory), audit=path.audit)

    def _command(self, q):
        for index, side in enumerate(("left", "right")):
            arm = self.controller.arms[side]
            arm.set_arm_qpos(q[index*8:index*8+6])
            aperture = self.closed[side] if side in self.owners.values() else float(q[index*8+6])
            arm.set_gripper(aperture)

    def _settled(self, q):
        if np.max(np.abs(self._qpos()[ARM]-q[ARM])) > .01:
            return False
        for i, side in enumerate(("left", "right")):
            target_p, target_r = self.planner.ik.pose(side, q[i*8:i*8+6])
            arm = self.controller.arms[side]
            actual_r = self.ik.mount_rotation.inv()*Rotation.from_quat(arm.hand_quat(), scalar_first=True)
            if (np.linalg.norm(self._model_point(arm.hand_pos())-target_p) > .0005
                    or (target_r.inv()*actual_r).magnitude() > .004):
                return False
        return True

    def _expect_event(self, kind, side, node):
        event = self.schedule[self.event_index]
        if (event["kind"], event["side"], event["node"]) != (kind, side, node):
            raise RuntimeError(f"Handoff event sequence mismatch: {event}")
        return event

    def _follow_bands(self):
        for band, side in self.owners.items():
            arm = self.controller.arms[side]
            orientation = Rotation.from_quat(arm.hand_quat(), scalar_first=True)
            self.bands[band]._handle.update_targets(arm.hand_pos()+orientation.apply(self.offsets[band]))

    def _join_qpos(self, source_time):
        q, hands, _, _ = self._sample(source_time)
        for i, side in enumerate(("left", "right")):
            indices = slice(i*8, i*8+6)
            q[indices] = self.ik.solve_reference(side, self.task.layout.transform(hands[i, :3]),
                                                hands[i, 3:], q[indices])
        return q

    def _next_stage(self, t):
        snapshot = self._snapshot()
        q, tip, tangent = [np.asarray(snapshot[key]) for key in ("qpos", "tip", "tangent")]
        if self.local_stage == "first_unpinch":
            gaps = self.gaps("right", self.node_to_band[80])
            if max(gaps) <= self.contact_distance+1e-6:
                self.unpinch_retries += 1
                if self.unpinch_retries >= 3:
                    raise RuntimeError("Right fingers remain in bilateral contact after first narrow release")
                self._begin_path("first_unpinch", self.planner.unpinch(q, side="right"), t, snapshot)
            else:
                self._begin_path("first_withdraw", self.planner.withdraw(q, side="right", distance=.08), t, snapshot)
        elif self.local_stage == "first_withdraw":
            join = self._join_qpos(self.first_join_source_s)
            self._begin_path("first_left_join", self.planner.join_arm(q, join, "left"), t, snapshot)
        elif self.local_stage == "first_left_join":
            join = self._join_qpos(self.first_join_source_s)
            self._begin_path("first_right_join", self.planner.join_arm(q, join, "right", match_fingers=True), t, snapshot)
        elif self.local_stage == "first_right_join":
            route = [hit["ring"]+("+" if hit["sign"] > 0 else "-") for hit in
                     route_crossings(self.monitor.last_centers, self.task.layout.rings(), self.task.layout.radius)]
            if route != ["R1-"]:
                raise RuntimeError(f"Actual rope route after first handoff is {route}; cannot resume")
            self.source_time = self.first_join_source_s
            self.adaptation_after_grasp.clear()
            self.pending_correction.clear()
            self.local_stage = self.local_path = None
            self.first_handoff_done = True
            self.unpinch_retries = 0
            self._record("first_handoff_complete_reference_resumed", t, actual_route=route, observation=snapshot)
        elif self.local_stage == "pivot":
            path, self.selected_angle = self.planner.approach(q, tip, tangent, transit=True)
            self._begin_path("transit", path, t, snapshot)
        elif self.local_stage == "transit":
            path, self.selected_angle = self.planner.approach(q, tip, tangent, transit=False,
                                                            preferred_angle=self.selected_angle)
            self._begin_path("approach", path, t, snapshot)
        elif self.local_stage == "approach":
            arm = self.controller.right
            actual_r = self.ik.mount_rotation.inv()*Rotation.from_quat(arm.hand_quat(), scalar_first=True)
            center = self._model_point(arm.hand_pos())+actual_r.apply(GRASP_OFFSET)
            miss = float(np.linalg.norm(center-tip))
            self._record("preclosure_tip_observed", t, tip_alignment_error_m=miss, observation=snapshot)
            if miss > .001:
                self.approach_retries += 1
                if self.approach_retries > 3:
                    raise RuntimeError("Measured free tip did not stabilize within the grasp target; replan required")
                path, self.selected_angle = self.planner.approach(q, tip, tangent, transit=False,
                                                                preferred_angle=self.selected_angle)
                self._begin_path("approach", path, t, snapshot)
                return
            event = self._expect_event("acquire", "right", 80)
            self.source_time = event["time"]
            self.pending_correction["right"] = np.zeros(3)
            self.wait_start = None
            self.closure_targets.pop("right", None)
            self.local_stage, self.local_path, self.local_start = "close", None, t
            self.hold_qpos = q.copy()
        elif self.local_stage == "unpinch":
            gaps = self.gaps("left", self.node_to_band[77])
            self._record("left_unpinch_observed", t,
                         gaps_m=[float(v) if np.isfinite(v) else None for v in gaps])
            # A one-sided resting contact is allowed; bilateral squeezing is not.
            if max(gaps) <= self.contact_distance+1e-6:
                self.unpinch_retries += 1
                if self.unpinch_retries >= 3:
                    raise RuntimeError("Left fingers remain in bilateral contact after narrow unpinching")
                self._begin_path("unpinch", self.planner.unpinch(q), t, snapshot)
            else:
                self._begin_path("withdraw", self.planner.withdraw(q), t, snapshot)
        elif self.local_stage == "withdraw":
            join = self._sample(JOIN_SOURCE_S)[0]
            self._begin_path("return_left", self.planner.return_left(q, join), t, snapshot)
        elif self.local_stage == "return_left":
            if self.owners != {self.node_to_band[80]: "right"}:
                raise RuntimeError("Right must retain the only active grasp before carrying to R3")
            join = self._sample(JOIN_SOURCE_S)[0]
            self._begin_path("carry", self.planner.carry(q, tip, join), t, snapshot)
        elif self.local_stage == "carry":
            route = [hit["ring"]+("+" if hit["sign"] > 0 else "-") for hit in
                     route_crossings(self.monitor.last_centers, self.task.layout.rings(), self.task.layout.radius)]
            if route != ["R1-", "R2+"]:
                raise RuntimeError(f"Actual rope route before R3 is {route}; cannot blindly resume reference")
            self.source_time = JOIN_SOURCE_S
            self.adaptation_after_grasp.clear()
            self.pending_correction.clear()
            self.local_stage = self.local_path = None
            self.handoff_done = True
            self._record("handoff_complete_reference_resumed", t, actual_route=route,
                         next_event_index=self.event_index, observation=snapshot)

    def update(self, t):
        dt = max(0., t-self.last_time)
        if self.local_stage is None and not self.first_handoff_done and self.event_index == 4:
            event = self._expect_event("release", "right", 80)
            if self.source_time+dt*self.speed >= event["time"]:
                if self.owners != {self.node_to_band[77]: "left", self.node_to_band[80]: "right"}:
                    raise RuntimeError("First handoff release requires both confirmed attachments")
                snapshot = self._snapshot()
                q = np.asarray(snapshot["qpos"])
                path = self.planner.unpinch(q, side="right")
                # Freeze the LEFT measured pose before right release, rather
                # than letting a previously lagging left target sweep into it.
                self._command(q)
                self.source_time = event["time"]
                self.release("right", t, open_qpos=float(q[14]))
                self.event_index += 1
                self._record("first_right_release_left_measured_pose_held", t, observation=snapshot)
                self._begin_path("first_unpinch", path, t, snapshot)
        if self.local_stage is None and not self.handoff_done and self.source_time+dt*self.speed >= self.trigger_source_s:
            if self.owners != {self.node_to_band[77]: "left"}:
                raise RuntimeError("R2 handoff requires left node-77 support and an empty right hand")
            self._expect_event("acquire", "right", 80)
            snapshot = self._snapshot()
            self._record("handoff_triggered", t, observation=snapshot)
            path = self.planner.pivot(np.asarray(snapshot["qpos"]), np.asarray(snapshot["anchor"]))
            self._begin_path("pivot", path, t, snapshot)
        if self.local_stage is None:
            super().update(t)
            return
        self.control_dt, self.last_time = dt, t
        self.stage = "feedback_"+self.local_stage
        if self.local_path is not None:
            elapsed = t-self.local_start
            q = self.local_path.sample(elapsed)
            self._command(q)
            if elapsed >= self.local_path.time[-1]:
                if self._settled(q):
                    self._record("path_endpoint_observed", t, stage=self.local_stage,
                                 endpoint_wait_s=elapsed-float(self.local_path.time[-1]))
                    self._next_stage(t)
                elif elapsed > self.local_path.time[-1]+3.:
                    raise RuntimeError(f"Robot did not settle at {self.local_stage} endpoint")
        elif self.local_stage == "close":
            self._command(self.hold_qpos)
            event = self._expect_event("acquire", "right", 80)
            if self._acquire(event, t, minimum_aperture=.010):
                self.event_index += 1
                self.local_stage, self.local_start = "dual_hold", t
                self.hold_qpos = self._qpos()
                self._record("right_native_contact_and_attachment_confirmed", t, observation=self._snapshot())
        elif self.local_stage == "dual_hold":
            self._command(self.hold_qpos)
            if t-self.local_start >= .5:
                if self.owners != {self.node_to_band[77]: "left", self.node_to_band[80]: "right"}:
                    raise RuntimeError("Both measured grasps are required before left release")
                snapshot = self._snapshot()
                q = np.asarray(snapshot["qpos"])
                path = self.planner.unpinch(q)  # Screen BEFORE releasing support.
                event = self._expect_event("release", "left", 77)
                self.source_time = event["time"]
                self.release("left", t, open_qpos=float(q[6]))
                self.event_index += 1
                self._record("left_support_released_after_right_confirmation", t)
                self._begin_path("unpinch", path, t, snapshot)
        self._follow_bands()

    def report(self):
        result = super().report()
        result["feedback_handoff"] = dict(completed=self.handoff_done, stage=self.local_stage,
            paths_planned=self.path_counter, events=self.feedback_log,
            source_clock_paused_during_local_motion=True, actual_observations_used=True)
        result["checks"]["measured_R2_handoff_completed"] = self.handoff_done
        result["checks"]["first_release_and_withdrawal_completed"] = self.first_handoff_done
        guard = getattr(self, "robot_mesh_guard", None)
        result["measured_robot_mesh_audit"] = guard.report() if guard else None
        result["checks"]["measured_robot_meshes_clear"] = bool(guard and guard.frames and not guard.failures)
        result["passed"] = all(result["checks"].values())
        return result

    def observe(self, t, monitor):
        super().observe(t, monitor)
        try:
            self.robot_mesh_guard.check(self._qpos(), t)
        except RuntimeError:
            self._record("measured_robot_geometry_rejected", t, audit=self.robot_mesh_guard.report(),
                         observation=self._snapshot())
            raise
        finally:
            self.samples[-1]["robot_mesh_audit"] = self.robot_mesh_guard.report()
