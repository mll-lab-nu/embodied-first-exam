#!/usr/bin/env bash
# ============================================================================
# TopoGym Genesis 1.1.0 candidate environment installer.
#
# Creates an isolated uv environment for testing Genesis 1.1.0 without touching
# the existing .venv. The main dependency pins live in:
#   requirements/uv-topogym-gs110.txt
#
# Typical use:
#   bash env_setup_gs110.sh
#
# Useful overrides:
#   CUDA_TAG=cpu bash env_setup_gs110.sh
#   CUDA_TAG=cu124 VENV_DIR=.venv-gs110-cu124 bash env_setup_gs110.sh
#   OPTIONAL_GROUPS="data dev viz" bash env_setup_gs110.sh
#   RUN_TOPOGYM_SMOKE=1 bash env_setup_gs110.sh
#   INSTALL_OPENPI=1 bash env_setup_gs110.sh
# ============================================================================

set -euo pipefail

PYTHON_VER="${PYTHON_VER:-3.11}"
CUDA_TAG="${CUDA_TAG:-cu126}"
VENV_DIR="${VENV_DIR:-.venv-gs110}"
TORCH_VERSION="${TORCH_VERSION:-2.12.0}"
TORCHVISION_VERSION="${TORCHVISION_VERSION:-0.27.0}"
OPTIONAL_GROUPS="${OPTIONAL_GROUPS:-}"
RUN_IMPORT_CHECKS="${RUN_IMPORT_CHECKS:-1}"
RUN_CPU_SMOKE="${RUN_CPU_SMOKE:-1}"
RUN_GPU_SMOKE="${RUN_GPU_SMOKE:-auto}"
STRICT_GPU_SMOKE="${STRICT_GPU_SMOKE:-0}"
RUN_TOPOGYM_SMOKE="${RUN_TOPOGYM_SMOKE:-0}"
FREEZE_LOCK="${FREEZE_LOCK:-0}"
INSTALL_OPENPI="${INSTALL_OPENPI:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQ_FILE="${REQ_FILE:-$SCRIPT_DIR/requirements/uv-topogym-gs110.txt}"
TOPOGYM_CACHE_ROOT="${TOPOGYM_CACHE_ROOT:-$SCRIPT_DIR/.cache}"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$TOPOGYM_CACHE_ROOT/uv-gs110}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$TOPOGYM_CACHE_ROOT/pip-gs110}"
export TMPDIR="${TMPDIR:-$TOPOGYM_CACHE_ROOT/tmp}"
export HF_HOME="${HF_HOME:-$TOPOGYM_CACHE_ROOT/hf}"
export TORCH_HOME="${TORCH_HOME:-$TOPOGYM_CACHE_ROOT/torch}"

mkdir -p "$UV_CACHE_DIR" "$PIP_CACHE_DIR" "$TMPDIR" "$HF_HOME" "$TORCH_HOME"

if [[ -f /usr/lib/wsl/lib/libcuda.so.1 ]]; then
    # WSL can contain stale Linux NVIDIA driver libraries under /lib.
    # Prefer the Windows-driver-provided CUDA stub before Genesis/Quadrants
    # tries to resolve libcuda.so.
    export LD_LIBRARY_PATH="/usr/lib/wsl/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

if [[ "$CUDA_TAG" == "cpu" ]]; then
    TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cpu}"
else
    TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/${CUDA_TAG}}"
fi

echo "[gs110] repo:              $SCRIPT_DIR"
echo "[gs110] venv:              $VENV_DIR"
echo "[gs110] python:            $PYTHON_VER"
echo "[gs110] torch index:       $TORCH_INDEX_URL"
echo "[gs110] requirements:      $REQ_FILE"
echo "[gs110] UV_CACHE_DIR:      $UV_CACHE_DIR"
echo "[gs110] PIP_CACHE_DIR:     $PIP_CACHE_DIR"
echo "[gs110] OPTIONAL_GROUPS:   ${OPTIONAL_GROUPS:-<none>}"

