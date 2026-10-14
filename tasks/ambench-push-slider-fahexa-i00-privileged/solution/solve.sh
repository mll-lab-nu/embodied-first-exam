#!/bin/bash
# Oracle: replay the reference rows (solution/oracle_actions.npy: AM-Bench's scripted expert for this task, run on this
# instance and recorded, then 2 s of holding its last command; the expert reads the simulator's true state) through the
# agent's own tooling, and save the trajectory. The rows live in solution/ only (never in the agent image, which has no
# expert).
set -e
mkdir -p /app/output
cp /solution/oracle.py /app/output/gen.py
python /solution/oracle.py
