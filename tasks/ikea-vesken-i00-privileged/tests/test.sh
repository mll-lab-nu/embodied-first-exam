#!/bin/bash
# Verifier: replay /app/output/trajectory.npz from the scene's initial state in two fresh processes.
# Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields, see docs/rcb/PROTOCOL.md).
# Harbor also mounts /logs/verifier into the agent's container: start from an empty directory, so nothing the agent
# left there (a planted reward, a symlink) can count. rm never follows symlinks.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/rcb/PROTOCOL.md §2.6)
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resource limits, after the grader (docs/PROTOCOL.md §2.10)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # the agent's files are untrusted input: no link out of /app/output, no FIFO or device (docs/PROTOCOL.md §2.6)
# The agent's files are untrusted input (PROTOCOL v2.0 H.1): no link out of /app/output, no FIFO, socket or device.
find /app/output -mindepth 1 \( -type l -o -type p -o -type s -o -type b -o -type c \) -delete 2>/dev/null || true
mkdir -p /logs/verifier
python /tests/grade.py --task vesken --binding /tests/runtime_binding.json --traj /app/output/trajectory.npz --repeat 2 --max-rows 990000 --budget-s 6060 \
  2> /logs/verifier/grade.log
chmod 0644 /logs/verifier/reward.txt /logs/verifier/reward.json
