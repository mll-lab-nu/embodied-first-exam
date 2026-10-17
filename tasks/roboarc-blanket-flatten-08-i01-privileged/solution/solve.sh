#!/bin/bash
# Reference solution (privileged): the trajectory the author's oracle produced and the verifier scored 1
# on the evidence run named in README.md (Reference solution). Uses nothing but the recorded file.
set -euo pipefail
mkdir -p /app/output
cp /solution/trajectory.npz /app/output/trajectory.npz
