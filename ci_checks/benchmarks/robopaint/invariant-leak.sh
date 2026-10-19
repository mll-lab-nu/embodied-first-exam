#!/usr/bin/env bash
# INVARIANT hook (docs/protocol/README.md Appendix H.2: no answer or pointer to one in the agent's reach), this benchmark's own:
# ci_checks/run_invariants.sh runs every ci_checks/benchmarks/*/invariant-* hook with the task directories in scope; the hook
# picks its benchmark's tasks (robopaint-*) and runs check_leak.sh on each.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; rc=0; n=0
for t in "$@"; do
  t="${t%/}"; case "$(basename "$t")" in robopaint-*) ;; *) continue ;; esac
  [ -f "$t/task.toml" ] || continue
  out="$(bash "$here/check_leak.sh" "$t" 2>&1)" || { echo "$out"; rc=1; }
  n=$((n + 1))
done
[ $rc -eq 0 ] && echo "ok robopaint leak check: $n task(s)"
exit $rc
