"""BuzzWire3D task environments (YAMLab port of the old RoboTangle buzz_wire_3d family).

Instruction: "Guide the metal loop along the entire wire without touching it, then release the
tool on the finish support and let it settle."

Goal check = old ``terminal_v4_traversal_then_deck_release`` (topogym tasks/buzz_wire_3d/common.py):
  * touch: any wand-metal (ring + stem) / wire contact fails the episode, latched. Measured every
    physics substep two ways: the wand ContactSensor force against the rail (contact forces) and a
    geometric surface gap between the ring/stem capsules and the rail capsules (both recorded; the
    episode fails on either).
  * traversal: the wire must cross the loop aperture (radius 12.67 mm = loop - tube - wire) as one
    tracked crossing from the start (within 10 mm of arc 0) to the end (within 10 mm of the last
    point), with the crossing moving at most 2 * motion + 3 mm per evaluation (evaluated every
    physics substep). An observed complete traversal is kept (the finish rest pose lies below the
    rail end, which removes the crossing).
  * finish: loop centre within 5 mm and orientation within 10 deg of the finish rest pose (half
    turn about the handle axis allowed), supported by the deck, released (no robot contact), quiet
    (<= 1 mm/s, <= 0.02 rad/s), all for stable_duration_s = 1.0 s (30 control steps).
"""

import math
import os

import gymnasium as gym
import numpy as np
import torch

from .yam_bimanual_env import YamBimanualEnv, make_task_env
from .buzz_wire_3d_manager_cfg import (BUZZ_ENV_CFGS, BUZZ_LAYOUTS, WAND_FILTERS, layout_point, layout_quat,
                                        load_buzz_geometry, _quat_mul)
from yamlab.configs import get_task_config

ENV_IDS = {"very_easy": "BuzzWire3D-VeryEasy-v0", "easier": "BuzzWire3D-Easier-v0"}


# ----------------------------------------------------------------------------- numpy helpers
def _qmat(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _rot_angle(Ra, Rb):
    c = (np.trace(Ra @ Rb.T) - 1.0) / 2.0
    return float(math.acos(max(-1.0, min(1.0, c))))


def aperture_crossings(points, center, normal, radius, tolerance=1e-9):
    """Copied from the old task helper topogym/utils/geometry/passage.py (unchanged logic)."""
    p = points
    c = np.asarray(center, float)
    n = np.asarray(normal, float)
    n = n / np.linalg.norm(n)
    d = (p - c) @ n
    away = np.flatnonzero(abs(d) > tolerance)
    hits, ambiguous = [], False
    for i in np.flatnonzero(abs(d) <= tolerance):
        if np.linalg.norm(p[i] - c) <= radius + tolerance:
            if i == 0 or i == len(p) - 1 or d[i - 1] * d[i + 1] >= 0 or abs(d[i - 1]) <= tolerance or abs(d[i + 1]) <= tolerance:
                ambiguous = True
    for i in range(len(p) - 1):
        if abs(d[i]) <= tolerance and abs(d[i + 1]) <= tolerance:
            edge = p[i + 1] - p[i]
            t = np.clip(np.dot(c - p[i], edge) / max(np.dot(edge, edge), 1e-30), 0, 1)
            ambiguous |= bool(np.linalg.norm(p[i] + t * edge - c) <= radius + tolerance)
    for left, right in zip(away[:-1], away[1:]):
        if d[left] * d[right] >= 0 or right - left > 2:
            continue
        t = -d[left] / (d[left + 1] - d[left])
        point = p[left] + t * (p[left + 1] - p[left])
        distance = np.linalg.norm(point - c)
        if abs(distance - radius) <= tolerance:
            ambiguous = True
        if distance < radius - tolerance:
            hits.append(float(left + t))
    return hits, bool(ambiguous)


class _Geometry:
    """World-frame task geometry (numpy) for one tier."""

    def __init__(self, tier):
        g = load_buzz_geometry(tier)
        self.tier = tier
        yaw = math.radians(BUZZ_LAYOUTS[tier]["yaw_deg"])
        Rl = np.array([[math.cos(yaw), -math.sin(yaw), 0], [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1]])
        t = np.array(BUZZ_LAYOUTS[tier]["translation"])
        self.rail = (Rl @ np.array(g["rail_m"]).T).T + t
        self.arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(self.rail, axis=0), axis=1))]
        self.finish_p = Rl @ np.array(g["finish_p"]) + t
        self.finish_R = Rl @ _qmat(g["finish_q_wxyz"])
        self.aperture = float(g["aperture_m"])
        self.loop_r, self.tube_r, self.wire_r = g["loop_radius_m"], g["tube_radius_m"], g["wire_radius_m"]
        a = np.linspace(0, 2 * np.pi, 256, endpoint=False)
        ring = np.c_[self.loop_r * np.cos(a), self.loop_r * np.sin(a), np.zeros_like(a)]
        stem = np.c_[np.linspace(self.loop_r, g["stem_end_m"], 12), np.zeros(12), np.zeros(12)]
        self.metal_pts = np.r_[ring, stem]          # centreline samples of the metal capsules (body frame)
        self.seg_a, self.seg_b = self.rail[:-1], self.rail[1:]

    def metal_gap(self, p, R):
        """Min surface gap between the ring/stem tubes and the wire (m); 1.0 if far away."""
        near = np.flatnonzero(np.linalg.norm(self.rail - p, axis=1) < 0.06)
        if len(near) == 0:
            return 1.0
        lo, hi = max(near.min() - 1, 0), min(near.max() + 1, len(self.rail) - 1)
        A, B = self.rail[lo:hi], self.rail[lo + 1:hi + 1]
        P = self.metal_pts @ R.T + p
        AB = B - A
        AP = P[:, None, :] - A[None]
        t = np.clip(np.einsum("nmk,mk->nm", AP, AB) / np.einsum("mk,mk->m", AB, AB), 0, 1)
        d = np.linalg.norm(AP - t[..., None] * AB[None], axis=-1)
        return float(d.min() - self.tube_r - self.wire_r)


