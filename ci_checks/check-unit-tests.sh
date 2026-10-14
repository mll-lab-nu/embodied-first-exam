#!/usr/bin/env bash
# Unit tests of benchmark and shared tooling, in two tiers.
#  1. Standard library and a shell only (no numpy, no simulator, no image): the graders and collect hooks that decide a
#     verdict from files, the usage gateway's raw log. Always run (run_all.sh, the required CI job), except one slow
#     test that waits for `--all`.
#  2. numpy + requests (no simulator, no image, no GPU): the shared service layers on stub simulators (the
#     eai-standard/2.2 and 2.4 selftests: crash recovery, request checks; the rcb_service and realtime layers) and the
#     benchmarks' service and grader tests. Run when both modules can be imported (the CI job `unit-tests` installs
#     them), skipped with a note otherwise; `--all` makes a missing module a failure.
# Not here: tests that need a simulator image or media libraries (scripts/roboolympics/tests/: the
# eai-robofunolympics image; scripts/maniguard/tests/test_mg_*.py: imageio, Pillow), run by hand as each benchmark's
# docs/benchmarks/<bench>.md says. The resource monitor's own tests are run by check-monitor.py.
# Usage: check-unit-tests.sh [--all] [--only <path prefix>...]   (repo-level; run_all.sh calls it once)
#   --only: just the tests whose path (scripts/...) starts with one of the prefixes (a pull request's scope,
#   ci_checks/ci_scope.py RCB_SCOPE_PATHS); the shared layers' tests (scripts/tests/, eai_standard/, usage_gateway/) run
#   in the full suite. The tests run concurrently (ci_checks/parallel.py, -j from RCB_CI_JOBS or the CPUs; the service
#   tests on ports one at a time, see lane() below).
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"; rc=0
if [ "${1:-}" = "--one" ]; then   # --one <timeout s> <test path under scripts/> [arguments of the test]
  limit="$2" t="$3"; shift 3
  [ -f "$root/scripts/$t" ] || { echo "FAIL scripts/$t: listed in check-unit-tests.sh but missing"; exit 1; }
  if out=$(cd "${TMPDIR:-/tmp}" && PYTHONDONTWRITEBYTECODE=1 timeout "$limit" python3 "$root/scripts/$t" "$@" 2>&1); then
    echo "ok scripts/$t${*:+ $*}: ${out##*$'\n'}"; exit 0
  else echo "FAIL scripts/$t${*:+ $*}:"; echo "$out" | tail -n 40; exit 1; fi
