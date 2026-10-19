#!/bin/bash
# Stage the upstream assets of the frozen MolmoSpaces instances for the image (images/molmospaces/build/, not committed):
#   1. build the image's `base` stage (Python environment, experts stubbed, WordNet);
#   2. in a container of it, with network: install_assets.py install (upstream's resource manager downloads what the
#      instances use, a traced run-time build marks the files they open, the rest is deleted, the hashes are checked).
#      The downloads land in $MS_ASSETS_WORK (default /data/$USER/molmospaces/image_assets: several GB before pruning);
#   3. copy the pruned tree, the instances and the tooling into build/.
# Then build the image (scripts/build_images.sh, or `docker build` in this directory: Dockerfile).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../.." && pwd); VER=$(cat "$HERE/VERSION")
WORK="${MS_ASSETS_WORK:-/data/$USER/molmospaces/image_assets}"
BASE="eai-molmospaces-base:$VER"
dk() { if docker ps >/dev/null 2>&1; then docker "$@"; else sg docker -c "docker $(printf '%q ' "$@")"; fi; }

dk build --target base -t "$BASE" "$HERE"
rm -rf "$WORK"; mkdir -p "$WORK/assets" "$WORK/cache" "$WORK/check"
# the frozen instances and the tooling, from the committed privileged tasks (tasks/molmospaces/molmospaces-<base>-privileged/)
mkdir -p "$WORK/check/instances"
for t in "$ROOT"/tasks/molmospaces/molmospaces-*-privileged; do
  b="$(basename "$t")"; b="${b#molmospaces-}"; cp "$t/environment/instance.json" "$WORK/check/instances/${b%-privileged}.json"
done
cp "$t/environment/rcb_molmospaces.py" "$HERE/install_assets.py" "$WORK/check/"
dk run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e RCB_SESSION_LOG= -e MUJOCO_GL=osmesa -e PYOPENGL_PLATFORM=osmesa \
   -e PYTHONPATH=/work --cap-add SYS_PTRACE \
   -v "$WORK/assets:/opt/molmospaces/assets" -v "$WORK/cache:/opt/molmospaces/cache" -v "$WORK/check:/work" -w /work \
   "$BASE" python install_assets.py install instances
rm -rf "$HERE/build"; mkdir -p "$HERE/build"
cp -a "$WORK/assets" "$WORK/cache" "$WORK/check" "$HERE/build/"
du -sh "$HERE/build"
