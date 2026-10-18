#!/bin/bash
# Oracle: the standard twin's reference episode as a privileged trajectory (solution/trajectory.npz, never in the agent
# image); the verifier replays it like any agent's.
set -e
mkdir -p /app/output
cp /solution/trajectory.npz /app/output/trajectory.npz
cp /solution/gen.py /app/output/gen.py
