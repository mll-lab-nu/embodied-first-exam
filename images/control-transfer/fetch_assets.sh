#!/usr/bin/env bash
# Stage images/control-transfer/assets/ (the build context's gitignored inputs) from the public upstreams, then build.sh
# builds the tags the roboEngineer tasks name. Every source is a pinned public commit; every staged file is checked.
#   - unitreerobotics/unitree_rl_mjlab @ 1425b15 (Apache-2.0): the G1 training subset (stage_nominal_assets.py);
#   - google-deepmind/mujoco_menagerie @ 0059d43, unitree_go2 (BSD-3-Clause): the Go2 model, public and evaluator copy;
#   - google-deepmind/mujoco_menagerie @ d7b481b, skydio_x2 (Apache-2.0): the Neural Fly appearance (sha256 pinned);
#   - the Neural Fly force surrogate forces.npz, fitted to aerorobotics/neural-fly's flight logs, whose terms allow
#     personal / educational use only (written permission for further use), so the fit is never redistributed:
#     --fit-fly clones aerorobotics/neural-fly @ 0ed5024 and fits it locally with calibrate_fly.py in a throwaway
#     python:3.12.14-slim container (numpy 2.3.1, mujoco 3.5.0: byte-identical to the pinned asset); --fly DIR uses a
#     forces.npz you already have. Either way its sha256 must be the tasks' pin. With neither, the evaluator is built with
#     no force asset, and the 8 roboengineer-neuralfly-* tasks refuse to start ("Missing or mismatched private force
#     asset"); every other task is unaffected.
# Needs git, python3 (standard library only) and network access to github.com (--fit-fly: also docker and PyPI).
# usage: images/control-transfer/fetch_assets.sh [--fit-fly | --fly DIR] [<source cache dir>]   (default ~/.cache/control-transfer-src)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FLY=""; FIT=""
if [ "${1:-}" = "--fly" ]; then FLY="${2:?--fly DIR}"; shift 2; fi
if [ "${1:-}" = "--fit-fly" ]; then FIT=1; shift; fi
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

if [ -n "$FIT" ]; then   # the flight logs (public, personal / educational use) -> a local fit, never redistributed
  checkout https://github.com/aerorobotics/neural-fly.git "$SRC/neural-fly" 0ed50246b1f1db194e8f0726749351636d3501bf
  FLY="$SRC/fly-fit"; rm -rf "$FLY"; mkdir -p "$FLY"
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$SRC/neural-fly:/src:ro" -v "$FLY:/out" \
    -v "$HERE/calibrate_fly.py:/fit/calibrate_fly.py:ro" python:3.12.14-slim sh -c \
    'pip install -q --no-cache-dir --disable-pip-version-check --target /tmp/py numpy==2.3.1 mujoco==3.5.0 &&
     PYTHONPATH=/tmp/py python3 /fit/calibrate_fly.py --source /src --out /out/fit'
  mv "$FLY/fit/forces.npz" "$FLY/fit/provenance.json" "$FLY/"; rmdir "$FLY/fit"
fi
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
  [ ! -f "$FLY/provenance.json" ] || cp "$FLY/provenance.json" "$STAGE/private-fly/provenance.json"
else
  printf '%s\n' "No Neural Fly force asset: the roboengineer-neuralfly-* tasks cannot run with this image." \
    > "$STAGE/private-fly/NO_FORCE_ASSET.txt"
fi
(cd "$HERE" && python3 prepare_assets.py --assets "$STAGE/nominal" --fly "$STAGE/private-fly" --go2 "$STAGE/private-go2" \
   --skydio "$STAGE/skydio")
echo "ok staged $HERE/assets (force asset: ${FLY:-none}); next: bash images/control-transfer/build.sh"
