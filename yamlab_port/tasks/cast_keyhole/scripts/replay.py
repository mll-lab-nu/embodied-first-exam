"""Open-loop replay of a saved CastKeyhole action sequence from the same reset.

usage: python replay.py --tier very_easy --actions runs/oracle_ve/actions.npy --out runs/replay_ve \
           [--reference runs/oracle_ve/states.npz] [--enable_cameras --frame_every 3]

With --enable_cameras (needs a host where Isaac RTX rendering works, e.g. ws/ws3) it writes
frames/top_XXXXX.png and frames/right_wrist_XXXXX.png (and left_wrist) every --frame_every steps;
make a video with e.g. ffmpeg -framerate 10 -i frames/top_%05d.png top.mp4
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ck_env

p = ck_env.base_parser("CastKeyhole open-loop replay")
p.add_argument("--actions", required=True)
p.add_argument("--reference", default=None, help="states.npz of the recorded run, for a bit-identity check")
p.add_argument("--frame_every", type=int, default=3)
p.add_argument("--extra_steps", type=int, default=0, help="hold the last action this many extra steps")
args, app = ck_env.launch(p)

import numpy as np
import torch

os.makedirs(args.out, exist_ok=True)
cams = bool(getattr(args, "enable_cameras", False))
env, tid = ck_env.make_env(args.tier, cameras=cams)
env.reset()
acts = np.load(args.actions)
if args.extra_steps:
    acts = np.concatenate([acts, np.repeat(acts[-1:], args.extra_steps, 0)])
log, hashes = [], []
if cams:
    from PIL import Image
    fdir = os.path.join(args.out, "frames"); os.makedirs(fdir, exist_ok=True)
t = time.time()
for i, a in enumerate(acts):
    obs, rew, term, trunc, info = env.step(torch.as_tensor(a, dtype=torch.float32)[None])
    s = ck_env.snapshot(env)
    for k, v in ck_env.ck_info_numpy(info["cast_keyhole"]).items():
        s["ck_" + k] = np.array(float(v))
    log.append(s)
    hashes.append(ck_env.state_hash({k: v for k, v in s.items() if not k.startswith("ck_")}))
    if cams and i % args.frame_every == 0:
        for cam in ("top", "left_wrist", "right_wrist"):
            img = env.scene[f"{cam}_camera"].data.output["rgb"][0].cpu().numpy()
            Image.fromarray(img[..., :3]).save(os.path.join(fdir, f"{cam}_{i:05d}.png"))
wall = time.time() - t
np.savez(os.path.join(args.out, "states.npz"), **{k: np.array([s[k] for s in log]) for k in log[0]})
succ = [i for i, s in enumerate(log) if s["ck_success"] > 0.5]
m = dict(task=tid, steps=len(acts), sim_time_s=len(acts) / 30.0, wall_time_s=wall,
         success=bool(succ), first_success_step=succ[0] if succ else None,
         final_check={k[3:]: float(v) for k, v in log[-1].items() if k.startswith("ck_")},
         final_state_hash=hashes[-1], cameras=cams)
if args.reference:
    ref = np.load(args.reference)
    n = min(len(log), len(ref["keyhole_gold"]))
    dev = {}
    for k in ("keyhole_gold", "keyhole_silver", "left_arm_q", "right_arm_q"):
        a = np.array([s[k] for s in log[:n]]); b = ref[k][:n]
        dev[k] = dict(max_abs=float(np.abs(a - b).max()), bit_identical=bool(np.array_equal(a, b)),
                      first_diff_step=(int(np.argmax(np.any(a != b, axis=1))) if not np.array_equal(a, b) else None))
    m["vs_reference"] = dev
    m["bit_identical"] = all(d["bit_identical"] for d in dev.values())
json.dump(m, open(os.path.join(args.out, "metrics.json"), "w"), indent=1, default=float)
open(os.path.join(args.out, "state_hashes.txt"), "w").write("\n".join(hashes) + "\n")
print(json.dumps(m, indent=1, default=float), flush=True)
env.close()
app.close()
