"""Env smoke test: build FiberBundling env (physics only), check start state, FK, settling."""
import argparse, json, os, sys, time
from isaaclab.app import AppLauncher
p = argparse.ArgumentParser(); p.add_argument("--task", default="FiberBundling-VeryEasy-v0"); p.add_argument("--steps", type=int, default=90)
AppLauncher.add_app_launcher_args(p); args = p.parse_args(); args.headless = True
app = AppLauncher(args).app
import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yamlab; print("yamlab from", yamlab.__file__)
from yamlab.utils.task_creation import create_task_environment
import yam_kin
env = create_task_environment(task_name=args.task, assets_instance_paths={}, mode="evaluation",
                              observation_modalities=["proprioception"], num_envs=1, device="cpu")
obs, _ = env.reset()
cab = env.scene["cable"]
lay = env.layout
pos = cab.data.body_link_pos_w[0].numpy()
err = max(np.linalg.norm(pos[i]-np.array(lay["links"][n]["origin"])) for i, n in enumerate(cab.body_names))
print("start link pose error vs layout (mm):", err*1000)
print("env origins", env.scene.env_origins.tolist())
for n in ["terminal", "lead_01", "trunk_00", "trunk_05", "fiber_00_09"]:
    i = cab.body_names.index(n); print(n, "sim", pos[i].round(4), "layout", np.round(lay["links"][n]["origin"], 4))
print("failure", env.failure_reason, env.last_metrics)
print("strand sensor bodies:", env.strand_sensor.body_names[:3], "... n=", len(env.strand_sensor.body_names),
      "filter shape", None if env.strand_sensor.data.force_matrix_w is None else tuple(env.strand_sensor.data.force_matrix_w.shape))
arm = env.scene["left_arm"]
print("left arm joints", arm.joint_names, "bodies", arm.body_names)
# FK check: drive the left arm to a few joint configurations and compare link_6 pose with numpy FK
qs = [np.array([0.3, 1.2, 1.3, -1.2, 0.2, 0.5]), np.array([-0.2, 1.6, 1.7, -1.4, -0.3, -1.0])]
a = torch.zeros(1, 14); a[0, 6] = -0.0475; a[0, 13] = -0.0475
i6 = arm.body_names.index("link_6")
for q in qs:
    a[0, :6] = torch.tensor(q, dtype=torch.float32)
    for _ in range(60):
        obs, r, term, trunc, info = env.step(a)
    qa = arm.data.joint_pos[0, :6].numpy().astype(float)
    T = yam_kin.fk_all(qa, "left")[-1]
    pi = arm.data.body_link_pos_w[0, i6].numpy()
    from yamlab.envs.tasks.fiber_bundling_goal import quat_wxyz_to_mat
    Ri = quat_wxyz_to_mat(arm.data.body_link_quat_w[0, i6].numpy())
    print("q target", q.round(3), "q actual", qa.round(4), "FK pos err (mm)", np.linalg.norm(T[:3, 3]-pi)*1000,
          "rot err (deg)", np.degrees(np.linalg.norm(yam_kin.rot_err(T[:3, :3], Ri))))
print("finger joint", arm.data.joint_pos[0, 6:].tolist())
p1 = cab.data.body_link_pos_w[0].numpy()
print("cable drift after arm motion (mm):", np.abs(p1-pos).max()*1000, "success", bool(info["success"][0]), "failed", bool(info["failed"][0]), info["goal_metrics"][0])
t = time.time()
for _ in range(args.steps):
    obs, r, term, trunc, info = env.step(a)
print("control steps/s", args.steps/(time.time()-t))
sys.stdout.flush(); os._exit(0)
