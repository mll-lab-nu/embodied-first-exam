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
  bash "$root/ci_checks/check-robopaint-leak.sh" "$t" || rc=1           # RoboPaint tasks only (the script skips others)
  bash "$root/ci_checks/check-limited-texts.sh" "$t" || rc=1            # rcb-limited/2.2 limited tasks: RGB in the wild
done
bash "$root/ci_checks/check-dataset-manifest.sh" || rc=1
bash "$root/ci_checks/check-robopaint-tooling.sh" || rc=1                  # RoboPaint: tooling byte-identical within a family
bash "$root/ci_checks/check-tooling-identity.sh" || rc=1                   # BEHAVIOR, RoboLab, RoboWits: shared files byte-identical per benchmark
[ $rc -eq 0 ] && echo "all checks passed"; exit $rc
