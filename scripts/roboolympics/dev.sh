#!/bin/bash
# Run python in the simulator image with this directory's sources mounted (development and the families' tests):
#   scripts/roboolympics/dev.sh /rfo/tests/test_sprint.py       # /rfo = scripts/roboolympics (read-only)
#   scripts/roboolympics/dev.sh -c "from rfo.testing import make; ..."
# PYTHONPATH = shared/ (rfo, rcb_rfo); RFO_OUT (default /tmp/rfo_out) is mounted at /out for images and videos.
# RFO_RW=1 mounts /rfo read-write (make_instances.py, make_oracles.py write into this directory).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${RFO_OUT:-/tmp/rfo_out}"; mkdir -p "$OUT"
IMAGE="ghcr.io/mll-lab-nu/eai-robofunolympics:$(cat "$HERE/../../images/robofunolympics/VERSION")"
exec docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONPATH=/work:/rfo/tests -e PYTHONDONTWRITEBYTECODE=1 \
  -e RCB_SESSION_LOG= -v "$HERE/shared:/work:ro" -v "$HERE:/rfo:$([ -n "${RFO_RW:-}" ] && echo rw || echo ro)" -v "$OUT:/out" -w /out "$IMAGE" python "$@"
