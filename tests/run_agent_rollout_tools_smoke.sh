#!/usr/bin/env bash
# Real SDK + videos, deterministic operator programs, no model API or key.
set -euo pipefail
rollout_repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
rollout_python="${TOPOGYM_PY:-$rollout_repo_root/.venv-gs121-nyx/bin/python}"
rollout_task=counter
rollout_output=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --task|--output|--python)
            if [[ $# -lt 2 || "$2" == --* ]]; then
                printf 'Missing value for %s\n' "$1" >&2; exit 2
            fi
            case "$1" in
                --task) rollout_task="$2" ;;
                --output) rollout_output="$2" ;;
                --python) rollout_python="$2" ;;
            esac
            shift 2 ;;
        -h|--help)
            printf 'Usage: bash tests/run_agent_rollout_tools_smoke.sh --output NEW_DIRECTORY [--task counter|cast_coil] [--python PATH]\nNo model calls. Cast Coil builds real Genesis scenes (CPU/rasterizer).\n'; exit 0 ;;
        *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
done
[[ "$rollout_task" == counter || "$rollout_task" == cast_coil ]] || { printf 'Unsupported task\n' >&2; exit 2; }
[[ -n "$rollout_output" ]] || { printf 'Specify --output NEW_DIRECTORY\n' >&2; exit 2; }
cd -- "$rollout_repo_root"
mkdir -- "$rollout_output"
"$rollout_python" -m topogym.agent_rollout prepare --task "$rollout_task" --variants 1 --seed 20260921 \
    --backend cpu --renderer rasterizer --resolution 320 180 --output "$rollout_output/presets"
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 "$rollout_python" -m topogym.agent_rollout evaluate \
    --suite "$rollout_output/presets/suite.json" --agents configs/agent_rollout/tools_smoke.json \
    --output "$rollout_output/evaluation" --repeats 1 --max-calls 1 --max-segments 4 \
    --max-steps 3 --max-total-steps 6 --max-resets 1 --max-api-calls 30 \
    --token-limit 0 --samples-per-camera 2 --worker-timeout-s 1200
"$rollout_python" - "$rollout_output/evaluation/results.json" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1]).parent
results = json.loads(Path(sys.argv[1]).read_text())
assert len(results) == 2
for result in results:
    assert result['status'] == 'agent_stopped', result
    assert result['ticks'] == 5, result
    assert result['resets'] == (1 if result['input_mode'] == 'simulator' else 0), result
    print(result['input_mode'], 'passed:', root/result['directory'])
print('SDK smoke passed. This is scripted transport/physics verification, not autonomous task success.')
PY
