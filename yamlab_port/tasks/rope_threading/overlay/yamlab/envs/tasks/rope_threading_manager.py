"""RopeThreading task environments (port of RoboTangle rope_threading, tiers easy and medium).

Instruction (old task): "Thread the rope through all rings in the prescribed order and direction, then
keep the whole rope still."

Goal check = old ``RopeThreadingTask.evaluate_state`` (tasks/rope_threading/common.py) on the capsule-chain
centreline (the polyline through the 111 joint points = the exact chain axis, material order = link_000 ->
link_109 = first -> last row of the old start CSV):
  threaded   for each ring: aperture_crossings of the centreline with the usable aperture
             (R - tube - (rope radius - 1 mm allowance) - 0.1 mm margin); crossings with the nominal aperture (R - tube) must
             be the same number (thickness clear), and the slices at +-tube radius along the normal must
             give the same sign list; no ambiguous tangencies; all hits sorted along the material
             coordinate == the required order (easy: R1-, R2+; medium: R1-, R2+, R3+)
  quiet      max speed of every material point (joint points + link centres) <= 1 cm/s, as the finite
             difference over one control step (PhysX's reported link velocities carry ~1 cm/s TGS noise
             at rest; knot_untying STATUS, deviation D3)
  intact     finite state, max joint gap <= 1 mm (reduced coordinates: ~1e-7 m)
held for 0.5 s (15 consecutive control steps at 30 Hz), then latched. Holding the rope is allowed.
Thresholds = the RELEASED task's terminal (release profile contact_relaxed_v16: 1 cm/s, 1 mm aperture contact
allowance, round-ring slices, 0.1 mm margin; configs/tasks/rope_threading.yaml). The old class defaults (1 mm/s,
no allowance, cylindrical slices) are evaluated as a diagnostic (``strict_*`` keys).
"""

import json
import os

import gymnasium as gym
import numpy as np
import torch

from .yam_bimanual_env import YamBimanualEnv, make_task_env
from .rope_threading_manager_cfg import (ASSET_ROOT, RopeThreadingEasyManagerEnvCfg,
                                         RopeThreadingMediumManagerEnvCfg)
from .rope_threading_lib import rope_chain as C, threading_geom as TH
from yamlab.configs import get_task_config
from yamlab.robot.yam import ROBOT


class RopeThreadingManager(YamBimanualEnv):
    """Thread the rope (capsule-chain articulation) through the rings in order and direction, keep it still."""

    def __init__(self, cfg, render_mode=None, **kwargs):
        succ = get_task_config(kwargs.get("env_name", "RopeThreading-Easy-v0"))["success"]
        self.max_speed = float(succ["max_speed_m_s"])
        self.aperture_margin = float(succ["aperture_margin_m"])
        self.aperture_allowance = float(succ.get("aperture_contact_allowance_m", 0.0))
        self.round_ring = bool(succ.get("round_ring_slices", 0.0))
        self.stable_steps = int(succ["stable_steps"])
        self.max_joint_gap = float(succ["max_joint_gap_m"])
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

        self.scn = TH.scene(self.tier)
        self.params_goal = dict(maximum_speed_m_s=self.max_speed, aperture_margin_m=self.aperture_margin,
                                allowance_m=self.aperture_allowance, profile="round_ring" if self.round_ring else "cylindrical")
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
        idx = [names.index(j) for j in rope.joint_names]
        jp = np.asarray(st["joint_pos"])[idx].astype(np.float32)
        self.rope_rest_joint_pos = torch.tensor(np.asarray(st["rest_joint_pos"])[idx], dtype=torch.float32,
                                                device=self.device)
        rope.data.default_joint_pos[:] = torch.tensor(jp, device=self.device)
        rope.data.default_joint_vel[:] = 0.0
        rs = torch.tensor(st["root_state"], dtype=torch.float32, device=self.device)
        rs[7:] = 0.0
        rope.data.default_root_state[:] = rs
        print(f"[INFO] RopeThreading ({self.tier}): rope {self.n_links} links, d={self.link_length*1000:.2f} mm, "
              f"order {self.scn['order']}")

    # ------------------------------------------------------------------ state
    def rope_state(self, env_id: int = 0):
        """(pos, quat, lin_vel, ang_vel) of the links in material order, env-local frame, numpy float64."""
        r = self.rope.data
        o = self._link_order
        pos = (r.body_link_pos_w[env_id, o] - self.scene.env_origins[env_id]).cpu().numpy().astype(np.float64)
        quat = r.body_link_quat_w[env_id, o].cpu().numpy().astype(np.float64)
        lv = r.body_link_lin_vel_w[env_id, o].cpu().numpy().astype(np.float64)
        av = r.body_link_ang_vel_w[env_id, o].cpu().numpy().astype(np.float64)
        return pos, quat, lv, av

    def centerline(self, env_id: int = 0):
        pos, quat, _, _ = self.rope_state(env_id)
        return C.chain_points_from_links(pos, quat, self.link_length)[0]

    def evaluate_goal(self, env_id: int = 0, update_history: bool = False):
        pos, quat, lv, av = self.rope_state(env_id)
        joints, gaps = C.chain_points_from_links(pos, quat, self.link_length)
        threaded, tdiag = TH.threading_check(joints, self.scn["rings"], self.scn["order"], self.rope_radius,
                                             self.params_goal)
        strict_threaded, sdiag = TH.threading_check(joints, self.scn["rings"], self.scn["order"], self.rope_radius,
                                                    TH.STRICT)
        mp = np.vstack((joints, pos))
        prev = self._prev_points[env_id]
        speeds = np.linalg.norm(mp - prev, axis=1) / self.step_dt if prev is not None else np.array([np.inf])
        quiet = bool(speeds.max() <= self.max_speed)
        intact = bool(np.isfinite(pos).all() and np.isfinite(quat).all() and gaps.max() <= self.max_joint_gap)
        if update_history:
            self._prev_points[env_id] = mp
        ok = bool(threaded and quiet and intact)
        diag = dict(threaded=threaded, quiet=quiet, intact=intact, **tdiag,
                    maximum_speed_m_s=float(speeds.max()), p99_speed_m_s=float(np.quantile(speeds, 0.99)),
                    reported_velocity_max_m_s=float(np.linalg.norm(lv, axis=1).max()),
                    max_joint_gap_m=float(gaps.max()),
                    strict_threaded=strict_threaded, strict_quiet=bool(speeds.max() <= TH.STRICT["maximum_speed_m_s"]),
                    strict_crossing_sequence=sdiag["crossing_sequence"], strict_per_ring=sdiag["per_ring"])
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
        return make_task_env(cls, RopeThreadingManager, **kwargs)
    return make


make_rope_threading_easy_env = _factory(RopeThreadingEasyManagerEnvCfg)
make_rope_threading_medium_env = _factory(RopeThreadingMediumManagerEnvCfg)

gym.register(id="RopeThreading-Easy-v0",
             entry_point="yamlab.envs.tasks.rope_threading_manager:make_rope_threading_easy_env")
gym.register(id="RopeThreading-Medium-v0",
             entry_point="yamlab.envs.tasks.rope_threading_manager:make_rope_threading_medium_env")
