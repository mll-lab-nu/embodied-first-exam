#!/usr/bin/env bash
# Push base images (needs: gh auth login && gh auth token | docker login ghcr.io -u <user> --password-stdin).
# An image with images/<name>/BUILD_ONLY (e.g. Isaac Sim inside, which may not be redistributed) is skipped: it is never
# public (PROTOCOL §2.4); maintainers may keep it as a private package for org members, pushed by hand.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
REG="${RCB_IMAGE_REGISTRY:-ghcr.io/mll-lab-nu}"
D=docker; docker ps >/dev/null 2>&1 || D="sg docker -c"
for dir in images/*/; do
  name="$(basename "$dir")"; VER="$(cat "$dir/VERSION" 2>/dev/null || cat images/VERSION)"
  if [ -f "$dir/BUILD_ONLY" ]; then echo "skip $name: images/$name/BUILD_ONLY, never pushed ($(grep -m1 . "$dir/BUILD_ONLY"))"; continue; fi
  for tag in "$VER" latest; do cmd="docker push $REG/eai-$name:$tag"; echo "+ $cmd"; if [ "$D" = docker ]; then eval "$cmd"; else sg docker -c "$cmd"; fi; done
  for sub in "$dir"*/; do   # a second image of the directory (scripts/build_images.sh): eai-<name>-<sub>
    [ -f "$sub/Dockerfile" ] && [ -f "$sub/VERSION" ] || continue
    s="$(basename "$sub")"; SV="$(cat "$sub/VERSION")"
    for tag in "$SV" latest; do cmd="docker push $REG/eai-$name-$s:$tag"; echo "+ $cmd"; if [ "$D" = docker ]; then eval "$cmd"; else sg docker -c "$cmd"; fi; done
  done
done
