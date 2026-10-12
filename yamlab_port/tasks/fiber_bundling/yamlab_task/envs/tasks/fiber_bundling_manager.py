"""FiberBundling task environments (port of the old RoboTangle fiber_bundling family).

Goal (old terminal_v4_fiber_ring_plane, unchanged thresholds): every strand passes the ring
plane inside the aperture tip first in material order and its stations are clear of the tube
on the exit side; the front sheath face has passed and is clear by the tube radius; the bend
between consecutive strand segments is at most 60 deg; all of it held for 0.5 s. Any gripper
contact with a strand (any physics substep) fails the task, latched. The cable root is fixed
(the terminal is the articulation's fixed base), so "keep the rear terminal anchored" holds
by construction.
"""

import json
import os

import numpy as np
import torch
import gymnasium as gym

from .yam_bimanual_env import YamBimanualEnv, make_task_env
from .fiber_bundling_manager_cfg import (FiberBundlingVeryEasyManagerEnvCfg, FiberBundlingEasierManagerEnvCfg,
                                         FiberBundlingEasyManagerEnvCfg)
from .fiber_bundling_goal import FiberGoal, quat_wxyz_to_mat
from yamlab.configs import get_task_config


class FiberBundlingManager(YamBimanualEnv):

    def __init__(self, cfg, render_mode=None, **kwargs):
        self.task_name = cfg.TASK_NAME
        self._success_cfg = dict(get_task_config(self.task_name)["success"])
        kwargs.pop("is_evaluation_mode", None)
        with open(os.path.join(cfg.ASSET_DIR, "layout_world.json")) as f:
            self.layout = json.load(f)
        super().__init__(cfg, render_mode, **kwargs)
        self.cable = self.scene["cable"]
        self.strand_sensor = self.scene["strand_contact"]
        names = self.cable.body_names
        self._fiber_names = [n for s in self.layout["fibers"]["names"] for n in s]
        self._goal_link_names = self._fiber_names+[self.layout["trunk"]["names"][-1]]
        self._goal_idx = [names.index(n) for n in self._goal_link_names]
        self._sensor_fiber_order = list(self.strand_sensor.body_names)
        n = self.num_envs
        self.goals = [FiberGoal(self.layout, self._success_cfg) for _ in range(n)]
        self.goal_success = torch.zeros(n, dtype=torch.bool, device=self.device)
        self.goal_failed = torch.zeros(n, dtype=torch.bool, device=self.device)
        self.goal_reached = torch.zeros(n, dtype=torch.bool, device=self.device)
        self.failure_reason = [None]*n
        self.first_touch_step = [None]*n
        self._stable_steps = torch.zeros(n, dtype=torch.int32, device=self.device)
        self._required_steps = int(np.ceil(self._success_cfg["stable_duration_s"]/self.step_dt-1e-9))
        self._eval_counter = -1
        self.last_metrics = [dict() for _ in range(n)]
        self._init_goal_history(None)
        print(f"[INFO] FiberBundling {self.task_name}: {len(self._fiber_names)} strand links, "
              f"success after {self._required_steps} consecutive control steps")

    # ---------------- state access ----------------
    def link_poses(self, env_id: int):
        """World link-frame poses of every cable link: {name: (pos(3), R(3,3))}."""
        pos = self.cable.data.body_link_pos_w[env_id].detach().cpu().numpy().astype(float)
        quat = self.cable.data.body_link_quat_w[env_id].detach().cpu().numpy().astype(float)
        R = quat_wxyz_to_mat(quat)
        return {name: (pos[i], R[i]) for i, name in enumerate(self.cable.body_names)}

    def strand_gripper_contact(self):
        """Max gripper-strand contact force over the substeps of the last control step, per env."""
        fm = self.strand_sensor.data.force_matrix_w_history  # (N, H, B, M, 3)
        if fm is None:
            fm = self.strand_sensor.data.force_matrix_w.unsqueeze(1)
        mag = torch.linalg.norm(fm, dim=-1)  # (N, H, B, M)
        return mag.amax(dim=(1, 2, 3))

    def _init_goal_history(self, env_ids):
        ids = range(self.num_envs) if env_ids is None else [int(i) for i in env_ids]
        for i in ids:
            # The reset state is the authored start layout (fixed base, joint positions 0); use it
            # directly, since articulation link buffers are only refreshed by the next physics step.
            self.goals[i].reset(self.goals[i].start_pose)
            self.goal_success[i] = False
            self.goal_failed[i] = False
            self.goal_reached[i] = False
            self.failure_reason[i] = None
            self.first_touch_step[i] = None
            self._stable_steps[i] = 0
            self.last_metrics[i] = dict()

    # ---------------- goal evaluation (once per control step) ----------------
    def evaluate_goal(self):
        if self._eval_counter == self.common_step_counter:
            return
        self._eval_counter = self.common_step_counter
        # Snapshot of the evaluated (pre-auto-reset) state, for logging the final step of an episode.
        self.last_eval_links = torch.cat([self.cable.data.body_link_pos_w, self.cable.data.body_link_quat_w], -1).detach().cpu().numpy().copy()
        self.last_eval_q = {a: self.scene[a].data.joint_pos.detach().cpu().numpy().copy() for a in ("left_arm", "right_arm")}
        force = self.strand_gripper_contact().detach().cpu().numpy()
        thr = float(self._success_cfg["strand_contact_force_n"])
        all_z = self.cable.data.body_link_pos_w[:, :, 2].detach().cpu().numpy()
        for i in range(self.num_envs):
            if bool(self.goal_failed[i]) or bool(self.goal_success[i]):
                continue
            if force[i] > thr:
                self.goal_failed[i] = True
                self.failure_reason[i] = "fiber_gripper_contact"
                self.first_touch_step[i] = int(self.episode_length_buf[i])
                self.last_metrics[i] = dict(strand_gripper_force_n=float(force[i]))
                continue
            reached, failure, metrics = self.goals[i].evaluate(self.link_poses(i), all_z[i])
            metrics["strand_gripper_force_n"] = float(force[i])
            self.last_metrics[i] = metrics
            if failure is not None:
                self.goal_failed[i] = True
                self.failure_reason[i] = failure
                continue
            self.goal_reached[i] = reached
            self._stable_steps[i] = self._stable_steps[i]+1 if reached else 0
            if int(self._stable_steps[i]) >= self._required_steps:
                self.goal_success[i] = True

    def get_task_success(self):
        return self.goal_success

    def reset_success_check(self, env_ids=None):
        pass

    def get_current_task_info(self):
        m = self.last_metrics[0]
        return {"intermediate_success": {"task_success": bool(self.goal_success[0])},
                "failed": bool(self.goal_failed[0]), "failure_reason": self.failure_reason[0],
                "episode_count": self._episode_count, "metrics": m}

    def step(self, actions):
        obs, reward, terminated, truncated, info = super().step(actions)
        # No-op when the termination terms already evaluated this step (before any auto-reset);
        # evaluates here when terminations are disabled (replay/teleop modes).
        self.evaluate_goal()
        info["success"] = self.goal_success.clone()
        info["failed"] = self.goal_failed.clone()
        info["goal_reached"] = self.goal_reached.clone()
        info["goal_metrics"] = [dict(m) for m in self.last_metrics]
        info["failure_reason"] = list(self.failure_reason)
        done = terminated | truncated
        if torch.any(done):
            # Auto-reset happened inside super().step(): restart the goal history for those envs.
            self._init_goal_history(done.nonzero(as_tuple=False).squeeze(-1).tolist())
        return obs, reward, terminated, truncated, info

    def reset(self, warm_up=True, seed=None, env_ids=None, options=None):
        obs, extras = super().reset(warm_up=warm_up, seed=seed, env_ids=env_ids, options=options)
        self._init_goal_history(env_ids)
        self._eval_counter = -1
        return obs, extras


def make_fiber_bundling_very_easy_env(**kwargs):
    return make_task_env(FiberBundlingVeryEasyManagerEnvCfg, FiberBundlingManager, **kwargs)


def make_fiber_bundling_easier_env(**kwargs):
    return make_task_env(FiberBundlingEasierManagerEnvCfg, FiberBundlingManager, **kwargs)


def make_fiber_bundling_easy_env(**kwargs):
    return make_task_env(FiberBundlingEasyManagerEnvCfg, FiberBundlingManager, **kwargs)


gym.register(id="FiberBundling-Easy-v0",
             entry_point="yamlab.envs.tasks.fiber_bundling_manager:make_fiber_bundling_easy_env")
gym.register(id="FiberBundling-VeryEasy-v0",
             entry_point="yamlab.envs.tasks.fiber_bundling_manager:make_fiber_bundling_very_easy_env")
gym.register(id="FiberBundling-Easier-v0",
             entry_point="yamlab.envs.tasks.fiber_bundling_manager:make_fiber_bundling_easier_env")
