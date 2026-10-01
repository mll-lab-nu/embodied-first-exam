#!/usr/bin/env bash
# Freeze the MetaWorld+ instances and record the oracles (freeze.py) inside the eai-metaworld image, with Meta-World's
# scripted policies mounted read-only from the pinned upstream commit: the image itself has none.
#   bash scripts/metaworldplus/freeze.sh [env ...]        # MW_SRC=<Metaworld checkout at 59fc34d> to reuse a clone
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
image="ghcr.io/embodied-agent-interface-v2-internal/eai-metaworld:$(cat "$root/images/metaworld/VERSION")"
commit=59fc34d7768af9785e4688c3e1db671424f4a6c3
src="${MW_SRC:-${XDG_CACHE_HOME:-$HOME/.cache}/eai-metaworld/Metaworld-$commit}"
if [ ! -d "$src/metaworld/policies" ]; then
  git clone -q https://github.com/Farama-Foundation/Metaworld "$src"
  git -C "$src" checkout -q "$commit"
fi
[ "$(git -C "$src" rev-parse HEAD)" = "$commit" ] || { echo "$src is not at $commit" >&2; exit 1; }
site=/usr/local/lib/python3.11/site-packages/metaworld/policies
docker run --rm --network none -u "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$src/metaworld/policies:$site:ro" -v "$here:/work" -w /work "$image" python freeze.py "$@"
