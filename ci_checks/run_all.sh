#!/usr/bin/env bash
# Run every per-task check on the given task dirs (default: all of tasks/*), then repo-level checks.
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"; rc=0
tasks=("$@"); [ ${#tasks[@]} -eq 0 ] && tasks=("$root"/tasks/*/)
for t in "${tasks[@]}"; do
  t="${t%/}"; [ -f "$t/task.toml" ] || continue
  for c in check-task-structure check-task-fields check-dockerfile check-instruction check-verifier-isolation; do
    bash "$root/ci_checks/$c.sh" "$t" || rc=1
  done
done
bash "$root/ci_checks/check-dataset-manifest.sh" || rc=1
# Protocol v1.0 report: warnings only until the migration (docs/PROTOCOL.md §7); RCB_PROTOCOL_STRICT=1 makes it blocking.
if [ $# -eq 0 ]; then python3 "$root/ci_checks/check-protocol-v1.py" || rc=1; else python3 "$root/ci_checks/check-protocol-v1.py" "$@" || rc=1; fi
[ $rc -eq 0 ] && echo "all checks passed"; exit $rc
