#!/usr/bin/env bash
# Run every per-task check on the given task dirs (default: all of tasks/*), then the repo-level checks.
#   run_all.sh [task dirs]       the per-task checks (check-task.sh, scripts/task_conventions.py --check) on the given
#                                tasks (default: all), and every repo-level check
#   run_all.sh --changed [REV]   a pull request's scope (ci_checks/ci_scope.py; REV: diff REV..HEAD, default: the merge base
#                                with origin/main). Shared code changed -> the full suite (as with no arguments). Only
#                                some benchmarks' own paths changed -> the per-task checks on those benchmarks' tasks, their
#                                generators' checks and unit tests, and the cheap repo-level checks on everything; the CI
#                                mutation self-test runs in the full suite only (it tests ci_checks/, which a scoped change
#                                does not touch). Nothing a scoped run skips goes unchecked: pushes to main run the full suite.
# Everything runs concurrently (ci_checks/parallel.py; RCB_CI_JOBS=N caps it, default: the CPUs), each command's output
# printed in one piece when it ends; any failure fails the run. RCB_SKIP_UNIT_TESTS=1: leave out check-unit-tests.sh (the
# CI workflow runs it, with --all, in a job of its own).
set -uo pipefail
# Seven generators' check modes compare file modes with a fresh render, which depends on the caller's umask: with 0002
# (a common default) every rendered file is group-writable and 179 checks fail on a clean checkout. The checks run with
# the umask the repository is written with; the checkout itself must be made with umask 022 too.
umask 022
root="$(cd "$(dirname "$0")/.." && pwd)"
if [ "${1:-}" != "--changed" ]; then   # task dirs given relative to the caller's directory: made absolute first
  args=(); for a in "$@"; do if [ -d "$a" ]; then args+=("$(cd "$a" && pwd)"); else args+=("$a"); fi; done; set -- "${args[@]}"
fi
cd "$root" || exit 1
q() { printf %q "$1"; }
# the mode registry (PROTOCOL §2.16, scripts/task_conventions.py MODE_REGISTRY), read once for the per-task shell checks
RCB_MODES_TABLE="$(python3 "$root/scripts/task_conventions.py" modes)" || { echo "FAIL scripts/task_conventions.py modes"; exit 1; }
export RCB_MODES_TABLE

scope=full; only=(); explicit=0
if [ "${1:-}" = "--changed" ]; then
  out="$(python3 "$root/ci_checks/ci_scope.py" ${2:+--diff-from "$2"})" || { echo "FAIL ci_checks/ci_scope.py"; exit 1; }
  eval "$out"
  scope="$RCB_SCOPE"
  echo "scope: $RCB_SCOPE ($RCB_SCOPE_REASON)${RCB_SCOPE_BENCHES:+ -- benchmarks: $RCB_SCOPE_BENCHES}"
  case "$scope" in
    full) tasks=(tasks/*/) ;;
    benchmarks) read -ra tasks <<<"$RCB_SCOPE_TASKS"; read -ra only <<<"$RCB_SCOPE_PATHS" ;;
    none) tasks=() ;;
    *) echo "FAIL ci_checks/ci_scope.py: unknown scope $scope"; exit 1 ;;
  esac
else
  tasks=("$@"); [ ${#tasks[@]} -eq 0 ] && tasks=(tasks/*/) || explicit=1
fi
real=(); for t in "${tasks[@]}"; do t="${t%/}"; [ -f "$t/task.toml" ] && real+=("$t"); done; tasks=("${real[@]}")
echo "per-task checks on ${#tasks[@]} task(s)"

cmds=""
add() { cmds+="$*"$'\n'; }
# the slow ones first
if [ "$scope" = full ]; then
  add bash ci_checks/check-generated-tasks.sh              # generators with a check mode: tasks/ is what they write
  add python3 ci_checks/check-ci-selftest.py               # the checks themselves: real tasks broken in one way each must fail their rule
  [ "${RCB_SKIP_UNIT_TESTS:-0}" = 1 ] || add bash ci_checks/check-unit-tests.sh   # graders / collect hooks: the tests that need only the standard library
elif [ "$scope" = benchmarks ]; then
  add bash ci_checks/check-generated-tasks.sh --only "${only[@]}"
  [ "${RCB_SKIP_UNIT_TESTS:-0}" = 1 ] || add bash ci_checks/check-unit-tests.sh --only "${only[@]}"
fi
# the per-task checks, in chunks: check-task.sh (the shell checks) and the generators' normal form
# (scripts/task_conventions.py --check: README, task.toml, test.sh are what normalize writes)
chunk=24
for ((i = 0; i < ${#tasks[@]}; i += chunk)); do
  part=""; for t in "${tasks[@]:i:chunk}"; do part+=" $(q "$t")"; done
  add bash ci_checks/check-task.sh"$part"
  add python3 scripts/task_conventions.py --check"$part"
done
# per-task Python checks over the tasks in scope: the given ones, else all (a scoped run: its benchmarks' tasks)
targs=""; if [ $explicit -eq 1 ] || [ "$scope" = benchmarks ]; then for t in "${tasks[@]}"; do targs+=" $(q "$t")"; done; fi
# PROTOCOL §2.7: no address of upstream material (repository, dataset, demonstration file, video) in a file the agent reads
[ "$scope" = none ] || add python3 ci_checks/check-agent-pointers.py"$targs"
# repo-level, cheap: always on everything, or on the given task dirs as before
pargs=""; [ $explicit -eq 1 ] && pargs="$targs"
add bash ci_checks/check-dataset-manifest.sh"$targs"        # every task's DIGEST is the digest of its files; tasks/dataset.toml not committed
add bash ci_checks/check-robopaint-tooling.sh               # RoboPaint: tooling byte-identical within a family / stack
add bash ci_checks/check-tooling-identity.sh                # D9 shared sources; the eai-standard/2.2 layer = scripts/eai_standard/
add bash ci_checks/check-standard-client.sh                 # standard agent + verifier images: the pinned client base and pins
# PROTOCOL §2.9 (v1.1.4): [metadata.resources] (minimum compute) in every task.toml, consistent with the GPU reservations and
# caps, and the README's Compute resources section rendered from it
add python3 ci_checks/check-resources.py"$pargs"
# PROTOCOL §2.12: the agent's time cutoff. One table (scripts/task_cutoffs.toml); task.toml, the closing `## Time limit` section of
# instruction.md, the README row and the standard modes' sim service all say its number, and nothing else states the limit
add python3 ci_checks/check-cutoffs.py"$pargs"
add python3 ci_checks/check-seeds.py"$pargs"
# PROTOCOL §2.14: scene dynamics, `[metadata] dynamics` from the one table (scripts/task_dynamics.toml)
add python3 ci_checks/check-dynamics.py"$pargs"
# PROTOCOL §4b: a standard-realtime task states its slowdown S ([metadata] slowdown, the instruction) and allows resets
add python3 ci_checks/check-realtime.py"$pargs"
# The task protocol (docs/PROTOCOL.md): the protocol version per mode, oracle fields, the image registry, no results/, no personal paths
add python3 ci_checks/check-protocol.py"$pargs"
# PROTOCOL §2.10 (v1.2): the resource monitor sidecar and the verifier step, wired by scripts/rcb_monitor/inject.py
add python3 ci_checks/check-monitor.py"$pargs"

t0=$SECONDS
printf %s "$cmds" | python3 "$root/ci_checks/parallel.py"; rc=$?
echo "run_all.sh: $(( SECONDS - t0 )) s, scope $scope, ${#tasks[@]} task(s)"
[ $rc -eq 0 ] && echo "all checks passed"; exit $rc
