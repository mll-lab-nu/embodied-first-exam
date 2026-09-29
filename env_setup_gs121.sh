#!/usr/bin/env bash
# Install simulator dependencies only. No imports, tests, smoke demos or agents.
set -euo pipefail

PYTHON_VER="${PYTHON_VER:-3.11}"
CUDA_TAG="${CUDA_TAG:-cpu}"
INSTALL_NYX="${INSTALL_NYX:-0}"
VENV_DIR="${VENV_DIR:-.venv-gs121}"
TORCH_VERSION="${TORCH_VERSION:-2.12.0}"
TORCHVISION_VERSION="${TORCHVISION_VERSION:-0.27.0}"
OPTIONAL_GROUPS="${OPTIONAL_GROUPS:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
    echo "Install uv before using this dependency installer." >&2
    exit 1
fi
if [[ "$INSTALL_NYX" == "1" && "$CUDA_TAG" == "cpu" ]]; then
    echo "Nyx requires a CUDA build; select CUDA_TAG explicitly." >&2
    exit 1
fi
cd "$SCRIPT_DIR"
if [[ ! -d "$VENV_DIR" ]]; then
    uv venv --python "$PYTHON_VER" "$VENV_DIR"
fi
TOPOGYM_PYTHON="$VENV_DIR/bin/python"
uv pip install --python "$TOPOGYM_PYTHON" \
    "torch==$TORCH_VERSION" "torchvision==$TORCHVISION_VERSION" \
    --index-url "https://download.pytorch.org/whl/$CUDA_TAG"
NYX_ARGS=()
if [[ "$INSTALL_NYX" == "1" ]]; then
    NYX_ARGS=(-r requirements/uv-topogym-gs121-nyx.txt --overrides requirements/uv-topogym-gs121-nyx.txt)
fi
uv pip install --python "$TOPOGYM_PYTHON" -r requirements/uv-topogym-gs121.txt "${NYX_ARGS[@]}"
for group in $OPTIONAL_GROUPS; do
    case "$group" in
        video) uv pip install --python "$TOPOGYM_PYTHON" imageio imageio-ffmpeg ;;
        data) uv pip install --python "$TOPOGYM_PYTHON" h5py ;;
        test) uv pip install --python "$TOPOGYM_PYTHON" pytest ;;
        *) echo "Unknown group: $group (choose video, data, test)." >&2; exit 1 ;;
    esac
done
echo "Dependencies installed. No test, import check, simulation or API experiment was run."
