#!/usr/bin/env bash
# Unit tests of the repository's shared tooling, in two tiers.
#  1. Standard library only: the runner's helpers (scripts/tests/), the usage gateway's raw log and budget stop, the
#     runner's lane stop and infra rules (account_failure_check.py --selftest).
#  2. numpy + requests (no simulator, no image, no GPU): the eai-standard/2.2 and 2.4 layers' selftests on a stub
#     simulator (embodied_first_exam/standard/). Run when both modules can be imported, skipped with a note otherwise;
#     `--all` makes a missing module a failure.
# A benchmark's own tests live with its tasks (their tests/), not here. The resource monitor's tests are run by
# check-monitor.py.
# Usage: check-unit-tests.sh [--all] [--only <path prefix>...]   (repo-level; run_all.sh calls it once)
#   --only: just the tests whose repository path starts with one of the prefixes (ci_checks/ci_scope.py RCB_SCOPE_PATHS).
#   The tests run concurrently (ci_checks/parallel.py); the ones that start a service run one at a time (lane `port`).
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"; rc=0
if [ "${1:-}" = "--one" ]; then   # --one <timeout s> <test path in the repository> [arguments of the test]
  limit="$2" t="$3"; shift 3
  [ -f "$root/$t" ] || { echo "FAIL $t: listed in check-unit-tests.sh but missing"; exit 1; }
  if out=$(cd "${TMPDIR:-/tmp}" && PYTHONDONTWRITEBYTECODE=1 timeout "$limit" python3 "$root/$t" "$@" 2>&1); then
    echo "ok $t${*:+ $*}: ${out##*$'\n'}"; exit 0
  else echo "FAIL $t${*:+ $*}:"; echo "$out" | tail -n 40; exit 1; fi
fi
all=0; [ "${1:-}" = "--all" ] && { all=1; shift; }
only=(); if [ "${1:-}" = "--only" ]; then shift; only=("$@"); fi
self=ci_checks/check-unit-tests.sh; cmds=""   # the commands run from the repository root
want() {   # want <path>: in the --only scope (or no --only)
  [ ${#only[@]} -eq 0 ] && return 0
  local p; for p in "${only[@]}"; do [[ "$1" == "$p"* ]] && return 0; done; return 1
}
lane() { grep -qE 'socket|free_port|_PORT|Popen|serve|import test_' "$root/$1" 2>/dev/null && printf '@lane:port '; }
run() {   # run <timeout s> <test path in the repository> [arguments of the test]: queue it when in scope
  want "$2" && cmds+="$(lane "$2")bash $self --one $*"$'\n'
}
for t in scripts/usage_gateway/tests/test_rawlog.py scripts/usage_gateway/tests/test_paths.py \
         scripts/usage_gateway/tests/test_budget_stop.py scripts/tests/test_codex_tools_off.py scripts/tests/test_task_seed.py \
         scripts/tests/test_runner_results.py scripts/tests/test_retry_policy.py scripts/tests/test_stamp_mtimes.py \
         scripts/tests/test_efe.py; do
  run 300 "$t"
done
run 120 scripts/account_failure_check.py --selftest
if python3 -c "import numpy, requests" 2>/dev/null; then
  export PATH="$(dirname "$(command -v python3)"):$PATH"   # run.sh starts `python`: the same interpreter
  for t in embodied_first_exam/standard/selftest.py embodied_first_exam/standard/v2_4/selftest.py; do run 900 "$t"; done
elif [ $all -eq 1 ]; then
  echo "FAIL check-unit-tests.sh --all: numpy and requests are needed for the second tier (pip install numpy requests)"; rc=1
else
  echo "note check-unit-tests.sh: numpy / requests not installed, the service-layer tests were not run (pip install numpy requests, then check-unit-tests.sh --all)"
fi
if [ -z "$cmds" ]; then echo "ok check-unit-tests.sh: no test in scope (${only[*]})"
else (cd "$root" && printf %s "$cmds" | python3 ci_checks/parallel.py) || rc=1; fi
exit $rc
