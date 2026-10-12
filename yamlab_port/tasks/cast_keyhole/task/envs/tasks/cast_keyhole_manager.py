"""CastKeyhole task environments (port of RoboTangle cast_keyhole, robotangle-r2 / topogym 2dafa5f).

Goal check = the old placement predicate (topogym/tasks/placement.py, evaluation/task_metrics.py,
utils/geometry/regions.py), evaluated every control step on the plates' exported geometry:
  - all_target_inside: every vertex of the silver plate inside the goal square (xy within the half size
    minus the 1 mm boundary margin; z between table - 1 mm and table + placement height),
  - remainder_on_system_side: every vertex of the gold plate is on the system side of the separator
    (old: y_old <= goal y_min - 30 mm; in world: sign * p[axis] <= offset, see layout.json),
  - quiet: silver |v| <= 1 mm/s and |w| <= 0.02 rad/s,
  - holding allowed (as in the old task); release is reported as a diagnostic only,
  - failure guards: non-finite state, or a plate point more than 0.1 m below the table top,
latched as success after stable_duration_s (0.5 s = 15 control steps at 30 Hz) of consecutive reached steps.
The old 1 mm task-contact penetration guard is evaluated offline from the logged poses (see
tools/penetration_audit.py); it needs the collider geometry and is not part of the per-step torch check.
"""

import math

import gymnasium as gym
import torch

from isaaclab.utils.math import quat_apply

from yamlab.configs import get_task_config
from .yam_bimanual_env import YamBimanualEnv, make_task_env
from .cast_keyhole_manager_cfg import TIERS, PLATES, task_id, load_layout, make_cfg_class


