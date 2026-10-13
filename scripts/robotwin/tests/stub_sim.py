"""A stand-in for the RoboTwin simulator, for tests of the standard-mode service and the graders without SAPIEN or a
GPU. test_standard_service.py copies this file next to the real server.py as rcb_traj.py (and writes a no-op
rcb_live.py), so the service under test is the shipped file, unchanged.

The "scene": 16 driven joints whose positions follow their drive targets at once. The left wrist camera's pose follows
the left arm's first joint. The task succeeds when fl_joint1's target is above 0.5 and RoboTwin's left-gripper-open
clause holds. Failure injection (environment variables): RCB_STUB_HASH_MISMATCH (the instance never rebuilds),
RCB_STUB_REPLAY_FAIL (the verification replay raises), RCB_STUB_VIDEO_S (render_video sleeps that long)."""
from __future__ import annotations

import hashlib
import json
import os
import time

import numpy as np

SCALE = [-0.01, 0.045]


class Joint:
    stiffness, damping = 1000.0, 200.0

    def __init__(self, name):
        self.name, self.drive_target, self.vel = name, 0.0, 0.0

    def get_name(self): return self.name
    def get_limits(self): return np.array([[-3.0, 3.0]])
    def get_drive_target(self): return np.array([self.drive_target])
    def get_drive_velocity_target(self): return np.array([self.vel])
    def set_drive_target(self, v): self.drive_target = float(v)
    def set_drive_velocity_target(self, v): self.vel = float(v)


class Entity:
    def __init__(self, joints): self.joints = joints
    def get_active_joints(self): return self.joints
    def get_qpos(self): return np.array([j.drive_target for j in self.joints])
    def get_qvel(self): return np.zeros(len(self.joints))


class Robot:
    def __init__(self):
        for side, p in (("left", "fl"), ("right", "fr")):
            setattr(self, f"{side}_arm_joints", [Joint(f"{p}_joint{i}") for i in range(1, 7)])
            setattr(self, f"{side}_gripper", [(Joint(f"{p}_joint7"), 1.0, 0.0), (Joint(f"{p}_joint8"), 1.0, 0.0)])
            setattr(self, f"{side}_gripper_scale", list(SCALE))
            setattr(self, f"{side}_gripper_val", 0.0)
        self.left_entity = self.right_entity = Entity(
            self.left_arm_joints + [g[0] for g in self.left_gripper] + self.right_arm_joints + [g[0] for g in self.right_gripper])

    def set_arm_joints(self, pos, vel, side):
        for j, p, v in zip(getattr(self, f"{side}_arm_joints"), pos, vel):
            j.set_drive_target(p); j.set_drive_velocity_target(v)

    def set_gripper(self, gripper_val, arm_tag, gripper_eps=0.1):       # RoboTwin's Robot.set_gripper
        gripper_val = float(np.clip(gripper_val, 0, 1))
        setattr(self, f"{arm_tag}_gripper_val", gripper_val)
        joints, sc = getattr(self, f"{arm_tag}_gripper"), getattr(self, f"{arm_tag}_gripper_scale")
        real = float(np.clip((joints[0][0].drive_target - sc[0]) / (sc[1] - sc[0]), 0, 1))
        if gripper_val - real > gripper_eps:
            gripper_val = real + gripper_eps
        for joint, mult, bias in joints:
            joint.set_drive_target((sc[0] + gripper_val * (sc[1] - sc[0])) * mult + bias)

    def _state(self, side):
        return [j.drive_target for j in getattr(self, f"{side}_arm_joints")] + [getattr(self, f"{side}_gripper_val")]

    def get_left_arm_jointState(self): return self._state("left")
    def get_right_arm_jointState(self): return self._state("right")
    def get_left_tcp_pose(self): return [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0]
    def get_right_tcp_pose(self): return [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0]
    def left_plan_path(self, pose): return {"status": "Success", "position": np.zeros((5, 6)), "velocity": np.zeros((5, 6))}
    def right_plan_path(self, pose): return {"status": "Success", "position": np.zeros((5, 6)), "velocity": np.zeros((5, 6))}
    def is_left_gripper_open(self): return self.left_gripper_val > 0.8


