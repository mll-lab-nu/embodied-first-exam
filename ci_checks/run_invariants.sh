#!/usr/bin/env bash
# The required CI job `invariants` (.github/workflows/static-checks.yml): every check and test that enforces the eight
# invariants of docs/protocol/README.md Appendix H, and nothing else (all other checks are advisory: ci_checks/run_all.sh).
# It fails on any failure, on any error, and on any incomplete run: `set -euo pipefail`, no check is allowed to warn
# instead of failing, ci_checks/parallel.py --expect requires exactly the scheduled commands to complete with exit 0, every
# command must print its `INVARIANT-PASS <id>` line, the per-task checks must have covered every task in scope, and the
# list of named checks must have its expected length (a check removed from the list fails the job).
#   run_invariants.sh [task dirs]       the given tasks (default: every task dir, tasks/*/*)
#   run_invariants.sh --changed [REV]   a pull request's scope (ci_checks/ci_scope.py), as run_all.sh --changed
# What enforces what (Appendix H):
#   H.1 verifier isolation      check-verifier-isolation.sh (per task), check-monitor.py --tier invariants,
#                               check-ci-selftest.py --tier invariants (the rules fire), benchmark hooks (a skill sandbox)
#   H.2 no answer in reach      check-agent-pointers.py, the benchmarks' ci_checks/benchmarks/*/invariant-* hooks
#   H.3 standard trust boundary check-standard-agent-image.sh, check-verifier-isolation.sh (ports, sidecar topology)
#   H.4 trusted verdict         check-verifier-isolation.sh (evidence from a sidecar), check-instance-copies.sh
#   H.5 infrastructure retry    scripts/tests/test_retry_policy.py, scripts/tests/test_runner_results.py (a voided
#                               attempt is never counted)
#   H.6 egress                  check-verifier-isolation.sh (the allowlist unless the task declares open)
#   H.7 comparable twins        check-twins.py, check-instance-copies.sh
#   H.8 DIGEST                  check-dataset-manifest.sh
set -euo pipefail
umask 022
root="$(cd "$(dirname "$0")/.." && pwd)"
if [ "${1:-}" != "--changed" ]; then
  args=(); for a in "$@"; do if [ -d "$a" ]; then args+=("$(cd "$a" && pwd)"); else args+=("$a"); fi; done
  set -- ${args[@]+"${args[@]}"}
fi
cd "$root"
q() { printf %q "$1"; }
RCB_MODES_TABLE="$(python3 scripts/task_conventions.py modes)"
export RCB_MODES_TABLE

scope=full; explicit=0; tasks=()
if [ "${1:-}" = "--changed" ]; then
  out="$(python3 ci_checks/ci_scope.py ${2:+--diff-from "$2"})"
  eval "$out"
  scope="$RCB_SCOPE"
  echo "scope: $RCB_SCOPE ($RCB_SCOPE_REASON)${RCB_SCOPE_BENCHES:+ -- benchmarks: $RCB_SCOPE_BENCHES}"
  case "$scope" in
    full|none) tasks=(tasks/*/*/) ;;     # nothing task-related changed: still every task (the invariants are cheap)
    benchmarks) read -ra tasks <<<"$RCB_SCOPE_TASKS" ;;
    *) echo "FAIL ci_checks/ci_scope.py: unknown scope $scope"; exit 1 ;;
  esac
  [ "$scope" = none ] && scope=full-tasks
