#!/usr/bin/env bash
# Reuse verified Git/LFS checkouts without fetching 11 GB again. Infrastructure only.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
assets="${1:?usage: build_local.sh /path/to/vlabench-assets-checkout}"
test "$(git -C "$assets" rev-parse HEAD)" = 08d7a4479a55c8fbb89ac0fd6fcf06e53d65b4a4
git -C "$assets" diff --quiet
git -C "$assets" lfs fsck
# Build the dependency/source stages with the exact same Dockerfile, excluding only
# the final remote asset fetch. The replacement COPY contains identical pinned files.
context="$(mktemp -d)"
trap 'rm -rf "$context"' EXIT
python3 - "$root/images/vlabench/Dockerfile" "$context/Dockerfile" <<'PY'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
start = source.index('RUN GIT_LFS_SKIP_SMUDGE=1')
end = source.index("RUN printf", start)
source = source[:start] + 'COPY --from=vlabench_assets /obj /opt/VLABench/VLABench/assets/obj\nCOPY --from=vlabench_assets /scenes /opt/VLABench/VLABench/assets/scenes\n' + source[end:]
Path(sys.argv[2]).write_text(source)
PY
docker build --build-context "vlabench_assets=$assets" -f "$context/Dockerfile" \
  -t ghcr.io/jameskrw/rcb-vlabench:0.1.1 "$root"
