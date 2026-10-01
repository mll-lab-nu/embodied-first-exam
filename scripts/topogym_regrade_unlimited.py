#!/usr/bin/env python3
"""Offline re-grade of one TopoGym UNLIMITED trial whose trajectory holds rows the agent's live session recorded but never
executed (the float32 joint-limit bug; the limited twin is scripts/topogym_regrade_limited.py).

The bug: rcb_topogym.py's Robot clips every row to float32-rounded joint limits, while topogym/robot/joint_position.py
validates the command against the exact model limits and raises ValueError("Joint target outside model limits"). For a
bound where float32 rounds outward (e.g. float32(2.8973) = 2.8973000049591064 on the Panda, float32(3.14158) on the ALOHA
roll joints), a row at that limit (also every row beyond it, which the clip puts there) raises inside Session.step AFTER
the row was appended to the recording and BEFORE the scene was stepped. An agent's saved trajectory can therefore hold
rows its live session never executed, and the verifier's replay raises on the first of them (grader_error 1).

This script runs the task's own tests/grade.py, with the arguments of the task's tests/test.sh, with Session.replay
patched to replay as live did: a row whose command raises exactly that ValueError is skipped; every other row is replayed
normally; all rows are replayed (unlimited has no live end). Nothing else changes: grade.py's own logic (its --repeat
replays in one process, the verdict fields, the video) and its own tooling copy in tests/. It changes nothing in
topogym/, the images or any task dir. grade.py writes reward.json / reward.txt (+ replay.mp4, replay.last.png) into
--out (RCB_VERIFIER_LOG_DIR), and regrade.json records the skipped rows of every replay and, with --original, the
trial's original verdict next to the new one. The original verifier output is only read.

Run it in a fresh container of the trial's verifier image (tests/Dockerfile, FROM the trial's own image), with the
trial's /app/output mounted read-only, e.g. (as bin/tg_regrade.sh does for plain re-grades):
  docker build -t <tag>:verifier <task>/tests
  docker run --rm --network none --runtime nvidia --gpus device=0 -e NVIDIA_DRIVER_CAPABILITIES=all --shm-size 2g \
    -v <trial>/artifacts/app/output:/app/output:ro -v <out>:/out -v scripts/topogym_regrade_unlimited.py:/regrade.py:ro \
    <tag>:verifier python /regrade.py --out /out [--original /orig/reward.json -v <trial>/verifier:/orig:ro]
"""
import argparse
import json
import os
import runpy
import shlex
import sys

import numpy as np

LIVE_ERROR = "Joint target outside model limits"   # topogym/robot/joint_position.py validate_action


def grade_argv(tests: str) -> list[str]:
    """The grade.py command line of the task's own tests/test.sh (without its stderr redirection)."""
    text = open(os.path.join(tests, "test.sh")).read().replace("\\\n", " ")
    line = next(l for l in text.splitlines() if l.strip().startswith("python") and "grade.py" in l)
    argv = shlex.split(line.split(" 2>")[0])
    return argv[next(i for i, x in enumerate(argv) if x.endswith("grade.py")):]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tests", default="/tests", help="the task's tests/ dir (grade.py, rcb_topogym.py, instance.json, test.sh)")
    ap.add_argument("--out", required=True, help="where grade.py writes the new verdict (the original stays untouched)")
    ap.add_argument("--original", help="the trial's original verifier reward.json, reported next to the new verdict")
    a = ap.parse_args()
    argv = grade_argv(a.tests)
    os.makedirs(a.out, exist_ok=True)
    os.environ["RCB_VERIFIER_LOG_DIR"] = a.out      # grade.py's own output location switch
    os.environ["RCB_SESSION_LOG"] = ""

    sys.path.insert(0, a.tests)                     # the tests/ tooling copy, the module grade.py imports
    import rcb_topogym as M
    skipped = []                                    # per replay: indices of the rows whose command raised

    def replay_as_live(self, actions):
        """Session.replay (reset, then step each row until the runaway guard) with the live control flow for the rows
        whose command raises the float32-limit ValueError: live, they were recorded and never stepped."""
        self.reset()
        rows = []
        for i, act in enumerate(np.asarray(actions, dtype=np.float32)):
            try:
                if self.step(act):
                    break
            except ValueError as exc:
                if str(exc) != LIVE_ERROR:
                    raise
                rows.append(i)
        skipped.append(rows)
        return self.status()

    M.Session.replay = replay_as_live
    sys.argv = argv
    try:
        runpy.run_path(argv[0], run_name="__main__")
    except SystemExit:
        pass
    reward = json.load(open(os.path.join(a.out, "reward.json")))
    traj = argv[argv.index("--traj") + 1] if "--traj" in argv else "/app/output/trajectory.npz"
    n_rows = int(np.load(traj, allow_pickle=False)["actions"].shape[0]) if os.path.isfile(traj) else None
    record = dict(script="scripts/topogym_regrade_unlimited.py", grade_argv=argv, trajectory_rows=n_rows,
                  skipped_rows_per_replay=skipped, verdict=reward,
                  original=json.load(open(a.original)) if a.original and os.path.isfile(a.original) else None)
    json.dump(record, open(os.path.join(a.out, "regrade.json"), "w"), indent=1)
    print(json.dumps({k: record[k] for k in ("trajectory_rows", "skipped_rows_per_replay", "verdict", "original")}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
