#!/usr/bin/env bash
# Per-task contract checks on the given task dirs (default: every limited and unlimited task), then the
# two-mode registry check (identities, frozen instances, isolation settings, budgets, fingerprints, dataset digests).
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"; rc=0
tasks=("$@"); [ ${#tasks[@]} -eq 0 ] && tasks=("$root"/limited_tasks/*/*/ "$root"/unlimited_tasks/*/*/)
for t in "${tasks[@]}"; do
  t="${t%/}"; [ -f "$t/task.toml" ] || continue
  for c in check-task-structure check-task-fields check-dockerfile check-instruction check-casa-action-contract check-casa-limited-contract; do
    bash "$root/ci_checks/$c.sh" "$t" || rc=1
  done
done
bash "$root/ci_checks/check-two-modes.sh" || rc=1
[ $rc -eq 0 ] && echo "all checks passed"; exit $rc
