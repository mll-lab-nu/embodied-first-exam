#!/bin/bash
# Oracle: the reference trajectory (solution/oracle_trajectory.npz, never in the agent image) is the deliverable; the
# verifier replays it like any agent's. The task's README says where it comes from.
set -e
mkdir -p /app/output
cp /solution/oracle_trajectory.npz /app/output/trajectory.npz
