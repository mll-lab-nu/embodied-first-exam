#!/usr/bin/env bash
# Build every base image under images/<name>/ as ghcr.io/mll-lab-nu/eai-<name>:<version> (+ :latest). The version is
# images/<name>/VERSION if present, else images/VERSION. images/<name>/.build-context-self builds with the
# image directory as context (eai-mujoco COPYs its asset tree rcb_mj/, see prepare_assets.sh); images/<name>/BUILD_CONTEXT names
# a context directory a script prepares (skipped while it is missing); else the repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
REG="${RCB_IMAGE_REGISTRY:-ghcr.io/mll-lab-nu}"
D=docker; docker ps >/dev/null 2>&1 || D="sg docker -c"
for dir in images/*/; do
  name="$(basename "$dir")"
  VER="$(cat "$dir/VERSION" 2>/dev/null || cat images/VERSION)"; CTX=.; [ -f "$dir/.build-context-self" ] && CTX="$dir"
  if [ -f "$dir/BUILD_CONTEXT" ]; then   # a context prepared by a script (BUILD_ONLY images; e.g. images/roboarc/)
    CTX="$dir$(cat "$dir/BUILD_CONTEXT")"; [ -d "$CTX" ] || { echo "skip $name: $CTX missing (see $dir/BUILD_ONLY)"; continue; }
  fi
  cmd="docker build -t $REG/eai-$name:$VER -t $REG/eai-$name:latest -f $dir/Dockerfile $CTX"
  echo "+ $cmd"; if [ "$D" = docker ]; then eval "$cmd"; else sg docker -c "$cmd"; fi
done
