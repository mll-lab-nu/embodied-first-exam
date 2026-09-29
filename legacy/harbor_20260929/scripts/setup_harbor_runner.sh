#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
runner_venv="${TOPOGYM_HARBOR_VENV:-$project_root/.venv-harbor}"
uv venv --python 3.12 "$runner_venv" --allow-existing
uv pip install --python "$runner_venv/bin/python" -r "$project_root/requirements/harbor-runner.lock"
# The orchestration host does not need Genesis, Torch, CUDA or the renderer.
uv pip install --python "$runner_venv/bin/python" --no-deps -e "$project_root"
"$runner_venv/bin/python" -m harbor_runners.run run --help
