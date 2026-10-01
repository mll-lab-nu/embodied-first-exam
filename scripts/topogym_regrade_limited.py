#!/usr/bin/env python3
"""Offline re-grade of one TopoGym limited trial whose finalize replay ran past the live episode's end.

The bug (2026-09-30, lab trial hwzz5dq): Session.step records a row BEFORE commanding it. The tooling clips a row to
float32-rounded joint limits (rcb_topogym.py Robot: float(np.float32(limit)), e.g. 3.141580104827881 for the ALOHA roll
joints) while topogym/robot/joint_position.py validates against the exact model limits (3.14158 from the MJCF) and raises
"Joint target outside model limits" instead of clipping. A row at such a limit therefore raises live: it is recorded but
never executed (n_steps does not advance; the server aborts the rest of that chunk). The recorded trajectory then holds
rows the live episode never executed (hwzz5dq: rows 81 and 805, 1113 rows vs 1111 control steps), the sim service's
finalize replay raises on the first of them, replay_success stays null and the verifier reports grader_error 1. After
the live end, rows are also recorded without being commanded; a GPU replay that ends later could command them.

This script replays the trajectory as the live episode executed it: a row whose command raises that same ValueError is
skipped (as live), and the replay stops once it has executed the live episode's control steps (final.json
control_steps, cross-checked against the episode's end event), so post-end rows are never executed either. It wraps
Session.step/reset (the same loop as Session.replay) and changes nothing in topogym/, the images or any task dir. Run
it in a fresh container of the trial's own sim image, on the GPU, from the trial's saved evidence (the sim service's
/data artifacts) and the task's own sim/ dir:

  docker run --rm --runtime nvidia --gpus device=0 -e NVIDIA_DRIVER_CAPABILITIES=all -w /tmp \
    -v <task>-limited/environment/sim:/srv:ro -v <trial artifacts>/data:/evidence:ro -v <out>:/out \
    -v scripts/topogym_regrade_limited.py:/regrade.py:ro -e PYTHONPATH=/srv:/opt/topogym <trial's sim image> \
    python /regrade.py --data /evidence --sim /srv --out /out

It writes <out>/final.json with the fields the limited tests/grade.py reads (live fields kept from the trial's
final.json; replay_success, replay_sha and deterministic from this replay; finalized true) plus a "regrade" record, and
copies trajectory.npz and episode.jsonl, so tests/grade.py can grade <out> as its /data. Only needed when a
live-success trial hit the bug: a live failure stays 0 whatever the replay says.
"""
import argparse
import json
import os
import shutil
import sys
import time

import numpy as np


def replay_as_live(s, acts, n_live):
    """Session.replay's loop (reset, then step each row) with the live episode's control flow: a row whose command
    raised live (joint target at a float32-rounded limit) is skipped, and the loop stops after n_live executed steps."""
    s.reset()
    executed, skipped = 0, []
    for i, a in enumerate(acts):
        if executed >= n_live:
            break
        try:
            guard = s.step(a)
        except ValueError as exc:
            if "outside model limits" not in str(exc):
                raise
            skipped.append(i)
            continue
        executed += 1
        if guard:
            break
    return s.status(), executed, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="the trial's sim /data artifacts: final.json, trajectory.npz, episode.jsonl")
    ap.add_argument("--sim", required=True, help="the task's environment/sim dir: instance.json (+ instance_assets), rcb_topogym.py")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    final = json.load(open(os.path.join(a.data, "final.json")))
    n_live = int(final["control_steps"])
    ends = [e for e in map(json.loads, open(os.path.join(a.data, "episode.jsonl"))) if e.get("ev") == "end"]
    if not ends or int(ends[-1]["control_steps"]) != n_live:
        sys.exit(f"live end mismatch: final.json control_steps {n_live}, episode end events {[e.get('control_steps') for e in ends]}")
    traj = np.load(os.path.join(a.data, "trajectory.npz"), allow_pickle=False)
    acts = np.asarray(traj["actions"], dtype=np.float32)
    instance = os.path.join(a.sim, "instance.json")
    inst = json.load(open(instance))
    if str(traj["instance_sha"]) != inst["state_sha"] or str(traj["task"]) != str(final["task"]):
        sys.exit(f"evidence/task mismatch: trajectory {traj['task']}/{traj['instance_sha']}, task {final['task']}/{inst['state_sha']}")
    if not 0 < n_live <= len(acts):
        sys.exit(f"live end {n_live} outside the recorded {len(acts)} rows")

    os.environ["RCB_SESSION_LOG"] = ""            # as the sim service: no agent-side interaction log
    sys.path.insert(0, a.sim)                     # the task's own tooling copy
    import rcb_topogym as M
    s = M.Session(str(final["task"]), instance=instance, strict=True)
    t0 = time.time()
    rep, executed, skipped = replay_as_live(s, acts, n_live)
    wall = round(time.time() - t0, 1)

    out = dict(final)
    out.update(finalized=True, n_actions=int(len(acts)), replay_success=bool(rep["success"]), replay_sha=rep["state_sha"],
               deterministic=rep["state_sha"] == final.get("live_sha"), video=False, video_done=True,
               regrade=dict(script="scripts/topogym_regrade_limited.py", live_control_steps=n_live, executed_rows=executed,
                            skipped_rows_raised_live=skipped, unreplayed_tail_rows=int(len(acts) - executed - len(skipped)),
                            replay_episode_end=rep.get("episode_end"),
                            replay_sim_steps=rep.get("sim_steps"), instance_matches=bool(s.instance_matches),
                            instance_exact=bool(s.instance_exact), replay_wall_s=wall,
                            original=dict(replay_success=final.get("replay_success"), replay_sha=final.get("replay_sha"),
                                          deterministic=final.get("deterministic"))))
    os.makedirs(a.out, exist_ok=True)
    for f in ("trajectory.npz", "episode.jsonl"):
        shutil.copy(os.path.join(a.data, f), os.path.join(a.out, f))
    json.dump(out, open(os.path.join(a.out, "final.json"), "w"), indent=1)
    print(json.dumps({k: out[k] for k in ("success", "replay_success", "deterministic", "replay_sha", "live_sha", "regrade")}), flush=True)
    s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
