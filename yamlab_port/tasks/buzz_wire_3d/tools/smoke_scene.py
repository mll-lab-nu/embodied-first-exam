"""Scene-only smoke test for BuzzWire3D (physics only, CPU): load, settle, FK check of the numpy model.

Run on vast:  BUZZ_NO_CAMERAS=1 PYTHONPATH=$RUN/yamlab python smoke_scene.py --headless --tier very_easy
"""
import argparse
import json
import os
import sys
import time

from isaaclab.app import AppLauncher

p = argparse.ArgumentParser()
p.add_argument("--tier", default="very_easy")
p.add_argument("--steps", type=int, default=150)
p.add_argument("--out", default="smoke.json")
AppLauncher.add_app_launcher_args(p)
args = p.parse_args()
args.headless = True
app = AppLauncher(args).app

import numpy as np
import torch
import yamlab
from yamlab.utils.task_creation import create_task_environment
from yamlab.configs import get_task_kwargs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yam_kin import YamArm

print("yamlab from", yamlab.__file__)
TASK = {"very_easy": "BuzzWire3D-VeryEasy-v0", "easier": "BuzzWire3D-Easier-v0"}[args.tier]
env = create_task_environment(task_name=TASK, assets_instance_paths={}, mode="evaluation",
                              observation_modalities=["proprioception"], num_envs=1, device="cpu",
                              **get_task_kwargs(TASK, "evaluation"))
obs, _ = env.reset()
wand = env.scene["wand"]
p0 = wand.data.root_link_pos_w[0].clone()
q0 = wand.data.root_link_quat_w[0].clone()
print("wand start", p0.tolist(), q0.tolist())
a = torch.zeros(1, 14)
a[:, 6] = -0.0475
a[:, 13] = -0.0475
traj = []
t = time.time()
for i in range(args.steps):
    obs, r, term, trunc, info = env.step(a)
    traj.append(wand.data.root_link_pos_w[0].tolist() + wand.data.root_link_quat_w[0].tolist())
    if i in (0, 1, 10, 50, args.steps - 1):
        d = info["buzz"][0]
        print(i, "dp_mm", ((wand.data.root_link_pos_w[0] - p0) * 1000).round(decimals=3).tolist(),
              {k: (round(v, 5) if isinstance(v, float) else v) for k, v in d.items()})
    if term.any() or trunc.any():
        print("terminated at", i, term, trunc)
        break
rate = args.steps / (time.time() - t)
diag = info["buzz"][0]
# ---- FK check of the numpy model against Isaac link poses (teleport the right arm)
res = {}
for side, name in (("right", "right_arm"), ("left", "left_arm")):
    arm = env.scene[name]
    kin = YamArm(base_pos=tuple(arm.data.root_pos_w[0].tolist()))
    rng = np.random.default_rng(0)
    errs = []
    jn = arm.joint_names
    for k in range(5):
        q = rng.uniform(kin.lo * 0.8, kin.hi * 0.8)
        qq = arm.data.default_joint_pos.clone()
        for j in range(6):
            qq[0, jn.index(f"joint{j + 1}")] = float(q[j])
        fq = -0.02
        qq[0, jn.index("left_finger")] = fq
        qq[0, jn.index("right_finger")] = fq
        arm.write_joint_state_to_sim(qq, torch.zeros_like(qq))
        arm.set_joint_position_target(qq)
        arm.write_data_to_sim()
        env.sim.step(render=False)
        env.scene.update(env.physics_dt)
        qa = arm.data.joint_pos[0]
        q = np.array([float(qa[jn.index(f"joint{j + 1}")]) for j in range(6)])
        fq = float(qa[jn.index("left_finger")])
        T = kin.fk_all(q, fq)
        for link in ("link_6", "left_finger", "right_finger"):
            bi = arm.body_names.index(link)
            pi = arm.data.body_link_pos_w[0, bi].numpy() - env.scene.env_origins[0].numpy()
            qi = arm.data.body_link_quat_w[0, bi].numpy()
            from scipy.spatial.transform import Rotation
            Ri = Rotation.from_quat([qi[1], qi[2], qi[3], qi[0]]).as_matrix()
            errs.append((link, float(np.linalg.norm(pi - T[link][:3, 3])), float(np.degrees(Rotation.from_matrix(Ri @ T[link][:3, :3].T).magnitude()))))
    for e in errs:
        print("   ", side, e[0], "pos err mm %.2f rot deg %.4f" % (e[1] * 1000, e[2]))
    res[side] = dict(max_pos_err_mm=max(e[1] for e in errs) * 1000, max_rot_err_deg=max(e[2] for e in errs),
                     body_names=arm.body_names, joint_names=jn)
    print(side, "FK max pos err mm", res[side]["max_pos_err_mm"], "rot deg", res[side]["max_rot_err_deg"])
out = dict(tier=args.tier, control_steps_per_s=rate, wand_start=[p0.tolist(), q0.tolist()],
           wand_end=traj[-1], drift_mm=float(np.linalg.norm(np.array(traj[-1][:3]) - p0.numpy()) * 1000),
           diag=diag, fk=res, filters=list(env._filters.keys()),
           sensor_shape=list(env.scene["wand_contacts"].data.force_matrix_w_history.shape))
json.dump(out, open(args.out, "w"), indent=1)
print("SMOKE_DONE", json.dumps({k: out[k] for k in ("control_steps_per_s", "drift_mm", "sensor_shape")}))
env.close()
app.close()