class Cameras:
    def __init__(self, robot): self.robot = robot
    def update_picture(self): pass

    def get_config(self):
        out = {}
        for name in ("left_camera", "right_camera", "head_camera", "front_camera"):
            m = np.eye(4)
            if name == "left_camera":
                m[0, 3] = self.robot.left_arm_joints[0].drive_target     # the wrist camera rides on the arm
            out[name] = {"intrinsic_cv": np.eye(3), "extrinsic_cv": m[:3], "cam2world_gl": m}
        return out

    def get_depth(self):
        return {c: {"depth": np.ones((240, 320), np.float32)} for c in ("left_camera", "right_camera", "head_camera", "front_camera")}


class Env:
    def __init__(self):
        self.robot = Robot(); self.cameras = Cameras(self.robot)

    def _update_render(self): pass
    def get_arm_pose(self, side): return [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0]

    def check_success(self):
        return bool(self.robot.left_arm_joints[0].drive_target > 0.5 and self.robot.is_left_gripper_open())


class Session:
    action_dim = 34

    def __init__(self, task, instance=None, seed=0, embodiment=None, enable_render=False, render_shader="default",
                 gripper_state="fingers"):
        if os.environ.get("RCB_STUB_HASH_MISMATCH"):
            raise RuntimeError("instance state hash 000000000000 != expected 111111111111: non-deterministic rebuild")
        data = os.environ.get("RCB_DATA")
        if data:
            with open(os.path.join(data, "stub_session.jsonl"), "a") as f:
                f.write(json.dumps({"task": task, "gripper_state": gripper_state, "enable_render": enable_render}) + "\n")
        self.task, self.seed = task, int(json.load(open(instance))["seed"]) if instance else seed
        self._recording = None
        # rcb_traj.Session's hand-in cap (MAX_T rows; save_trajectory and replay refuse more), small here: RCB_STUB_MAX_T
        self.max_rows = int(os.environ["RCB_STUB_MAX_T"]) if os.environ.get("RCB_STUB_MAX_T") else None
        self._build()

    def _build(self):
        self.env = Env(); self._sim_steps = 0
        r = self.env.robot
        self._joints = list(r.left_arm_joints) + [g[0] for g in r.left_gripper] + list(r.right_arm_joints) + [g[0] for g in r.right_gripper]

    def _row(self):
        r = self.env.robot
        return np.array([j.drive_target for j in self._joints] + [j.vel for j in self._joints] + [r.left_gripper_val, r.right_gripper_val])

    def step(self, row=None):
        if row is not None:
            row = np.asarray(row, dtype=np.float64); r = self.env.robot
            for j, p, v in zip(self._joints, row[:16], row[16:32]):
                j.set_drive_target(p); j.set_drive_velocity_target(v)
            r.left_gripper_val, r.right_gripper_val = float(row[32]), float(row[33])
        if self._recording is not None:
            self._recording.append(self._row())
        self._sim_steps += 1

    def state_sha(self):
        return hashlib.sha1(np.ascontiguousarray(self._row()).tobytes()).hexdigest()[:12]

    def record_start(self): self._recording = []

    def record_stop(self):
        acts = np.array(self._recording or [], dtype=np.float64).reshape(-1, 34); self._recording = None
        return acts

    def _too_long(self, n):
        if self.max_rows is not None and n > self.max_rows:
            raise ValueError(f"the trajectory has {n} rows; the verifier grades at most {self.max_rows} rows (stub)")

    def save_trajectory(self, actions, path, meta=None):
        self._too_long(len(actions))
        np.savez(path, actions=np.asarray(actions, dtype=np.float64), task=self.task, seed=self.seed, meta=json.dumps(meta or {}))

    def replay(self, actions):
        if os.environ.get("RCB_STUB_REPLAY_FAIL"):
            raise RuntimeError("CUDA out of memory (stub)")
        self._too_long(len(actions))
        self._build()
        for row in np.asarray(actions, dtype=np.float64):
            self.step(row)
        return {"success": bool(self.env.check_success()), "sim_steps": self._sim_steps, "state_sha": self.state_sha()}

    def render_frame(self, camera="head_camera", size=None):
        return np.zeros((240, 320, 3), np.uint8)

    def render_video(self, actions, path, **kw):
        time.sleep(float(os.environ.get("RCB_STUB_VIDEO_S", "0")))
        open(path, "wb").write(b"stub")
        return {}

    def close(self): pass
