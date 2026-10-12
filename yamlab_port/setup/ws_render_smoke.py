# Render smoke on ws (inside eai-robolab container): YAMLab PutPotOnCooktop-v0 with cameras, 40 steps, PNG frames.
import argparse, os, time
from isaaclab.app import AppLauncher
p = argparse.ArgumentParser(); AppLauncher.add_app_launcher_args(p)
args = p.parse_args(); args.headless = True; args.enable_cameras = True
app = AppLauncher(args).app
import numpy as np, torch
from PIL import Image
from yamlab.utils.task_creation import create_task_environment
from yamlab.configs import get_objects_randomization, get_task_kwargs
O = "/data/yamlab_datasets/tasks_data/PutPotOnCooktop/objects"
env = create_task_environment(task_name="PutPotOnCooktop-v0",
    assets_instance_paths={"pot": f"{O}/Pot/pot_000", "cooktop": f"{O}/Cooktop/cooktop_000"},
    objects_randomization=get_objects_randomization("PutPotOnCooktop-v0"), mode="evaluation",
    observation_modalities=["rgb", "proprioception"], num_envs=1, device="cpu",
    camera_width=640, camera_height=480, image_downsample_factor=1,
    **get_task_kwargs("PutPotOnCooktop-v0", "evaluation"))
obs, _ = env.reset()
out = "/data/out/render_smoke"; os.makedirs(out, exist_ok=True)
a = torch.zeros(1, 14); a[:, 6] = -0.0475; a[:, 13] = -0.0475
t = time.time()
for i in range(40):
    a[:, 7:13] = 0.4 * min(1.0, i / 30)
    obs, *_ = env.step(a)
    if i % 10 == 9:
        for cam in ("top_camera", "right_wrist_camera"):
            img = env.scene[cam].data.output["rgb"][0].cpu().numpy().astype(np.uint8)
            Image.fromarray(img[..., :3]).save(f"{out}/{cam}_{i:03d}.png")
print("RENDER_SMOKE_OK", time.time() - t, sorted(os.listdir(out)))
env.close(); app.close()
