#!/bin/bash
# Authoring evidence: two fresh-process replays of every control trajectory (verdict + determinism) on the host,
# then one recorded replay (mp4) of each physical control inside the eai-dexhand image (CPU osmesa rendering, so no
# GPU lock is needed). Usage, from the repository root, after generate.py has written the task directories:
#   bash scripts/dexhand/families/paper_half_fold/tools/run_evidence.sh <controls dir> <out dir>
set -u
CONTROLS=$(cd "$1" && pwd)
mkdir -p "$2"
OUT=$(cd "$2" && pwd)
ROOT=$(cd "$(dirname "$0")/../../../../.." && pwd)
FAMILY=$ROOT/scripts/dexhand/families/paper_half_fold
TOOLS=$ROOT/tasks/dexhand-paper-half-fold-i00-privileged/environment
IMAGE=ghcr.io/mll-lab-nu/eai-dexhand:$(cat "$ROOT/images/dexhand/VERSION")
PY=${PY:-python3}
export DEXHAND_ASSET_DIR=${DEXHAND_ASSET_DIR:-$ROOT/images/dexhand/assets/hand}
export PYTHONPATH=$FAMILY:$ROOT/scripts/dexhand/shared OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
unset DEXHAND_HAND
VIDEO="oracle nop_hold partial_no_crease_press partial_early_stop drop_pull_over_edge wuji_nop_hold wuji_wrist_and_finger_motion"
for traj in "$CONTROLS"/*.npz; do
  name=$(basename "$traj" .npz)
  for i in 1 2; do
    "$PY" "$FAMILY/replay.py" --task paper_half_fold --traj "$traj" --out "$OUT/$name.replay$i.json" > "$OUT/$name.replay$i.log" 2>&1 &
  done
  wait
  "$PY" - "$OUT" "$name" <<'EOF'
import json, sys
from pathlib import Path
out, name = Path(sys.argv[1]), sys.argv[2]
a, b = (json.loads((out / f"{name}.replay{i}.json").read_text()) for i in (1, 2))
row = {k: a.get(k) for k in ("success", "reason", "bad_trajectory", "hand", "steps", "n_actions", "stage", "state_sha")}
row["deterministic"] = bool(a.get("state_sha")) and a.get("state_sha") == b.get("state_sha")
row["reward"] = int(bool(a.get("success")) and bool(b.get("success")) and row["deterministic"])
row["error"] = a.get("error")
(out / f"{name}.summary.json").write_text(json.dumps(row, indent=2) + "\n")
print(name, json.dumps(row), flush=True)
EOF
done
for name in $VIDEO; do
  [ -f "$CONTROLS/$name.npz" ] || continue
  sudo -n docker run --rm --cpus 2 -e OPENBLAS_NUM_THREADS=1 -e PYTHONDONTWRITEBYTECODE=1 -v "$TOOLS":/opt/tools:ro \
    -v "$CONTROLS":/controls:ro -v "$OUT":/out "$IMAGE" python /opt/tools/replay.py --task paper_half_fold \
    --traj "/controls/$name.npz" --fps 25 --out "/out/$name.video.json" --video "/out/$name.mp4" > "$OUT/$name.video.log" 2>&1
  echo "video $name rc=$? $(python3 -c "import json;d=json.load(open('$OUT/$name.video.json'));print(d.get('success'), d.get('reason'), d.get('steps'), d.get('state_sha'))")"
done
sudo -n chown -R "$(id -u):$(id -g)" "$OUT"
