"""Shared helpers for the CastKeyhole scripts: app launch, env creation, state snapshots, hashing.

Import order matters (Isaac): call ``launch(parser)`` first, then import anything from yamlab.
"""
import argparse
import hashlib
import os
import sys

import numpy as np

TIER_KEYS = {"very_easy": "VeryEasy", "easier": "Easier", "easy": "Easy"}


def base_parser(desc):
    p = argparse.ArgumentParser(description=desc)
    p.add_argument("--tier", default="very_easy", choices=list(TIER_KEYS))
    p.add_argument("--out", required=True, help="output directory")
    p.add_argument("--enable_cameras_frames", action="store_true",
                   help="(replay only) render top + wrist frames; needs a host where RTX works")
    return p


def launch(parser, argv=None):
    from isaaclab.app import AppLauncher
    AppLauncher.add_app_launcher_args(parser)
    args = parser.parse_args(argv)
    args.headless = True
    if not getattr(args, "enable_cameras", False):
        os.environ["YAMLAB_NO_CAMERAS"] = "1"
    app = AppLauncher(args).app
    return args, app


def make_env(tier, cameras=False, clamp=True):
    import yamlab
    print("[ck] yamlab from", yamlab.__file__, flush=True)
    from yamlab.utils.task_creation import create_task_environment
    from yamlab.envs.tasks.cast_keyhole_manager_cfg import asset_paths
    from yamlab.configs import get_task_kwargs
    tid = f"CastKeyhole-{TIER_KEYS[tier]}-v0"
    env = create_task_environment(
        task_name=tid, assets_instance_paths=asset_paths(tier), objects_randomization=None,
        mode="evaluation", observation_modalities=(["rgb", "proprioception"] if cameras else ["proprioception"]),
        num_envs=1, device="cpu", enable_gripper_grasp_clamp=clamp, **get_task_kwargs(tid, "evaluation"))
    return env, tid


def body_pose(arm, name):
    i = arm.body_names.index(name)
    return np.r_[arm.data.body_pos_w[0, i].cpu().numpy(), arm.data.body_quat_w[0, i].cpu().numpy()]


def snapshot(env):
    """Full per-step state (float64 numpy): plates, arms (joints, targets, link_6 + fingers)."""
    s = {}
    for name in ("keyhole_gold", "keyhole_silver"):
        d = env.scene[name].data
        s[name] = np.r_[d.root_pos_w[0].cpu().numpy(), d.root_quat_w[0].cpu().numpy(),
                        d.root_lin_vel_w[0].cpu().numpy(), d.root_ang_vel_w[0].cpu().numpy()].astype(np.float64)
    for arm_name in ("left_arm", "right_arm"):
        arm = env.scene[arm_name]
        s[arm_name + "_q"] = arm.data.joint_pos[0].cpu().numpy().astype(np.float64)
        s[arm_name + "_qtarget"] = arm.data.joint_pos_target[0].cpu().numpy().astype(np.float64)
        s[arm_name + "_link6"] = body_pose(arm, "link_6").astype(np.float64)
    return s


def state_hash(s):
    h = hashlib.sha256()
    for k in sorted(s):
        h.update(k.encode()); h.update(np.ascontiguousarray(s[k], dtype=np.float64).tobytes())
    return h.hexdigest()


def ck_info_numpy(info):
    return {k: (v[0].item() if hasattr(v, "shape") else v) for k, v in info.items()}


def arm_q(env, arm_name):
    return env.scene[arm_name].data.joint_pos[0, :6].cpu().numpy().astype(np.float64)


def tools_path():
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(here, "..", "tools"))
