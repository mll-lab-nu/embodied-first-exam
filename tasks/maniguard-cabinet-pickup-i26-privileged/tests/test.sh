#!/bin/bash
# Verifier: replay /app/output/trajectory.npz from the frozen instance (the tests/ copy) in two fresh processes.
# Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields, see docs/benchmarks/maniguard.md).
# Harbor also mounts /logs/verifier into the agent's container: start from an empty directory, so nothing the agent left
# there (a planted reward, a symlink) can count. rm never follows symlinks.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/PROTOCOL.md §2.6)
mkdir -p /logs/verifier
python /tests/grade.py --task cabinet_pickup/task_0026 --instance /tests/instance --traj /app/output/trajectory.npz --repeat 2 \
  2> /logs/verifier/grade.log
