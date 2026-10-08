#!/usr/bin/env bash
# Export the RoboTangle image build context (images/robotangle/BUILD_ONLY): the release tree at scripts/robotangle/release.json
# `release_commit` (the paths images/topogym/Dockerfile copies) plus the audited libuipc wheel, into images/robotangle/context/,
# and check that it reproduces the runtime the tasks are bound to (public simulator source, uipc-build.json).
# usage: UIPC_PREBUILT_DIR=<dir with the audited wheel and its uipc-build.json> scripts/robotangle/fetch_image_context.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; OUT="$ROOT/images/robotangle/context"
COMMIT="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["release_commit"])' "$ROOT/scripts/robotangle/release.json")"
git -C "$ROOT" cat-file -e "$COMMIT^{commit}" 2>/dev/null || git -C "$ROOT" fetch origin dev/jianwen   # read access to this repository
rm -rf "$OUT"; mkdir -p "$OUT"
git -C "$ROOT" archive "$COMMIT" .dockerignore images/topogym requirements assets/robots scripts/prepare_nyx_studio.py topogym | tar -x -C "$OUT"
: "${UIPC_PREBUILT_DIR:?set UIPC_PREBUILT_DIR to the directory with the audited libuipc wheel and its uipc-build.json (BUILD_ONLY)}"
mkdir -p "$OUT/images/topogym/uipc-prebuilt"; cp "$UIPC_PREBUILT_DIR"/* "$OUT/images/topogym/uipc-prebuilt/"
python3 "$ROOT/scripts/robotangle/check_context.py" "$OUT"
