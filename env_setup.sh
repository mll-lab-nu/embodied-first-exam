#!/usr/bin/env bash
# ============================================================================
# TopoGym 环境引导脚本  -  §0-§2 baseline (Genesis + PyTorch + rsl-rl)
#
# 目标:在一台干净的 Linux + CUDA 机器上,一键得到一个能立刻
#       (a) 跑 Genesis 物理仿真 (模块 A/C/D)
#       (b) 跑 rsl-rl PPO 训练 (模块 G1)
#       (c) 跑离线数据生成 (模块 G2)
#       (d) 跑评测 (模块 G3)
#       的 Python venv。
#
# 不包含:VLA / VLM 模型相关库 (transformers / openai SDK / anthropic / google-genai /
#       flash-attn / bitsandbytes 等)。等具体选定 OpenVLA / RT-2 / π₀ / GPT-4V 哪个 policy
#       子类要做 baseline 时再用 `uv pip install -e ".[vla,vlm]"` 增量补上。
#
# 完整依赖说明见  docs/develop/framework/env.md
# ============================================================================

set -euo pipefail

# ----------------------------------------------------------------------------
# 0. 可调旋钮 (run-as ENV-VAR=value bash env_setup.sh 覆盖)
# ----------------------------------------------------------------------------
PYTHON_VER="${PYTHON_VER:-3.11}"      # Genesis 要求 3.10 ≤ X < 3.14;3.11 最稳
CUDA_TAG="${CUDA_TAG:-cu126}"         # PyTorch CUDA wheel tag;按本机 driver 调 (cu121/cu124/cu126)
VENV_DIR="${VENV_DIR:-.venv}"
USE_UV="${USE_UV:-1}"                 # 设 0 改用纯 pip

# ----------------------------------------------------------------------------
# 0.0 缓存重定向 - 把所有下载/解压缓存指向项目盘,避免 HPC home 配额爆掉
#     (常见症状: `Disk quota exceeded` 在 ~/.cache/uv 或 ~/.cache/pip)
# ----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOPOGYM_CACHE_ROOT="${TOPOGYM_CACHE_ROOT:-$SCRIPT_DIR/.cache}"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$TOPOGYM_CACHE_ROOT/uv}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$TOPOGYM_CACHE_ROOT/pip}"
export TMPDIR="${TMPDIR:-$TOPOGYM_CACHE_ROOT/tmp}"
# 提前给未来的 transformers / torch hub 也留好家,免得后续装 VLA 时再炸 home 配额
export HF_HOME="${HF_HOME:-$TOPOGYM_CACHE_ROOT/hf}"
export TORCH_HOME="${TORCH_HOME:-$TOPOGYM_CACHE_ROOT/torch}"
mkdir -p "$UV_CACHE_DIR" "$PIP_CACHE_DIR" "$TMPDIR" "$HF_HOME" "$TORCH_HOME"

echo "[setup] caches redirected under: ${TOPOGYM_CACHE_ROOT}"
echo "          UV_CACHE_DIR  = $UV_CACHE_DIR"
echo "          PIP_CACHE_DIR = $PIP_CACHE_DIR"
echo "          TMPDIR        = $TMPDIR"

# ----------------------------------------------------------------------------
# 0.1 环境探测 (GPU/driver - 在 login node 上失败是正常的)
# ----------------------------------------------------------------------------
echo "[setup] target: Python ${PYTHON_VER}  /  CUDA wheel ${CUDA_TAG}  /  venv ${VENV_DIR}"

GPU_AVAILABLE=0
if command -v nvidia-smi >/dev/null 2>&1; then
    NV_RAW="$(nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null | head -n1 || true)"
    if [[ -n "$NV_RAW" ]]; then
        GPU_AVAILABLE=1
        echo "[setup] detected GPU: ${NV_RAW}"
    else
        echo "[setup] nvidia-smi present but driver unreachable -- this is normal on HPC login"
        echo "        nodes; install will proceed CPU-side and GPU validation will be skipped."
        echo "        Use \`srun --gres=gpu:1 --pty bash\` to land on a compute node when ready."
    fi
else
    echo "[setup] nvidia-smi not found - skipping GPU validation"
fi

# ----------------------------------------------------------------------------
# 1. 装 uv (如缺) - 与 topobench 风格一致,比 pip 快十几倍
# ----------------------------------------------------------------------------
if [[ "$USE_UV" == "1" ]]; then
    if ! command -v uv >/dev/null 2>&1; then
        echo "[setup] uv not found, installing..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        # uv 默认装到 ~/.local/bin 或 ~/.cargo/bin,临时塞进 PATH
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    fi
    UV_BIN="$(command -v uv)"
    echo "[setup] using $($UV_BIN --version)"
fi

# ----------------------------------------------------------------------------
# 2. 创建 / 复用 venv
# ----------------------------------------------------------------------------
if [[ ! -d "$VENV_DIR" ]]; then
    echo "[setup] creating venv at ${VENV_DIR} (Python ${PYTHON_VER})"
    if [[ "$USE_UV" == "1" ]]; then
        "$UV_BIN" venv --python "$PYTHON_VER" "$VENV_DIR"
    else
        "python${PYTHON_VER}" -m venv "$VENV_DIR"
    fi
else
    echo "[setup] venv ${VENV_DIR} already exists - reusing"
fi

