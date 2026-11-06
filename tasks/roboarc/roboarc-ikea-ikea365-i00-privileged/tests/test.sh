#!/bin/bash
# Verifier: replay /app/output/trajectory.npz from the scene's initial state in two fresh processes.
# Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields, see docs/protocol/README.md).
# Harbor also mounts /logs/verifier into the agent's container: start from an empty directory, so nothing the agent
# left there (a planted reward, a symlink) can count. rm never follows symlinks.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/protocol/README.md Appendix H.1)
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resources, after the grader (PROTOCOL §6)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # untrusted agent files (PROTOCOL H.1)
# The agent's files are untrusted input (PROTOCOL H.1): no link out of /app/output, no FIFO, socket or device.
find /app/output -mindepth 1 \( -type l -o -type p -o -type s -o -type b -o -type c \) -delete 2>/dev/null || true
mkdir -p /logs/verifier
python /tests/grade.py --task ikea365 --binding /tests/runtime_binding.json --traj /app/output/trajectory.npz --repeat 2 --max-rows 495000 --budget-s 5640 \
  2> /logs/verifier/grade.log
chmod 0644 /logs/verifier/reward.txt /logs/verifier/reward.json
