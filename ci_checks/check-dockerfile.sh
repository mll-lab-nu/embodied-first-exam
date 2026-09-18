#!/usr/bin/env bash
# Reproducibility: FROM must be a registry image with an explicit, non-'latest' tag or digest.
t="$1"; from=$(grep -m1 '^FROM ' "$t/environment/Dockerfile" | awk '{print $2}')
case "$from" in
  *@sha256:*) exit 0 ;;
  *:latest|*:*latest) echo "FAIL $t: Dockerfile FROM '$from' uses :latest"; exit 1 ;;
  */*:*) exit 0 ;;
  *) echo "FAIL $t: Dockerfile FROM '$from' must be <registry>/<image>:<tag> (pinned)"; exit 1 ;;
esac
