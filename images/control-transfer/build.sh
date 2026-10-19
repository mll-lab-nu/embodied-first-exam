#!/bin/bash
# Base images (not a task: no stamp_mtimes.py stage needed, docs/protocol/running.md "Building task images"): the agent's
# nominal base and the private evaluator, from this directory as the build context (after prepare_assets.py, README.md).
# BUILD_TRAIN=1 also builds the G1 family's GPU training base (the agent's image, -train) FROM the nominal tag;
# TRAIN_ONLY=1 builds only that (a host that pulled the nominal image needs no assets).
set -euo pipefail
cd "$(dirname "$0")"
V=$(cat VERSION)
N=ghcr.io/mll-lab-nu/efe-private:control-transfer-${V}
if [ "${TRAIN_ONLY:-0}" != 1 ]; then docker build --target nominal -t "$N-nominal" .; fi
if [ "${BUILD_TRAIN:-0}" = 1 ] || [ "${TRAIN_ONLY:-0}" = 1 ]; then
  docker build --target train --build-arg NOMINAL_IMAGE="$N-nominal" -t "$N-train" .
fi
if [ "${TRAIN_ONLY:-0}" != 1 ]; then docker build --target evaluator -t "$N" .; fi
