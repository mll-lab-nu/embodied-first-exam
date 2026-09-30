"""Verifier-side, inside the sim image: replay and score every episode of one limited HumanoidBench trial, and
render each. Run by scripts/results/collect.py; by hand:
  python replay.py <trial_dir> <task_sim_dir> <out_dir> [--no-render]
      -> <out_dir>/episodes.json, <out_dir>/episodes/epN.mp4 (--no-render: scores only, and keeps the videos an
         earlier episodes.json in <out_dir> names)
Each episode also records how the robot was left (final_head_h: the head's height above the lower foot, m, about
1.6 standing, under 1 sitting on the floor or lying; None on the high bar, where the robot hangs and a handstand is the
task; final_upright: the torso's uprightness, 1 vertical) and, for a multi-stage task, how far it got (progress:
rcb_rewards.progress).
Each replay is checked against the live run: `exact` = it ends in the state the service logged for that episode
(`end_sha` on the reset that ended it; final.json's state_sha for the last). Services before end_sha logged actions
rounded to 5 decimals, so only their graded episode, replayed from trajectory.npz, is exact. None of this was
visible to the agent."""
import json
import os
import sys

import imageio.v2 as imageio
import numpy as np

trial, simdir, out = sys.argv[1:4]
render = "--no-render" not in sys.argv[4:]
sys.path.insert(0, simdir)
from rcb_hb import Session  # noqa: E402  (first: it picks MuJoCo's GL backend, as grade.py and server.py do)
from rcb_rewards import progress, restore  # noqa: E402

restore(os.path.join(simdir, "rewards.json"))

eps, ends, cur = [], [], []
for line in open(f"{trial}/artifacts/data/episode.jsonl"):
    e = json.loads(line)
    if e["ev"] == "step":
        cur.append(e["action"])
    elif e["ev"] == "reset":
        eps.append(cur); ends.append(e.get("end_sha")); cur = []
final = f"{trial}/artifacts/data/final.json"
eps.append(cur); ends.append(json.load(open(final)).get("state_sha") if os.path.exists(final) else None)
traj = f"{trial}/artifacts/data/trajectory.npz"
exact = np.load(traj)["actions"] if os.path.exists(traj) else None

s = Session(instance=os.path.join(simdir, "instance.npz"), enable_render=render)
assert s.scored, "the reward was not restored: cannot score"
hangs = "HighBar" in type(s.low.task).__name__   # the head below the feet is no fall there
os.makedirs(f"{out}/episodes", exist_ok=True)
before = {r["ep"]: r for r in json.load(open(f"{out}/episodes.json"))} if not render and os.path.exists(f"{out}/episodes.json") else {}
rows = []
for i, acts in enumerate(eps):
    graded = i == len(eps) - 1
    A = exact if graded and exact is not None else np.asarray(acts, dtype=np.float64).reshape(-1, s.nu)
    row = {"ep": i, "graded": graded, "exact": None, "n_actions": len(A)}   # None: nothing to replay
    if len(A):
        s.reset(); x0 = float(s.data.qpos[0]); dx = []
        for a in A:
            done = s.step(a)[2]
            dx.append(float(s.data.qpos[0]) - x0)   # the robot's root (pelvis) x, the direction every task faces
            if done:
                break
        st = s.status()
        row["exact"] = s.state_sha() == ends[i]
        robot = s.low.robot
        row.update({"return": round(st["episode_return"], 2), "success": bool(st["success"]), "bar": st["success_bar"],
                    "max_dx": round(max(dx), 2), "final_dx": round(dx[-1], 2), "final_z": round(float(s.data.qpos[2]), 2),
                    "final_upright": round(float(robot.torso_upright()), 2),
                    "final_head_h": None if hangs else round(float(robot.head_height() - min(robot.left_foot_height(), robot.right_foot_height())), 2),
                    **({"progress": p} if (p := progress(s.low.task)) else {})})
        if render:
            s.render_video(A, f"{out}/episodes/ep{i}.mp4", every=2, fps=25)   # real time: 50 Hz control, every 2nd step
            frames = imageio.mimread(f"{out}/episodes/ep{i}.mp4", memtest=False)
            imageio.imwrite(f"{out}/episodes/ep{i}.jpg", frames[int(0.6 * (len(frames) - 1))])   # poster: late, before the end
            row["video"], row["poster"] = f"episodes/ep{i}.mp4", f"episodes/ep{i}.jpg"
        elif (b := before.get(i, {})).get("video") and os.path.exists(f"{out}/{b['video']}"):
            row["video"], row["poster"] = b["video"], b.get("poster")
    rows.append(row)
    print(json.dumps(row), flush=True)
json.dump(rows, open(f"{out}/episodes.json", "w"), indent=1)