class CastKeyholeManager(YamBimanualEnv):
    """Take the silver plate out of the gold one and rest it in the goal square."""

    def __init__(self, cfg, render_mode: str | None = None, **kwargs):
        kwargs.pop("is_evaluation_mode", None)
        env_name = kwargs.get("env_name")
        self.ck_tier = cfg._ck_tier
        self.ck_layout = load_layout(self.ck_tier)
        task_cfg = get_task_config(env_name)
        self.ck_success_cfg = dict(task_cfg["success"])
        self.ck_friction = dict(task_cfg.get("friction") or {"static": 0.35, "dynamic": 0.35})
        super().__init__(cfg, render_mode, **kwargs)
        # Per-arm grasp target (the task's grasp_detect): left holds gold, right holds silver.
        self.robot.left_arm.end_effector.default_target = "keyhole_gold"
        self.robot.right_arm.end_effector.default_target = "keyhole_silver"
        self._apply_physics_materials_to_objects()

        dev, n = self.device, self.num_envs
        g = self.ck_layout["goal_region"]
        self.ck_goal = g
        self.ck_vertices = {name: torch.tensor(self.ck_layout["vertices_part_m"][name], dtype=torch.float32,
                                               device=dev) for name in PLATES}
        self.ck_lo = torch.tensor(g["xy_min"], dtype=torch.float32, device=dev)
        self.ck_hi = torch.tensor(g["xy_max"], dtype=torch.float32, device=dev)
        step_dt = self.cfg.sim.dt * self.cfg.decimation
        self.ck_required_steps = int(math.ceil(self.ck_success_cfg["stable_duration_s"] / step_dt - 1e-9))
        self.ck_success = torch.zeros(n, dtype=torch.bool, device=dev)
        self.ck_failure = torch.zeros(n, dtype=torch.bool, device=dev)
        self.ck_count = torch.zeros(n, dtype=torch.int32, device=dev)
        self.ck_info = {}
        print(f"[INFO] CastKeyhole {self.ck_tier}: success after {self.ck_required_steps} consecutive steps")

    def get_object_names_for_physics_material(self) -> list[str]:
        return list(PLATES)

    def _apply_physics_materials_to_objects(self):
        # Plate material: the old friction 0.35, combine mode "max" (PhysX uses the higher-priority mode of the
        # pair): plate-plate stays 0.35, plate-finger takes the finger's 3.0 (YAMLab's own finger material),
        # plate-table max(0.35, table). Object-side knob only; the robot is unchanged.
        for name in self.get_object_names_for_physics_material():
            self._apply_physics_material_to_object(name, static_friction=float(self.ck_friction["static"]),
                                                   dynamic_friction=float(self.ck_friction["dynamic"]),
                                                   friction_combine_mode="max")

    # ------------------------------------------------------------------ goal check
    def plate_points(self, name: str) -> torch.Tensor:
        obj = self.scene[name]
        p, q = obj.data.root_pos_w, obj.data.root_quat_w            # (n,3), (n,4) wxyz, world
        p = p - self.scene.env_origins
        v = self.ck_vertices[name]
        nv = v.shape[0]
        return quat_apply(q.repeat_interleave(nv, 0), v.repeat(p.shape[0], 1)).view(-1, nv, 3) + p[:, None, :]

    def evaluate_goal(self):
        g, sc = self.ck_goal, self.ck_success_cfg
        silver_pts = self.plate_points("keyhole_silver")
        gold_pts = self.plate_points("keyhole_gold")
        bm, tz = g["boundary_margin"], g["table_z"]
        inside_xy = ((silver_pts[..., :2] >= self.ck_lo + bm - 1e-9) & (silver_pts[..., :2] <= self.ck_hi - bm + 1e-9)).all(-1)
        inside_z = (silver_pts[..., 2] >= tz - g["penetration_tolerance"] - 1e-9) & (silver_pts[..., 2] <= tz + g["height"] + 1e-9)
        all_inside = (inside_xy & inside_z).all(-1)
        sep_s = float(g.get("separator_sign", 1.0))
        gold_side = (sep_s * gold_pts[..., g["separator_axis"]] <= g["separator_offset"] + 1e-9).all(-1)
        silver = self.scene["keyhole_silver"].data
        lin = torch.linalg.norm(silver.root_lin_vel_w, dim=-1)
        ang = torch.linalg.norm(silver.root_ang_vel_w, dim=-1)
        quiet = (lin <= sc["linear_speed_limit_m_s"]) & (ang <= sc["angular_speed_limit_rad_s"])
        finite = torch.ones_like(quiet)
        lowest = torch.full_like(lin, float("inf"))
        for name, pts in (("keyhole_gold", gold_pts), ("keyhole_silver", silver_pts)):
            d = self.scene[name].data
            finite &= torch.isfinite(pts).all(-1).all(-1) & torch.isfinite(d.root_lin_vel_w).all(-1) & \
                torch.isfinite(d.root_ang_vel_w).all(-1)
            lowest = torch.minimum(lowest, pts[..., 2].min(-1).values)
        fell = lowest < tz - sc["below_table_failure_m"]
        failure = ~finite | fell
        reached = all_inside & gold_side & quiet & ~failure
        # margins (diagnostics): how far the silver is from leaving the square, gold from the separator
        m_xy = torch.minimum(silver_pts[..., :2] - (self.ck_lo + bm), (self.ck_hi - bm) - silver_pts[..., :2]).amin((-1, -2))
        left_grip, right_grip = self.robot.is_grasping()
        info = dict(reached=reached, all_target_inside=all_inside, remainder_on_system_side=gold_side, quiet=quiet,
                    failure=failure, silver_lin_speed=lin, silver_ang_speed=ang, silver_xy_margin=m_xy,
                    silver_min_z=silver_pts[..., 2].min(-1).values - tz,
                    silver_max_z=silver_pts[..., 2].max(-1).values - tz,
                    gold_separator_margin=g["separator_offset"] - (sep_s * gold_pts[..., g["separator_axis"]]).max(-1).values,
                    lowest_point_rel_table=lowest - tz,
                    left_grasping_gold=left_grip, right_grasping_silver=right_grip)
        return info

    def update_success(self):
        info = self.evaluate_goal()
        self.ck_failure |= info["failure"]
        self.ck_count = torch.where(info["reached"] & ~self.ck_success, self.ck_count + 1,
                                    torch.where(self.ck_success, self.ck_count, torch.zeros_like(self.ck_count)))
        self.ck_success |= (self.ck_count >= self.ck_required_steps) & ~self.ck_failure
        info["consecutive_steps"] = self.ck_count.clone()
        info["success"] = self.ck_success.clone()
        self.ck_info = info
        return info

    def reset_success_check(self, env_ids=None):
        if env_ids is None:
            env_ids = torch.arange(self.num_envs, device=self.device)
        self.ck_success[env_ids] = False
        self.ck_failure[env_ids] = False
        self.ck_count[env_ids] = 0
        if hasattr(self, "_success_reward_given"):
            self._success_reward_given[env_ids] = False

    def get_task_success(self):
        return self.ck_success

    def get_current_task_info(self):
        d = {}
        for name in PLATES:
            o = self.scene[name].data
            d[f"{name}_position"] = o.root_pos_w[0].cpu().tolist()
            d[f"{name}_orientation"] = o.root_quat_w[0].cpu().tolist()
        d.update(total_objs=2, episode_count=self._episode_count,
                 intermediate_success={"task_success": bool(self.ck_success[0].item())})
        return d

    def step(self, actions):
        pre = self.ck_success.clone()
        obs, reward, terminated, truncated, info = super().step(actions)
        if hasattr(self, "reset_buf") and torch.any(self.reset_buf):
            self.reset_success_check(self.reset_buf.nonzero(as_tuple=False).squeeze(-1))
        ck = self.update_success()
        info["success"] = torch.where(terminated, pre, self.ck_success)
        info["cast_keyhole"] = ck
        return obs, reward, terminated, truncated, info

    def reset(self, warm_up=True, seed=None, env_ids=None, options=None):
        self.reset_success_check(env_ids)
        out = super().reset(warm_up=warm_up, seed=seed, env_ids=env_ids, options=options)
        self.update_success()
        return out


def _make_factory(tier: str):
    cfg_cls = make_cfg_class(tier)

    def factory(**kwargs):
        return make_task_env(cfg_cls, CastKeyholeManager, **kwargs)
    return factory


REGISTERED = []
for _key, _tier in TIERS.items():
    try:
        _factory = _make_factory(_tier)
    except FileNotFoundError:
        continue                      # assets of this tier not built
    gym.register(id=task_id(_key), entry_point=_factory)
    REGISTERED.append(task_id(_key))
