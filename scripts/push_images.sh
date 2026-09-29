#!/usr/bin/env bash
# Push base images, named one by one: `scripts/push_images.sh topogym` (no default: every push is a choice).
# TopoGym (adapted from robot_coding_bench fa59c1a6): registry ghcr.io/luigivamper; rcb-topogym is not pushed until the Nyx
# renderer's redistribution terms are confirmed (it is built locally with scripts/build_images.sh topogym).
# Registry as in build_images.sh. Needs `docker login ghcr.io` by the package owner (a classic PAT with write:packages,
# or `gh auth refresh -s write:packages && gh auth token | docker login ghcr.io -u <user> --password-stdin`).
# A new ghcr.io package is PRIVATE until its owner sets it public (package settings -> Change visibility).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
[ $# -gt 0 ] || { echo "usage: $0 <image name>... (a directory under images/)" >&2; exit 2; }
REG="${RCB_IMAGE_REGISTRY:-ghcr.io/luigivamper}"; VER="$(cat images/VERSION)"
D=docker; docker ps >/dev/null 2>&1 || D="sg docker -c"
# containerd image store (e.g. the laptop): push the linux/amd64 manifest alone, as built. The image index would also carry
# BuildKit's provenance attestation, which names the (private) source repository and commit.
if [ "$D" = docker ]; then drv="$(docker info -f '{{.DriverStatus}}' 2>/dev/null)"; else drv="$(sg docker -c "docker info -f '{{.DriverStatus}}'" 2>/dev/null)"; fi
P=""; case "$drv" in *io.containerd.snapshotter*) P="--platform linux/amd64" ;; esac
for name in "$@"; do
  dir="images/$name"; [ -f "$dir/Dockerfile" ] || { echo "no $dir/Dockerfile" >&2; exit 2; }
  case "$name" in behavior|robolab)   # NVIDIA Isaac Sim / Omniverse Kit inside: its licence forbids redistribution (NOTICE)
    echo "rcb-$name is never published (NVIDIA Isaac Sim licence, see NOTICE): users build it with scripts/build_images.sh $name" >&2; exit 2 ;;
  topogym)                              # the Nyx renderer inside: redistribution terms not confirmed yet
    echo "rcb-topogym is not published until the Nyx renderer's redistribution terms are confirmed: build it with scripts/build_images.sh topogym" >&2; exit 2 ;;
  esac
  reg="$REG"; case "$name" in robotwin|robosuite) reg="${RCB_IMAGE_REGISTRY:-ghcr.io/jameskrw}" ;; esac
  ver="$VER"; [ -f "$dir/VERSION" ] && ver="$(cat "$dir/VERSION")"       # an image may carry its own VERSION
  for tag in "$ver" latest; do cmd="docker push $P $reg/rcb-$name:$tag"; echo "+ $cmd"; if [ "$D" = docker ]; then eval "$cmd"; else sg docker -c "$cmd"; fi; done
done