fi
all=0; [ "${1:-}" = "--all" ] && { all=1; shift; }
only=(); if [ "${1:-}" = "--only" ]; then shift; only=("$@"); fi
self=ci_checks/check-unit-tests.sh; cmds=""   # the commands run from the repository root
want() {   # want <path under scripts/>...: one of them is in the --only scope (or no --only)
  [ ${#only[@]} -eq 0 ] && return 0
  local p a; for a in "$@"; do for p in "${only[@]}"; do [[ "scripts/$a" == "$p"* ]] && return 0; done; done; return 1
}
# Tests that start a service on a port they pick (or may: sockets, subprocesses, servers) run one at a time, in the lane
# `port` of parallel.py: two of them at once can pick the same free port and one test then talks to the other's service
# (seen on the 4-CPU runners: eai_standard/selftest.py's client reached v2_4/selftest.py's service). The rest run concurrently.
lane() { grep -qE 'socket|free_port|_PORT|Popen|serve|import test_' "$root/scripts/$1" 2>/dev/null && printf '@lane:port '; }
run() {   # run <timeout s> <test path under scripts/> [arguments of the test]: queue it when in scope
  want "$2" && cmds+="$(lane "$2")bash $self --one $*"$'\n'
}
for t in robolab/tests/test_grade_standard.py \
         myosuite/tests/test_standard_grade.py mujoco-playground/tests/test_grade_privileged.py \
         robocasa/tests/test_graders.py usage_gateway/tests/test_rawlog.py usage_gateway/tests/test_paths.py \
         tests/test_codex_tools_off.py tests/test_task_seed.py tests/test_runner_results.py \
         roboolympics/tests/test_skill_sandbox.py; do
  run 300 "$t"
done
# RoboDojo's collect hook and standard grader on both of its rules (its tasks pull request adds the test); its privileged
# grader's test needs numpy and runs in the second tier
if [ -f "$root/scripts/robodojo/tests/test_standard_grading.py" ]; then run 300 robodojo/tests/test_standard_grading.py; fi
# RoboSafeBench's standard grader (its tasks pull request adds the test)
if [ -f "$root/scripts/robosafe/tests/test_grade.py" ]; then run 300 robosafe/tests/test_grade.py; run 300 robosafe/tests/test_score.py; fi
# ... and its standard-realtime grader (the realtime tasks' commit adds the test)
if [ -f "$root/scripts/robosafe/tests/test_grade_rt.py" ]; then run 300 robosafe/tests/test_grade_rt.py; fi
# DexHand's graders, privileged and standard, on stub replays (its tasks pull request adds the test)
if [ -f "$root/scripts/dexhand/tests/test_grading.py" ]; then run 300 dexhand/tests/test_grading.py; fi
# standard library too, but slow (RoboLab's collect hook under its real time limits: two to four minutes): with --all
if [ $all -eq 1 ]; then run 900 robolab/tests/test_finalize.py; fi

if python3 -c "import numpy, requests" 2>/dev/null; then
  export PATH="$(dirname "$(command -v python3)"):$PATH"   # run.sh starts `python`: the same interpreter
  for t in eai_standard/selftest.py eai_standard/v2_4/selftest.py \
           humanoidbench/tests/test_standard_service.py humanoidbench/tests/test_realtime_service.py \
           kinder/tests/test_standard_service.py \
           behavior/tests/test_fall.py behavior/tests/test_grading.py behavior/tests/test_standard_service.py \
           molmospaces/tests/test_ms.py robolab/tests/test_grade_privileged.py robolab/tests/test_server.py \
           robolab/tests/test_tooling_units.py robotwin/tests/test_gripper_state.py robotwin/tests/test_standard_service.py \
           robopaint_strict/tests/test_server_requests.py roboarc/tests/test_server_requests.py \
           mujoco-playground/tests/test_standard_2_1_servers.py dexjoco/tests/test_standard_server.py \
           dexjoco/tests/test_grade_privileged.py dexjoco/tests/test_server_validation.py \
           myosuite/tests/test_standard_server.py robowits/tests/test_server_frames.py \
           robodojo/tests/test_privileged_grading.py; do
    run 900 "$t"
  done
  # RoboSafeBench's adapter serves the control interface only (its tasks pull request adds the test)
  if [ -f "$root/scripts/robosafe/tests/test_interface_guard.py" ]; then run 300 robosafe/tests/test_interface_guard.py; fi
  # Panda Dynamic Scenes' graders, privileged and standard (its tasks pull request adds the test)
  if [ -f "$root/scripts/pandadyn/tests/test_grading.py" ]; then run 300 pandadyn/tests/test_grading.py; fi
  # LIBERO-MAX's rcb_service.py is its own variant (its verdict and video protocol differ): the classes of the shared
  # service test that apply to it, run against that copy
  want humanoidbench/tests/test_standard_service.py libero-max/shared/standard &&
    cmds+="@lane:port RCB_SERVICE_DIR=$(printf %q "$root/scripts/libero-max/shared/standard") bash $self --one 900 humanoidbench/tests/test_standard_service.py Endpoints Submit Observe AgentClock ResetCapability ResetChecks Client Boot"$'\n'
  # the realtime clock under request load: the classes that do not depend on the runner's speed (TestClockUnderLoad
  # measures step counts under floods of requests; run the whole file by hand on a quiet host)
  run 900 humanoidbench/tests/test_realtime_load.py TestRequests TestStallEvidence TestGraders
elif [ $all -eq 1 ]; then
  echo "FAIL check-unit-tests.sh --all: numpy and requests are needed for the second tier (pip install numpy requests)"; rc=1
else
  echo "note check-unit-tests.sh: numpy / requests not installed, the service-layer tests were not run (CI job unit-tests runs them; locally: pip install numpy requests, then check-unit-tests.sh --all)"
fi
if [ -z "$cmds" ]; then echo "ok check-unit-tests.sh: no test in scope (${only[*]})"
else (cd "$root" && printf %s "$cmds" | python3 ci_checks/parallel.py) || rc=1; fi
exit $rc
