#!/usr/bin/env bash
# Legacy RoboCasa with the object assets needed by the full task set.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"
registry="${RCB_IMAGE_REGISTRY:-ghcr.io/jameskrw}"
# Build this pinned dependency using scripts/robot24/build.py robocasa-gr1 first.
docker image inspect ghcr.io/jameskrw/rcb-robocasa-gr1:0.1.1 >/dev/null
docker build -f images/robocasa/Dockerfile -t ghcr.io/jameskrw/rcb-robocasa:0.1.0 .
docker build -f images/robocasa/Dockerfile.coverage -t "$registry/rcb-robocasa:0.1.1" .
