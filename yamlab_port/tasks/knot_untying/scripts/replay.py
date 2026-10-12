"""Open-loop replay of a saved KnotUntying action sequence from the same reset.

  python replay.py --task KnotUntying-VeryEasy-v0 --actions <run>/actions.npy --out <dir> [--enable_cameras]

Without --enable_cameras the camera sensors are stripped (physics only, works on vast). With
--enable_cameras (needs a host where Isaac RTX rendering works) it writes top-camera and
right/left-wrist frames every --frame_every control steps to <out>/frames/ and, if imageio is
available, top.mp4 / wrist.mp4. Reports success, the goal log and a hash of the rope trajectory
(compare rope_state_sha16 with the oracle's metrics.json for bit-identity).
"""
import argparse, hashlib, json, os, sys, time
from isaaclab.app import AppLauncher

p = argparse.ArgumentParser()
p.add_argument("--task", default="KnotUntying-VeryEasy-v0")
p.add_argument("--actions", required=True)
p.add_argument("--out", default="replay_run")
p.add_argument("--frame_every", type=int, default=3)
p.add_argument("--wrist", default="right_wrist", choices=["right_wrist", "left_wrist"])
p.add_argument("--extra_steps", type=int, default=0, help="hold the last action this many more steps")
AppLauncher.add_app_launcher_args(p)
args = p.parse_args()
args.headless = True
app = AppLauncher(args).app

import numpy as np
import torch
from yamlab.utils.task_creation import create_task_environment

os.makedirs(args.out, exist_ok=True)
A = np.load(args.actions)
cams = bool(getattr(args, "enable_cameras", False))
# normal evaluation behaviour: terminations active; the replay stops at the first terminated step
env = create_task_environment(task_name=args.task, assets_instance_paths={}, mode="evaluation",
                              observation_modalities=["proprioception"], num_envs=1, device="cpu",
                              strip_cameras=not cams, timeout_steps=len(A) + args.extra_steps + 10)
env.reset()
frames_top, frames_wr = [], []
if cams:
    os.makedirs(os.path.join(args.out, "frames"), exist_ok=True)


def grab(k):
    top = env.scene["top_camera"].data.output["rgb"][0].cpu().numpy()
    wr = env.scene[f"{args.wrist}_camera"].data.output["rgb"][0].cpu().numpy()
    frames_top.append(top[..., :3].astype(np.uint8)); frames_wr.append(wr[..., :3].astype(np.uint8))
    try:
        import imageio.v2 as iio
        iio.imwrite(os.path.join(args.out, "frames", f"top_{k:05d}.png"), frames_top[-1])
        iio.imwrite(os.path.join(args.out, "frames", f"wrist_{k:05d}.png"), frames_wr[-1])
    except Exception as e:  # noqa
        if k == 0:
            print("[WARN] frame write failed:", e)


rope_pos, log = [], []
latch_gap = None
first_success = None
t0 = time.time()
seq = list(A) + [A[-1]] * args.extra_steps
for k, a in enumerate(seq):
    obs, r, term, trunc, info = env.step(torch.tensor(a, dtype=torch.float32)[None])
    pos, quat, lv, av = env.rope_state(0)
    rope_pos.append(pos.astype(np.float32))
    g = info["goal"][0]
    log.append(dict(step=k + 1, success=bool(info["success"][0]), goal_now=bool(info["goal_now"][0]),
                    n_crossings=g["n_crossings"], minimum_nonlocal_distance_m=g["minimum_nonlocal_distance_m"],
                    maximum_speed_m_s=g["maximum_speed_m_s"], on_table=g["on_table"], planar_clear=g["planar_clear"]))
    if info["success"][0] and first_success is None:
        first_success = k + 1
        latch_gap = g["minimum_nonlocal_distance_m"]
    if cams and k % args.frame_every == 0:
        grab(k)
    if term[0] or trunc[0]:
        break
wall = time.time() - t0
h = hashlib.sha256(np.stack(rope_pos[:len(A)]).tobytes()).hexdigest()[:16]
res = dict(task=args.task, actions=args.actions, steps=len(rope_pos), success=first_success is not None,
           success_step=first_success, latch_min_nonlocal_m=latch_gap, wall_time_s=wall, rope_state_sha16=h, final=log[-1], cameras=cams)
if cams and frames_top:
    try:
        import imageio.v2 as iio
        iio.mimsave(os.path.join(args.out, "top.mp4"), frames_top, fps=30 // args.frame_every)
        iio.mimsave(os.path.join(args.out, "wrist.mp4"), frames_wr, fps=30 // args.frame_every)
    except Exception as e:  # noqa
        print("[WARN] video write failed:", e)
json.dump(log, open(os.path.join(args.out, "goal_log.json"), "w"))
json.dump(res, open(os.path.join(args.out, "replay_metrics.json"), "w"), indent=1)
np.savez_compressed(os.path.join(args.out, "replay_states.npz"), rope_pos=np.stack(rope_pos))
print("REPLAY", json.dumps(res))
sys.stdout.flush(); os._exit(0)
