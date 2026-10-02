#!/usr/bin/env bash
# Import and verify the frozen instances and references (import_references.py) inside the benchmark image, with the
# PR #4 checkout that authored them mounted read-only.
#   bash scripts/<benchmark>/import_references.sh <PR #4 checkout> [--workers N] [env ...]
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
bench="$(basename "$here")"
src="$(cd "$1" && pwd)"
shift
image="ghcr.io/mll-lab-nu/eai-$bench:$(cat "$root/images/$bench/VERSION")"
# As root (RoboCasa writes temporary model files into its package); hand frozen/ back to the caller afterwards.
docker run --rm --network none --cpus 12 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e OWNER="$(id -u):$(id -g)" \
  -v "$src:/src:ro" -v "$here:/work/$bench" -w "/work/$bench" "$image" \
  sh -c 'python import_references.py "$@"; rc=$?; chown -R "$OWNER" frozen; exit $rc' sh "$@"
