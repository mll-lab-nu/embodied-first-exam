#!/usr/bin/env bash
# ADVISORY hook: this benchmark's standard tasks give no world coordinates in their texts (its tasks/<benchmark>/README.md,
# "World-frame information"; PROTOCOL §5). Run by ci_checks/run_all.sh with the task directories in scope.
root="$(cd "$(dirname "$0")/../../.." && pwd)"
exec bash "$root/ci_checks/check-world-frame-texts.sh" --prefix robolab- "$@"
