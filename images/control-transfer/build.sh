#!/bin/bash
# Base images (not a task: no stamp_mtimes.py stage needed, docs/protocol/running.md "Building task images"): the agent's
# nominal base and the private evaluator, from this directory as the build context (after prepare_assets.py, README.md).
# BUILD_TRAIN=1 also builds the GPU training stage (the G1 family, not shipped as tasks).
set -euo pipefail
cd "$(dirname "$0")"
V=$(cat VERSION)
docker build --target nominal -t ghcr.io/mll-lab-nu/eai-control-transfer:${V}-nominal .
if [ "${BUILD_TRAIN:-0}" = 1 ]; then docker build --target train -t ghcr.io/mll-lab-nu/eai-control-transfer:${V}-train .; fi
docker build --target evaluator -t ghcr.io/mll-lab-nu/eai-control-transfer:${V} .
