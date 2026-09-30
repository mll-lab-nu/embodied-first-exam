"""TopoGym observations and actions <-> standard vectors, driven by the episode's action_spec.

Per arm, in ``action_spec["arms"]`` order (ALOHA: left, right):
  joint / joint_abs: [q_1 .. q_n, opening]                   rad
  ee / ee_abs:       [x, y, z, r_1 .. r_6, opening]          TopoGym world frame, m
r_1..r_6 are the first two rotation-matrix columns, [R11, R21, R31, R12, R22, R32]. Opening is in [0, 1],
1 = fully open. Joints and openings are clipped before stepping; EE poses are not (IK failure is an
invalid action).
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation

from vla.protocol import Observation

# Native gripper coordinates (fully open, fully closed), as in docs/vla_doc/vla_eval_demo.py.
GRIPPER_OPEN_CLOSED = {"aloha": (0.037, 0.002), "panda_robotiq": (0.0, 0.8)}


def rot6d(wxyz):
    matrix = Rotation.from_quat(np.asarray(wxyz)[[1, 2, 3, 0]]).as_matrix()
    return np.r_[matrix[:, 0], matrix[:, 1]]


def rot6d_to_wxyz(r):
    """Gram-Schmidt on the two columns, then a unit quaternion (w, x, y, z)."""
    a = r[:3] / np.linalg.norm(r[:3])
    b = r[3:] - (a @ r[3:]) * a
    b = b / np.linalg.norm(b)
    return Rotation.from_matrix(np.stack([a, b, np.cross(a, b)], axis=1)).as_quat()[[3, 0, 1, 2]]


class Adapter:
    def __init__(self, action_spec, spec):
        if action_spec["robot_id"] != spec.embodiment:
            raise ValueError(f"Policy {spec.name} expects {spec.embodiment}, the task uses {action_spec['robot_id']}")
        self.spec = spec
        self.arms = tuple(action_spec["arms"])
        self.groups = action_spec["groups"]
        self.open, self.closed = GRIPPER_OPEN_CLOSED[spec.embodiment]
        self.pose_sizes = [len(self.groups[arm]["arm_joint_names"]) if spec.action_space == "joint_abs" else 9
                           for arm in self.arms]
        self.action_dim = sum(self.pose_sizes) + len(self.arms)
        self.openings = np.cumsum([size + 1 for size in self.pose_sizes]) - 1  # opening index of each arm
        self.clipped = 0  # action rows changed by clipping

    def observation(self, rgb, robot, instruction, episode_id, step):
        images = {camera: rgb[camera] for camera in self.spec.cameras}
        state = {key: self.state(key, robot) for key in self.spec.state_keys}
        return Observation(images, state, instruction, episode_id, step)

    def state(self, key, robot):
        parts = []
        for arm in self.arms:
            measured = robot[arm]
            if key == "joint":
                parts.append(measured["joint_position_rad"])
            else:
                parts += [measured["tcp_position_world_m"], rot6d(measured["tcp_orientation_wxyz"])]
            fingers = next(value for name, value in measured.items() if name.startswith("finger_position_"))
            parts.append([np.clip((fingers[0] - self.closed) / (self.open - self.closed), 0.0, 1.0)])
        return np.concatenate(parts).astype(np.float32)

    def reached(self, row, robot, tolerance):
        """Whether every measured TCP is within ``tolerance`` m of its position target in an ee row."""
        starts = self.openings - np.asarray(self.pose_sizes)
        return all(np.linalg.norm(row[start:start + 3] - robot[arm]["tcp_position_world_m"]) <= tolerance
                   for arm, start in zip(self.arms, starts))

    def hold(self, row, robot):
        """An ee action that keeps every arm at its measured pose, with the gripper openings of ``row``."""
        held = self.state("ee", robot)
        held[self.openings] = row[self.openings]
        return self.action(held)

    def action(self, row):
        action, start, clipped = {}, 0, False
        for arm, size in zip(self.arms, self.pose_sizes):
            group = self.groups[arm]
            pose, opening = row[start:start + size], row[start + size]
            start += size + 1
            if self.spec.action_space == "joint_abs":
                limits = np.asarray(group["joint_limits_rad"])
                q = np.clip(pose, limits[:, 0], limits[:, 1])
                clipped |= bool((q != pose).any())
                command = {"joint_position_rad": q.tolist()}
            else:
                command = {"position_world_m": pose[:3].tolist(), "orientation_wxyz": rot6d_to_wxyz(pose[3:]).tolist()}
            g = float(np.clip(opening, 0.0, 1.0))
            clipped |= bool(g != opening)
            command[group["gripper_field"]] = self.closed + g * (self.open - self.closed)
            action[arm] = command
        self.clipped += clipped
        return action
