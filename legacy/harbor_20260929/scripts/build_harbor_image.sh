#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
image_tag="${1:-topogym-rollout:dev}"
docker build --file "$project_root/docker/Dockerfile.topogym" --tag "$image_tag" "$project_root"
docker image inspect --format '{{.Id}}' "$image_tag"
