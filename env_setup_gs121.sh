#!/usr/bin/env bash
# ============================================================================
# TopoGym Genesis 1.2.1 candidate environment installer.
#
# Creates an isolated uv environment for testing Genesis 1.2.1 without touching
# the existing .venv or .venv-gs110. The main dependency pins live in:
#   requirements/uv-topogym-gs121.txt
#
# Genesis 1.2.1 is the pinned project baseline. Relevant
# breaking changes vs the 1.1.0 we currently ship:
#   - 1.2.0: kinematic trees are parsed depth-first instead of breadth-first;
#     review any code that relies on robot link/joint ordering.
#   - 1.2.0: islands partitioning is enabled by default.
#   - 1.2.1: center-of-mass alignment fixed for composite links.
# PBD/FEM/MPM solvers were not changed, so deformable flows (cable_routing,
# untangle, peeling) should be unaffected.
#
# Typical use:
#   bash env_setup_gs121.sh
#
# Useful overrides:
#   INSTALL_NYX=0 CUDA_TAG=cpu bash env_setup_gs121.sh
#   CUDA_TAG=cu124 VENV_DIR=.venv-gs121-cu124 bash env_setup_gs121.sh
#   OPTIONAL_GROUPS="data dev viz" bash env_setup_gs121.sh
#   RUN_TOPOGYM_SMOKE=1 bash env_setup_gs121.sh
#   INSTALL_OPENPI=1 bash env_setup_gs121.sh
#   INSTALL_NYX=0 bash env_setup_gs121.sh  # optional raster-only .venv-gs121
# ============================================================================

set -euo pipefail

PYTHON_VER="${PYTHON_VER:-3.11}"
CUDA_TAG="${CUDA_TAG:-cu126}"
INSTALL_NYX="${INSTALL_NYX:-1}"
if [[ "$INSTALL_NYX" == "1" ]]; then
    VENV_DIR="${VENV_DIR:-.venv-gs121-nyx}"
else
    VENV_DIR="${VENV_DIR:-.venv-gs121}"
fi
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
REQ_FILE="${REQ_FILE:-$SCRIPT_DIR/requirements/uv-topogym-gs121.txt}"
NYX_REQ_FILE="$SCRIPT_DIR/requirements/uv-topogym-gs121-nyx.txt"
TOPOGYM_CACHE_ROOT="${TOPOGYM_CACHE_ROOT:-$SCRIPT_DIR/.cache}"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$TOPOGYM_CACHE_ROOT/uv-gs121}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$TOPOGYM_CACHE_ROOT/pip-gs121}"
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

echo "[gs121] repo:              $SCRIPT_DIR"
echo "[gs121] venv:              $VENV_DIR"
echo "[gs121] python:            $PYTHON_VER"
echo "[gs121] torch index:       $TORCH_INDEX_URL"
echo "[gs121] requirements:      $REQ_FILE"
echo "[gs121] UV_CACHE_DIR:      $UV_CACHE_DIR"
echo "[gs121] PIP_CACHE_DIR:     $PIP_CACHE_DIR"
echo "[gs121] OPTIONAL_GROUPS:   ${OPTIONAL_GROUPS:-<none>}"

if [[ ! -f "$REQ_FILE" ]]; then
    echo "[gs121][ERROR] requirements file not found: $REQ_FILE" >&2
    exit 1
fi

if [[ "$INSTALL_NYX" == "1" && "$CUDA_TAG" == "cpu" ]]; then
    echo "[gs121][ERROR] Nyx requires CUDA; use the CUDA PyTorch build." >&2
    exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "[gs121] uv not found; installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

UV_BIN="$(command -v uv)"
echo "[gs121] using $("$UV_BIN" --version)"

cd "$SCRIPT_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
    echo "[gs121] creating venv..."
    "$UV_BIN" venv --python "$PYTHON_VER" "$VENV_DIR"
else
    echo "[gs121] venv exists; reusing $VENV_DIR"
fi

PY="$VENV_DIR/bin/python"
if [[ ! -x "$PY" ]]; then
    echo "[gs121][ERROR] venv python not executable: $PY" >&2
    exit 1
fi

echo "[gs121] installing PyTorch first..."
"$UV_BIN" pip install --python "$PY" \
    "torch==${TORCH_VERSION}" \
    "torchvision==${TORCHVISION_VERSION}" \
    --index-url "$TORCH_INDEX_URL"

echo "[gs121] installing Genesis/RL baseline..."
NYX_INSTALL_ARGS=()
if [[ "$INSTALL_NYX" == "1" ]]; then
    # Nyx 0.1.4 supports Genesis 1.2.x but requires numpy<2.4. Override only
    # this Nyx environment; the raster-only gs121 requirements stay unchanged.
    NYX_INSTALL_ARGS=(-r "$NYX_REQ_FILE" --overrides "$NYX_REQ_FILE")
