"""Passive JOINT_ABS relay policy replaying checked IK samples with grasp feedback.

Inputs are the relay samples of plan_rope_threading_ik.py: for every sample a
phase name, the moving hand, both TCP poses, the planned joints and the
modelled rope station. The arms follow the planned joints, so the planner's
branch carries through the ViperX wrist singularity (wrist_angle = 0) that a
per-step EE IK from the measured joints drifts away from. Before a hand
pinches, its approach is shifted towards the measured FEM station so the pads
meet the real rope; optional material feedback also rotates the approach about
that station to match the measured tangent. Shifted poses are solved by IK seeded on the planned
joints, and the corrections decay over the first part of the hold. Transit, retreat
and park replay the planned joints unshifted. Grasp
acquisition and release are awaited through the assist state. Only standard
actions are emitted; no simulator write.
"""
import numpy as np
from scipy.spatial.transform import Rotation, Slerp
from .relay_artifact import load_plan


class LiveArmIK:
    """Planned arm joints, and read-only IK seeded on the planned branch for shifted TCP poses."""
    def __init__(self, robot, *, max_branch_step_rad=.25, position_tolerance_m=1e-4,
                 orientation_tolerance_rad=1e-3, max_solver_iterations=400):
        from topogym.solvers.genesis_kinematics import GenesisIKSolver
        self.robot, self.solver, self.max_step = robot, GenesisIKSolver(robot.entity), float(max_branch_step_rad)
        self.position_tolerance, self.orientation_tolerance = position_tolerance_m, orientation_tolerance_rad
        self.iterations = max_solver_iterations

    def planned(self, qpos, side):
        return np.asarray(qpos, float)[self.robot._q_indices[side][:6]]

    def solve(self, side, p, r, qpos):
        g = self.robot.groups[side]
        hand_r = r*Rotation.from_quat(np.asarray(g.tcp_orientation_in_hand_wxyz)[[1, 2, 3, 0]]).inv()
        candidate = self.solver.solve_checked(
            link_name=g.hand_link, position_world_m=p-hand_r.apply(g.tcp_position_in_hand_m),
            orientation_wxyz=hand_r.as_quat()[[3, 0, 1, 2]], joint_dof_indices=self.robot._indices[side][:6],
            initial_qpos=np.asarray(qpos, float), max_solver_iterations=self.iterations,
            position_tolerance_m=self.position_tolerance, orientation_tolerance_rad=self.orientation_tolerance)
        q = candidate[self.robot._q_indices[side][:6]]
        step = float(np.abs(q-self.planned(qpos, side)).max())
        if step > self.max_step:
            raise ValueError(f"Shifted {side} pose left the planned IK branch ({step:.3f} rad)")
        return q


