#!/usr/bin/env bash
# Verify the frozen instances and oracles (freeze.py) inside the eai-vlabench image; writes frozen/report.json.
#   bash scripts/vlabench/freeze.sh [task ...]          # FREEZE_JOBS=6 tasks at a time
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
image="ghcr.io/embodied-agent-interface-v2-internal/eai-vlabench:$(cat "$root/images/vlabench/VERSION")"
docker run --rm --network none -u "$(id -u):$(id -g)" -e HOME=/tmp -e "FREEZE_JOBS=${FREEZE_JOBS:-6}" \
  -v "$here:/work" -w /work "$image" python freeze.py "$@"
