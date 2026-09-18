#!/usr/bin/env bash
# Push base images (needs: gh auth login && gh auth token | docker login ghcr.io -u <user> --password-stdin).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
REG="${RCB_IMAGE_REGISTRY:-ghcr.io/jameskrw}"; VER="$(cat images/VERSION)"
D=docker; docker ps >/dev/null 2>&1 || D="sg docker -c"
for dir in images/*/; do
  name="$(basename "$dir")"
  for tag in "$VER" latest; do cmd="docker push $REG/rcb-$name:$tag"; echo "+ $cmd"; if [ "$D" = docker ]; then eval "$cmd"; else sg docker -c "$cmd"; fi; done
done
