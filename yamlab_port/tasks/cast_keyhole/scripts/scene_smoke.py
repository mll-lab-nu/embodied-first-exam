"""Scene-only check: load, settle with the arms parked, measure plate drift; validate numpy FK vs Isaac.

usage: python scene_smoke.py --tier very_easy --out runs/smoke_ve [--steps 150]
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ck_env

p = ck_env.base_parser("CastKeyhole scene smoke")
p.add_argument("--steps", type=int, default=150)
args, app = ck_env.launch(p)

import numpy as np
import torch
from scipy.spatial.transform import Rotation

ck_env.tools_path()
import yam_kin as yk

os.makedirs(args.out, exist_ok=True)
env, tid = ck_env.make_env(args.tier)
env.reset()
s0 = ck_env.snapshot(env)
q_test = {"left_arm": [0.6, 1.2, 1.4, -0.5, 0.5, 0.8], "right_arm": [-0.6, 1.0, 1.2, 0.4, -0.5, -0.8]}
a = torch.zeros(1, 14)
a[0, 6] = -0.0475; a[0, 13] = -0.0475
log = []
t = time.time()
for i in range(args.steps):
    if i >= args.steps // 2:      # second half: move both arms (high up) to FK test poses
        u = min(1.0, (i - args.steps // 2) / 30)
        a[0, 0:6] = torch.tensor(q_test["left_arm"]) * u
        a[0, 7:13] = torch.tensor(q_test["right_arm"]) * u
    obs, r, term, trunc, info = env.step(a)
    s = ck_env.snapshot(env)
    log.append(s)
wall = time.time() - t
res = {"task": tid, "steps": args.steps, "wall_s": wall, "steps_per_s": args.steps / wall}
for name in ("keyhole_gold", "keyhole_silver"):
    p0, q0 = s0[name][:3], s0[name][3:7]
    traj = np.array([s[name] for s in log])
    half = args.steps // 2
    p1 = traj[half - 1, :3]
    rot = (Rotation.from_quat(traj[half - 1, [4, 5, 6, 3]]) * Rotation.from_quat(q0[[1, 2, 3, 0]]).inv()).magnitude()
    res[name] = dict(start_pos=p0.tolist(), settle_drift_mm=float(np.linalg.norm(p1 - p0) * 1000),
                     settle_rot_deg=float(np.degrees(rot)), final_speed=float(np.linalg.norm(traj[half - 1, 7:10])),
                     max_speed=float(np.linalg.norm(traj[:half, 7:10], axis=1).max()),
                     end_drift_mm=float(np.linalg.norm(traj[-1, :3] - p0) * 1000))
# FK validation: Isaac link_6 vs numpy FK at the measured joints
for arm_name, side in (("left_arm", "left"), ("right_arm", "right")):
    s = log[-1]
    q = s[arm_name + "_q"][:6]
    T = yk.base_to_world(yk.fk_all(q)[-1], side)
    iso = s[arm_name + "_link6"]
    dq = (Rotation.from_quat(iso[[4, 5, 6, 3]]) * Rotation.from_matrix(T[:3, :3]).inv()).magnitude()
    res[arm_name + "_fk"] = dict(q=q.tolist(), pos_err_mm=float(np.linalg.norm(T[:3, 3] - iso[:3]) * 1000),
                                 rot_err_deg=float(np.degrees(dq)),
                                 q_err=float(np.abs(q - np.array(q_test[arm_name])).max()))
res["info"] = ck_env.ck_info_numpy(info["cast_keyhole"])
print(json.dumps(res, indent=1, default=float))
json.dump(res, open(os.path.join(args.out, "scene_smoke.json"), "w"), indent=1, default=float)
np.savez(os.path.join(args.out, "scene_smoke_states.npz"),
         **{k: np.array([s[k] for s in log]) for k in log[0]})
env.close()
app.close()
