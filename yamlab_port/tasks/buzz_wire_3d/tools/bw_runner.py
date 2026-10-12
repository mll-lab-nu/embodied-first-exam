"""Isaac-side helpers for BuzzWire3D runs: env creation, state read-out, stepping with logging.

Import only after the Isaac app is launched.
"""
import hashlib
import json
import os
import time

import numpy as np
import torch
from scipy.spatial.transform import Rotation

TASKS = {"very_easy": "BuzzWire3D-VeryEasy-v0", "easier": "BuzzWire3D-Easier-v0"}
OPEN, CLOSED = -0.0475, 0.0


def make_env(tier, cameras=False):
    from yamlab.utils.task_creation import create_task_environment
    from yamlab.configs import get_task_kwargs
    task = TASKS[tier]
    mods = ["rgb", "proprioception"] if cameras else ["proprioception"]
    env = create_task_environment(task_name=task, assets_instance_paths={}, mode="evaluation",
                                  observation_modalities=mods, num_envs=1, device="cpu",
                                  enable_gripper_grasp_clamp=True, **get_task_kwargs(task, "evaluation"))
    return env


def q_wxyz_to_R(q):
    return Rotation.from_quat([q[1], q[2], q[3], q[0]]).as_matrix()


def T_of(p, q_wxyz):
    T = np.eye(4)
    T[:3, :3] = q_wxyz_to_R(q_wxyz)
    T[:3, 3] = p
    return T


