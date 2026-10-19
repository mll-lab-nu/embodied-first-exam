#!/usr/bin/env bash
# Push base images (needs: gh auth login && gh auth token | docker login ghcr.io -u <user> --password-stdin).
# An image with images/<name>/BUILD_ONLY (e.g. Isaac Sim inside, which may not be redistributed) is skipped: it is never
# public (PROTOCOL §2.4); RCB_PUSH_PRIVATE=1 pushes it to the organization's private package efe-private (org members
# only). Public images are tags <name>-<version> of the one public package efe: no package visibility to set.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
REG="${RCB_IMAGE_REGISTRY:-ghcr.io/mll-lab-nu}"
D=docker; docker ps >/dev/null 2>&1 || D="sg docker -c"
for dir in images/*/; do
  name="$(basename "$dir")"; VER="$(cat "$dir/VERSION" 2>/dev/null || cat images/VERSION)"
  P=efe
  if [ -f "$dir/BUILD_ONLY" ]; then
    [ "${RCB_PUSH_PRIVATE:-0}" = 1 ] || { echo "skip $name: images/$name/BUILD_ONLY, never public ($(grep -m1 . "$dir/BUILD_ONLY"))"; continue; }
    P=efe-private
  fi
  for tag in "$VER" latest; do cmd="docker push $REG/$P:$name-$tag"; echo "+ $cmd"; if [ "$D" = docker ]; then eval "$cmd"; else sg docker -c "$cmd"; fi; done
  for sub in "$dir"*/; do   # a second image of the directory (scripts/build_images.sh): <pkg>:<name>-<sub>-<version>
    [ -f "$sub/Dockerfile" ] && [ -f "$sub/VERSION" ] || continue
    s="$(basename "$sub")"; SV="$(cat "$sub/VERSION")"
    for tag in "$SV" latest; do cmd="docker push $REG/$P:$name-$s-$tag"; echo "+ $cmd"; if [ "$D" = docker ]; then eval "$cmd"; else sg docker -c "$cmd"; fi; done
  done
done
