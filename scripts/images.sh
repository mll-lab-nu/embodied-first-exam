#!/usr/bin/env bash
# Build or push every base image under images/<name>/.
#   scripts/images.sh build   build each as ghcr.io/mll-lab-nu/efe:<name>-<version> (+ <name>-latest), or
#                             efe-private:<name>-<version> when images/<name>/BUILD_ONLY marks it private
#   scripts/images.sh push    push them (needs: gh auth login && gh auth token | docker login ghcr.io -u <user> --password-stdin)
# One public and one private package: a new image is a new tag (no package visibility to set). The version is
# images/<name>/VERSION (every image directory has one). images/<name>/.build-context-self builds with the image
# directory as context (images/mujoco/ COPYs its asset tree rcb_mj/, see prepare_assets.sh); images/<name>/BUILD_CONTEXT
# names a context directory a script prepares (skipped while it is missing); else the repo root. A subdirectory
# images/<name>/<sub>/ with its own Dockerfile and VERSION is a second image, <pkg>:<name>-<sub>-<its version>, built after
# <name> with itself as context (e.g. images/ikea-mujoco/sim/, the standard tasks' sidecar image FROM efe:ikea-mujoco-<version>).
# push: an image with images/<name>/BUILD_ONLY (e.g. Isaac Sim inside, which may not be redistributed) is skipped: it is
# never public (PROTOCOL §1); RCB_PUSH_PRIVATE=1 pushes it to the organization's private package efe-private (org members
# only).
# A files-only image (images/<name>/FILES.json) is no docker build: `build` runs scripts/files_image.py build (the same
# digest as the pinned one); `push` skips it, since `docker push` would recompress its layer (another digest): push one
# with scripts/files_image.py push <name> <user> (the token on stdin), then pin it.
set -euo pipefail
case "${1:-}" in build|push) action="$1" ;; *) echo "usage: scripts/images.sh build|push"; exit 2 ;; esac
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
REG="${RCB_IMAGE_REGISTRY:-ghcr.io/mll-lab-nu}"
D=docker; docker ps >/dev/null 2>&1 || D="sg docker -c"
run() { echo "+ $1"; if [ "$D" = docker ]; then eval "$1"; else sg docker -c "$1"; fi; }
for dir in images/*/; do
  name="$(basename "$dir")"; P=efe; [ -f "$dir/BUILD_ONLY" ] && P=efe-private
  if [ -f "$dir/FILES.json" ]; then
    if [ "$action" = build ]; then echo "+ python3 scripts/files_image.py build $name"; python3 scripts/files_image.py build "$name"
    else echo "skip $name: a files-only image (scripts/files_image.py push)"; fi
    continue
  fi
  [ -f "$dir/VERSION" ] || { echo "FAIL $name: no images/$name/VERSION"; exit 1; }
  VER="$(cat "$dir/VERSION")"
  if [ "$action" = build ]; then
    CTX=.; [ -f "$dir/.build-context-self" ] && CTX="$dir"
    if [ -f "$dir/BUILD_CONTEXT" ]; then   # a context prepared by a script (e.g. images/roboarc/)
      CTX="$dir$(cat "$dir/BUILD_CONTEXT")"; [ -d "$CTX" ] || { echo "skip $name: $CTX missing (prepared by a script: see the docs in $dir)"; continue; }
    fi
    # a base image from images/, not a task dir: no scripts/stamp_mtimes.py stamp needed (issue #258 is about task contexts)
    # a private image is the build cache of tasks that build its recipe themselves when they cannot pull it (compose
    # build.cache_from, scripts/task_conventions.py normalize_base_stages): it carries BuildKit's inline cache metadata
    IC=""; [ "$P" = efe-private ] && IC="--build-arg BUILDKIT_INLINE_CACHE=1"
    run "docker build $IC -t $REG/$P:$name-$VER -t $REG/$P:$name-latest -f $dir/Dockerfile $CTX"
  else
    if [ -f "$dir/BUILD_ONLY" ] && [ "${RCB_PUSH_PRIVATE:-0}" != 1 ]; then
      echo "skip $name: images/$name/BUILD_ONLY, never public ($(grep -m1 . "$dir/BUILD_ONLY"))"; continue
    fi
    for tag in "$VER" latest; do run "docker push $REG/$P:$name-$tag"; done
  fi
  for sub in "$dir"*/; do   # a second image of the directory: <pkg>:<name>-<sub>-<version>
    [ -f "$sub/Dockerfile" ] && [ -f "$sub/VERSION" ] || continue
    s="$(basename "$sub")"; SV="$(cat "$sub/VERSION")"
    if [ "$action" = build ]; then run "docker build -t $REG/$P:$name-$s-$SV -t $REG/$P:$name-$s-latest -f $sub/Dockerfile $sub"
    else for tag in "$SV" latest; do run "docker push $REG/$P:$name-$s-$tag"; done; fi
  done
done
