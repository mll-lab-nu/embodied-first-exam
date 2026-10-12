"""Open-loop replay of a saved RopeThreading action sequence from the same reset (adapted from knot_untying's).

  python replay.py --task RopeThreading-Easy-v0 --actions <run>/actions.npy --out <dir> [--enable_cameras]

Without --enable_cameras the camera sensors are stripped (physics only; works on vast). With --enable_cameras
(needs a host where Isaac RTX rendering works, e.g. ws in the eai-robolab:0.1.2 container) it writes top-camera
and wrist-camera frames every --frame_every control steps to <out>/frames/ and, if imageio is available,
top.mp4 / wrist.mp4. Reports success, the first success step and the rope trajectory hash (compare
rope_state_sha16 with the oracle's metrics.json for bit-identity on the same host/stack).
"""
import argparse, hashlib, json, os, sys, time
from isaaclab.app import AppLauncher

p = argparse.ArgumentParser()
p.add_argument("--task", default="RopeThreading-Easy-v0")
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
env = create_task_environment(task_name=args.task, assets_instance_paths={}, mode="evaluation",
                              observation_modalities=["proprioception"], num_envs=1, device="cpu",
                              strip_cameras=not cams)
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
first_success = None
t0 = time.time()
seq = list(A) + [A[-1]] * args.extra_steps
for k, a in enumerate(seq):
    obs, r, term, trunc, info = env.step(torch.tensor(a, dtype=torch.float32)[None])
    pos, quat, _, _ = env.rope_state(0)
    rope_pos.append(pos.astype(np.float32))
    g = info["goal"][0]
    log.append(dict(step=k + 1, success=bool(info["success"][0]), threaded=g.get("threaded"), quiet=g.get("quiet"),
                    crossing_sequence=g.get("crossing_sequence"), maximum_speed_m_s=g.get("maximum_speed_m_s"),
                    strict_threaded=g.get("strict_threaded"), strict_quiet=g.get("strict_quiet")))
    if log[-1]["success"] and first_success is None:
        first_success = k + 1
    if cams and k % args.frame_every == 0:
        grab(k)
    if bool(term[0] or trunc[0]):
        break
sha = hashlib.sha256(np.ascontiguousarray(np.stack(rope_pos)).tobytes()).hexdigest()[:16]
if cams and frames_top:
    try:
        import imageio.v2 as iio
        fps = 30 // args.frame_every
        iio.mimwrite(os.path.join(args.out, "top.mp4"), frames_top, fps=fps)
        iio.mimwrite(os.path.join(args.out, "wrist.mp4"), frames_wr, fps=fps)
    except Exception as e:  # noqa
        print("[WARN] video write failed:", e)
m = dict(success=first_success is not None, first_success_step=first_success, steps=len(log),
         sim_time_s=len(log) * env.step_dt, wall_time_s=time.time() - t0, rope_state_sha16=sha, final=log[-1], cameras=cams)
json.dump(m, open(os.path.join(args.out, "metrics.json"), "w"), indent=1)
np.savez_compressed(os.path.join(args.out, "states.npz"), rope_pos=np.stack(rope_pos))
print("REPLAY", json.dumps(m))
sys.stdout.flush(); os._exit(0)
