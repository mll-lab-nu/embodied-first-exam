#!/bin/bash
# Reference solution (privileged): the IKEA MuJoCo robot demo's ctrl rows (README.md, Reference solution).
set -euo pipefail
mkdir -p /app/output
cp /solution/trajectory.npz /app/output/trajectory.npz
