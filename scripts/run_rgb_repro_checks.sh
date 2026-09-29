#!/usr/bin/env bash
# Re-run the original lifecycle path with lossless RGB diagnostics and controls.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'HELP'
Usage: bash scripts/run_rgb_repro_checks.sh [NEW_OUTPUT_DIRECTORY]

Serial GPU checks: cast_coil, blanket_flatten, rope_threading (previous failures),
cast_keyhole and knot_untying (previous rigid/FEM passing controls).
Uses the existing full lifecycle test, 3 control steps as in the failed batch,
then seed 0 -> 1 -> 0. Strict RGB equality is still required.
Writes raw PNG pairs, masks, fixed-scale error maps and comparison.json per camera.
Copies source/config/model assets before testing; external Nyx assets and engine
libraries remain shared. Per-task crashes do not stop the next task; Ctrl+C stops.

Defaults: .venv-gs121-nyx/bin/python, .external/nyx-assets, 3600 seconds/task.
Overrides: TOPOGYM_TEST_PYTHON, TOPOGYM_VISUAL_ASSET_ROOT, TOPOGYM_TEST_TIMEOUT.
HELP
    exit 0
fi
if (( $# > 1 )); then
    echo "Expected at most one new output directory; see --help." >&2
    exit 2
fi
PYTHON="${TOPOGYM_TEST_PYTHON:-$ROOT/.venv-gs121-nyx/bin/python}"
VISUAL_ROOT="${TOPOGYM_VISUAL_ASSET_ROOT:-$ROOT/.external/nyx-assets}"
CASE_TIMEOUT="${TOPOGYM_TEST_TIMEOUT:-3600}"
OUT="${1:-$ROOT/runs/test_results/rgb_repro_$(date -u +%Y%m%dT%H%M%SZ)_$$}"
[[ -x "$PYTHON" ]] || { echo "Python not executable: $PYTHON" >&2; exit 2; }
[[ -d "$VISUAL_ROOT" ]] || { echo "Missing Nyx visual assets: $VISUAL_ROOT" >&2; exit 2; }
[[ "$CASE_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || { echo "Timeout must be a positive integer." >&2; exit 2; }
"$PYTHON" - "$ROOT" "$OUT" <<'PY'
import hashlib
import json
from pathlib import Path
import shutil
import sys

root, out = (Path(p).resolve() for p in sys.argv[1:])
out.mkdir(parents=True, exist_ok=False)
snapshot = out / "source"
snapshot.mkdir()
ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "agents")
for name in ("topogym", "tests", "scripts", "configs", "assets"):
    shutil.copytree(root / name, snapshot / name, ignore=ignore)
shutil.copy2(root / "pyproject.toml", snapshot / "pyproject.toml")
hashes, changed = {}, []
for path in sorted(snapshot.rglob("*")):
    if not path.is_file():
        continue
    relative = path.relative_to(snapshot)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    hashes[str(relative)] = digest
    original = root / relative
    if not original.is_file() or hashlib.sha256(original.read_bytes()).hexdigest() != digest:
        changed.append(str(relative))
(out / "snapshot_manifest.json").write_text(json.dumps(dict(
    source_root=str(root), snapshot_root=str(snapshot), sha256=hashes,
    changed_during_copy=changed,
    scope="Source/config/repository assets copied; external Nyx assets and engine libraries shared",
), indent=2) + "\n")
if changed:
    raise SystemExit("Source changed during snapshot; no tests started. Retry with a new output directory.")
PY
OUT="$(cd -- "$OUT" && pwd)"
VISUAL_ROOT="$(cd -- "$VISUAL_ROOT" && pwd)"
export TOPOGYM_ASSET_ROOT="$OUT/source/assets"
export PYTHONFAULTHANDLER=1
echo "Results: $OUT/checks"
echo "Send: $OUT/checks/summary.json (RGB evidence: TASK/rgb_repro/comparison.json)"
exec "$PYTHON" -u "$OUT/source/scripts/test_base_tasks.py" \
    --checks base --tasks cast_coil blanket_flatten rope_threading cast_keyhole knot_untying \
    --steps 3 --timeout "$CASE_TIMEOUT" --visual-asset-root "$VISUAL_ROOT" \
    --output "$OUT/checks"
