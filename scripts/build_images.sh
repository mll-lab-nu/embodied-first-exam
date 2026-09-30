#!/usr/bin/env bash
# Build every base image under images/<name>/ as ghcr.io/jameskrw/rcb-<name>:<version> (+ :latest). The version is
# images/<name>/VERSION if present (rcb-mujoco), else images/VERSION. images/<name>/.build-context-self builds with the
# image directory as context (rcb-mujoco COPYs its asset tree rcb_mj/, see prepare_assets.sh); else the repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
REG="${RCB_IMAGE_REGISTRY:-ghcr.io/jameskrw}"
D=docker; docker ps >/dev/null 2>&1 || D="sg docker -c"
for dir in images/*/; do
  name="$(basename "$dir")"
  VER="$(cat "$dir/VERSION" 2>/dev/null || cat images/VERSION)"; CTX=.; [ -f "$dir/.build-context-self" ] && CTX="$dir"
  cmd="docker build -t $REG/rcb-$name:$VER -t $REG/rcb-$name:latest -f $dir/Dockerfile $CTX"
  echo "+ $cmd"; if [ "$D" = docker ]; then eval "$cmd"; else sg docker -c "$cmd"; fi
done
