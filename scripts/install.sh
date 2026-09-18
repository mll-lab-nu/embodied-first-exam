#!/usr/bin/env bash
# Host setup for task authors: Harbor CLI + cap-x venv (for making instances / running selftests outside Docker).
# Running the benchmark only needs Harbor + Docker (images are pulled from GHCR).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install harbor || uv tool upgrade harbor
git -C "$ROOT" submodule update --init --depth 1 third_party/cap-x
git -C "$ROOT/third_party/cap-x" submodule update --init --depth 1 \
  capx/third_party/robosuite capx/third_party/sam3 capx/third_party/contact_graspnet_pytorch \
  capx/third_party/curobo capx/third_party/LIBERO-PRO capx/third_party/verl capx/third_party/libero_dependencies/robosuite
cd "$ROOT/third_party/cap-x" && uv python install 3.10 && uv venv -p 3.10 && uv sync --extra robosuite
echo "OK. Selftest: cd third_party/cap-x && MUJOCO_GL=egl uv run --no-sync python $ROOT/tasks/robosuite-cube-stack-i00/environment/rcb_traj.py selftest --task cube_stack"