fi
"$UV_BIN" pip install --python "$PY" -r "$REQ_FILE" "${NYX_INSTALL_ARGS[@]}"

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
            echo "[gs121][ERROR] unknown optional group: $group" >&2
            echo "Known groups: data dev viz vlm vla il ik all" >&2
            exit 1
            ;;
    esac
}

if [[ -n "$OPTIONAL_GROUPS" ]]; then
    echo "[gs121] installing optional groups: $OPTIONAL_GROUPS"
    for group in $OPTIONAL_GROUPS; do
        install_group "$group"
    done
fi

echo "[gs121] checking package consistency..."
"$UV_BIN" pip check --python "$PY"

if [[ "$RUN_IMPORT_CHECKS" == "1" ]]; then
    echo "[gs121] running import checks..."
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

if [[ "$INSTALL_NYX" == "1" && "$RUN_IMPORT_CHECKS" == "1" ]]; then
    echo "[gs121] checking Nyx plugin and Genesis sensor API imports..."
    "$PY" - <<'PY'
from importlib.metadata import version
from gs_nyx_plugin.nyx_camera_options import NyxCameraOptions

for package in ("genesis-world", "gs-nyx-plugin", "gs-nyx", "numpy"):
    print(f"[ok] {package}: {version(package)}")
camera = NyxCameraOptions(res=(512, 512), spp=32)
print(f"[ok] NyxCameraOptions, res={camera.res}, spp={camera.spp}")
print("[note] Import success does not validate GPU rendering.")
PY
fi

if [[ "$RUN_CPU_SMOKE" == "1" ]]; then
    echo "[gs121] running Genesis CPU smoke..."
    "$PY" -c "import genesis as gs; gs.init(backend=gs.cpu); print('[ok] Genesis CPU:', gs.__version__)"
fi

GPU_AVAILABLE=0
if command -v nvidia-smi >/dev/null 2>&1; then
    if nvidia-smi --query-gpu=name --format=csv,noheader >/dev/null 2>&1; then
        GPU_AVAILABLE=1
    fi
fi

if [[ "$RUN_GPU_SMOKE" == "1" || ( "$RUN_GPU_SMOKE" == "auto" && "$GPU_AVAILABLE" == "1" ) ]]; then
    echo "[gs121] running Genesis CUDA smoke..."
    if ! "$PY" -c "import genesis as gs; gs.init(backend=gs.cuda); print('[ok] Genesis CUDA:', gs.__version__)"; then
        cat <<'EOF' >&2
[gs121][WARN] Genesis CUDA smoke failed.
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
    echo "[gs121] skipping Genesis CUDA smoke (RUN_GPU_SMOKE=$RUN_GPU_SMOKE, GPU_AVAILABLE=$GPU_AVAILABLE)"
fi

if [[ "$RUN_TOPOGYM_SMOKE" == "1" ]]; then
    echo "[gs121] running TopoGym smoke demos..."
    "$PY" -m prototypes.basic_env_demo --backend cpu --no-robot --hold-steps 1 --verbose
    "$PY" -m prototypes.swap_empty_slot_demo \
        --backend cpu \
        --seed 7 \
        --move-steps 1 \
        --gripper-steps 1 \
        --verbose
fi

if [[ "$FREEZE_LOCK" == "1" ]]; then
    if [[ "$INSTALL_NYX" == "1" ]]; then
        LOCK_FILE="$SCRIPT_DIR/requirements/uv-topogym-gs121-nyx.lock.txt"
    else
        LOCK_FILE="$SCRIPT_DIR/requirements/uv-topogym-gs121.lock.txt"
    fi
    echo "[gs121] writing resolved lock snapshot: $LOCK_FILE"
    "$UV_BIN" pip freeze --python "$PY" > "$LOCK_FILE"
fi

if [[ "$INSTALL_OPENPI" == "1" ]]; then
    echo "[gs121] installing OpenPI in its separate environment..."
    bash "$SCRIPT_DIR/env_setup_vla_openpi.sh"
fi

if [[ "$INSTALL_NYX" == "1" ]]; then
    echo "[gs121] Nyx assets: $PY scripts/prepare_nyx_studio.py"
    echo "[gs121] GPU render: $PY -m demos.environment_bootstrap.presentation_preview"
fi

cat <<EOF

============================================================================
Genesis 1.2.1 candidate environment is ready.

Activate it with:
    source ${VENV_DIR}/bin/activate

Useful A/B smoke:
    RUN_TOPOGYM_SMOKE=1 bash env_setup_gs121.sh

Optional groups:
    OPTIONAL_GROUPS="data dev viz vlm vla il ik" bash env_setup_gs121.sh

OpenPI remains isolated:
    INSTALL_OPENPI=1 bash env_setup_gs121.sh
============================================================================
EOF
