#!/usr/bin/env bash
# Host setup for running the benchmark: Harbor CLI. Running needs Harbor + Docker; the TopoGym image is built locally
# (images/topogym/BUILD_ONLY).
# TopoGym (adapted from robot_coding_bench e768a13a8 scripts/install.sh): Harbor pinned to 0.23.0 (upstream README's
# Quick start; the version the helper release was tested with); ~/.local/bin, where uv and Harbor install, is put on PATH
# (a fresh shell may lack it, so `uv` is not found right after its installer); the task-author cap-x setup is left out
# (a helper release tree has no third_party/).
set -euo pipefail
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv tool install harbor==0.23.0
echo "OK. harbor $(harbor --version) at $(command -v harbor). A shell that does not find it: export PATH=\"\$HOME/.local/bin:\$PATH\""
