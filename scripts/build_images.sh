#!/usr/bin/env bash
# Build every base image under images/<name>/ as ghcr.io/jameskrw/rcb-<name>:<images/VERSION> (+ :latest).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
REG="${RCB_IMAGE_REGISTRY:-ghcr.io/jameskrw}"; VER="$(cat images/VERSION)"
D=docker; docker ps >/dev/null 2>&1 || D="sg docker -c"
for dir in images/*/; do
  name="$(basename "$dir")"
  cmd="docker build -t $REG/rcb-$name:$VER -t $REG/rcb-$name:latest -f $dir/Dockerfile ."
  echo "+ $cmd"; if [ "$D" = docker ]; then eval "$cmd"; else sg docker -c "$cmd"; fi
done