if [[ ! -f "$REQ_FILE" ]]; then
    echo "[gs110][ERROR] requirements file not found: $REQ_FILE" >&2
    exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "[gs110] uv not found; installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

UV_BIN="$(command -v uv)"
echo "[gs110] using $("$UV_BIN" --version)"

cd "$SCRIPT_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
    echo "[gs110] creating venv..."
    "$UV_BIN" venv --python "$PYTHON_VER" "$VENV_DIR"
else
    echo "[gs110] venv exists; reusing $VENV_DIR"
fi

PY="$SCRIPT_DIR/$VENV_DIR/bin/python"
if [[ ! -x "$PY" ]]; then
    echo "[gs110][ERROR] venv python not executable: $PY" >&2
    exit 1
fi

echo "[gs110] installing PyTorch first..."
"$UV_BIN" pip install --python "$PY" \
    "torch==${TORCH_VERSION}" \
    "torchvision==${TORCHVISION_VERSION}" \
    --index-url "$TORCH_INDEX_URL"

echo "[gs110] installing Genesis/RL baseline..."
"$UV_BIN" pip install --python "$PY" -r "$REQ_FILE"

install_group() {
    local group="$1"
    case "$group" in
        data)
            "$UV_BIN" pip install --python "$PY" "zarr>=2.18" "pyarrow>=16"
            ;;
        dev)
            "$UV_BIN" pip install --python "$PY" "pyright>=1.1.380" "pre-commit>=3.8"
            ;;
        viz)
            "$UV_BIN" pip install --python "$PY" "opencv-python>=4.10" "wandb>=0.17"
            ;;
        vlm)
            "$UV_BIN" pip install --python "$PY" \
                "openai>=1.40" \
                "anthropic>=0.34" \
                "google-genai>=0.5" \
                "httpx>=0.27" \
                "tenacity>=8.5"
            ;;
        vla)
            "$UV_BIN" pip install --python "$PY" \
                "transformers>=4.45" \
                "accelerate>=0.30" \
                "peft>=0.11" \
                "sentencepiece>=0.2" \
                "huggingface-hub>=0.24"
            ;;
        il)
            "$UV_BIN" pip install --python "$PY" "torchrl>=0.5" "diffusers>=0.30"
            ;;
        ik)
            "$UV_BIN" pip install --python "$PY" pyroboplan placo
            ;;
        all)
            install_group data
            install_group dev
            install_group viz
            install_group vlm
            install_group vla
            install_group il
            install_group ik
            ;;
        "")
            ;;
        *)
            echo "[gs110][ERROR] unknown optional group: $group" >&2
            echo "Known groups: data dev viz vlm vla il ik all" >&2
            exit 1
            ;;
    esac
}

if [[ -n "$OPTIONAL_GROUPS" ]]; then
    echo "[gs110] installing optional groups: $OPTIONAL_GROUPS"
    for group in $OPTIONAL_GROUPS; do
        install_group "$group"
    done
fi

echo "[gs110] checking package consistency..."
"$UV_BIN" pip check --python "$PY"

if [[ "$RUN_IMPORT_CHECKS" == "1" ]]; then
    echo "[gs110] running import checks..."
    "$PY" - <<'PY'
import sys

import genesis as gs
import gymnasium
import h5py
import hydra
import imageio
import matplotlib
import numpy
import omegaconf
import pydantic
import rsl_rl
import scipy
import tensorboard
import torch
import torchvision

