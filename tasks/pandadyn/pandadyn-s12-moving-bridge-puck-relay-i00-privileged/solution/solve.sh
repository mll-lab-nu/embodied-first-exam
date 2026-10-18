#!/bin/bash
# Oracle: replay the reference rows (solution/oracle_actions.npy: a recorded, replay-checked rollout of this instance by
# the benchmark's reference controller, which reads the simulator's true state) through the agent's own tooling and save
# the trajectory. The rows live in solution/ only (never in the agent image).
set -e
mkdir -p /app/output
cp /solution/oracle.py /app/output/gen.py
python /solution/oracle.py