class RopeRelayPolicy:
    def __init__(self, samples, *, kinematics, speed_m_s=.04, control_dt_s=.025, pinch_opening_m=.0123, free_opening_m=.03,
                 acquire_wait_s=3., release_wait_s=1.5, settle_s=5., feedback_decay_m=.10, max_feedback_m=.08,
                 angular_speed_rad_s=.8, joint_speed_rad_s=1., free_speed_m_s=None, material_feedback=False,
                 keeper_planner=None, measured_regrasps=False):
        free_speed_m_s = speed_m_s if free_speed_m_s is None else free_speed_m_s
        if not samples or not all(np.isfinite(v) and v > 0 for v in
                (speed_m_s, control_dt_s, acquire_wait_s, release_wait_s, settle_s, feedback_decay_m,
                 angular_speed_rad_s, joint_speed_rad_s, free_speed_m_s)):
            raise ValueError("Samples must be nonempty and timing/speeds must be finite and positive")
        self.samples, self.kin = [dict(row) for row in samples], kinematics
        self.speed, self.dt = float(speed_m_s), float(control_dt_s)
        self.free_speed = float(free_speed_m_s)
        self.pinch, self.free = float(pinch_opening_m), float(free_opening_m)
        self.acquire_wait = int(round(acquire_wait_s/self.dt))
        self.release_wait = int(round(release_wait_s/self.dt))
        self.settle = int(round(settle_s/self.dt))
        self.decay, self.max_feedback = float(feedback_decay_m), float(max_feedback_m)
        self.index = 0             # next sample to reach
        self.active_index = None
        self.sub, self.substeps = 0, 1
        self.phase = "start"
        self.offset = {"left": np.zeros(3), "right": np.zeros(3)}
        self.rotation_offset = {"left": np.zeros(3), "right": np.zeros(3)}
        self.material_feedback = bool(material_feedback)
        if self.material_feedback and any("station_tangent" not in s for s in samples):
            raise ValueError("Material feedback requires regenerated samples with station_tangent")
        self.offset_origin = {"left": 0., "right": 0.}
        self.waiting = None        # (kind, side, remaining ticks)
        self.targets = {}          # side -> (joints, tcp p, tcp r, opening) currently commanded
        self.expected_holders = set()
        self.angular_speed = float(angular_speed_rad_s)
        self.joint_speed = float(joint_speed_rad_s)
        self.tracking = dict(feedback_m={}, material_feedback_rad={}, acquisitions=[], releases=[], failures=[])
        self.done = False
        self.settle_left = None
        if measured_regrasps and keeper_planner is None:
            raise ValueError("Measured regrasps require a calibration planner")
        self.measured_regrasps = bool(measured_regrasps)
        self.keeper_planner = keeper_planner
        self.keeper_sides = set()
        self.repair = None

    def initialize(self, context):
        if context["action_spec"]["mode"] != "JOINT_ABS":
            raise ValueError("RopeRelayPolicy requires JOINT_ABS")

    # ----- measurement helpers -------------------------------------------
    @staticmethod
    def _station_position(world, station_m, half_width=.003):
        rope = world["fem"]["rope"]
        s = np.asarray(rope["material_s_m"], float).reshape(-1)
        x = np.asarray(rope["position_m"], float).reshape(-1, 3)
        mask = np.abs(s-station_m) <= half_width
        if not mask.any():
            mask = np.argsort(np.abs(s-station_m))[:24]
        return x[mask].mean(axis=0)

    @staticmethod
    def _binding(world, side):
        return world["grasp"]["hands"][side]["binding"]

    @staticmethod
    def _holding(world, side):
        state = world["grasp"]["hands"][side]
        binding = state["binding"]
        return (state["phase"] == "holding" and state.get("solved_ticks", 0) > 0
                and binding is not None and binding.get("target", [None])[0] == "rope")

    def _pose(self, sample, side):
        row = sample["tcp_"+side]
        return np.asarray(row[:3], float), Rotation.from_quat(np.asarray(row[3:7])[[1, 2, 3, 0]]), float(row[7])

    def _joints(self, sample, side, p, r):
        planned_p, planned_r, _ = self._pose(sample, side)
        if np.linalg.norm(p-planned_p) < 1e-10 and (r*planned_r.inv()).magnitude() < 1e-10:
            return self.kin.planned(sample["qpos"], side)
        try:
            return self.kin.solve(side, p, r, sample["qpos"])
        except ValueError as error:
            self.tracking["failures"].append(dict(kind="feedback_ik", side=side, index=self.index,
                phase=self.phase, translation_m=float(np.linalg.norm(p-planned_p)),
                rotation_rad=float((r*planned_r.inv()).magnitude()), error=str(error)))
            raise

    def _feedback_pose(self, sample, side, scale):
        p, r, _ = self._pose(sample, side)
        if not scale:
            return p, r
        correction = Rotation.from_rotvec(scale*self.rotation_offset[side])
        station = np.asarray(sample["station"][:3])
        # Rotate the approach about its material station, preserving the pad
        # offset and approach distance, then translate to the measured rope.
        return station+scale*self.offset[side]-correction.apply(station-p), correction*r

    def _action(self):
        return {side: dict(joint_position_rad=q.tolist(), gripper_position_m=opening)
                for side, (q, _, _, opening) in self.targets.items()}

    def _repair_action(self):
        """Execute checked measured-keeper waypoints with ordinary joint actions."""
        repair = self.repair
        side, row = repair["side"], repair["rows"][repair["index"]]
        self.phase = row["phase"]
        if self.phase.startswith("pinch:"):
            q, p, r, _ = self.targets[side]
            self.targets[side] = (q, p, r, self.pinch)
            self.waiting = ("acquire", side, self.acquire_wait)
            self.keeper_sides.add(side)
            repair["index"] += 1
            if repair["index"] == len(repair["rows"]):
                self.index, self.repair, self.sub = repair["resume"], None, 0
            return self._action()
        if repair["sub"] == 0:
            start = self.targets[side]
            tcp = np.asarray(row["tcp"])
            end = (self.kin.planned(row["q"], side), tcp[:3],
                   Rotation.from_quat(tcp[3:7][[1, 2, 3, 0]]))
            speed = self.speed if self.phase.startswith(("approach:", "hold:")) else self.free_speed
            repair.update(start=start, end=end, steps=max(1,
                int(np.ceil(np.linalg.norm(end[1]-start[1])/(speed*self.dt))),
                int(np.ceil((end[2]*start[2].inv()).magnitude()/(self.angular_speed*self.dt))),
                int(np.ceil(np.abs(end[0]-start[0]).max()/(self.joint_speed*self.dt)))))
        a, b = repair["start"], repair["end"]
        u = (repair["sub"]+1)/repair["steps"]
        self.targets[side] = (a[0]+u*(b[0]-a[0]), a[1]+u*(b[1]-a[1]),
            Slerp([0., 1.], Rotation.concatenate([a[2], b[2]]))(u),
            self.pinch if self.phase.startswith("hold:") else self.free)
        repair["sub"] += 1
        if repair["sub"] >= repair["steps"]:
            repair["sub"] = 0
            repair["index"] += 1
            if repair["index"] == len(repair["rows"]):
                self.index, self.repair, self.sub = repair["resume"], None, 0
        return self._action()

    def _start_keeper_repair(self, obs, *, retreat=False):
        sample = self.samples[self.index]
        side = str(sample["side"])
        end = self.index
        normalize_target = None
        follow_targets = []
        if retreat:
            while end < len(self.samples) and str(self.samples[end]["side"]) == side and str(self.samples[end]["phase"]).split(":")[0] in {"retreat", "park"}:
                end += 1
        else:
            while end < len(self.samples) and not str(self.samples[end]["phase"]).startswith("pinch:"):
                end += 1
            if end == len(self.samples):
                raise ValueError("Keeper has no acquisition sample")
            normalize_target = self.samples[end]
            end += 1
            # Stationary helper holds have no material travel to replay.
            while end < len(self.samples) and str(self.samples[end]["phase"]).startswith("hold:") and str(self.samples[end]["phase"]).endswith("_keeper"):
                end += 1
            for index in range(end, len(self.samples)):
                row = self.samples[index]
                if str(row["side"]) != side:
                    continue
                if not str(row["phase"]).startswith("hold:"):
                    break
                follow_targets.append(dict(row, index=index))
        try:
            result = self.keeper_planner(obs, sample, self.targets,
                retreat_target=self.samples[end-1] if retreat else None, normalize_target=normalize_target,
                follow_targets=follow_targets)
        except Exception as error:
            self.tracking["failures"].append(dict(kind="calibration", side=side, index=self.index,
                retreat=retreat, error=f"{type(error).__name__}: {error}"))
            raise
        self.tracking.setdefault("keeper_repairs", []).append(dict(index=self.index, resume=end,
            retreat=retreat, **{k: v for k, v in result.items()
                             if k not in {"rows", "checks", "failures", "follow_rows", "follow_checks"}}))
        if not result["passed"]:
            raise ValueError("No collision-checked measured keeper path; see calibration evidence")
        overrides = result.get("follow_rows", [])
        if overrides:
            if [row["index"] for row in overrides] != [row["index"] for row in follow_targets]:
                raise ValueError("Calibration must replan the complete upcoming hold")
            for row in overrides:
                qpos = np.asarray(row["qpos"], float)
                if qpos.shape != (16,) or not np.isfinite(qpos).all():
                    raise ValueError("Invalid replanned hold joint target")
                index = row["index"]
                self.samples[index] = dict(self.samples[index], qpos=qpos)
        self.repair = dict(side=side, rows=result["rows"], resume=end, index=0, sub=0)
        if retreat:
            self.keeper_sides.discard(side)
        self.offset[side] = np.zeros(3)
        self.rotation_offset[side] = np.zeros(3)
        return self._repair_action()

    # ----- main -----------------------------------------------------------
    def act(self, obs):
        if self.done:
            return None
        world = obs["privileged"]["world"]
        for side in self.expected_holders:
            if not self._holding(world, side):
                self.tracking["failures"].append(dict(kind="lost", side=side, index=self.index,
                    phase=self.phase, rejection=world["grasp"]["hands"][side].get("rejection"),
                    health=dict(world["grasp"].get("health", {}).get(side, {}))))
                raise RuntimeError(f"Rope grasp lost for {side} in {self.phase}")
        if not self.targets:
            for side in ("left", "right"):
                arm = obs["robot"][side]
                self.targets[side] = (np.asarray(arm["joint_position_rad"], float),
                                      np.asarray(arm["tcp_position_world_m"], float),
                                      Rotation.from_quat(np.asarray(arm["tcp_orientation_wxyz"])[[1, 2, 3, 0]]), self.free)
        if self.settle_left is not None:
            self.settle_left -= 1
            if self.settle_left <= 0:
                self.done = True
                return None
            return self._action()
        if self.waiting is not None:
            kind, side, remaining = self.waiting
            binding = self._binding(world, side)
            if (kind == "acquire" and self._holding(world, side)) or (kind == "release" and binding is None):
                self.tracking["acquisitions" if kind == "acquire" else "releases"].append(dict(side=side, index=self.index))
                if kind == "acquire":
                    self.expected_holders.add(side)
                self.waiting = None
            elif remaining <= 0:
                self.tracking["failures"].append(dict(kind=kind, side=side, index=self.index))
                raise RuntimeError(f"grasp assist did not {kind} for {side}")
            else:
                self.waiting = (kind, side, remaining-1)
                return self._action()
        if self.repair is not None:
            return self._repair_action()
        if self.index >= len(self.samples):
            self.settle_left = self.settle
            return self._action()
        sample = self.samples[self.index]
        self.active_index = self.index
        phase, side = str(sample["phase"]), str(sample["side"])
        kind = phase.split("/")[0].split(":")[0]
        if self.keeper_planner is not None and self.sub == 0:
            if kind == "transit" and (phase.split("/")[0].endswith("_keeper")
                    or (self.measured_regrasps and self.expected_holders and side not in self.expected_holders
                        and not phase.split("/")[0].endswith(":R1") and np.isfinite(sample["station"]).all())):
                return self._start_keeper_repair(obs)
            if kind == "retreat" and side in self.keeper_sides and side not in self.expected_holders:
                return self._start_keeper_repair(obs, retreat=True)
        # Task success permits retaining the final grasp. The planning artifact
        # also audits release/park, but dropping the rope is not a task goal.
        # Hold the last commanded pose for the native quiet/stability window.
        if (kind == "retreat" and self.index > 0 and self.expected_holders
                and str(self.samples[self.index-1]["phase"]).startswith("hold:")
                and not any(str(s["phase"]).startswith("hold:") for s in self.samples[self.index:])):
            self.phase, self.settle_left = "settle:held", self.settle
            self.active_index = self.index-1
            return self._action()
        if self.sub == 0:
            # Entering a new sample: decide feedback and gripper events.
            self.phase = phase
            if side:
                if kind in ("transit", "approach") and np.isfinite(sample["station"]).all():
                    measured = self._station_position(world, float(sample["station"][3]))
                    delta = measured-np.asarray(sample["station"][:3])
                    norm = float(np.linalg.norm(delta))
                    if norm > self.max_feedback:
                        self.tracking["failures"].append(dict(kind="station_out_of_range", side=side,
                            index=self.index, error_m=norm, limit_m=self.max_feedback))
                        raise ValueError(f"Measured {side} rope station is {norm:.3f} m from the plan "
                                         f"(feedback limit {self.max_feedback:.3f} m)")
                    self.offset[side] = delta
                    self.offset_origin[side] = float(sample["sigma"])
                    self.tracking["feedback_m"][side] = norm
                    if self.material_feedback:
                        material = float(sample["station"][3])
                        limits = np.asarray(world["fem"]["rope"]["material_s_m"])
                        actual_t = (self._station_position(world, min(material+.01, limits.max()))
                                    -self._station_position(world, max(material-.01, limits.min())))
                        length = np.linalg.norm(actual_t)
                        if length < 1e-5:
                            raise ValueError("Measured rope tangent is degenerate")
                        actual_t /= length
                        planned_t = np.asarray(sample["station_tangent"])
                        cross = np.cross(planned_t, actual_t)
                        angle = float(np.arccos(np.clip(np.dot(planned_t, actual_t), -1., 1.)))
                        if angle > .8:
                            raise ValueError(f"Measured material direction differs by {angle:.3f} rad (limit .8)")
                        self.rotation_offset[side] = cross*(angle/max(np.linalg.norm(cross), 1e-12))
                        self.tracking["material_feedback_rad"][side] = angle
                if kind == "pinch":
                    p, r = self._feedback_pose(sample, side, 1.)
                    self.targets[side] = (self._joints(sample, side, p, r), p, r, self.pinch)
                    self.waiting = ("acquire", side, self.acquire_wait)
                    self.index += 1
                    return self._action()
                if kind == "retreat" and side in self.expected_holders:
                    q, p, r, _ = self.targets[side]
                    opening = self._pose(sample, side)[2]
                    self.targets[side] = (q, p, r, opening)
                    self.waiting = ("release", side, self.release_wait)
                    self.expected_holders.discard(side)
                    return self._action()
            self.segment_start = self.targets[side] if side else None
            p, r, _ = self._pose(sample, side) if side else (None, None, None)
            # Free-space motion (transit, retreat, park) replays the planned joints unchanged; the measured-rope
            # shift applies only while the pads close in on the rope, away from the home-side wrist singularity.
            scale = (max(0., 1.-(float(sample["sigma"])-self.offset_origin[side])/self.decay)
                     if side and kind == "hold" else 1. if kind == "approach" else 0.)
            if side:
                p, r = self._feedback_pose(sample, side, scale)
            self.segment_end = (self._joints(sample, side, p, r), p, r) if side else None
            distance = 0. if not side else float(np.linalg.norm(self.segment_end[1]-self.segment_start[1]))
            angle = 0. if not side else float((r*self.segment_start[2].inv()).magnitude())
            joint_span = 0. if not side else float(np.max(np.abs(self.segment_end[0]-self.segment_start[0])))
            speed = self.free_speed if kind in {"transit", "retreat", "park"} else self.speed
            self.substeps = max(1, int(np.ceil(distance/(speed*self.dt))),
                               int(np.ceil(angle/(self.angular_speed*self.dt))),
                               int(np.ceil(joint_span/(self.joint_speed*self.dt))))
        if side:
            q, p, r = self.segment_end
            start_q, start_p, start_r, _ = self.segment_start
            u = (self.sub+1)/self.substeps
            target_p = start_p+u*(p-start_p)
            target_r = Slerp([0., 1.], Rotation.concatenate([start_r, r]))(u)
            current = self.pinch if kind == "hold" else self._pose(sample, side)[2]
            self.targets[side] = (start_q+u*(q-start_q), target_p, target_r, current)
        self.sub += 1
        if self.sub >= self.substeps:
            self.sub = 0
            self.index += 1
        return self._action()


def load_samples(path):
    return load_plan(path)[0]
