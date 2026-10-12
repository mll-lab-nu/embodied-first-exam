"""KnotUntying task environments (port of RoboTangle knot_untying, tiers very_easy, easier, easy, medium).

Instruction (old task): "Untangle the rope and leave it still on the table with no projected
crossings or overlapping segments."

Goal check = old ``evaluate_state`` (tasks/knot_untying/common.py, terminal_v5) on the capsule-chain
centreline (end point, link centres, end point as material stations):
  planar_clearance(points, stations, 2r)   top view: no intersection, non-local gaps >= 8 mm
  on_table   rope surface z_min >= table - 1 mm and z_max <= table + 2r + 3 mm
  quiet      max point speed (link centres and link ends) <= 1 mm/s
  intact     finite state, joint gaps <= 1 mm (reduced coordinates: ~0)
held for 0.5 s (15 consecutive control steps at 30 Hz), then latched.
"""

import json
import os

import gymnasium as gym
import numpy as np
import torch

from .yam_bimanual_env import YamBimanualEnv, make_task_env
from .knot_untying_manager_cfg import (ASSET_ROOT, TIERS, KnotUntyingVeryEasyManagerEnvCfg,
                                       KnotUntyingEasierManagerEnvCfg, KnotUntyingEasyManagerEnvCfg,
                                       KnotUntyingMediumManagerEnvCfg)
from .knot_untying_lib import rope_geom as G
from yamlab.configs import get_task_config
from yamlab.robot.yam import ROBOT

# Physical support height of the table collider. ROBOT.table_position z (0.7517) is the nominal top;
# the workstation's table_surface collider puts resting bodies at 0.7500 (measured: settled rope
# centres sit at 0.7540 = 0.7500 + r). The old predicate's table height is the support height.
TABLE_SUPPORT_Z = 0.7500


class KnotUntyingManager(YamBimanualEnv):
    """Untangle the rope (capsule chain articulation) and leave it still and crossing-free."""

    def __init__(self, cfg, render_mode=None, **kwargs):
        succ = get_task_config(kwargs.get("env_name", "KnotUntying-VeryEasy-v0"))["success"]
        self.max_speed = float(succ["max_speed_m_s"])
        self.table_clearance = float(succ["table_clearance_m"])
        self.penetration_tol = float(succ["penetration_tolerance_m"])
        self.stable_steps = int(succ["stable_steps"])
        self.tier = cfg.TIER
        n = cfg.scene.num_envs
        dev = cfg.sim.device
        self.goal_latched = torch.zeros(n, dtype=torch.bool, device=dev)
        self._goal_now = torch.zeros(n, dtype=torch.bool, device=dev)
        self._goal_count = torch.zeros(n, dtype=torch.int32, device=dev)
        self._goal_diag = [{} for _ in range(n)]
        self._goal_stamp = -1
        self._prev_points = [None] * n
        super().__init__(cfg, render_mode, **kwargs)
        self.goal_latched = self.goal_latched.to(self.device)
        self._goal_now = self._goal_now.to(self.device)
        self._goal_count = self._goal_count.to(self.device)

        rope = self.scene["rope"]
        self.rope = rope
        meta = json.load(open(os.path.join(ASSET_ROOT, self.tier, "rope_meta.json")))
        self.link_length = float(meta["link_length_m"])
        self.n_links = int(meta["n_links"])
        self.rope_radius = float(meta["radius_m"])
        self._link_order = torch.tensor([rope.body_names.index(f"link_{i:03d}") for i in range(self.n_links)],
                                        device=self.device)
        st = np.load(os.path.join(ASSET_ROOT, self.tier, "start_state.npz"))
        names = [str(x) for x in st["joint_names"]]
        jp = np.array([st["joint_pos"][names.index(j)] for j in rope.joint_names], dtype=np.float32)
        rope.data.default_joint_pos[:] = torch.tensor(jp, device=self.device)
        rope.data.default_joint_vel[:] = 0.0
        rs = torch.tensor(st["root_state"], dtype=torch.float32, device=self.device)
        rs[7:] = 0.0
        rope.data.default_root_state[:] = rs
        print(f"[INFO] KnotUntying ({self.tier}): rope {self.n_links} links, d={self.link_length*1000:.2f} mm, "
              f"start crossings {meta.get('settled_over_under')}")

    # ------------------------------------------------------------------ state
    def rope_state(self, env_id: int = 0):
        """(pos, quat, lin_vel, ang_vel) of the links in material order, env-local frame, numpy."""
        r = self.rope.data
        o = self._link_order
        pos = (r.body_link_pos_w[env_id, o] - self.scene.env_origins[env_id]).cpu().numpy().astype(np.float64)
        quat = r.body_link_quat_w[env_id, o].cpu().numpy().astype(np.float64)
        lv = r.body_link_lin_vel_w[env_id, o].cpu().numpy().astype(np.float64)
        av = r.body_link_ang_vel_w[env_id, o].cpu().numpy().astype(np.float64)
        return pos, quat, lv, av

    def evaluate_goal(self, env_id: int = 0, update_history: bool = False):
        pos, quat, lv, av = self.rope_state(env_id)
        ok, diag = G.evaluate(pos, quat, lv, av, self.link_length, radius=self.rope_radius, table_z=TABLE_SUPPORT_Z,
                              max_speed=self.max_speed, table_clearance=self.table_clearance,
                              penetration_tol=self.penetration_tol, prev_points=self._prev_points[env_id],
                              dt=self.step_dt)
        if update_history:
            self._prev_points[env_id] = G.material_points(pos, quat, self.link_length)
        return ok, diag

    def update_goal(self):
        """Evaluate the goal for all envs once per control step; returns the latched flags."""
        if self._goal_stamp == self.common_step_counter:
            return self.goal_latched
        self._goal_stamp = self.common_step_counter
        for e in range(self.num_envs):
            ok, diag = self.evaluate_goal(e, update_history=True)
            self._goal_now[e] = ok
            self._goal_diag[e] = diag
        self._goal_count = torch.where(self._goal_now, self._goal_count + 1, torch.zeros_like(self._goal_count))
        self.goal_latched |= self._goal_count >= self.stable_steps
        self._latched_at_eval = self.goal_latched.clone()
        return self.goal_latched

    def reset_success_check(self, env_ids=None):
        if env_ids is None:
            env_ids = torch.arange(self.num_envs, device=self.device)
        self.goal_latched[env_ids] = False
        self._goal_now[env_ids] = False
        self._goal_count[env_ids] = 0
        for e in (env_ids.tolist() if torch.is_tensor(env_ids) else list(env_ids)):
            self._prev_points[e] = None

    def get_task_success(self):
        return self.goal_latched.clone()

    def get_current_task_info(self):
        ok, diag = self.evaluate_goal(0)
        return {"tier": self.tier, "goal_now": bool(ok), "goal_latched": bool(self.goal_latched[0]),
                "goal": diag, "episode_count": self._episode_count}

    def step(self, actions):
        self._latched_at_eval = self.goal_latched.clone()
        obs, reward, terminated, truncated, info = super().step(actions)
        if hasattr(self, "reset_buf") and torch.any(self.reset_buf):
            self.reset_success_check(self.reset_buf.nonzero(as_tuple=False).squeeze(-1))
        if self._goal_stamp != self.common_step_counter:
            self.update_goal()
        done = terminated | truncated
        info["success"] = torch.where(done, self._latched_at_eval, self.goal_latched)
        info["goal_now"] = self._goal_now.clone()
        info["goal_hold_steps"] = self._goal_count.clone()
        info["goal"] = [dict(d) for d in self._goal_diag]
        return obs, reward, terminated, truncated, info

    def reset(self, warm_up=True, seed=None, env_ids=None, options=None):
        self.reset_success_check(env_ids)
        out = super().reset(warm_up=warm_up, seed=seed, env_ids=env_ids, options=options)
        self.reset_success_check(env_ids)
        return out


