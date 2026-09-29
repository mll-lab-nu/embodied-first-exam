"""Verifier-side, inside the sim image: replay every episode of one limited KinDER trial and render each. Run by
scripts/results/collect.py; by hand:
  python replay.py <trial_dir> <task_sim_dir> <out_dir> [--no-render]
      -> <out_dir>/episodes.json, <out_dir>/episodes/epN.mp4 + epN.jpg (--no-render: no videos, and keeps the ones an
         earlier episodes.json in <out_dir> names)
An episode is replayed through the sidecar's own adapter (environment/sim/server.py), from the actions the agent sent
as the service logged them, so it goes through the same odometry-to-world step the live run did. `exact` = it ends in
the state the service logged for that episode (`end_sha` on the reset that ended it; final.json's state_sha for the
last). None of this was visible to the agent."""
import json
import os
import sys

import imageio.v2 as imageio
import numpy as np

trial, simdir, out = sys.argv[1:4]
render = "--no-render" not in sys.argv[4:]
sys.path.insert(0, simdir)
from server import make  # noqa: E402

eps, ends, cur = [], [], []
for line in open(f"{trial}/artifacts/data/episode.jsonl"):
    e = json.loads(line)
    if e["ev"] == "step":
        cur.append((e["type"], e["action"]))
    elif e["ev"] == "reset":
        eps.append(cur); ends.append(e.get("end_sha")); cur = []
final = f"{trial}/artifacts/data/final.json"
eps.append(cur); ends.append(json.load(open(final)).get("state_sha") if os.path.exists(final) else None)

sim = make(os.path.join(simdir, "instance.json"))
os.makedirs(f"{out}/episodes", exist_ok=True)
before = {r["ep"]: r for r in json.load(open(f"{out}/episodes.json"))} if not render and os.path.exists(f"{out}/episodes.json") else {}
rows = []
for i, acts in enumerate(eps):
    row = {"ep": i, "graded": i == len(eps) - 1, "exact": None, "n_actions": len(acts)}   # None: nothing to replay
    if acts:
        sim.reset()
        success = False
        for typ, a in acts:
            done, success, _ = sim.apply(typ, np.asarray(a, dtype=np.float64))
            if done:
                break
        row["exact"], row["success"] = sim.state_sha() == ends[i], bool(success)
        if render:
            every = 1 if sim.s.mujoco else None      # MuJoCo: every step, real time; PyBullet (slow to draw): ~500 frames
            v = sim.s.render_video(sim.actions(), f"{out}/episodes/ep{i}.mp4", every=every, fps=10)
            with imageio.get_reader(f"{out}/episodes/ep{i}.mp4", format="FFMPEG") as r:   # poster: late, before the end
                imageio.imwrite(f"{out}/episodes/ep{i}.jpg", r.get_data(int(0.6 * (r.count_frames() - 1))))
            row["video"], row["poster"], row["video_every"] = f"episodes/ep{i}.mp4", f"episodes/ep{i}.jpg", v["every"]
        elif (b := before.get(i, {})).get("video") and os.path.exists(f"{out}/{b['video']}"):
            row["video"], row["poster"] = b["video"], b.get("poster")
    rows.append(row)
    print(json.dumps(row), flush=True)
json.dump(rows, open(f"{out}/episodes.json", "w"), indent=1)
