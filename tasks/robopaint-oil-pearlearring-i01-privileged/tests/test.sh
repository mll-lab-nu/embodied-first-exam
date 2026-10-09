#!/bin/bash
# Verifier: replay /app/output/trajectory.npz from the graders' frozen instance (the tests/ copy) in two fresh processes and score it.
# Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields, see docs/PROTOCOL.md).
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/PROTOCOL.md §2.6)
mkdir -p /logs/verifier
# Harbor also mounts /logs/verifier into the agent's container: start from an empty directory, so nothing the agent
# left there (a planted reward, a symlink) can count. rm never follows symlinks.
find /logs/verifier -mindepth 1 -maxdepth 1 ! -name test-stdout.txt -exec rm -rf {} +
python /tests/grade.py --family robopaint_oil_pearlearring --instance /tests/instance.json --traj /app/output/trajectory.npz --repeat 2 \
  2> /logs/verifier/grade.log
