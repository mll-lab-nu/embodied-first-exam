#!/usr/bin/env bash
# Prepare the RoboTangle image build context images/robotangle/context/ (images/robotangle/BUILD_CONTEXT):
#   - the paths images/robotangle/Dockerfile copies, from the release commit (scripts/robotangle/release.json
#     release_commit, a commit of dev/robotangle_mujoco in this repository): topogym/, assets/robots/,
#     images/topogym/prune.py, images/robotangle/vbd-requirements.txt, images/robotangle/warp_precompile.py;
#   - instances/: every task's frozen MuJoCo instance, from the private HF dataset at the revision pinned in
#     scripts/robotangle/assets.json (every file's sha256 is checked).
# The image builds FROM the published eai-robotangle 0.2.22 (images/robotangle/), which it extends.
# Needs read access to eai-v2-internal/robotangle-assets: `hf auth login`, or HF_TOKEN in the environment (never printed),
# and the release commit in this clone (`git fetch origin dev/robotangle_mujoco`).
# usage: scripts/robotangle/fetch_image_context.sh [<download dir>]   (default: $RCB_ROBOTANGLE_ASSETS or ~/.cache/robotangle-assets)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; HERE="$ROOT/scripts/robotangle"; OUT="$ROOT/images/robotangle/context"
DL="${1:-${RCB_ROBOTANGLE_ASSETS:-$HOME/.cache/robotangle-assets}}"
COMMIT="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["release_commit"])' "$HERE/release.json")"
python3 "$HERE/assets.py" fetch "$DL"
rm -rf "$OUT"; mkdir -p "$OUT"
git -C "$ROOT" archive "$COMMIT" topogym assets/robots images/topogym/prune.py images/robotangle/vbd-requirements.txt \
  images/robotangle/warp_precompile.py | tar -x -C "$OUT"
mkdir -p "$OUT/instances"
python3 - "$HERE/assets.json" "$DL" "$OUT/instances" <<'PY'
import json, pathlib, shutil, sys
pins, dl, out = json.load(open(sys.argv[1])), pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
for base in pins["instances"]:                     # only this benchmark's instances (the dataset also holds RoboTangle's)
    shutil.copytree(dl / "instances" / base, out / base)
print(f"context: {len(pins['instances'])} instances")
PY
