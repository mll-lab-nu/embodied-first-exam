#!/usr/bin/env bash
# Build every base image under images/<name>/ as <registry>/rcb-<name>:<images/<name>/VERSION or images/VERSION> (+ :latest);
# `scripts/build_images.sh topogym` builds only that one. Registry: ghcr.io/luigivamper (RCB_IMAGE_REGISTRY overrides it).
# TopoGym appends its CUDA profile to both tags and uses that profile's pinned build arguments.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
REG="${RCB_IMAGE_REGISTRY:-ghcr.io/luigivamper}"; VER="$(cat images/VERSION)"
D=docker; docker ps >/dev/null 2>&1 || D="sg docker -c"
dirs=(); for n in "$@"; do dirs+=("images/$n/"); done; [ ${#dirs[@]} -eq 0 ] && dirs=(images/*/)
for dir in "${dirs[@]}"; do
  name="$(basename "$dir")"
  reg="$REG"; case "$name" in robotwin|robosuite) reg="${RCB_IMAGE_REGISTRY:-ghcr.io/jameskrw}" ;; esac
  ver="$VER"; [ -f "${dir%/}/VERSION" ] && ver="$(cat "${dir%/}/VERSION")"       # an image may carry its own VERSION
  args=(docker build -t "$reg/rcb-$name:$ver" -t "$reg/rcb-$name:latest")
  if [ "$name" = topogym ]; then
    profile="${TOPOGYM_CUDA_FLAVOR:-cu128}"
    resolved="$(python3 scripts/cuda_profiles.py --profile "$profile")"
    mapfile -t config <<< "$resolved"
    args=(docker build -t "${config[0]}" -t "$reg/rcb-$name:latest-$profile")
    for value in "${config[@]:1}"; do args+=(--build-arg "$value"); done
  fi
  args+=(-f "$dir/Dockerfile" .)
  printf -v cmd '%q ' "${args[@]}"
  echo "+ $cmd"; if [ "$D" = docker ]; then "${args[@]}"; else sg docker -c "$cmd"; fi
done