def make_buzz_wire_3d_env(tier="very_easy", **kwargs):
    kwargs["tier"] = tier
    return make_task_env(BUZZ_ENV_CFGS[tier], BuzzWire3DManager, **kwargs)


class BuzzWire3DManager(YamBimanualEnv):
    """Buzz wire: traverse the wire with the loop without touching it, then rest the tool on the deck."""

    def __init__(self, cfg, render_mode: str | None = None, **kwargs):
        self.tier = kwargs.pop("tier", "very_easy")
        kwargs.pop("is_evaluation_mode", None)
        super().__init__(cfg, render_mode, **kwargs)
        task_cfg = get_task_config(ENV_IDS[self.tier])
        self.thr = dict(task_cfg["success"])
        self.stable_steps = int(round(self.thr["stable_duration_s"] / (self.cfg.sim.dt * self.cfg.decimation)))
        self.geo = _Geometry(self.tier)
        fr = dict(task_cfg.get("friction") or {})
        if os.environ.get("BUZZ_GRIP_MU"):  # experiment override (object-side friction knob)
            fr["wand_grip"] = float(os.environ["BUZZ_GRIP_MU"])
        self._apply_buzz_friction(fr)
        n = self.num_envs
        dev = self.device
        self.buzz_success = torch.zeros(n, dtype=torch.bool, device=dev)
        self.buzz_touched = torch.zeros(n, dtype=torch.bool, device=dev)
        self._ok_steps = torch.zeros(n, dtype=torch.int32, device=dev)
        self._filters = {name: i for i, name in enumerate(WAND_FILTERS)}
        self._robot_cols = [i for name, i in self._filters.items() if "/arm/" in name]
        self._reset_tracking(range(n))
        # Every physics substep: geometric wand-metal / wire gap + aperture-crossing traversal tracking.
        self.sim.add_physics_callback("buzz_wire_substep", self._on_physics_step)
        print(f"[INFO] BuzzWire3D ({self.tier}) initialized: stable_steps={self.stable_steps}, "
              f"aperture={self.geo.aperture * 1000:.2f} mm, rail points={len(self.geo.rail)}")

    # ------------------------------------------------------------------ setup helpers
    def _apply_buzz_friction(self, fr):
        from isaaclab.sim.spawners.materials import RigidBodyMaterialCfg
        from isaaclab.sim.utils import bind_physics_material
        import omni.usd
        stage = omni.usd.get_context().get_stage()
        root = "/World/envs/env_0"
        groups = {
            "wand_grip": [f"{root}/wand/collisions/grip"],
            "wand_metal": [f"{root}/wand/collisions/ring_{i:02d}" for i in range(64)] + [f"{root}/wand/collisions/stem"],
            "deck": [f"{root}/deck"],
        }
        for key, paths in groups.items():
            if key not in fr:
                continue
            mu = float(fr[key])
            mat_path = f"{root}/buzz_materials/{key}"
            RigidBodyMaterialCfg(static_friction=mu, dynamic_friction=mu, restitution=0.0).func(
                mat_path, RigidBodyMaterialCfg(static_friction=mu, dynamic_friction=mu, restitution=0.0))
            for p in paths:
                if stage.GetPrimAtPath(p).IsValid():
                    bind_physics_material(p, mat_path)
        print(f"[INFO] BuzzWire3D friction: {fr}")

    def _reset_tracking(self, env_ids):
        if not hasattr(self, "_trk"):
            self._trk = [None] * self.num_envs
        for i in env_ids:
            i = int(i)
            self._trk[i] = dict(cursor=0.0, started=False, complete=False, prev_p=None, prev_R=None,
                                min_gap=1.0, min_gap_step=None, gap_touch=False, force_touch=False,
                                max_rail_force=0.0, substeps=0, tracked=False, ever_started=False,
                                first_touch_substep=None)
            if hasattr(self, "buzz_touched"):
                self.buzz_touched[i] = False
                self.buzz_success[i] = False
                self._ok_steps[i] = 0

    # ------------------------------------------------------------------ per physics substep
    def _on_physics_step(self, dt):
        wand = self.scene["wand"]
        tf = wand.root_physx_view.get_transforms().cpu().numpy()  # (N, 7): pos, quat xyzw (world)
        origins = self.scene.env_origins.cpu().numpy()
        for i in range(self.num_envs):
            s = self._trk[i]
            if s is None:
                continue
            p = tf[i, :3] - origins[i]
            x, y, z, w = tf[i, 3:7]
            R = _qmat((w, x, y, z))
            s["substeps"] += 1
            gap = self.geo.metal_gap(p, R)
            if gap < s["min_gap"]:
                s["min_gap"], s["min_gap_step"] = gap, s["substeps"]
            if gap <= 0.0 and not s["gap_touch"]:
                s["gap_touch"] = True
                s["first_touch_substep"] = s["first_touch_substep"] or s["substeps"]
            self._track(s, p, R)

    def _track(self, s, p, R):
        g, thr = self.geo, self.thr
        hits, ambiguous = aperture_crossings(g.rail, p, R[:, 2], g.aperture)
        tracking = len(hits) == 1 and not ambiguous
        cursor, started = s["cursor"], s["started"]
        if tracking:
            cand = float(np.interp(hits[0], np.arange(len(g.arc)), g.arc))
            if not started:
                started = cand <= thr["start_route_tolerance_m"] + 1e-12
                if started:
                    cursor = cand
            else:
                movement = np.linalg.norm(p - s["prev_p"]) + g.aperture * _rot_angle(R, s["prev_R"])
                tracking = abs(cand - cursor) <= 2 * movement + thr["route_progress_tolerance_m"]
                if tracking:
                    cursor = cand
                else:
                    started = False
        else:
            started = False
        s["complete"] = bool(s["complete"] or (started and tracking and cursor >= g.arc[-1] - thr["start_route_tolerance_m"] - 1e-12))
        s["cursor"], s["started"], s["tracked"] = cursor, bool(started), bool(started and tracking)
        s["ever_started"] = s["ever_started"] or bool(started)
        s["prev_p"], s["prev_R"] = p.copy(), R.copy()

    # ------------------------------------------------------------------ per control step
    def _evaluate(self):
        wand = self.scene["wand"]
        sensor = self.scene["wand_contacts"]
        fm = sensor.data.force_matrix_w_history  # (N, T=4, 1, F, 3), newest first
        fmag = torch.linalg.norm(fm, dim=-1)[:, :, 0, :]  # (N, T, F)
        rail_f = fmag[:, :, self._filters["rail"]].amax(dim=1)
        deck_f = fmag[:, 0, self._filters["deck"]]
        robot_f = fmag[:, 0, self._robot_cols].amax(dim=-1)
        # finger sensors (grasp detection) also count as robot contact
        try:
            left, right = self.robot.is_grasping()
            gripped = left | right
        except Exception:
            gripped = torch.zeros_like(self.buzz_success)
        pos = (wand.data.root_link_pos_w - self.scene.env_origins).cpu().numpy()
        quat = wand.data.root_link_quat_w.cpu().numpy()
        lin = torch.linalg.norm(wand.data.root_link_lin_vel_w, dim=-1).cpu().numpy()
        ang = torch.linalg.norm(wand.data.root_link_ang_vel_w, dim=-1).cpu().numpy()
        g, thr = self.geo, self.thr
        sym = np.diag([1.0, -1.0, -1.0])  # half turn about the handle (body x) axis
        diag = []
        for i in range(self.num_envs):
            s = self._trk[i]
            R = _qmat(quat[i])
            dist = float(np.linalg.norm(pos[i] - g.finish_p))
            ang_err = math.degrees(min(_rot_angle(R, g.finish_R), _rot_angle(R, g.finish_R @ sym)))
            if float(rail_f[i]) > 0.0:
                s["force_touch"] = True
                s["first_touch_substep"] = s["first_touch_substep"] or s["substeps"]
            s["max_rail_force"] = max(s["max_rail_force"], float(rail_f[i]))
            touched = s["gap_touch"] or s["force_touch"]
            supported = float(deck_f[i]) > 0.0
            released = (float(robot_f[i]) <= 0.0) and not bool(gripped[i])
            quiet = lin[i] <= thr["maximum_speed_m_s"] and ang[i] <= thr["maximum_angular_speed_rad_s"]
            ok = (s["complete"] and not touched and dist <= thr["finish_position_tolerance_m"]
                  and ang_err <= thr["finish_angle_tolerance_deg"] and supported and released and quiet)
            self.buzz_touched[i] = bool(touched)
            if ok and not self.buzz_success[i]:
                self._ok_steps[i] += 1
            elif not self.buzz_success[i]:
                self._ok_steps[i] = 0
            if self._ok_steps[i] >= self.stable_steps and not touched:
                self.buzz_success[i] = True
            diag.append(dict(touched=bool(touched), gap_touch=s["gap_touch"], force_touch=s["force_touch"],
                             min_gap_m=s["min_gap"], max_rail_force_n=s["max_rail_force"],
                             route_cursor_m=s["cursor"], route_length_m=float(g.arc[-1]), traversal_tracked=s["tracked"],
                             traversal_started_ever=s["ever_started"], traversal_complete=s["complete"],
                             distance_to_finish_m=dist, finish_angle_deg=ang_err, supported=supported,
                             deck_force_n=float(deck_f[i]), released=released, robot_force_n=float(robot_f[i]),
                             gripped=bool(gripped[i]), lin_speed_m_s=float(lin[i]), ang_speed_rad_s=float(ang[i]),
                             quiet=bool(quiet), ok_now=bool(ok), ok_steps=int(self._ok_steps[i]),
                             success=bool(self.buzz_success[i])))
        self.buzz_diag = diag
        return diag

    def get_task_success(self):
        return self.buzz_success.clone()

    def reset_success_check(self, env_ids=None):
        if env_ids is None:
            env_ids = range(self.num_envs)
        self._reset_tracking([int(i) for i in env_ids])

    def get_current_task_info(self):
        wand = self.scene["wand"]
        return {
            "wand_position": wand.data.root_link_pos_w[0].cpu().numpy().tolist(),
            "wand_orientation": wand.data.root_link_quat_w[0].cpu().numpy().tolist(),
            "episode_count": self._episode_count,
            "intermediate_success": {"task_success": bool(self.buzz_success[0])},
            "buzz": (self.buzz_diag[0] if getattr(self, "buzz_diag", None) else {}),
        }

    def buzz_update(self):
        """Evaluate the goal once per control step (called by the termination terms, before any
        auto-reset, and by step() when terminations are disabled)."""
        if getattr(self, "_buzz_eval_step", None) != self.common_step_counter:
            self._buzz_eval_step = self.common_step_counter
            self._evaluate()
        return self.buzz_diag

    def step(self, actions):
        obs, reward, terminated, truncated, info = super().step(actions)
        diag = self.buzz_update()  # no-op if the termination terms already evaluated this step
        success = torch.tensor([d["success"] for d in diag], dtype=torch.bool, device=self.device)
        if hasattr(self, "reset_buf") and torch.any(self.reset_buf):
            self.reset_success_check(self.reset_buf.nonzero(as_tuple=False).squeeze(-1).tolist())
        info["success"] = success
        info["buzz"] = diag
        return obs, reward, terminated, truncated, info

    def reset(self, warm_up=True, seed=None, env_ids=None, options=None):
        self.reset_success_check(env_ids)
        obs, extras = super().reset(warm_up=warm_up, seed=seed, env_ids=env_ids, options=options)
        # warm-up substeps ran the tracker; start the episode from a clean record
        self.reset_success_check(env_ids)
        return obs, extras


gym.register(id="BuzzWire3D-VeryEasy-v0",
             entry_point="yamlab.envs.tasks.buzz_wire_3d_manager:make_buzz_wire_3d_env",
             kwargs={"tier": "very_easy"})
gym.register(id="BuzzWire3D-Easier-v0",
             entry_point="yamlab.envs.tasks.buzz_wire_3d_manager:make_buzz_wire_3d_env",
             kwargs={"tier": "easier"})
