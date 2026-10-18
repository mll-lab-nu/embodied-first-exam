#!/bin/bash
# Reference solution: the human demonstration's actions (float32), replayed through the task tooling until success.
set -e
mkdir -p /app/output
cp /solution/oracle_trajectory.npz /app/output/trajectory.npz
cp /solution/gen.py /app/output/gen.py
