#!/bin/bash
# Assemble the players' visual meshes for the eai-olympiad image (build context images/olympiad, tree ro_lod/, not
# committed): the "25k" level of detail of MuJoCo Menagerie's franka_emika_panda and kuka_iiwa_14 (commit f054586a,
# Apache-2.0; renderers/presentation/menagerie.json), decimated by RoboOlympics' lod.py with its pinned tools
# (images/olympiad/lod.py; trimesh 5.1.1, fast-simplification 0.2.0; the rebuild is bit-identical) and checked file by file against the
# sha256 in lod.json, the same manifest every task's simulator verifies them against at run time (RO_LOD_DIR).
# Needs Docker and network access to GitHub raw and PyPI. Then: scripts/build_images.sh (or docker build here).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../.." && pwd); OUT=$HERE/ro_lod; TMP=$(mktemp -d)
cp -r "$ROOT/scripts/roboolympics/shared/sim/renderers" "$TMP/renderers"
cp "$HERE/lod.py" "$TMP/renderers/presentation/lod.py"     # RoboOlympics renderers/presentation/lod.py, unchanged
cat > "$TMP/build.sh" <<'SH'
set -e
pip install -q --root-user-action=ignore numpy==2.2.6 trimesh==5.1.1 fast-simplification==0.2.0 mujoco==3.3.7
python -m renderers.presentation.assets fetch franka_emika_panda kuka_iiwa_14
python -m renderers.presentation.lod build franka_emika_panda 25k
python -m renderers.presentation.lod build kuka_iiwa_14 25k
python - <<'PY'
import sys
from renderers.presentation import assets
bad = [m for m in ("franka_emika_panda", "kuka_iiwa_14") if assets.missing(m, "25k", assets.HERE / "lod" / "25k")]
sys.exit(f"not the files lod.json pins: {bad}" if bad else 0)
PY
SH
docker run --rm -v "$TMP":/w -w /w -e RO_ASSET_CACHE=/w/cache -e HOST_ID="$(id -u):$(id -g)" \
  docker.io/library/python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7 \
  sh -c 'sh /w/build.sh; rc=$?; chown -R "$HOST_ID" /w; exit $rc'
rm -rf "$OUT"; mkdir -p "$OUT"
cp -r "$TMP/renderers/presentation/lod/25k" "$OUT/25k"
cp "$ROOT/scripts/roboolympics/shared/sim/renderers/presentation/LICENSE.franka_emika_panda" \
   "$ROOT/scripts/roboolympics/shared/sim/renderers/presentation/LICENSE.kuka_iiwa_14" "$OUT/"
rm -rf "$TMP"; du -sh "$OUT"