# 启用 venv
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# 选定 install 命令
if [[ "$USE_UV" == "1" ]]; then
    PIP_INSTALL=("$UV_BIN" pip install --python "$VENV_DIR/bin/python")
else
    PIP_INSTALL=(python -m pip install --upgrade)
fi

# ----------------------------------------------------------------------------
# 3. PyTorch  (必须先于 Genesis 装好,且 wheel 要匹配 CUDA)
# ----------------------------------------------------------------------------
echo "[setup] installing torch + torchvision (${CUDA_TAG})..."
"${PIP_INSTALL[@]}" \
    "torch>=2.4" \
    "torchvision>=0.19" \
    --index-url "https://download.pytorch.org/whl/${CUDA_TAG}"

# ----------------------------------------------------------------------------
# 4. §1 物理仿真核心  (Genesis + 数学基线)
# ----------------------------------------------------------------------------
echo "[setup] installing Genesis + numerical baseline..."
"${PIP_INSTALL[@]}" \
    "genesis-world>=0.4.5" \
    "numpy>=1.24" \
    "scipy>=1.11"

# ----------------------------------------------------------------------------
# 5. §2 RL 训练栈  (Genesis 官方推荐路径)
# ----------------------------------------------------------------------------
echo "[setup] installing rsl-rl + gymnasium..."
"${PIP_INSTALL[@]}" \
    "rsl-rl-lib>=5.0.0" \
    "gymnasium>=0.29" \
    "tensordict>=0.5"

# ----------------------------------------------------------------------------
# 6. 最小 dev / 框架辅助包
#    严格不在 §0-§2 的范围,但 G1 / G2 / G3 跑起来必须要的零碎 (config / logging /
#    image I/O / data I/O / 测试工具).VLA / VLM 仍然不装.
# ----------------------------------------------------------------------------
echo "[setup] installing minimal framework + dev essentials..."
"${PIP_INSTALL[@]}" \
    "hydra-core>=1.3" "omegaconf>=2.3" "pydantic>=2.8" \
    "typer>=0.12" "rich>=13" \
    "tensorboard>=2.16" \
    "Pillow>=10" "imageio>=2.34" "imageio-ffmpeg>=0.5" \
    "matplotlib>=3.9" \
    "h5py>=3.11" \
    "pytest>=8" "pytest-xdist>=3.6" "ruff>=0.6" "ipython>=8"

# ----------------------------------------------------------------------------
# 7. 校验 - import smoke tests
# ----------------------------------------------------------------------------
echo ""
echo "[verify] running import smoke checks..."
"$VENV_DIR/bin/python" - <<'PY'
import sys
print(f"[ok] python  {sys.version.split()[0]}")

import numpy, scipy
print(f"[ok] numpy   {numpy.__version__}")
print(f"[ok] scipy   {scipy.__version__}")

import torch
print(f"[ok] torch   {torch.__version__}  (CUDA available: {torch.cuda.is_available()})")
if torch.cuda.is_available():
    print(f"           device:   {torch.cuda.get_device_name(0)}")
    print(f"           CUDA ver: {torch.version.cuda}")

import genesis as gs
print(f"[ok] genesis {getattr(gs, '__version__', '<unknown>')}")

import rsl_rl
print(f"[ok] rsl_rl  {getattr(rsl_rl, '__version__', '<unknown>')}")

import gymnasium, hydra, omegaconf, pydantic, h5py, tensorboard
print(f"[ok] gymnasium {gymnasium.__version__}")
print(f"[ok] hydra     {hydra.__version__}")
print(f"[ok] pydantic  {pydantic.VERSION}")

print("")
print("[done] §0-§2 baseline ready.")
print("       VLA / VLM extras are intentionally deferred (see docs/develop/framework/env.md §3).")
PY

# ----------------------------------------------------------------------------
# 8. Genesis-on-GPU 可选深度校验 (只在能用 GPU 的节点上跑)
# ----------------------------------------------------------------------------
if [[ "$GPU_AVAILABLE" == "1" ]]; then
    echo ""
    echo "[verify] Genesis GPU smoke (optional, may take ~10s)..."
    "$VENV_DIR/bin/python" - <<'PY' || {
        echo "[verify][WARN] Genesis GPU init failed - inspect output above." >&2
        exit 0
    }
import genesis as gs
gs.init(backend=gs.cuda)
print("[ok] genesis initialized on CUDA backend")
PY
else
    echo ""
    echo "[verify] skipping Genesis GPU smoke (no GPU visible on this node)."
    echo "         re-run this script on a compute node to validate GPU path."
fi

# ----------------------------------------------------------------------------
# 9. 收尾
# ----------------------------------------------------------------------------
cat <<EOF

============================================================================
Done.

To start working:
    source ${VENV_DIR}/bin/activate

Sanity-test rsl-rl + Genesis later anytime by re-running:
    bash env_setup.sh        # idempotent - reuses existing venv & re-verifies

Next milestone (MVP):
    1. 写一个最小 dummy task (e.g. order_swap_puzzle 物理版骨架)
    2. 跑 10-iter rsl-rl PPO,验证 G1 通路
    3. 用 RandomPolicy 跑 G2 / G3 smoke,验证三种模式骨架

VLA / VLM 加法 (等 OpenVLA / GPT-4V baseline 启动时再做):
    uv pip install -e ".[vla,vlm]"
============================================================================
EOF
