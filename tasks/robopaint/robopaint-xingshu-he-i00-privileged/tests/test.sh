#!/bin/bash
# Verifier: replay /app/output/trajectory.npz from the graders' frozen instance (the tests/ copy) in one fresh process and score it.
# Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields, see docs/protocol/README.md).
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/protocol/README.md Appendix H.1)
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resources, after the grader (PROTOCOL §6)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # untrusted agent files (PROTOCOL H.1)
mkdir -p /logs/verifier
# Harbor also mounts /logs/verifier into the agent's container: start from an empty directory, so nothing the agent
# left there (a planted reward, a symlink) can count. rm never follows symlinks.
find /logs/verifier -mindepth 1 -maxdepth 1 ! -name test-stdout.txt -exec rm -rf {} +
python /tests/grade.py --family robopaint_xingshu_he --instance /tests/instance.json --traj /app/output/trajectory.npz \
  2> /logs/verifier/grade.log
