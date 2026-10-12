"""Physics probe (not part of the task): do resting plates report quiet velocities?

Places the silver flat on the table (state write, test only) and lets it rest; also measures the interlocked
settled pair. Variants patch the plates' rigid-body / collision properties.

usage: python rest_test.py --tier very_easy --out runs/rest --variant base|vel4|damp|off1|sleep
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ck_env

p = ck_env.base_parser("rest probe")
p.add_argument("--variant", default="base")
args, app = ck_env.launch(p)

import gymnasium as gym
import numpy as np
import torch

import yamlab.envs.tasks.cast_keyhole_manager as mgr
from yamlab.envs.tasks.cast_keyhole_manager_cfg import make_cfg_class, asset_paths
from yamlab.envs.tasks.yam_bimanual_env import make_task_env

cfg_cls = make_cfg_class(args.tier)


def patched_cfg():
    c = cfg_cls()
    for name in ("keyhole_gold", "keyhole_silver"):
        sp = getattr(c.scene, name).spawn
        if args.variant == "vel4":
            sp.rigid_props.solver_velocity_iteration_count = 4
        elif args.variant == "damp":
            sp.rigid_props.linear_damping = 0.5
            sp.rigid_props.angular_damping = 0.5
        elif args.variant == "off1":
            sp.collision_props.contact_offset = 0.001
        elif args.variant == "sleep":
            sp.rigid_props.sleep_threshold = 0.001
            sp.rigid_props.stabilization_threshold = 0.001
    return c


patched_cfg.CONTACT_OBJECT_NAMES = cfg_cls.CONTACT_OBJECT_NAMES
tid = "CastKeyhole-RestProbe-v0"
gym.register(id=tid, entry_point=lambda **kw: make_task_env(patched_cfg, mgr.CastKeyholeManager, **kw))
from yamlab.utils.task_creation import create_task_environment
from yamlab.configs import get_task_kwargs
env = create_task_environment(task_name=tid, assets_instance_paths=asset_paths(args.tier), mode="evaluation",
                              observation_modalities=["proprioception"], num_envs=1, device="cpu",
                              env_name="CastKeyhole-VeryEasy-v0",
                              **get_task_kwargs("CastKeyhole-VeryEasy-v0", "evaluation"))
env.reset()
a = torch.zeros(1, 14); a[0, 6] = -0.0475; a[0, 13] = -0.0475
res = {"variant": args.variant}


def run(n):
    v = []
    for _ in range(n):
        env.step(a)
        s = ck_env.snapshot(env)
        v.append([np.linalg.norm(s[k][7:10]) for k in ("keyhole_gold", "keyhole_silver")] +
                 [np.linalg.norm(s[k][10:13]) for k in ("keyhole_gold", "keyhole_silver")])
    return np.array(v)


v = run(150)
res["interlocked_last1s_max"] = dict(zip(["gold_v", "silver_v", "gold_w", "silver_w"], v[-30:].max(0).round(4).tolist()))
# place the silver alone, flat, inside the goal; gold flat on the system side (test-only state write)
silver, gold = env.scene["keyhole_silver"], env.scene["keyhole_gold"]
from scipy.spatial.transform import Rotation as R
lay = env.ck_layout
ext = {"keyhole_silver": 0.009, "keyhole_gold": 0.009}
q_flat = R.from_euler("x", 90, degrees=True).as_quat()[[3, 0, 1, 2]]      # part y (silver normal) -> vertical
for obj, xy in ((silver, (0.52, 0.143)), (gold, (0.45, -0.08))):
    st = obj.data.default_root_state.clone()
    st[0, 0:3] = torch.tensor([xy[0], xy[1], 0.7517 + 0.0047])
    st[0, 3:7] = torch.tensor(q_flat if obj is silver else R.from_euler("y", 90, degrees=True).as_quat()[[3, 0, 1, 2]])
    st[0, 7:] = 0
    obj.write_root_state_to_sim(st)
v = run(150)
res["alone_flat_last1s_max"] = dict(zip(["gold_v", "silver_v", "gold_w", "silver_w"], v[-30:].max(0).round(4).tolist()))
res["alone_flat_ck"] = ck_env.ck_info_numpy(env.ck_info)
print("REST", json.dumps(res, default=float), flush=True)
os.makedirs(args.out, exist_ok=True)
json.dump(res, open(os.path.join(args.out, f"rest_{args.variant}.json"), "w"), indent=1, default=float)
env.close()
app.close()
