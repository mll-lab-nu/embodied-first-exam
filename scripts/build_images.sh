#!/usr/bin/env bash
# Build every base image under images/<name>/ as ghcr.io/mll-lab-nu/efe:<name>-<version> (+ <name>-latest), or
# efe-private:<name>-<version> when images/<name>/BUILD_ONLY marks it private: one public and one private package, a
# new image is a new tag (no package visibility to set). The version is
# images/<name>/VERSION if present, else images/VERSION. images/<name>/.build-context-self builds with the
# image directory as context (eai-mujoco COPYs its asset tree rcb_mj/, see prepare_assets.sh); images/<name>/BUILD_CONTEXT names
# a context directory a script prepares (skipped while it is missing); else the repo root. A subdirectory
# images/<name>/<sub>/ with its own Dockerfile and VERSION is a second image, <pkg>:<name>-<sub>-<its version>, built after
# <name> with itself as context (e.g. images/ikea-mujoco/sim/, the standard tasks' sidecar image FROM eai-ikea-mujoco).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
REG="${RCB_IMAGE_REGISTRY:-ghcr.io/mll-lab-nu}"
D=docker; docker ps >/dev/null 2>&1 || D="sg docker -c"
for dir in images/*/; do
  name="$(basename "$dir")"; P=efe; [ -f "$dir/BUILD_ONLY" ] && P=efe-private
  VER="$(cat "$dir/VERSION" 2>/dev/null || cat images/VERSION)"; CTX=.; [ -f "$dir/.build-context-self" ] && CTX="$dir"
  if [ -f "$dir/BUILD_CONTEXT" ]; then   # a context prepared by a script (e.g. images/roboarc/)
    CTX="$dir$(cat "$dir/BUILD_CONTEXT")"; [ -d "$CTX" ] || { echo "skip $name: $CTX missing (prepared by a script: see the docs in $dir)"; continue; }
  fi
  # a base image from images/, not a task dir: no scripts/stamp_mtimes.py stamp needed (issue #258 is about task contexts)
  cmd="docker build -t $REG/$P:$name-$VER -t $REG/$P:$name-latest -f $dir/Dockerfile $CTX"
  echo "+ $cmd"; if [ "$D" = docker ]; then eval "$cmd"; else sg docker -c "$cmd"; fi
  for sub in "$dir"*/; do
    [ -f "$sub/Dockerfile" ] && [ -f "$sub/VERSION" ] || continue
    s="$(basename "$sub")"; SV="$(cat "$sub/VERSION")"
    cmd="docker build -t $REG/$P:$name-$s-$SV -t $REG/$P:$name-$s-latest -f $sub/Dockerfile $sub"
    echo "+ $cmd"; if [ "$D" = docker ]; then eval "$cmd"; else sg docker -c "$cmd"; fi
  done
done
