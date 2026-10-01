#!/usr/bin/env python3
"""Generate a DexToolBench task's oracle: run SimToolReal's pretrained policy (not shipped; download it separately)
inside rcb_dtb.Session (the exact scene the verifier replays) and save its joint targets.
usage (in an image with torch + the simtoolreal repo at /str incl. pretrained_policy/, rcb_dtb.py on the path):
  python dtb_mk_oracle.py <instance.json> <out oracle_targets.npy>"""
import json, sys, numpy as np
sys.path[:0] = ["/str", "/str/rl_games"]
import rcb_dtb
from deployment.rl_player import RlPlayer
from dextoolbench.objects import NAME_TO_OBJECT
from isaacgymenvs.utils.observation_action_utils_sharpa import compute_observation, compute_joint_pos_targets, create_urdf_object
import torch
inst, out = sys.argv[1], sys.argv[2]
s = rcb_dtb.Session(inst); pol = RlPlayer(num_observations=140, num_actions=29, config_path="/str/pretrained_policy/config.yaml",
                                          checkpoint_path="/str/pretrained_policy/model.pth", device="cpu")
urdf = create_urdf_object(robot_name="iiwa14_left_sharpa_adjusted_restricted"); obs_list = pol.cfg["task"]["env"]["obsList"]
scales = np.array(NAME_TO_OBJECT[s.obj].scale); s.record_start()
while True:
    st = s.state(); g = st["goal"] or s.goals[-1]
    obj = np.concatenate([st["object_pos"], st["object_quat_wxyz"][[1, 2, 3, 0]]]); goal = np.array(g[:3] + g[3:7])
    o = compute_observation(q=st["q"][None], qd=st["qd"][None], prev_action_targets=st["targets"][None], object_pose=obj[None],
                            goal_object_pose=goal[None], object_scales=scales[None], urdf=urdf, obs_list=obs_list)
    a = pol.get_normalized_action(torch.from_numpy(o).float(), deterministic_actions=True)
    tg = compute_joint_pos_targets(actions=a.cpu().numpy(), prev_targets=st["targets"][None], hand_moving_average=0.1, arm_moving_average=0.1,
                                   hand_dof_speed_scale=1.5, dt=rcb_dtb.CONTROL_DT)[0]
    p = s.step(tg)
    if p["done"] or p["failed"]: break
A = s.record_stop(); np.save(out, A); live = s.state_sha()
r1 = s.replay(A); r2 = s.replay(A)
print(json.dumps({"live": p, "live_sha": live, "n": len(A), "replay1": r1, "replay_sha_equal": r1["state_sha"] == r2["state_sha"] == live}))