print(f"[ok] python      {sys.version.split()[0]}")
print(f"[ok] torch       {torch.__version__}  CUDA available: {torch.cuda.is_available()}")
print(f"[ok] torchvision {torchvision.__version__}")
print(f"[ok] genesis     {getattr(gs, '__version__', '<unknown>')}")
print(f"[ok] numpy       {numpy.__version__}")
print(f"[ok] scipy       {scipy.__version__}")
print(f"[ok] rsl_rl      {getattr(rsl_rl, '__version__', '<unknown>')}")
print(f"[ok] gymnasium   {gymnasium.__version__}")
print(f"[ok] hydra       {hydra.__version__}")
print(f"[ok] omegaconf   {omegaconf.__version__}")
print(f"[ok] pydantic    {pydantic.__version__}")
print(f"[ok] h5py        {h5py.__version__}")
print(f"[ok] imageio     {imageio.__version__}")
print(f"[ok] matplotlib  {matplotlib.__version__}")
print(f"[ok] tensorboard {tensorboard.__version__}")
PY
fi

if [[ "$RUN_CPU_SMOKE" == "1" ]]; then
    echo "[gs110] running Genesis CPU smoke..."
    "$PY" -c "import genesis as gs; gs.init(backend=gs.cpu); print('[ok] Genesis CPU:', gs.__version__)"
fi

GPU_AVAILABLE=0
if command -v nvidia-smi >/dev/null 2>&1; then
    if nvidia-smi --query-gpu=name --format=csv,noheader >/dev/null 2>&1; then
        GPU_AVAILABLE=1
    fi
fi

if [[ "$RUN_GPU_SMOKE" == "1" || ( "$RUN_GPU_SMOKE" == "auto" && "$GPU_AVAILABLE" == "1" ) ]]; then
    echo "[gs110] running Genesis CUDA smoke..."
    if ! "$PY" -c "import genesis as gs; gs.init(backend=gs.cuda); print('[ok] Genesis CUDA:', gs.__version__)"; then
        cat <<'EOF' >&2
[gs110][WARN] Genesis CUDA smoke failed.
             If PyTorch reports CUDA available but Genesis fails with a missing
             libcuda.so symbol such as cuGraphConditionalHandleCreate, update
             the host NVIDIA driver / WSL CUDA driver mapping and ensure WSL is
             not shadowing the Windows-provided libcuda.so with a Linux driver.
EOF
        if [[ "$RUN_GPU_SMOKE" == "1" || "$STRICT_GPU_SMOKE" == "1" ]]; then
            exit 1
        fi
    fi
else
    echo "[gs110] skipping Genesis CUDA smoke (RUN_GPU_SMOKE=$RUN_GPU_SMOKE, GPU_AVAILABLE=$GPU_AVAILABLE)"
fi

if [[ "$RUN_TOPOGYM_SMOKE" == "1" ]]; then
    echo "[gs110] running TopoGym smoke demos..."
    "$PY" -m prototypes.basic_env_demo --backend cpu --no-robot --hold-steps 1 --verbose
    "$PY" -m prototypes.swap_empty_slot_demo \
        --backend cpu \
        --seed 7 \
        --move-steps 1 \
        --gripper-steps 1 \
        --verbose
fi

if [[ "$FREEZE_LOCK" == "1" ]]; then
    LOCK_FILE="$SCRIPT_DIR/requirements/uv-topogym-gs110.lock.txt"
    echo "[gs110] writing resolved lock snapshot: $LOCK_FILE"
    "$UV_BIN" pip freeze --python "$PY" > "$LOCK_FILE"
fi

if [[ "$INSTALL_OPENPI" == "1" ]]; then
    echo "[gs110] installing OpenPI in its separate environment..."
    bash "$SCRIPT_DIR/env_setup_vla_openpi.sh"
fi

cat <<EOF

============================================================================
Genesis 1.1.0 candidate environment is ready.

Activate it with:
    source ${VENV_DIR}/bin/activate

Useful A/B smoke:
    RUN_TOPOGYM_SMOKE=1 bash env_setup_gs110.sh

Optional groups:
    OPTIONAL_GROUPS="data dev viz vlm vla il ik" bash env_setup_gs110.sh

OpenPI remains isolated:
    INSTALL_OPENPI=1 bash env_setup_gs110.sh
============================================================================
EOF
