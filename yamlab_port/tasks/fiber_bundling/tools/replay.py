"""Open-loop replay of a saved FiberBundling action sequence from the same reset.

Reports success / failure, per-step state hashes (cable link poses + arm joint positions), and
compares them with the oracle run's states.npz when given. With --enable_cameras (needs an RTX
host; do NOT set YAMLAB_STRIP_CAMERAS) it writes top-camera and left-wrist-camera frames
(PNG every --frame_every steps) and, if imageio is available, MP4 videos.

  physics only (vast): YAMLAB_STRIP_CAMERAS=1 PYTHONPATH=<yamlab> python replay.py --actions A.npy --out D --device cpu
  with video (ws):     PYTHONPATH=<yamlab> python replay.py --actions A.npy --out D --device cpu --enable_cameras
"""
import argparse, hashlib, json, os, sys, time
from isaaclab.app import AppLauncher

p = argparse.ArgumentParser()
p.add_argument("--task", default="FiberBundling-VeryEasy-v0")
p.add_argument("--actions", required=True)
p.add_argument("--out", required=True)
p.add_argument("--reference", default=None, help="states.npz of the oracle run to compare against")
p.add_argument("--frame_every", type=int, default=2)
p.add_argument("--extra_hold", type=int, default=0, help="extra steps holding the last action")
AppLauncher.add_app_launcher_args(p)
args = p.parse_args(); args.headless = True
app = AppLauncher(args).app

import numpy as np, torch
from yamlab.utils.task_creation import create_task_environment

os.makedirs(args.out, exist_ok=True)
cams = bool(getattr(args, "enable_cameras", False))
env = create_task_environment(task_name=args.task, assets_instance_paths={}, mode="evaluation",
                              observation_modalities=["proprioception"], num_envs=1, device=args.device or "cpu",
                              timeout_steps=100000)
env.reset(seed=0)
A = np.load(args.actions)
if args.extra_hold:
    A = np.concatenate([A, np.repeat(A[-1:], args.extra_hold, 0)])
cab, arm = env.scene["cable"], env.scene["left_arm"]
hashes, links, succ, fail, frames = [], [], [], [], {"top": [], "left_wrist": []}
t0 = time.time(); first_success = None; reason = None
for k, a in enumerate(A):
    obs, r, term, trunc, info = env.step(torch.tensor(a).unsqueeze(0))
    s = bool(info["success"][0]); f = bool(info["failed"][0])
    succ.append(s); fail.append(f)
    if s and first_success is None: first_success = k
    if f and reason is None: reason = info["failure_reason"][0]
    pose = env.last_eval_links[0].astype(np.float32)        # evaluated (pre-auto-reset) state
    q = env.last_eval_q["left_arm"][0].astype(np.float32)
    links.append(pose)
    hashes.append(hashlib.sha256(pose.tobytes()+q.tobytes()).hexdigest()[:16])
    if cams and k % args.frame_every == 0:
        for name in frames:
            img = env.scene[f"{name}_camera"].data.output["rgb"][0].cpu().numpy()
            frames[name].append(img[..., :3].astype(np.uint8))
    if bool(term[0]) or bool(trunc[0]):
        break
wall = time.time()-t0
res = dict(task=args.task, actions=args.actions, steps_run=len(succ), success=any(succ), first_success_step=first_success,
           failed=any(fail), failure_reason=reason, wall_time_s=wall, final_state_hash=hashes[-1] if hashes else None,
           state_hash_chain=hashlib.sha256("".join(hashes).encode()).hexdigest())
if args.reference:
    R = np.load(args.reference, allow_pickle=True)["links"]
    n = min(len(R), len(links))
    diff = np.abs(np.array(links[:n])-R[:n]).reshape(n, -1).max(1)
    res.update(reference_steps=int(len(R)), compared_steps=int(n), max_abs_state_diff=float(diff.max()),
               bit_identical=bool(np.all(diff == 0)), first_diff_step=int(np.argmax(diff > 0)) if np.any(diff > 0) else None)
np.savez_compressed(os.path.join(args.out, "replay_states.npz"), links=np.array(links), success=np.array(succ), failed=np.array(fail),
                    hashes=np.array(hashes))
if cams:
    from PIL import Image
    for name, imgs in frames.items():
        d = os.path.join(args.out, f"frames_{name}"); os.makedirs(d, exist_ok=True)
        for i, img in enumerate(imgs):
            Image.fromarray(img).save(os.path.join(d, f"{i:05d}.png"))
        try:
            import imageio
            imageio.mimsave(os.path.join(args.out, f"{name}.mp4"), imgs, fps=int(30/args.frame_every))
        except Exception as e:  # noqa
            print("video write skipped:", e)
json.dump(res, open(os.path.join(args.out, "replay_metrics.json"), "w"), indent=1)
print("REPLAY", json.dumps(res))
sys.stdout.flush(); os._exit(0)
