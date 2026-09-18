#!/usr/bin/env bash
# Run every per-task check on the given task dirs (default: all of tasks/*), then repo-level checks.
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"; rc=0
tasks=("$@"); [ ${#tasks[@]} -eq 0 ] && tasks=("$root"/tasks/*/)
for t in "${tasks[@]}"; do
  t="${t%/}"; [ -f "$t/task.toml" ] || continue
  for c in check-task-structure check-task-fields check-dockerfile check-instruction; do
    bash "$root/ci_checks/$c.sh" "$t" || rc=1
  done
done
bash "$root/ci_checks/check-dataset-manifest.sh" || rc=1
[ $rc -eq 0 ] && echo "all checks passed"; exit $rc
