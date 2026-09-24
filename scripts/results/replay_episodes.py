"""Verifier-side, inside the sim image: replay and score every episode of one limited HumanoidBench trial, and
render each. Run by collect.py; by hand:
  python replay_episodes.py <trial_dir> <task_sim_dir> <out_dir>   -> <out_dir>/episodes.json, <out_dir>/episodes/epN.mp4
The sidecar logs each action rounded to 5 decimals, so an earlier episode's replay is approximate; the graded (last)
episode is replayed from the exact trajectory.npz. None of this was visible to the agent."""
import json
import os
import sys

import imageio.v2 as imageio
import numpy as np

trial, simdir, out = sys.argv[1:4]
sys.path.insert(0, simdir)
from rcb_rewards import restore  # noqa: E402

restore(os.path.join(simdir, "rewards.json"))
from rcb_hb import Session  # noqa: E402

eps, cur = [], []
for line in open(f"{trial}/artifacts/data/episode.jsonl"):
    e = json.loads(line)
    if e["ev"] == "step":
        cur.append(e["action"])
    elif e["ev"] == "reset":
        eps.append(cur); cur = []
eps.append(cur)
traj = f"{trial}/artifacts/data/trajectory.npz"
exact = np.load(traj)["actions"] if os.path.exists(traj) else None

s = Session(instance=os.path.join(simdir, "instance.npz"), enable_render=True)
assert s.scored, "the reward was not restored: cannot score"
os.makedirs(f"{out}/episodes", exist_ok=True)
rows = []
for i, acts in enumerate(eps):
    graded = i == len(eps) - 1
    A = exact if graded and exact is not None else np.asarray(acts, dtype=np.float64).reshape(-1, s.nu)
    row = {"ep": i, "graded": graded, "exact": bool(graded and exact is not None), "n_actions": len(A)}
    if len(A):
        s.reset(); x0 = float(s.data.qpos[0]); dx = []
        for a in A:
            done = s.step(a)[2]
            dx.append(float(s.data.qpos[0]) - x0)   # the robot's root (pelvis) x, the direction every task faces
            if done:
                break
        st = s.status()
        row.update({"return": round(st["episode_return"], 2), "success": bool(st["success"]), "bar": st["success_bar"],
                    "max_dx": round(max(dx), 2), "final_dx": round(dx[-1], 2), "final_z": round(float(s.data.qpos[2]), 2)})
        s.render_video(A, f"{out}/episodes/ep{i}.mp4", every=2, fps=25)   # real time: 50 Hz control, every 2nd step
        frames = imageio.mimread(f"{out}/episodes/ep{i}.mp4", memtest=False)
        imageio.imwrite(f"{out}/episodes/ep{i}.jpg", frames[int(0.6 * (len(frames) - 1))])   # poster: late, before the end
        row["video"], row["poster"] = f"episodes/ep{i}.mp4", f"episodes/ep{i}.jpg"
    rows.append(row)
    print(json.dumps(row), flush=True)
json.dump(rows, open(f"{out}/episodes.json", "w"), indent=1)
