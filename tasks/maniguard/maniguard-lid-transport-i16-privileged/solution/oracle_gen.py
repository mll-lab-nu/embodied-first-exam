#!/usr/bin/env python3
"""Reference trajectory of maniguard lid_transport/task_0016 (oracle side only: solution/, never in the agent's reach).

It is built from one of ManiGuard's public demonstrations of this task, episode 640 of the Hugging Face dataset
IDEAS-Lab-Northwestern/datagen-lid-v1-joint-5cam (LeRobot v2.1, 30 Hz, revision b0a8980abaab64e111e07280a1d721ba07033cb9;
(c) IDEAS Lab, Northwestern University, CC BY-NC 4.0, https://creativecommons.org/licenses/by-nc/4.0/), and the trajectory
derived from it is under the same licence. Replayed as it is, the demonstration sets the cap down a little high and
tilted: OmniGibson never welds it to the jug (AttachedTo needs the cap's attachment point within 5 cm and 15° of the
jug's when they touch), and it falls off when the jug is carried. So the cap placement is redone here:

  1. host:  uv run --no-project --with pyarrow --with numpy python oracle_gen.py --demo-out demo_rows.npz [--parquet episode_000640.parquet]
     the demonstration's commanded joint targets read at the midpoint of each 20 Hz control step (as for the other
     ManiGuard oracles);
  2. simulator (the eai-maniguard image, the task's frozen instance):
     ORACLE_DEMO=demo_rows.npz python rcb_maniguard.py run-oracle --task lid_transport/task_0016 --instance <instance dir> \
         --code oracle_gen.py --out oracle_trajectory.npz
     runs the demonstration's rows up to the cap held over the jug (row K_LIFTED), puts the cap's attachment point over the
     jug's (their poses read from the simulator) and lowers it 1.5 mm per two control steps until OmniGibson welds it,
     opens the gripper and lifts the hand 10 cm, goes back over the demonstration's approach of the jug (row K_JOIN) from
     above, and runs the demonstration's remaining rows (the jug taken and carried into the sphere), then 40 hold rows.
Result: the recorded (T, 8) float32 rows for env.step, which this task's verifier scores 1.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os

import numpy as np

TASK = "lid_transport/task_0016"
REPO = "IDEAS-Lab-Northwestern/datagen-lid-v1-joint-5cam"
REVISION = "b0a8980abaab64e111e07280a1d721ba07033cb9"
EPISODE = 640
PATH = f"data/chunk-000/episode_{EPISODE:06d}.parquet"
SHA256 = "66e5077a4bb83d9c8568dd861ba087d255f47541a5db965eb344e5273e36ae26"
HZ_IN, HZ_OUT = 30.0, 20.0
K_LIFTED, K_JOIN = 200, 320            # rows of the resampled demonstration: cap lifted over the jug; approach of the jug


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


def sim_main(s, ik, move_ee, move_joints, open_gripper, hold, PrimitiveError) -> None:
    """Run inside `rcb_maniguard.py run-oracle` (the session `s` and the primitives are in scope there)."""
    import rcb_maniguard as RM
    from omnigibson.object_states import AttachedTo
    D = np.load(os.environ.get("ORACLE_DEMO", "demo_rows.npz"))["actions"]
    lid_name = [c for c in s.goal_conditions if c.get("predicate") == "ontop"][0]["subject"]
    lid, cont = s.get_object(lid_name), s.get_object(s.goal_region()["target"])
    for a in D[:K_LIFTED]:
        s.step(a)
    if s.object_in_hand() != lid_name:
        raise PrimitiveError(f"the lid is not in the hand at row {K_LIFTED}: {s.object_in_hand()}")
    male = [l for l in lid.states[AttachedTo].links.values() if l.meta_link_id.endswith("M")][0]
    fem = [l for l in cont.states[AttachedTo].links.values() if l.meta_link_id.endswith("F")][0]

    def pose(link):
        p, q = link.get_position_orientation()
        return RM._T_of(RM._np(p), RM._np(q))
    tp, tq = s.ee_pose("tcp")
    T_goal = pose(fem) @ np.linalg.inv(pose(male)) @ RM._T_of(tp, tq)     # the hand pose that puts the lid's point on the jug's
    pd, qd = T_goal[:3, 3], RM._xyzw_of_R(T_goal[:3, :3])
    move_ee([pd[0], pd[1], pd[2] + 0.04], qd, max_dq=0.01)
    for _ in range(40):                                                      # down 1.5 mm per two control steps until welded
        if lid.states[AttachedTo].get_value(cont):
            break
        sol = ik([pd[0], pd[1], s.ee_pose("tcp")[0][2] - 0.0015], qd, seed=s.joint_positions()[:7])
        if sol is None:
            raise PrimitiveError("no IK while lowering the lid")
        move_joints(sol, steps=2)
    if not lid.states[AttachedTo].get_value(cont):
        raise PrimitiveError("the lid did not weld to the container")
    open_gripper(15)
    cur, cq = s.ee_pose("tcp")
    p0 = cur.copy()
    for k in range(1, 11):                                                   # straight up 10 cm
        sol = ik([p0[0], p0[1], p0[2] + 0.01 * k], cq, seed=s.joint_positions()[:7])
        move_joints(sol, max_dq=0.01)
    fk = s.kinematics({"op": "fk", "q": D[K_JOIN, :7].tolist(), "links": ["tcp"]})["poses"]["tcp"]
    move_ee([fk[0], fk[1], fk[2] + 0.12], fk[3:], max_dq=0.02)               # over the demonstration's approach of the jug
    move_joints(D[K_JOIN, :7], max_dq=0.01)
    for a in D[K_JOIN:]:
        if s.step(a):
            return
    hold(40)


if "s" in globals() and hasattr(globals()["s"], "step"):        # exec'd by rcb_maniguard.py run-oracle
    sim_main(s, ik, move_ee, move_joints, open_gripper, hold, PrimitiveError)  # noqa: F821
elif __name__ == "__main__":
    host_main()
