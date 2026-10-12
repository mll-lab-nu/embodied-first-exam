# Physics-only YAMLab smoke test (no RTX): PutPotOnCooktop-v0 with the camera sensors stripped
# from the scene cfg, proprioception only, CPU physics, 1 env, 60 control steps.
import argparse, time
from isaaclab.app import AppLauncher
p = argparse.ArgumentParser(); AppLauncher.add_app_launcher_args(p)
args = p.parse_args(); args.headless = True
app = AppLauncher(args).app
import torch
import yamlab.envs.yam_bimanual_scene as ys
_orig = ys.YamBimanualSceneCfg.__post_init__
def _no_cams(self):
    _orig(self)
    for n in list(vars(self)):
        if n.endswith("_camera"):
            setattr(self, n, None)
ys.YamBimanualSceneCfg.__post_init__ = _no_cams
from yamlab.utils.task_creation import create_task_environment
from yamlab.configs import get_objects_randomization, get_task_kwargs
O = "/workspace/yamlab_port/yamlab_datasets/tasks_data/PutPotOnCooktop/objects"
env = create_task_environment(task_name="PutPotOnCooktop-v0",
    assets_instance_paths={"pot": f"{O}/Pot/pot_000", "cooktop": f"{O}/Cooktop/cooktop_000"},
    objects_randomization=get_objects_randomization("PutPotOnCooktop-v0"), mode="evaluation",
    observation_modalities=["proprioception"], num_envs=1, device="cpu",
    **get_task_kwargs("PutPotOnCooktop-v0", "evaluation"))
obs, _ = env.reset()
arm = env.scene["right_arm"]
print("joint_names", arm.joint_names)
print("q0", arm.data.joint_pos[0].tolist())
t = time.time()
a = torch.zeros(1, 14); a[:, 6] = -0.0475; a[:, 13] = -0.0475
for i in range(60):
    a[:, 7:13] = 0.3 * min(1.0, i / 30)
    obs, r, term, trunc, info = env.step(a)
print("q60", arm.data.joint_pos[0].tolist())
print("ee_body", arm.body_names[-3:], arm.data.body_pos_w[0, -3:].tolist())
print("PHYSICS_SMOKE_OK steps/s", 60 / (time.time() - t))
env.close(); app.close()
