#!/bin/bash
# Run one training under a hard memory cap (systemd user scope): at the cap the kernel stops this run, not other
# users' jobs. PYTHON: an interpreter with mujoco==3.3.7, torch, rsl-rl-lib, tensordict.
HERE=$(cd "$(dirname "$0")" && pwd)
exec systemd-run --user --scope -q -p MemoryMax=${RCB_MEM_MAX:-48G} -p MemorySwapMax=0 \
  ${PYTHON:-python} -u "$HERE/train.py" "$@"
