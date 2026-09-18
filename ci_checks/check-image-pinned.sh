#!/usr/bin/env bash
# environment/Dockerfile must FROM a published rcb base image pinned to images/VERSION (never :latest or a local tag).
t="$1"; ver=$(cat "$(dirname "$0")/../images/VERSION"); from=$(grep -m1 '^FROM ' "$t/environment/Dockerfile" | awk '{print $2}')
case "$from" in
  ghcr.io/*/rcb-*:"$ver") exit 0 ;;
  *) echo "FAIL $t: Dockerfile FROM '$from' must be ghcr.io/<org>/rcb-<image>:$ver"; exit 1 ;;
esac
