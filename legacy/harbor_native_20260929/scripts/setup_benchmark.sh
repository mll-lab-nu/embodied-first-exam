#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
benchmark_venv="${TOPOGYM_HARBOR_VENV:-$project_root/.venv-harbor}"
uv venv --python 3.12 "$benchmark_venv" --allow-existing
uv pip install --python "$benchmark_venv/bin/python" -r "$project_root/requirements/benchmark-host.lock"
uv pip install --python "$benchmark_venv/bin/python" --no-deps -e "$project_root"
"$benchmark_venv/bin/harbor" run --help
