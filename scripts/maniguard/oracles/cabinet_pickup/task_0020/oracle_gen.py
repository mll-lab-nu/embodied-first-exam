#!/usr/bin/env python3
"""Reference trajectory of maniguard cabinet_pickup/task_0020 (oracle side only: solution/, never in the agent's reach).

It is built from one of ManiGuard's public demonstrations of this task, episode 800 of the Hugging Face dataset
IDEAS-Lab-Northwestern/datagen-cabinet-v1-joint-5cam (LeRobot v2.1, 30 Hz, revision ea8d12429d71879f361a8e1ff1ce9ed62e023fb4;
(c) IDEAS Lab, Northwestern University, CC BY-NC 4.0, https://creativecommons.org/licenses/by-nc/4.0/), and the trajectory
derived from it is under the same licence. Replayed as it is, the demonstration's final push leaves the drawer only just
inside the 5 % of its stroke (1.8 cm) that counts as closed (1.73 cm open), so its final push is made a little deeper here
(user decision 2026-10-04: several millimetres of margin):

  1. host:  uv run --no-project --with pyarrow --with numpy python oracle_gen.py --demo-out demo_rows.npz [--parquet episode_000800.parquet]
     the demonstration's commanded joint targets read at the midpoint of each 20 Hz control step (as for the other
     ManiGuard oracles);
  2. simulator (the eai-maniguard image, the task's frozen instance):
     ORACLE_DEMO=demo_rows.npz python rcb_maniguard.py run-oracle --task cabinet_pickup/task_0020 --instance <instance dir> \
         --code oracle_gen.py --out oracle_trajectory.npz
     runs the demonstration's rows as they are up to its final push (row K_PUSH, where its gripper closes in front of the
     drawer), then the push's rows up to the gripper's opening (row K_RELEASE) with the fingertip centre moved further
     along the drawer's closing direction (the task file's slide direction, reversed), ramped from 0 to EXTRA_M over the
     push (IK per row, seeded with the measured joints; the demonstration's orientation kept), then holds that pose with
     the gripper closed until the episode ends.
Result: the recorded (T, 8) float32 rows for env.step, which this task's verifier scores 1.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os

import numpy as np

TASK = "cabinet_pickup/task_0020"
REPO = "IDEAS-Lab-Northwestern/datagen-cabinet-v1-joint-5cam"
REVISION = "ea8d12429d71879f361a8e1ff1ce9ed62e023fb4"
EPISODE = 800
PATH = f"data/chunk-000/episode_{EPISODE:06d}.parquet"
SHA256 = "9e903147bfb462fc6023396d35b9a92db7149aaed99d4b34b994343b894075f6"
HZ_IN, HZ_OUT = 30.0, 20.0
K_PUSH, K_RELEASE = 2059, 2126    # rows of the resampled demonstration: the gripper closes for the final push; it opens again
EXTRA_M = 0.02                      # how much deeper the final push ends (metres, along the drawer's closing direction)


def resample(cmd: np.ndarray) -> np.ndarray:
    n = len(cmd); m = int(math.floor(n / HZ_IN * HZ_OUT))
    out = np.zeros((m, 8), np.float32)
    for k in range(m):
        i = min(n - 1, int(math.floor((k + 0.5) / HZ_OUT * HZ_IN + 1e-9)))
        out[k, :7] = cmd[i, :7]
        out[k, 7] = 1.0 if cmd[i, 7] > 0 else -1.0
    return out


def host_main() -> None:
    import argparse
    import urllib.request
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo-out", required=True)
    ap.add_argument("--parquet", help="a local copy of the episode (default: download it from the pinned revision)")
    a = ap.parse_args()
    raw = open(a.parquet, "rb").read() if a.parquet else \
        urllib.request.urlopen(f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{PATH}", timeout=60).read()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise SystemExit("the episode's sha256 does not match the pinned one")
    import pyarrow.parquet as pq
    cols = pq.read_table(io.BytesIO(raw)).to_pydict()
    assert set(cols["episode_index"]) == {EPISODE}
    rows = resample(np.array(cols["actions_commanded"], np.float32))
    np.savez(a.demo_out, actions=rows, task=TASK, control_hz=20,
             meta=json.dumps({"source": f"hf://datasets/{REPO}@{REVISION}/{PATH}", "license": "CC BY-NC 4.0"}))
    print(json.dumps({"demo_out": a.demo_out, "rows": int(len(rows))}))


def sim_main(s, ik, hold, PrimitiveError) -> None:
    """Run inside `rcb_maniguard.py run-oracle` (the session `s` and the primitives are in scope there)."""
    D = np.load(os.environ.get("ORACLE_DEMO", "demo_rows.npz"))["actions"]
    info = s.diag["cabinet_info"]
    sd = np.asarray(info["slide_dir"], dtype=np.float64)
    close_dir = -np.array([sd[0], sd[1], 0.0]) / float(np.linalg.norm(sd))

    def most_open() -> float:
        return max(float(v["position"]) - float(v["lower"]) for v in s.objects()[info["name"]]["joints"].values())
    for a in D[:K_PUSH]:
        if s.step(a):
            raise PrimitiveError("the episode ended before the final push")
    q_prev = s.joint_positions()[:7]
    for k in range(K_PUSH, K_RELEASE):
        fk = s.kinematics({"op": "fk", "q": D[k, :7].tolist(), "links": ["tcp"]})["poses"]["tcp"]
        d = EXTRA_M * (k - K_PUSH + 1) / (K_RELEASE - K_PUSH)
        sol = ik((np.asarray(fk[:3]) + close_dir * d).tolist(), fk[3:], seed=q_prev)
        if sol is None:
            raise PrimitiveError(f"no IK for the deeper push at row {k}")
        q_prev = sol
        if s.step(np.r_[np.asarray(sol, dtype=np.float32), D[k, 7]]):
            print(json.dumps({"drawer_open_m_at_goal": round(most_open(), 5), "step": s.steps}), flush=True)
            return
    hold(200)
    print(json.dumps({"drawer_open_m_at_goal": round(most_open(), 5), "step": s.steps, "done": s.done}), flush=True)


if "s" in globals() and hasattr(globals()["s"], "step"):        # exec'd by rcb_maniguard.py run-oracle
    sim_main(s, ik, hold, PrimitiveError)  # noqa: F821
elif __name__ == "__main__":
    host_main()