def _strip_cameras(cfg_cls):
    """Physics-only variant: camera sensors removed (RTX unavailable on the compute host)."""
    class _NoCam(cfg_cls):
        def __post_init__(self):
            super().__post_init__()
            for name in ROBOT.camera_names:
                setattr(self.scene, f"{name}_camera", None)
    _NoCam.__name__ = cfg_cls.__name__ + "NoCam"
    _NoCam.TIER = cfg_cls.TIER
    _NoCam.CONTACT_OBJECT_NAMES = []
    return _NoCam


def _factory(cfg_cls):
    def make(**kwargs):
        strip = kwargs.pop("strip_cameras", False)
        cls = _strip_cameras(cfg_cls) if strip else cfg_cls
        return make_task_env(cls, KnotUntyingManager, **kwargs)
    return make


make_knot_untying_very_easy_env = _factory(KnotUntyingVeryEasyManagerEnvCfg)
make_knot_untying_easier_env = _factory(KnotUntyingEasierManagerEnvCfg)
make_knot_untying_easy_env = _factory(KnotUntyingEasyManagerEnvCfg)
make_knot_untying_medium_env = _factory(KnotUntyingMediumManagerEnvCfg)

gym.register(id="KnotUntying-VeryEasy-v0",
             entry_point="yamlab.envs.tasks.knot_untying_manager:make_knot_untying_very_easy_env")
gym.register(id="KnotUntying-Easier-v0",
             entry_point="yamlab.envs.tasks.knot_untying_manager:make_knot_untying_easier_env")
gym.register(id="KnotUntying-Easy-v0",
             entry_point="yamlab.envs.tasks.knot_untying_manager:make_knot_untying_easy_env")
gym.register(id="KnotUntying-Medium-v0",
             entry_point="yamlab.envs.tasks.knot_untying_manager:make_knot_untying_medium_env")
