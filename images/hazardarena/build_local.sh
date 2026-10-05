#!/usr/bin/env bash
# Build eai-hazardarena from images/hazardarena/Dockerfile with an existing assets checkout instead of the 15 GB Git LFS
# fetch (identical pinned files, checked here). Run from anywhere; the build context is the repository root.
#   bash images/hazardarena/build_local.sh /path/to/hazardarena-assets   # git checkout of the HF dataset @ aa1d9e1
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
assets="${1:?usage: build_local.sh /path/to/hazardarena-assets-checkout}"
test "$(git -C "$assets" rev-parse HEAD)" = aa1d9e1b53df2c890707e40ec9fae3481cccb24c
git -C "$assets" diff --quiet
git -C "$assets" lfs fsck
context="$(mktemp -d)"
trap 'rm -rf "$context"' EXIT
python3 - "$root/images/hazardarena/Dockerfile" "$context/Dockerfile" <<'PY'
import sys
from pathlib import Path

src = Path(sys.argv[1]).read_text()
start = src.index("RUN GIT_LFS_SKIP_SMUDGE=1")
end = src.index("RUN printf", start)
copy = "COPY --from=hazardarena_assets /HazardArena/assets /opt/HazardArena/HazardArena/assets\n"
Path(sys.argv[2]).write_text(src[:start] + copy + src[end:])
PY
docker build --build-context "hazardarena_assets=$assets" -f "$context/Dockerfile" \
  -t "ghcr.io/mll-lab-nu/eai-hazardarena:$(cat "$root/images/hazardarena/VERSION")" "$root"
