#!/usr/bin/env bash
# Build one model environment: bash vla/setup.sh <pi05|groot|molmoact2|xvla>
# 1) clone the official repo into vla/third_party/<model> at a fixed commit; 2) create vla/.envs/<model> with uv;
# 3) install per the official README, plus omegaconf; 4) download the checkpoints to the official default cache;
# 5) import check. The TopoGym environment is not touched.
set -euo pipefail

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
        install() { (cd "$REPO_DIR" && GIT_LFS_SKIP_SMUDGE=1 UV_PROJECT_ENVIRONMENT="$ENV_DIR" uv sync --frozen --no-dev); }
        download() {  # into ~/.cache/openpi (OPENPI_DATA_HOME)
            "$PY" -c "from openpi.shared.download import maybe_download
for name in ('pi05_droid_jointpos', 'pi05_base'): print(maybe_download(f'gs://openpi-assets/checkpoints/{name}'))"
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
