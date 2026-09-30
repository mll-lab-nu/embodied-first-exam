#!/usr/bin/env bash
# Build one model environment: bash vla/setup.sh <pi05|groot|molmoact2|xvla>
# 1) clone the official repo into vla/third_party/<model> at a fixed commit; 2) create vla/.envs/<model> with uv;
# 3) install per the official README, plus omegaconf; 4) download the checkpoints to the official default cache;
# 5) import check. The TopoGym environment is not touched.
set -euo pipefail
export GIT_LFS_SKIP_SMUDGE=1  # LFS files (demo data, test artifacts) are not needed for inference

MODEL="${1:-}"
VLA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$VLA_DIR/third_party/$MODEL"
ENV_DIR="$VLA_DIR/.envs/$MODEL"
PY="$ENV_DIR/bin/python"

# Each branch sets REPO, COMMIT, PYTHON and defines install() and download().
case "$MODEL" in
    pi05)
        REPO=https://github.com/Physical-Intelligence/openpi
        COMMIT=215abfb217dbac7d5f1273282331b9b1866c0479
        PYTHON=3.11
        install() { (cd "$REPO_DIR" && UV_PROJECT_ENVIRONMENT="$ENV_DIR" uv sync --frozen --no-dev); }
        download() {  # into ~/.cache/openpi (OPENPI_DATA_HOME)
            "$PY" -c "from openpi.shared.download import maybe_download
for name in ('pi05_droid_jointpos', 'pi05_base'): print(maybe_download(f'gs://openpi-assets/checkpoints/{name}'))"
        }
        ;;
    groot)
        REPO=https://github.com/NVIDIA/Isaac-GR00T
        COMMIT=51d4c89f72fda44cbf77285c6a8114b52676b8a1
        PYTHON=3.12
        install() { (cd "$REPO_DIR" && UV_PROJECT_ENVIRONMENT="$ENV_DIR" uv sync --python "$PYTHON" --frozen); }
        download() {  # into ~/.cache/huggingface; the Cosmos-Reason2-2B backbone is gated: request access first
            "$PY" -c "from huggingface_hub import snapshot_download
print(snapshot_download('nvidia/GR00T-N1.7-DROID', revision='05e7cc97e40dbd33b0890c35cc0214fcb0547ab5'))
print(snapshot_download('nvidia/Cosmos-Reason2-2B'))"
        }
        ;;
    molmoact2)
        REPO=https://github.com/allenai/molmoact2
        COMMIT=66b87e64efd99dfd103241418113955cf64dfa9c
        PYTHON=3.12
        install() { (cd "$REPO_DIR" && UV_PROJECT_ENVIRONMENT="$ENV_DIR" uv sync --python "$PYTHON"); }
        download() {  # into ~/.cache/huggingface (21.8 GB)
            "$PY" -c "from huggingface_hub import snapshot_download
print(snapshot_download('allenai/MolmoAct2-DROID', revision='d8c1abd8a27d8e859455bbe514df2bcc617db0fb'))"
        }
        ;;
    xvla)
        REPO=https://github.com/2toinf/X-VLA
        COMMIT=6bc2513f5f1cbec715cc668b414392a6cae5c671
        PYTHON=3.10
        install() {  # requirements.txt leaves torch unpinned; 2.6.0+cu124 runs the model code on this GPU
            uv pip install --python "$PY" torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
            uv pip install --python "$PY" -r "$REPO_DIR/requirements.txt"
        }
        download() {  # into ~/.cache/huggingface (3.5 GB)
            "$PY" -c "from huggingface_hub import snapshot_download
print(snapshot_download('2toINF/X-VLA-RoboTwin2', revision='a157c580cfe6f9f445614490f3bec1b2f9ef9f18'))"
        }
        ;;
    *) echo "usage: bash vla/setup.sh <pi05|groot|molmoact2|xvla>" >&2; exit 1 ;;
esac

command -v uv >/dev/null || { echo "Install uv first: https://docs.astral.sh/uv/" >&2; exit 1; }
cd "$VLA_DIR/.."
[[ -d "$REPO_DIR/.git" ]] || git clone "$REPO" "$REPO_DIR"
git -C "$REPO_DIR" checkout --quiet "$COMMIT"
[[ -d "$ENV_DIR" ]] || uv venv --python "$PYTHON" "$ENV_DIR"
install
uv pip install --python "$PY" omegaconf
download
"$PY" -c "import vla.models.$MODEL.model"
echo "$MODEL ready: $PY -m vla.models.serve --config vla/configs/models/<checkpoint>.yaml"
