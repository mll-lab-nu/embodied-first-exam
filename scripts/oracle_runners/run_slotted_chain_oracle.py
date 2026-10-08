#!/usr/bin/env python3
"""Run the rigid-chain Slotted oracle (topogym.planning.slotted_post_ring.chain) from a setting's reset in one Session:
M1, M2, M3, M4b, M4a, then both hands home, the scene settled and the task's own confirmation window held. Writes
OUT/trajectory.npz (the recorded actions, Session.save_trajectory) and OUT/report.json (the task's status and state
hash, each stage's end check, the bead1 rule, IK jumps, the arm joints' largest step per control step). Exit status 0
when the task succeeds with no bead1-rule step and no IK jump.

The physics runs on the CPU (in the topogym image: Genesis with images/topogym/genesis-1.2.1-cpu-tree.patch); the
session is headless (no cameras, no GPU needed).

    python scripts/oracle_runners/run_slotted_chain_oracle.py --variation hard --out runs/slotted_chain/hard
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SETTLE_STEPS = 40            # after E: both hands home, then held this many control steps,
MORE_SETTLE_STEPS = 160      # and up to this many more (in 20s) while a part still moves
GOAL_HOLD_S = 2.             # then the final targets held at most this long, for the task's own episode end
JOINT_STEP_LIMIT_RAD = .04   # the standard service's per-control-step arm joint target limit
RULE_EVERY = 5               # the bead1 rule checked every this many control steps


def commit():
    """(HEAD, files changed against it) of the repository, None where git is not available."""
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True,
                               text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None, None
    return head.stdout.strip(), [line[3:] for line in dirty.stdout.splitlines()]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--variation", default="hard", choices=("hard", "medium", "easy"))
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    from topogym.planning.slotted_post_ring.chain import oracle, states
    from topogym.planning.slotted_post_ring.chain.motion import Hands, StageFailure
    from topogym.planning.slotted_post_ring.chain.session import build_session, scene
    a.out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    session = build_session(variation=f"slotted_post_ring_{a.variation}_chain")
    task = session.env._task
    log = []
    H = Hands(session, log)
    report = dict(variation=session.config["variation_id"])
    rule_steps, plain_step = [], session.step

    def step(*args, **kw):                   # the lifted ring never passes the post with bead1 in its hole
        out = plain_step(*args, **kw)
        if session.n_steps % RULE_EVERY == 0 and states.bead1_with_post_in_hole(scene(session), task.layout):
            rule_steps.append(int(session.n_steps))
        return out
    session.step = step
    session.record_start()
    try:
        oracle.run(H)
    except (StageFailure, RuntimeError) as exc:
        report["failure"] = f"{type(exc).__name__}: {exc}"[:1500]
        traceback.print_exc()
    for hand in ("A", "B"):
        H.go_home(hand)
    H.hold(SETTLE_STEPS)
    for _ in range(MORE_SETTLE_STEPS//20):
        if scene(session).speed_m_s < states.AT_REST_M_S:
            break
        H.hold(20)
    for _ in range(int(GOAL_HOLD_S*session.control_hz)):
        if session.episode_end is not None:
            break
        H.hold(1)
    actions = session.record_stop()
    session.save_trajectory(actions, a.out/"trajectory.npz")
    arm = [i for i in range(len(session.action_layout)) if i not in set(session.robot.grip_index.values())]
    steps_rad = np.abs(np.diff(actions[:, arm], axis=0)).max(axis=1) if len(actions) > 1 else np.zeros(0)
    head, dirty = commit()
    report.update(episode_end=session.episode_end, status=session.status(), actions=int(len(actions)),
                  stages=[dict(stage=x["stage"], holds=x["holds"], checks=x["checks"]) for x in log
                          if x.get("event") == "stage end"],
                  bead1_rule_steps=rule_steps, ik_jumps=session.safety().get("ik_jumps"),
                  max_joint_step_rad=round(float(steps_rad.max(initial=0.)), 4),
                  rows_over_limit=int((steps_rad > JOINT_STEP_LIMIT_RAD).sum()), safety=session.safety(episode=True),
                  commit=head, changed_files=dirty, wall_s=round(time.time()-started, 1), log=log)
    (a.out/"report.json").write_text(json.dumps(report, indent=1, default=str)+"\n")
    passed = session.episode_end == "success" and not rule_steps and not report["ik_jumps"]
    print(json.dumps({k: report[k] for k in ("variation", "episode_end", "actions", "max_joint_step_rad",
                                             "rows_over_limit", "ik_jumps")}, default=str), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
