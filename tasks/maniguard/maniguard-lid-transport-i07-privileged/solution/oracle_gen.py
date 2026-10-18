#!/usr/bin/env python3
"""Reference trajectory of maniguard lid_transport/task_0007 (oracle side only: solution/, never in the agent's reach).

It is built from one of ManiGuard's public demonstrations of this task, episode 280 of the Hugging Face dataset
IDEAS-Lab-Northwestern/datagen-lid-v1-joint-5cam (LeRobot v2.1, 30 Hz, revision b0a8980abaab64e111e07280a1d721ba07033cb9;
(c) IDEAS Lab, Northwestern University, CC BY-NC 4.0, https://creativecommons.org/licenses/by-nc/4.0/), and the trajectory
derived from it is under the same licence. The demonstrations of this task put the lid on the jar (OmniGibson welds it)
and then carry the jar by its lid; ManiGuard's evaluator counts only a grasp of the jar itself as holding it, so none of
them reaches the goal. The carry is redone here:

  1. host:  uv run --no-project --with pyarrow --with numpy python oracle_gen.py --demo-out demo_rows.npz [--parquet episode_000280.parquet]
     the demonstration's commanded joint targets read at the midpoint of each 20 Hz control step (as for the other
     ManiGuard oracles);
  2. simulator (the eai-maniguard image, the task's frozen instance):
     ORACLE_DEMO=demo_rows.npz python rcb_maniguard.py run-oracle --task lid_transport/task_0007 --instance <instance dir> \
         --code oracle_gen.py --out oracle_trajectory.npz
     runs the demonstration's rows up to the lid welded on the jar and released (row K_REL), lifts the hand 5 cm, brings
     the fingertips in at 45° to the jar's wall facing the robot and closes the gripper on it (sticky grasp), lifts the
     jar 1.5 cm and carries it along the countertop to the sphere, the fingertip centre moved in IK steps seeded with the
     measured joints, then holds.
Result: the recorded (T, 8) float32 rows for env.step, which this task's verifier scores 1.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os

import numpy as np

TASK = "lid_transport/task_0007"
REPO = "IDEAS-Lab-Northwestern/datagen-lid-v1-joint-5cam"
REVISION = "b0a8980abaab64e111e07280a1d721ba07033cb9"
EPISODE = 280
PATH = f"data/chunk-000/episode_{EPISODE:06d}.parquet"
SHA256 = "b727f21685117eaed20258b75d868d1215db82c65eb4fdab5b8b3b75f96e573f"
HZ_IN, HZ_OUT = 30.0, 20.0
K_REL = 260                            # row of the resampled demonstration: the lid welded on the jar and released


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


def sim_main(s, ik, move_ee, move_joints, close_gripper, hold, PrimitiveError) -> None:
    """Run inside `rcb_maniguard.py run-oracle` (the session `s` and the primitives are in scope there)."""
    import rcb_maniguard as RM
    from omnigibson.object_states import AttachedTo
    D = np.load(os.environ.get("ORACLE_DEMO", "demo_rows.npz"))["actions"]
    g = s.goal_region(); jar_name = g["target"]
    lid_name = [c for c in s.goal_conditions if c.get("predicate") == "ontop"][0]["subject"]
    for a in D[:K_REL]:
        s.step(a)
    if not s.get_object(lid_name).states[AttachedTo].get_value(s.get_object(jar_name)):
        raise PrimitiveError(f"the lid is not welded to the jar at row {K_REL}")
    ob = s.objects()[jar_name]
    lo, hi = np.array(ob["aabb"][0]), np.array(ob["aabb"][1]); c = (lo + hi) / 2
    base = np.array(s.robot_spec()["base"]["pose"][:3])
    toward = float(np.sign(base[1] - c[1]))                  # the jar's wall facing the robot
    sq = math.sqrt(0.5)
    z_ax = np.array([0.0, -toward * sq, -sq]); y_ax = np.array([1.0, 0.0, 0.0]); x_ax = np.cross(y_ax, z_ax)
    q = RM._xyzw_of_R(np.stack([x_ax, y_ax, z_ax], axis=1))
    wall = np.array([c[0], hi[1] if toward > 0 else lo[1], c[2] + 0.02]) - np.array([0.0, toward * 0.004, 0.0])

    def line_to(p1, n, max_dq=0.01):
        p0 = s.ee_pose("tcp")[0]
        for k in range(1, n + 1):
            sol = ik((p0 + (np.asarray(p1) - p0) * k / n).tolist(), q, seed=s.joint_positions()[:7])
            if sol is None:
                raise PrimitiveError(f"no IK on the line at step {k}")
            move_joints(sol, max_dq=max_dq)
    cur, cq = s.ee_pose("tcp")
    move_ee([cur[0], cur[1], cur[2] + 0.05], cq, max_dq=0.02)
    move_ee((wall + z_ax * -0.15).tolist(), q, max_dq=0.02)
    line_to(wall + z_ax * -0.03, 15)
    line_to(wall, 10, max_dq=0.003)
    close_gripper(15)
    if s.object_in_hand() != jar_name:
        raise PrimitiveError(f"the jar is not held: {s.object_in_hand()}")
    cur = s.ee_pose("tcp")[0]
    line_to([cur[0], cur[1], cur[2] + 0.015], 8)
    cur = s.ee_pose("tcp")[0]
    line_to([cur[0] + (float(g["center"][0]) - c[0]), cur[1], cur[2]], 120, max_dq=0.006)
    hold(40)


if "s" in globals() and hasattr(globals()["s"], "step"):        # exec'd by rcb_maniguard.py run-oracle
    sim_main(s, ik, move_ee, move_joints, close_gripper, hold, PrimitiveError)  # noqa: F821
elif __name__ == "__main__":
    host_main()
