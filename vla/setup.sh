#!/usr/bin/env bash
# Build one conda environment; then `conda activate <env>` and run `python -m ...` from the repository root.
#   bash vla/setup.sh topogym                        # evaluation side (conda env topogym)
#   bash vla/setup.sh <pi05|groot|molmoact2|xvla>    # one model server (conda env vla-<model>)
# topogym: the repo's env_setup_gs121.sh installs TopoGym with Nyx into the conda env, then the Nyx assets are
# prepared in .external/nyx-assets. Models: clone the official repo into vla/third_party/<model> at a fixed commit,
# install it as its README does (uv sync with the repo's lock file where there is one), download the checkpoints
# to the official default cache (openpi: ~/.cache/openpi; others: ~/.cache/huggingface), then an import check.
# Requires conda and uv (`pip install uv`). An existing environment is reused, never recreated.
set -euo pipefail
export GIT_LFS_SKIP_SMUDGE=1  # LFS files (demo data, test artifacts) are not needed for inference
export PYTHONNOUSERSITE=1    # unlike a venv, a conda env also imports ~/.local packages (pip install --user)

TARGET="${1:-}"
VLA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$VLA_DIR")"
REPO_DIR="$VLA_DIR/third_party/$TARGET"

# Each branch sets ENV, PYTHON and defines install() and download(); model branches also set REPO and COMMIT,
# topogym sets the import CHECK.
case "$TARGET" in
    topogym)
        ENV=topogym
        PYTHON=3.11
        CHECK=vla.gym.run_eval
        install() {  # the directory exists, so env_setup_gs121.sh installs into it instead of creating a venv
            (cd "$ROOT" && VENV_DIR="$PREFIX" CUDA_TAG=cu126 INSTALL_NYX=1 OPTIONAL_GROUPS="video test" \
                bash env_setup_gs121.sh)
        }
        download() {  # checksummed: fetches only missing or damaged files
            (cd "$ROOT" && TOPOGYM_VISUAL_ASSET_ROOT="$ROOT/.external/nyx-assets" "$PY" scripts/prepare_nyx_studio.py)
        }
        ;;
    pi05)
        ENV=vla-pi05
        REPO=https://github.com/Physical-Intelligence/openpi
        COMMIT=215abfb217dbac7d5f1273282331b9b1866c0479
        PYTHON=3.11
        install() { (cd "$REPO_DIR" && UV_PROJECT_ENVIRONMENT="$PREFIX" uv sync --frozen --no-dev --inexact); }
        download() {
            "$PY" -c "from openpi.shared.download import maybe_download
for name in ('pi05_droid_jointpos', 'pi05_base'): print(maybe_download(f'gs://openpi-assets/checkpoints/{name}'))"
        }
        ;;
    groot)
        ENV=vla-groot
        REPO=https://github.com/NVIDIA/Isaac-GR00T
        COMMIT=51d4c89f72fda44cbf77285c6a8114b52676b8a1
        PYTHON=3.12
        install() { (cd "$REPO_DIR" && UV_PROJECT_ENVIRONMENT="$PREFIX" uv sync --frozen --inexact); }
        download() {  # the Cosmos-Reason2-2B backbone is gated: request access on its Hugging Face page first
            "$PY" -c "from huggingface_hub import snapshot_download
print(snapshot_download('nvidia/GR00T-N1.7-DROID', revision='05e7cc97e40dbd33b0890c35cc0214fcb0547ab5'))
print(snapshot_download('nvidia/Cosmos-Reason2-2B'))"
        }
        ;;
    molmoact2)
        ENV=vla-molmoact2
        REPO=https://github.com/allenai/molmoact2
        COMMIT=66b87e64efd99dfd103241418113955cf64dfa9c
        PYTHON=3.12
        install() { (cd "$REPO_DIR" && UV_PROJECT_ENVIRONMENT="$PREFIX" uv sync --inexact); }
        download() {  # 21.8 GB
            "$PY" -c "from huggingface_hub import snapshot_download
print(snapshot_download('allenai/MolmoAct2-DROID', revision='d8c1abd8a27d8e859455bbe514df2bcc617db0fb'))"
        }
        ;;
    xvla)
        ENV=vla-xvla
        REPO=https://github.com/2toinf/X-VLA
        COMMIT=6bc2513f5f1cbec715cc668b414392a6cae5c671
        PYTHON=3.10
        install() {  # requirements.txt leaves torch unpinned; 2.6.0+cu124 runs the model code on this GPU
            uv pip install --python "$PY" torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
            uv pip install --python "$PY" -r "$REPO_DIR/requirements.txt"
        }
        download() {  # 3.5 GB
            "$PY" -c "from huggingface_hub import snapshot_download
print(snapshot_download('2toINF/X-VLA-RoboTwin2', revision='a157c580cfe6f9f445614490f3bec1b2f9ef9f18'))"
        }
        ;;
    *) echo "usage: bash vla/setup.sh <topogym|pi05|groot|molmoact2|xvla>" >&2; exit 1 ;;
esac

command -v conda >/dev/null || { echo "Install conda first" >&2; exit 1; }
command -v uv >/dev/null || { echo "Install uv first: pip install uv" >&2; exit 1; }
if [[ -n "${REPO:-}" ]]; then
    [[ -d "$REPO_DIR/.git" ]] || git clone "$REPO" "$REPO_DIR"
    git -C "$REPO_DIR" checkout --quiet "$COMMIT"
fi
conda run -n "$ENV" true >/dev/null 2>&1 || conda create -y -n "$ENV" "python=$PYTHON"
conda env config vars set -n "$ENV" PYTHONNOUSERSITE=1 >/dev/null  # applied by conda activate
PREFIX="$(conda run -n "$ENV" python -c 'import sys; print(sys.prefix)')"
PY="$PREFIX/bin/python"
install
uv pip install --python "$PY" omegaconf  # config loading on both sides
download
(cd "$ROOT" && "$PY" -c "import ${CHECK:-vla.models.$TARGET.model}")
echo "Ready: conda activate $ENV"
