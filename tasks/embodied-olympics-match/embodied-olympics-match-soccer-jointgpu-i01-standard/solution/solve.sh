#!/bin/bash
# Oracle: our joint-level reference team (capture-point walking) over HTTP, after a short practice-service check.
set -eo pipefail
mkdir -p /app/output
cd /solution && python3 joint_oracle.py --practice-steps 300 2>&1 | tail -c 20000 > /app/output/oracle.log
# the GPU tier: the agent's GPU is visible to the training environment
/opt/train/bin/python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))" > /app/output/gpu_check.txt 2>&1 || true
