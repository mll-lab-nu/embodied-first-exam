#!/usr/bin/env bash
# Stage images/control-transfer/assets/ (the build context's gitignored inputs) from the public upstreams, then build.sh
# builds the tags the roboEngineer tasks name. Every source is a pinned public commit; every staged file is checked.
#   - unitreerobotics/unitree_rl_mjlab @ 1425b15 (Apache-2.0): the G1 training subset (stage_nominal_assets.py);
#   - google-deepmind/mujoco_menagerie @ 0059d43, unitree_go2 (BSD-3-Clause): the Go2 model, public and evaluator copy;
#   - google-deepmind/mujoco_menagerie @ d7b481b, skydio_x2 (Apache-2.0): the Neural Fly appearance (sha256 pinned);
#   - the Neural Fly force surrogate forces.npz (fitted to aerorobotics/neural-fly's flight logs, whose terms allow
#     personal / educational use only and no redistribution): not downloadable. Pass --fly DIR with a forces.npz whose
#     sha256 is the tasks' pin; without it the evaluator is built with no force asset, and the 8 roboengineer-neuralfly-*
#     tasks refuse to start ("Missing or mismatched private force asset"); every other task is unaffected.
# Needs git, python3 (standard library only) and network access to github.com.
# usage: images/control-transfer/fetch_assets.sh [--fly DIR] [<source cache dir>]   (default ~/.cache/control-transfer-src)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FLY=""
if [ "${1:-}" = "--fly" ]; then FLY="${2:?--fly DIR}"; shift 2; fi
SRC="${1:-${RCB_CONTROL_SRC:-$HOME/.cache/control-transfer-src}}"
FLY_SHA256=8e1c148ed034b9f4c541dfaa71b70b48a652f43c7abcc381416040d7901459b9   # trusted/fly.py ASSET_SHA256 (image 0.2.0)

checkout() {   # <url> <dir> <commit>: a clean checkout of <commit>
  local url="$1" dir="$2" commit="$3"
  [ -d "$dir/.git" ] || git clone -q --filter=blob:none --no-checkout "$url" "$dir"
  git -C "$dir" -c advice.detachedHead=false checkout -q --force "$commit"
  test "$(git -C "$dir" rev-parse HEAD)" = "$commit"
  git -C "$dir" diff --quiet HEAD
}
mkdir -p "$SRC/workspace/sim2realbench/vendor"
checkout https://github.com/unitreerobotics/unitree_rl_mjlab.git "$SRC/workspace/sim2realbench/vendor/unitree_rl_mjlab" \
  1425b15f73bd4095f0df53709d7c389c3eb9e790
checkout https://github.com/google-deepmind/mujoco_menagerie.git "$SRC/mujoco_menagerie" \
  0059d4335f8156206f63a35662313385f7ad6d74

if [ -n "$FLY" ]; then
  echo "$FLY_SHA256  $FLY/forces.npz" | sha256sum -c --quiet - \
    || { echo "FAIL $FLY/forces.npz is not the force asset the tasks pin ($FLY_SHA256)" >&2; exit 1; }
fi
[ ! -e "$HERE/assets" ] || { echo "FAIL $HERE/assets exists: remove it first (it is the staged build input)" >&2; exit 1; }
STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT
(cd "$HERE" && python3 stage_nominal_assets.py --workspace "$SRC/workspace" --go2-source "$SRC/mujoco_menagerie" \
   --out "$STAGE/nominal" --private-go2-out "$STAGE/private-go2")
python3 "$HERE/neuralfly_visual.py" --out "$STAGE/skydio"
mkdir -p "$STAGE/private-fly"
if [ -n "$FLY" ]; then
  cp "$FLY/forces.npz" "$STAGE/private-fly/forces.npz"
else
  printf '%s\n' "No Neural Fly force asset: the roboengineer-neuralfly-* tasks cannot run with this image." \
    > "$STAGE/private-fly/NO_FORCE_ASSET.txt"
fi
(cd "$HERE" && python3 prepare_assets.py --assets "$STAGE/nominal" --fly "$STAGE/private-fly" --go2 "$STAGE/private-go2" \
   --skydio "$STAGE/skydio")
echo "ok staged $HERE/assets (force asset: ${FLY:+included}${FLY:-none}); next: bash images/control-transfer/build.sh"
