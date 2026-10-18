#!/bin/bash
# Oracle: our joint-level reference team (capture-point walking) over HTTP, after a short practice-service check.
set -eo pipefail
mkdir -p /app/output
cd /solution && python3 joint_oracle.py --practice-steps 300 2>&1 | tail -c 20000 > /app/output/oracle.log