elif [ $# -gt 0 ]; then tasks=("$@"); explicit=1
else tasks=(tasks/*/*/)
fi
real=(); for t in "${tasks[@]}"; do t="${t%/}"; [ -f "$t/task.toml" ] && real+=("$t"); done
tasks=(${real[@]+"${real[@]}"})
ntasks=${#tasks[@]}
[ "$ntasks" -gt 0 ] || { echo "FAIL run_invariants.sh: no task in scope"; exit 1; }
targs=""; if [ $explicit -eq 1 ] || [ "$scope" = benchmarks ]; then for t in "${tasks[@]}"; do targs+=" $(q "$t")"; done; fi

cmds=""; ids=()
add() { ids+=("$1"); shift; cmds+="{ $*; } && echo INVARIANT-PASS ${ids[-1]}"$'\n'; }
# the named checks, in this order; their number is fixed below
add pointers        python3 ci_checks/check-agent-pointers.py"$targs"                       # H.2
add dataset-manifest bash ci_checks/check-dataset-manifest.sh"$targs"                      # H.8
add twins           python3 ci_checks/check-twins.py"$targs"                                # H.7
add monitor         python3 ci_checks/check-monitor.py --tier invariants"$targs"            # H.1
add retry-policy    python3 scripts/tests/test_retry_policy.py                              # H.5
add runner-results  python3 scripts/tests/test_runner_results.py                            # H.5
EXPECTED_NAMED=6
if [ "$scope" = full ] && [ $explicit -eq 0 ]; then
  add selftest      python3 ci_checks/check-ci-selftest.py --tier invariants                # H.1-H.8: the rules fire
  EXPECTED_NAMED=7
fi
[ "${#ids[@]}" -eq "$EXPECTED_NAMED" ] || { echo "FAIL run_invariants.sh: ${#ids[@]} named checks, $EXPECTED_NAMED expected"; exit 1; }
# the benchmarks' own invariant hooks (H.1 / H.2: leak checks, a skill sandbox's test): every ci_checks/benchmarks/*/invariant-*,
# given the tasks in scope as arguments, through xargs from a list file (every task's path in one command line is
# longer than a single argument may be, 128 KiB)
list="$(mktemp)"; log=""; trap 'rm -f "$list" ${log:+"$log"}' EXIT
printf '%s\n' "${tasks[@]}" > "$list"
hooks=()
for h in ci_checks/benchmarks/*/invariant-*; do
  [ -f "$h" ] || continue
  hooks+=("$h")
  case "$h" in *.py) run="python3 $(q "$h")" ;; *) run="bash $(q "$h")" ;; esac
  add "hook:$h" "xargs $run < $(q "$list")"
done
# the per-task checks, in chunks; each prints `INVARIANT-PASS per-task <n>` (not an id of its own: their sum is checked)
chunk=24; nchunks=0
for ((i = 0; i < ntasks; i += chunk)); do
  part=""; for t in "${tasks[@]:i:chunk}"; do part+=" $(q "$t")"; done
  cmds+="bash ci_checks/check-task.sh --tier invariants$part"$'\n'; nchunks=$((nchunks + 1))
done
total=$(( ${#ids[@]} + nchunks ))
echo "invariants: ${#ids[@]} named check(s) and hook(s) (${#hooks[@]} benchmark hook(s)), $nchunks per-task chunk(s) over $ntasks task(s)"

t0=$SECONDS
log="$(mktemp)"
rc=0; printf %s "$cmds" | python3 ci_checks/parallel.py --expect "$total" | tee "$log" || rc=$?
[ $rc -eq 0 ] || { echo "FAIL run_invariants.sh: a check failed or the run was incomplete (parallel.py exit $rc)"; exit 1; }
missing=()
for id in "${ids[@]}"; do grep -qxF "INVARIANT-PASS $id" "$log" || missing+=("$id"); done
[ ${#missing[@]} -eq 0 ] || { echo "FAIL run_invariants.sh: no INVARIANT-PASS line from: ${missing[*]}"; exit 1; }
covered=$(awk '$1 == "INVARIANT-PASS" && $2 == "per-task" { s += $3 } END { print s + 0 }' "$log")
[ "$covered" -eq "$ntasks" ] || { echo "FAIL run_invariants.sh: the per-task checks covered $covered of $ntasks task(s)"; exit 1; }
echo "run_invariants.sh: $(( SECONDS - t0 )) s; all $total command(s) passed: ${#ids[@]} named check(s) and hook(s), $covered task(s)"
echo "all invariants hold"
