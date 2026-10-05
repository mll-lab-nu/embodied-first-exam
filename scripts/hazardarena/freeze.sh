#!/usr/bin/env bash
# Freeze and verify the instances of tasks.json in eai-hazardarena (freeze.py): HazardArena's own build of each track
# episode, from its full source at the pinned commit (mounted read-only; the image itself holds only the engine), then
# the frozen scene in the image's stripped engine. Writes scripts/hazardarena/frozen/.
#   bash scripts/hazardarena/freeze.sh /path/to/HazardArena [code-iNN ...]     # a checkout of HazardArena @ ab5a8ed
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
src="${1:?usage: freeze.sh /path/to/HazardArena-checkout [code-iNN ...]}"; shift
test "$(git -C "$src" rev-parse HEAD)" = ab5a8ed7b2da502b9b3d7b8b97eb6d296a4a0d2a
git -C "$src" diff --quiet
docker run --rm --network none -u "$(id -u):$(id -g)" -e HOME=/tmp -e FREEZE_JOBS="${FREEZE_JOBS:-4}" \
  -v "$root/scripts/hazardarena:/work" -v "$(cd "$src" && pwd):/opt/ha-src:ro" \
  "ghcr.io/mll-lab-nu/eai-hazardarena:$(cat "$root/images/hazardarena/VERSION")" python /work/freeze.py all "$@"
