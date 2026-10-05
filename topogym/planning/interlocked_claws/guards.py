"""Observation-only guards for Claws joint-space action sequences.

Tick-end contact samples and link poses are the only evidence used. The
guards cannot certify the absence of contact between samples or within a
solver substep; the independent audit re-derives the same limits offline.
"""
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.planning.base import ActionSequencePolicy
from topogym.planning.rigid_reference.feedback import body_pose, relative_pose, errors


class ClawsGuardedSequence(ActionSequencePolicy):
    """Both hands must keep their piece; robot links other than the holding fingers stay clear."""

    def __init__(self, actions, *, pieces, hands, forbidden_force_n=.01, piece_force_n=5.,
                 drift_translation_m=.003, drift_rotation_rad=.05, integral_gain=.3, integral_limit_rad=.06,
                 relative_targets=None, kin=None, servo_side=None, wrist_load=None, servo_gain=.5, servo_step_rad=.01,
                 initial_offset=None):
        super().__init__(actions)
        self.servo_gain, self.servo_step_rad = servo_gain, servo_step_rad
        self.servo_last = None
        # Model-based wrist_rotate droop feedforward: the low-gain wrist (kp 10.4) sags by tau/kp under the held
        # piece's gravity moment about the gripper axis. wrist_load = {side: dict(mass_kg, com_in_tcp_m)}; the
        # gain/sign is calibrated from the measured error during the first steps, then applied open-loop
        # (no integration, so contact cannot wind it up).
        self.wrist_load = wrist_load or {}
        self.wrist_calibration = {side: dict(errors=[], torques=[], gain=None) for side in self.wrist_load}
        self.wrist_ff = dict(max_torque_nm=0., max_offset_rad=0., gains={})
        # Optional relative-pose servo: per step, the planned relative pose of the servoed hand's piece is
        # re-targeted onto the measured pose of the other piece and converted to joints by read-only IK, so the
        # pair geometry (what the clearance certificate is about) is closed-loop rather than open-loop.
        self.relative_targets, self.kin, self.servo_side = relative_targets, kin, servo_side
        self.servo = dict(steps=0, ik_failures=0, max_relative_error_m=0., max_relative_error_rad=0.)
        # Integral tracking correction: the position actuators droop under the held load by a few
        # milliradians; the planned joint targets are offset by the accumulated measured error so the
        # executed posture, not just the command, follows the checked plan. Only arm joints are corrected.
        self.integral_gain, self.integral_limit_rad = integral_gain, integral_limit_rad
        self.offset, self.last_command = {}, {}
        # Optional starting value of that correction (side -> arm offset): the droop the held load already
        # causes (actuator target - measured joints). The first planned row is the measured posture, so a zero
        # start drops the hold target onto the sagged posture and both arms sag further in one step.
        for side, offset in (initial_offset or {}).items():
            self.offset[side] = np.clip(np.asarray(offset, float), -integral_limit_rad, integral_limit_rad)
        self.pieces, self.hands = tuple(pieces), dict(hands)   # hands: side -> (hand link name, piece name)
        self.forbidden_force_n, self.piece_force_n = forbidden_force_n, piece_force_n
        self.drift_translation_m, self.drift_rotation_rad = drift_translation_m, drift_rotation_rad
        self.reference = {}
        self.maximum = dict(piece_piece_force_n=0., forbidden_force_n=0., drift_translation_m=0., drift_rotation_rad=0.,
                            tracking_error_rad=0.)

    def act(self, obs):
        world = obs["privileged"]["world"]
        bodies, contacts = world["bodies"], world["contacts"]
        robot_ids = set(bodies["robot"]["link_indices"])
        table_ids = set(bodies["table"]["link_indices"])
        piece_ids = {name: set(bodies[name]["link_indices"]) for name in self.pieces}
        links = world["articulations"]["robot"]["links"]
        order = list(links)
        index_of = dict(zip(order, bodies["robot"]["link_indices"], strict=True))
        finger_ids = {name: {index_of[f"{side}/left_finger_link"], index_of[f"{side}/right_finger_link"]}
                      for side, (_, name) in self.hands.items()}
        base = min(robot_ids)
        a = np.asarray(contacts["link_a"]).reshape(-1)
        b = np.asarray(contacts["link_b"]).reshape(-1)
        force = np.asarray(contacts["force"], float).reshape(-1, 3)
        if not (len(a) == len(b) == len(force)) or not np.isfinite(force).all():
            raise RuntimeError("Missing or invalid contact sample")
        for x, y, f in zip(a, b, force):
            value = float(np.linalg.norm(f))
            pair = {int(x), int(y)}
            if pair & robot_ids and pair & table_ids and not pair & {base}:
                self.maximum["forbidden_force_n"] = max(self.maximum["forbidden_force_n"], value)
                if value > self.forbidden_force_n:
                    raise RuntimeError(f"Robot/table contact: links {x}, {y}; force {value:.4g} N")
            for name, ids in piece_ids.items():
                if pair & ids and pair & robot_ids:
                    if pair & finger_ids.get(name, set()):
                        continue   # the holding fingers legitimately touch their own piece
                    self.maximum["forbidden_force_n"] = max(self.maximum["forbidden_force_n"], value)
                    if value > self.forbidden_force_n:
                        raise RuntimeError(f"Robot/{name} contact outside the holding fingers: links {x}, {y}; force {value:.4g} N")
            if all(pair & ids for ids in piece_ids.values()):
                self.maximum["piece_piece_force_n"] = max(self.maximum["piece_piece_force_n"], value)
                if value > self.piece_force_n:
                    raise RuntimeError(f"Piece/piece contact force {value:.4g} N exceeds {self.piece_force_n} N")
            for name, ids in piece_ids.items():
                if pair & ids and pair & table_ids:
                    if value > self.piece_force_n:
                        raise RuntimeError(f"{name}/table contact force {value:.4g} N")
        if not world["assist_active"]:
            raise RuntimeError("Assisted grasp is not active")
        for side, (hand_link, name) in self.hands.items():
            binding = world["grasp"]["hands"][side]["binding"]
            if binding is None:
                raise RuntimeError(f"{side} hand lost its binding")
            relative = relative_pose(body_pose(links[hand_link]), body_pose(bodies[name]))
            if side not in self.reference:
                self.reference[side] = relative
            translation, angle = errors(relative, self.reference[side])
            self.maximum["drift_translation_m"] = max(self.maximum["drift_translation_m"], translation)
            self.maximum["drift_rotation_rad"] = max(self.maximum["drift_rotation_rad"], angle)
            if translation > self.drift_translation_m or angle > self.drift_rotation_rad:
                raise RuntimeError(f"{side} grasp drift: {translation:.6g} m, {angle:.6g} rad")
        step = self._index
        action = super().act(obs)
        if action is None:
            return action
        if self.relative_targets is not None and self.servo_side in action and "joint_position_rad" in action[self.servo_side] and step < len(self.relative_targets):
            planned = self.relative_targets[step]
            if planned is not None:
                other_hand, other_piece = self.hands[self.servo_side]
                target_piece = next(name for side, (_, name) in self.hands.items() if side != self.servo_side)
                measured_target = body_pose(bodies[target_piece])
                measured_other = body_pose(bodies[other_piece])
                desired = (measured_target[0]+measured_target[1].apply(planned[0]), measured_target[1]*planned[1])
                error = errors(measured_other, desired)
                self.servo["max_relative_error_m"] = max(self.servo["max_relative_error_m"], error[0])
                self.servo["max_relative_error_rad"] = max(self.servo["max_relative_error_rad"], error[1])
                full = np.concatenate([np.asarray(obs["robot"][s]["joint_position_rad"], float) for s in ("left", "right")])
                seed = self.kin.seed.copy(); seed[self.kin.arm_q["left"]] = full[:6]; seed[self.kin.arm_q["right"]] = full[8:14] if full.shape[0] >= 14 else full[6:12]
                try:
                    q = self.kin.solve_arm(self.servo_side, self.kin.tcp_from_piece(self.servo_side, desired), seed)
                    planned_j = np.asarray(action[self.servo_side]["joint_position_rad"], float)
                    # Gentle outer loop: a fraction of the IK correction, rate-limited per step, so contact cannot excite it.
                    target_j = planned_j+self.servo_gain*(q[self.kin.arm_q[self.servo_side]]-planned_j)
                    if self.servo_last is None:
                        self.servo_last = planned_j
                    target_j = self.servo_last+np.clip(target_j-self.servo_last, -self.servo_step_rad, self.servo_step_rad)
                    self.servo_last = target_j
                    action = dict(action); action[self.servo_side] = dict(action[self.servo_side], joint_position_rad=target_j.tolist())
                    self.servo["steps"] += 1
                except ValueError:
                    self.servo["ik_failures"] += 1
        for side, load in self.wrist_load.items():
            if side not in action or "joint_position_rad" not in action[side]:
                continue
            arm = obs["robot"][side]
            rotation = Rotation.from_quat(np.roll(np.asarray(arm["tcp_orientation_wxyz"], float), -1))
            r_com = rotation.apply(np.asarray(load["com_in_tcp_m"], float))
            torque = float(np.cross(r_com, np.array([0., 0., -9.81*load["mass_kg"]]))@rotation.apply([1., 0., 0.]))
            self.wrist_ff["max_torque_nm"] = max(self.wrist_ff["max_torque_nm"], abs(torque))
            cal = self.wrist_calibration[side]
            planned = np.asarray(action[side]["joint_position_rad"], float)
            measured = np.asarray(arm["joint_position_rad"], float)[:len(planned)]
            if cal["gain"] is None:
                if side in self.last_command:
                    cal["errors"].append(float(self.last_command[side][-1]-measured[-1])); cal["torques"].append(torque)
                if len(cal["errors"]) >= 20:
                    t = np.asarray(cal["torques"]); e = np.asarray(cal["errors"])
                    cal["gain"] = float((t@e)/(t@t)) if abs(t@t) > 1e-6 else 0.
                    self.wrist_ff["gains"][side] = cal["gain"]
            else:
                offset = float(np.clip(cal["gain"]*torque, -.25, .25))
                self.wrist_ff["max_offset_rad"] = max(self.wrist_ff["max_offset_rad"], abs(offset))
                command = dict(action[side]); planned = planned.copy(); planned[-1] += offset
                command["joint_position_rad"] = planned.tolist(); action = dict(action); action[side] = command
        if not self.integral_gain:
            for side, command in action.items():
                if "joint_position_rad" in command:
                    self.last_command[side] = np.asarray(command["joint_position_rad"], float)
            return action
        corrected = {}
        for side, command in action.items():
            command = dict(command)
            if "joint_position_rad" in command:
                planned = np.asarray(command["joint_position_rad"], float)
                measured = np.asarray(obs["robot"][side]["joint_position_rad"], float)[:len(planned)]
                if side in self.last_command:
                    error = self.last_command[side]-measured
                    self.maximum["tracking_error_rad"] = max(self.maximum["tracking_error_rad"], float(np.abs(error).max()))
                    offset = self.offset.get(side, np.zeros_like(planned))+self.integral_gain*error
                    self.offset[side] = np.clip(offset, -self.integral_limit_rad, self.integral_limit_rad)
                self.last_command[side] = planned
                command["joint_position_rad"] = (planned+self.offset.get(side, 0.)).tolist()
            corrected[side] = command
        return corrected
