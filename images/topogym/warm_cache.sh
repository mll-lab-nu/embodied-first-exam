#!/usr/bin/env bash
# Warm the TopoGym image's shared cache on a GPU host and commit it as the published tag (the cache needs the GPU that runs
# the trials: CUDA kernels and Nyx shaders are compiled for its architecture; another GPU still works, it compiles again).
#   images/topogym/warm_cache.sh <base image> <published tag> <gpu> <tasks dir> [<dir glob>]
# <base image> = the plain build of images/topogym/Dockerfile; <tasks dir> = a tasks/ tree whose privileged dirs provide the
# instances (environment/instance.json + instance_assets) and the tooling (environment/rcb_topogym.py). <dir glob> defaults
# to every family's easy tier: the compiled kernels are per family setting, not per tier (2026-10-02: an unwarmed tier of
# a warmed family built in 27.5 s instead of 86.5 s).
set -euo pipefail
BASE=$1; TAG=$2; GPU=$3; TASKS=$(cd "$4" && pwd); GLOB=${5:-topogym-*-easy-i00-privileged}; NAME=rcb-topogym-warm-$$
# The warm-up sessions must not write the agent interaction log (RCB_SESSION_LOG=""), but only their exec gets that
# variable: docker commit keeps the container's environment, and an empty RCB_SESSION_LOG in the published image turned
# the log off in every trial container (images 0.2.14 / 0.2.15).
docker run -d --name "$NAME" --gpus "device=$GPU" -e NVIDIA_DRIVER_CAPABILITIES=all --network none \
  -v "$TASKS":/tasks:ro "$BASE" sleep infinity > /dev/null
trap 'docker rm -f "$NAME" > /dev/null 2>&1 || true' EXIT
docker cp "$(dirname "$0")/warm_cache.py" "$NAME":/opt/warm_cache.py
for dir in "$TASKS"/$GLOB; do
  slug=$(basename "$dir"); fam=$(echo "$slug" | sed -e 's/^topogym-//' -e 's/-\(easy\|medium\|hard\)-i00-privileged$//' -e 's/-/_/g')
  docker exec -e RCB_SESSION_LOG= -w /tmp "$NAME" python /opt/warm_cache.py "$fam" "/tasks/$slug/environment/instance.json" \
    "/tasks/$slug/environment" \
    2> /dev/null | tail -1 || echo "{\"family\": \"$fam\", \"slug\": \"$slug\", \"error\": true}"
done
docker exec "$NAME" bash -c 'rm -rf /tmp/* && chmod -R a+rwX /opt/rcb-cache && du -sh /opt/rcb-cache'
docker commit "$NAME" "$TAG" > /dev/null
if docker image inspect "$TAG" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -q '^RCB_SESSION_LOG='; then
  echo "error: $TAG carries RCB_SESSION_LOG (trial sessions would not be logged)" >&2; exit 1
fi
echo "committed $TAG"
