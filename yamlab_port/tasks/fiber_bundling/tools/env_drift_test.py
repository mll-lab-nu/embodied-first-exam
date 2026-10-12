"""Inside the YAMLab env (arms idle at home): lift trunk_04 with an external PD wrench, measure strand drift
in the trunk_05 frame (compare with strand_drift_test.py, cable-only)."""
import argparse, os, sys
from isaaclab.app import AppLauncher
p = argparse.ArgumentParser(); AppLauncher.add_app_launcher_args(p); p.add_argument("--link", default="trunk_04")
args = p.parse_args(); args.headless = True
app = AppLauncher(args).app
import numpy as np, torch
from scipy.spatial.transform import Rotation
from isaaclab.utils.math import quat_box_minus
from yamlab.utils.task_creation import create_task_environment
env = create_task_environment(task_name="FiberBundling-VeryEasy-v0", assets_instance_paths={}, mode="evaluation",
                              observation_modalities=["proprioception"], num_envs=1, device="cpu", timeout_steps=100000)
env.reset()
cab = env.scene["cable"]; names = cab.body_names; i4 = names.index(args.link); i5 = names.index("trunk_05")
tips = [names.index("fiber_00_09"), names.index("fiber_01_09")]
def local_tips():
    p5 = cab.data.body_link_pos_w[0, i5].numpy(); R5 = Rotation.from_quat(cab.data.body_link_quat_w[0, i5].numpy()[[1, 2, 3, 0]]).as_matrix()
    return [((cab.data.body_link_pos_w[0, t].numpy()-p5) @ R5)*1000 for t in tips]
L0 = local_tips(); p0 = cab.data.body_link_pos_w[0, i4].clone(); q0 = cab.data.body_link_quat_w[0, i4].clone()
m = cab.root_physx_view.get_masses()[0, i4].item()
a = torch.zeros(1, 14); a[0, 6] = -0.0475; a[0, 13] = -0.0475
for k in range(240):
    t = k/30; u = min(max((t-1)/3, 0), 1); u = u*u*(3-2*u)
    target = p0+torch.tensor([0, 0, 0.035*u])
    pos = cab.data.body_link_pos_w[0, i4]; vel = cab.data.body_lin_vel_w[0, i4]
    f = (m*(400*(target-pos)-40*vel)).float()
    err = quat_box_minus(q0.unsqueeze(0), cab.data.body_link_quat_w[0, i4].unsqueeze(0))[0]
    tq = (2e-5*(400*err-40*cab.data.body_ang_vel_w[0, i4])).float()
    cab.set_external_force_and_torque(f.view(1, 1, 3), tq.view(1, 1, 3), body_ids=[i4], is_global=True)
    env.step(a)
    if k % 30 == 0 or k == 239:
        Lt = local_tips()
        print(f"t {t:4.1f} dz {(pos[2]-p0[2]).item()*1000:6.2f} mm tip drift {[round(float(np.linalg.norm(x-y)), 2) for x, y in zip(Lt, L0)]} mm")
sys.stdout.flush(); os._exit(0)
