#!/usr/bin/env bash
# Prepare the RoboTangle image build context images/robotangle/context/ (images/robotangle/README.md), from our private
# Hugging Face dataset at the revision pinned in scripts/robotangle/assets.json. Every file's sha256 is checked there.
#   - image/release-<commit>.tar.gz: the release tree (scripts/robotangle/release.json `release_commit`), only the paths
#     images/topogym/Dockerfile copies;
#   - image/uipc-prebuilt/: the audited libuipc wheel and its uipc-build.json, which the task bindings name;
#   - image/uipc-sm86/: the sm86 libuipc build of the same recipe and its uipc-build.json (release.json uipc_builds), which
#     the image installs in /opt/uipc_sm86 (install_uipc_prefix.py) and checks with verify_uipc_wheel.py, as the audited one;
#   - instances/: every task's frozen instance. The image keeps them under /opt/robotangle/instances, and
#     stage_instance.py copies a task's own instance into it at task build / sim start.
# Then scripts/robotangle/check_context.py checks the context against the runtime the tasks are bound to.
# Needs read access to eai-v2-internal/robotangle-assets: `hf auth login`, or HF_TOKEN in the environment (never printed).
# usage: scripts/robotangle/fetch_image_context.sh [<download dir>]   (default: $RCB_ROBOTANGLE_ASSETS or ~/.cache/robotangle-assets)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; OUT="$ROOT/images/robotangle/context"
DL="${1:-${RCB_ROBOTANGLE_ASSETS:-$HOME/.cache/robotangle-assets}}"
python3 "$ROOT/scripts/robotangle/assets.py" fetch "$DL"
ARCHIVE="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["release_archive"])' "$ROOT/scripts/robotangle/assets.json")"
rm -rf "$OUT"; mkdir -p "$OUT"
tar -xzf "$DL/$ARCHIVE" -C "$OUT"
mkdir -p "$OUT/images/topogym/uipc-prebuilt"; cp "$DL"/image/uipc-prebuilt/* "$OUT/images/topogym/uipc-prebuilt/"
mkdir -p "$OUT/uipc-sm86"; cp "$DL"/image/uipc-sm86/* "$OUT/uipc-sm86/"
cp -a "$DL/instances" "$OUT/instances"
cp "$ROOT/images/robotangle/stage_instance.py" "$OUT/stage_instance.py"
cp "$ROOT/images/robotangle/install_uipc_prefix.py" "$ROOT/images/robotangle/verify_uipc_wheel.py" "$OUT/"
# the release's .dockerignore admits only what images/topogym/Dockerfile copies; ours also reads these
printf '%s\n' '# robot_coding_bench (scripts/robotangle/fetch_image_context.sh): the frozen instances and their staging script,' \
  '# the sm86 libuipc build, its installer and the wheel check' \
  '!instances/' '!instances/**' '!stage_instance.py' '!uipc-sm86/' '!uipc-sm86/**' '!install_uipc_prefix.py' \
  '!verify_uipc_wheel.py' >> "$OUT/.dockerignore"
python3 "$ROOT/scripts/robotangle/check_context.py" "$OUT"
