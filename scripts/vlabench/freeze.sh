#!/usr/bin/env bash
# Verify the frozen instances and oracles (freeze.py) inside the eai-vlabench image; writes frozen/report.json. The
# committed instances are read from tasks/ (mounted read-only at /tasks), a new import's from frozen/<task>/.
#   bash scripts/vlabench/freeze.sh [task ...]          # FREEZE_JOBS=6 tasks at a time
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
image="ghcr.io/mll-lab-nu/eai-vlabench:$(cat "$root/images/vlabench/VERSION")"
docker run --rm --network none -u "$(id -u):$(id -g)" -e HOME=/tmp -e "FREEZE_JOBS=${FREEZE_JOBS:-6}" \
  -v "$here:/work" -v "$root/tasks:/tasks:ro" -w /work "$image" python freeze.py "$@"
