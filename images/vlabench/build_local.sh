#!/usr/bin/env bash
# Build vlabench from images/vlabench/Dockerfile with an existing assets checkout instead of the 11 GB Git LFS fetch
# (identical pinned files, checked here). Run from anywhere; the build context is the repository root.
#   bash images/vlabench/build_local.sh /path/to/vlabench-assets   # git checkout of lerobot/vlabench-assets @ 08d7a44
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
assets="${1:?usage: build_local.sh /path/to/vlabench-assets-checkout}"
test "$(git -C "$assets" rev-parse HEAD)" = 08d7a4479a55c8fbb89ac0fd6fcf06e53d65b4a4
git -C "$assets" diff --quiet
git -C "$assets" lfs fsck
context="$(mktemp -d)"
trap 'rm -rf "$context"' EXIT
python3 - "$root/images/vlabench/Dockerfile" "$context/Dockerfile" <<'PY'
import sys
from pathlib import Path

src = Path(sys.argv[1]).read_text()
start = src.index("RUN GIT_LFS_SKIP_SMUDGE=1")
end = src.index("RUN printf", start)
copy = (
    "COPY --from=vlabench_assets /obj /opt/VLABench/VLABench/assets/obj\n"
    "COPY --from=vlabench_assets /scenes /opt/VLABench/VLABench/assets/scenes\n"
)
Path(sys.argv[2]).write_text(src[:start] + copy + src[end:])
PY
docker build --build-context "vlabench_assets=$assets" -f "$context/Dockerfile" \
  -t "ghcr.io/mll-lab-nu/efe-private:vlabench-$(cat "$root/images/vlabench/VERSION")" "$root"
