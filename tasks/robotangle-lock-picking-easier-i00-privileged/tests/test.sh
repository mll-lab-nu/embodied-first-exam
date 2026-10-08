#!/bin/bash
# Verifier: replay /app/output/trajectory.npz from the frozen instance (the tests/ copy) in a fresh process.
# Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields, see docs/rcb/PROTOCOL.md).
# Harbor also mounts /logs/verifier into the agent's container: start from an empty directory, so nothing the agent
# left there (a planted reward, a symlink) can count. rm never follows symlinks.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/rcb/PROTOCOL.md §2.6)
mkdir -p /logs/verifier
python /tests/grade.py --family lock_picking --instance /tests/instance.json --traj /app/output/trajectory.npz --repeat 2 \
  2> /logs/verifier/grade.log
# Recover compatibility rewards if the replay process died after committing its verdict.
python -c "import sys; sys.path.insert(0, '/tests'); from rcb_topogym import recover_reward; recover_reward('/logs/verifier')"
# Atomic publication creates mode 0600 files; the host Harbor reader may have a different UID.
chmod 0644 /logs/verifier/reward.txt /logs/verifier/reward.json
