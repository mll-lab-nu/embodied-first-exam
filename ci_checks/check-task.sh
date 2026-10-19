#!/usr/bin/env bash
# The per-task checks on each given task dir (run_all.sh / run_invariants.sh run this on chunks of tasks/ concurrently).
# Exit 1 when any check failed on any of them. RCB_MODES_TABLE (`python3 scripts/task_conventions.py modes`) is read once
# by the caller; set here when missing.
#   --tier invariants  the checks that enforce docs/protocol/README.md Appendix H (the required CI job `invariants`); prints
#                      `INVARIANT-PASS per-task <n>` on success, n = the number of task dirs checked
#   --tier advisory    the advisory checks (the CI job `advisories`: findings are warnings)
#   (no --tier)        both
# Benchmark-specific checks are not here: each benchmark's ci_checks/benchmarks/<bench>/{invariant,advisory}-* hooks (run_all.sh).
# Usage: check-task.sh [--tier invariants|advisory] <task dir>...
set -uo pipefail
umask 022
root="$(cd "$(dirname "$0")/.." && pwd)"; rc=0; tier=all
if [ "${1:-}" = --tier ]; then tier="$2"; shift 2; fi
case "$tier" in invariants|advisory|all) ;; *) echo "FAIL check-task.sh: --tier invariants|advisory"; exit 1 ;; esac
if [ -z "${RCB_MODES_TABLE:-}" ]; then
  RCB_MODES_TABLE="$(python3 "$root/scripts/task_conventions.py" modes)" || { echo "FAIL scripts/task_conventions.py modes"; exit 1; }
  export RCB_MODES_TABLE
fi
INVARIANT_CHECKS=(check-verifier-isolation check-instance-copies check-standard-agent-image)   # Appendix H.1, H.3, H.4, H.6, H.7
ADVISORY_CHECKS=(check-task-structure check-task-fields check-dockerfile check-instruction)
checks=()
[ "$tier" != advisory ] && checks+=("${INVARIANT_CHECKS[@]}")
[ "$tier" != invariants ] && checks+=("${ADVISORY_CHECKS[@]}")
n=0
for t in "$@"; do
  t="${t%/}"; [ -f "$t/task.toml" ] || continue
  for c in "${checks[@]}"; do
    bash "$root/ci_checks/$c.sh" "$t" || rc=1
  done
  n=$((n + 1))
done
[ "$tier" = invariants ] && [ $rc -eq 0 ] && echo "INVARIANT-PASS per-task $n"
exit $rc