class Runner:
    """Steps the env with 14-D joint targets and records everything needed for replay and evidence."""

    ARM_COLS = {"left": slice(0, 6), "right": slice(7, 13)}
    GRIP_COL = {"left": 6, "right": 13}

    def __init__(self, env, out_dir, frames_dir=None, frame_every=3):
        self.env = env
        self.out_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)
        self.frames_dir = frames_dir
        self.frame_every = frame_every
        self.action = np.zeros(14, dtype=np.float32)
        self.action[6] = OPEN
        self.action[13] = OPEN
        self.actions, self.log, self.diags, self.phases = [], [], [], []
        self.phase = "init"
        self.done = False
        self.term_reason = None
        self.t0 = time.time()
        self.success_step = None
        self.touch_step = None

    # ------------------------------------------------------------------ state
    def arm_q(self, side):
        arm = self.env.scene[f"{side}_arm"]
        jn = arm.joint_names
        q = arm.data.joint_pos[0].cpu().numpy()
        return np.array([q[jn.index(f"joint{i + 1}")] for i in range(6)]), float(q[jn.index("left_finger")])

    def link_T(self, side, link="link_6"):
        arm = self.env.scene[f"{side}_arm"]
        i = arm.body_names.index(link)
        p = arm.data.body_link_pos_w[0, i].cpu().numpy() - self.env.scene.env_origins[0].cpu().numpy()
        return T_of(p, arm.data.body_link_quat_w[0, i].cpu().numpy())

    def wand_T(self):
        w = self.env.scene["wand"]
        p = w.data.root_link_pos_w[0].cpu().numpy() - self.env.scene.env_origins[0].cpu().numpy()
        return T_of(p, w.data.root_link_quat_w[0].cpu().numpy())

    def state_vector(self):
        w = self.env.scene["wand"]
        parts = [w.data.root_link_pos_w[0], w.data.root_link_quat_w[0], w.data.root_link_vel_w[0]]
        for side in ("left", "right"):
            a = self.env.scene[f"{side}_arm"]
            parts += [a.data.joint_pos[0], a.data.joint_vel[0]]
        return torch.cat([x.reshape(-1).cpu() for x in parts]).numpy().astype(np.float64)

    # ------------------------------------------------------------------ stepping
    def set_arm(self, side, q):
        self.action[self.ARM_COLS[side]] = np.asarray(q, dtype=np.float32)

    def set_grip(self, side, g):
        self.action[self.GRIP_COL[side]] = np.float32(g)

    def step(self, n=1):
        for _ in range(n):
            if self.done:
                return
            a = torch.from_numpy(self.action.copy()).unsqueeze(0)
            obs, rew, term, trunc, info = self.env.step(a)
            k = len(self.actions)
            self.actions.append(self.action.copy())
            d = info["buzz"][0]
            self.diags.append(d)
            self.phases.append(self.phase)
            sv = self.state_vector()
            rec = dict(step=k, wand=self.wand_T()[:3, :4].reshape(-1).tolist(), state=sv.tolist())
            for side in ("left", "right"):
                rec[f"{side}_link6"] = self.link_T(side)[:3, :4].reshape(-1).tolist()
            self.log.append(rec)
            if d["touched"] and self.touch_step is None:
                self.touch_step = k
            if d["success"] and self.success_step is None:
                self.success_step = k
            if self.frames_dir and k % self.frame_every == 0:
                self._save_frames(k)
            if bool(term[0]) or bool(trunc[0]):
                self.done = True
                self.term_reason = "success" if d["success"] else ("touch" if d["touched"] else ("timeout" if bool(trunc[0]) else "terminated"))

    def _save_frames(self, k):
        try:
            import imageio.v2 as imageio
        except Exception:
            return
        os.makedirs(self.frames_dir, exist_ok=True)
        for cam in ("top_camera", "right_wrist_camera", "left_wrist_camera"):
            try:
                img = self.env.scene[cam].data.output["rgb"][0].cpu().numpy()
                imageio.imwrite(os.path.join(self.frames_dir, f"{cam}_{k:05d}.png"), img[..., :3])
            except Exception:
                pass

    # ------------------------------------------------------------------ outputs
    def save(self, name, extra=None):
        acts = np.array(self.actions, dtype=np.float32)
        np.save(os.path.join(self.out_dir, f"{name}_actions.npy"), acts)
        states = np.array([r["state"] for r in self.log])
        wand = np.array([r["wand"] for r in self.log])
        l6 = np.array([r["left_link6"] for r in self.log])
        r6 = np.array([r["right_link6"] for r in self.log])
        keys = ["min_gap_m", "max_rail_force_n", "route_cursor_m", "distance_to_finish_m", "finish_angle_deg",
                "deck_force_n", "robot_force_n", "lin_speed_m_s", "ang_speed_rad_s"]
        flags = ["touched", "traversal_tracked", "traversal_complete", "supported", "released", "quiet", "ok_now", "success"]
        diag_num = np.array([[float(d[k]) for k in keys] for d in self.diags])
        diag_flag = np.array([[bool(d[k]) for k in flags] for d in self.diags])
        np.savez_compressed(os.path.join(self.out_dir, f"{name}_states.npz"), actions=acts, states=states, wand_T=wand,
                            left_link6_T=l6, right_link6_T=r6, diag_num=diag_num, diag_num_keys=np.array(keys),
                            diag_flag=diag_flag, diag_flag_keys=np.array(flags), phases=np.array(self.phases))
        h = hashlib.sha256(states.tobytes()).hexdigest()
        last = self.diags[-1] if self.diags else {}
        dt = self.env.cfg.sim.dt * self.env.cfg.decimation
        metrics = dict(name=name, success=bool(last.get("success", False)), success_step=self.success_step,
                       termination=self.term_reason, steps=len(self.actions), sim_time_s=len(self.actions) * dt,
                       wall_time_s=time.time() - self.t0, touched=bool(last.get("touched", False)),
                       first_touch_step=self.touch_step,
                       min_metal_wire_gap_mm=1000 * min((d["min_gap_m"] for d in self.diags), default=1.0),
                       max_rail_force_n=max((d["max_rail_force_n"] for d in self.diags), default=0.0),
                       traversal_complete=bool(last.get("traversal_complete", False)),
                       max_route_cursor_m=max((d["route_cursor_m"] for d in self.diags), default=0.0),
                       route_length_m=last.get("route_length_m"),
                       final=dict((k, last.get(k)) for k in ("distance_to_finish_m", "finish_angle_deg", "supported",
                                                            "released", "quiet", "lin_speed_m_s", "ang_speed_rad_s")),
                       state_sha256=h, phases=sorted(set(self.phases), key=self.phases.index))
        if extra:
            metrics.update(extra)
        json.dump(metrics, open(os.path.join(self.out_dir, f"{name}_metrics.json"), "w"), indent=1)
        return metrics
