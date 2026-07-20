#!/usr/bin/env bash
# ============================================================================
# Optional VLA setup for OpenPI / pi0 / pi0.5.
#
# This intentionally lives outside env_setup.sh so the Genesis + rsl-rl
# baseline remains small and stable. OpenPI has a heavier stack and should use
# its own uv-managed environment under .external/openpi.
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OPENPI_REPO_URL="${OPENPI_REPO_URL:-https://github.com/Physical-Intelligence/openpi.git}"
OPENPI_DIR="${OPENPI_DIR:-$SCRIPT_DIR/.external/openpi}"
TOPOGYM_CACHE_ROOT="${TOPOGYM_CACHE_ROOT:-$SCRIPT_DIR/.cache}"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$TOPOGYM_CACHE_ROOT/uv-openpi}"
export HF_HOME="${HF_HOME:-$TOPOGYM_CACHE_ROOT/hf}"
export OPENPI_DATA_HOME="${OPENPI_DATA_HOME:-$TOPOGYM_CACHE_ROOT/openpi}"
export TMPDIR="${TMPDIR:-$TOPOGYM_CACHE_ROOT/tmp}"
# OpenPI's optional PyTorch setup may patch transformers. Copy mode prevents
# patched hardlinks from leaking back into the global uv cache.
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"

mkdir -p "$UV_CACHE_DIR" "$HF_HOME" "$OPENPI_DATA_HOME" "$TMPDIR" "$(dirname "$OPENPI_DIR")"

echo "[openpi] install dir:       $OPENPI_DIR"
echo "[openpi] UV_CACHE_DIR:      $UV_CACHE_DIR"
echo "[openpi] HF_HOME:           $HF_HOME"
echo "[openpi] OPENPI_DATA_HOME:  $OPENPI_DATA_HOME"
echo "[openpi] UV_LINK_MODE:      $UV_LINK_MODE"

if ! command -v uv >/dev/null 2>&1; then
    echo "[openpi] uv not found; installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

UV_BIN="$(command -v uv)"
echo "[openpi] using $("$UV_BIN" --version)"

if [[ ! -d "$OPENPI_DIR/.git" ]]; then
    echo "[openpi] cloning OpenPI with submodules..."
    GIT_LFS_SKIP_SMUDGE=1 git clone --recurse-submodules "$OPENPI_REPO_URL" "$OPENPI_DIR"
else
    echo "[openpi] OpenPI repo already exists; updating submodules..."
    git -C "$OPENPI_DIR" submodule update --init --recursive
fi

pushd "$OPENPI_DIR" >/dev/null

echo "[openpi] syncing OpenPI uv environment..."
GIT_LFS_SKIP_SMUDGE=1 "$UV_BIN" sync

echo "[openpi] installing OpenPI editable package..."
GIT_LFS_SKIP_SMUDGE=1 "$UV_BIN" pip install -e .

echo "[openpi] installed package summary:"
"$UV_BIN" pip list | grep -E '^(openpi|torch|jax|jaxlib|transformers|lerobot|numpy|pillow|huggingface-hub) ' || true

cat <<'EOF'

OpenPI setup complete.

Useful checks from inside .external/openpi:
    uv pip show transformers
    uv run python -c "from openpi.training import config; print(config.get_config('pi05_droid'))"

Official inference sketch:
    config = _config.get_config("pi05_droid")
    checkpoint_dir = download.maybe_download("gs://openpi-assets/checkpoints/pi05_droid")
    policy = policy_config.create_trained_policy(config, checkpoint_dir)
    action_chunk = policy.infer(example)["actions"]

Note:
    OpenPI officially expects Ubuntu + NVIDIA GPU. Checkpoints are downloaded
    lazily into OPENPI_DATA_HOME / the OpenPI cache when first used.
EOF

popd >/dev/null
