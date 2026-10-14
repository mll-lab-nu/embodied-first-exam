#!/usr/bin/env bash
# Generated task dirs are what their generator writes from today's sources (PROTOCOL §2.1): runs the check mode of
# every generator that has one (no simulator needed), which compares tasks/ with a fresh render. Whether it also flags
# a task dir the generator no longer writes is up to the generator. Generators without a check mode
# (scripts/robotwin_mk_*.py, dtb_mk_task.py, mj_mk_limited.py, metaworldplus/generate.py) are re-run by hand; the files they
# write unchanged into every task are held together by check-tooling-identity.sh (part 4). The RoboTwin tasks'
# shared files (tooling, service, graders, collect hook, the instruction's common part) are checked against the template
# tasks by scripts/robotwin_sync_shared.py --check. RoboPaint's check
# (robopaint_strict/mk_tasks.py) runs robopaint_brush_mk_task.py --refresh into a temporary directory and adds the process rules
# (standard library only), as does RoboOlympics' (scripts/roboolympics/gen_tasks.py check, which compares the executable
# bits too). The VLABench, RoboCasa, MuJoCo Playground (quadruped) and LIBERO-MAX checks also compare file modes, so run
# them from a checkout made with umask 022.
# Usage: check-generated-tasks.sh [--only <path prefix>...]   (repo-level; run_all.sh calls it once)
#   --only: run just the generators whose script path (scripts/...) starts with one of the prefixes (a pull request's
#   scope, ci_checks/ci_scope.py RCB_SCOPE_PATHS). The generators run concurrently (ci_checks/parallel.py, -j from
#   RCB_CI_JOBS or the CPUs), each one's output printed in one piece.
set -uo pipefail
umask 022   # the renders these checks compare with: never the caller's umask (a checkout is made with umask 022)
root="$(cd "$(dirname "$0")/.." && pwd)"
if [ "${1:-}" = "--one" ]; then   # --one <script under scripts/> <check arguments>...: one generator's check
  script="$2"; shift 2
  if out=$(python3 "$root/scripts/$script" "$@" 2>&1); then echo "ok scripts/$script: ${out##*$'\n'}"; exit 0
  else echo "FAIL scripts/$script $*:"; echo "$out" | tail -n 40; exit 1; fi
fi
only=(); if [ "${1:-}" = "--only" ]; then shift; only=("$@"); fi
want() {   # want <script under scripts/>: in the --only scope (or no --only)
  [ ${#only[@]} -eq 0 ] && return 0
  local p; for p in "${only[@]}"; do [[ "scripts/$1" == "$p"* ]] && return 0; done; return 1
}
gens=("kinder/gen_tasks.py check" "humanoidbench/gen_tasks.py check" "behavior/mk_tasks.py --check"
      "robolab/mk_tasks.py --check" "robowits/mk_tasks.py --check" "vlabench/generate.py --check"
      "robocasa/generate.py --check" "robocasa365/generate.py --check" "robocasa-gr1/generate.py --check"
      "maniguard/mk_tasks.py --check" "robopaint_strict/mk_tasks.py --check"
      "mujoco-playground/generate.py --check" "libero-max/generate.py --check"
      "myosuite/generate.py --check" "dexjoco/generate.py --check")
# generators that their tasks pull request adds: run when present (DexHand: the release families of
# scripts/dexhand/release.json)
for g in "roboolympics/gen_tasks.py check" "roboarc/mk_tasks.py --check" "yamlab/mk_tasks.py --check" \
         "pandadyn/mk_tasks.py --check" "ambench/mk_tasks.py --check" "robodojo/mk_tasks.py --check" \
         "bigym2/gen_tasks.py check" "robofunolympics/gen_tasks.py check" \
         "dexhand/generate.py --check --release" \
         "labutopia/generate.py --check" \
         "molmospaces/mk_tasks.py --check" "autobio/generate.py --check" \
         "robotwin_sync_shared.py --check"; do   # RoboTwin 2.0: every task's shared files are the template tasks' (no simulator needed)
  [ -f "$root/scripts/${g%% *}" ] && gens+=("$g")
done
cmds=""
for g in "${gens[@]}"; do
  read -r script mode <<<"$g"
  [ -f "$root/scripts/$script" ] || { echo "FAIL scripts/$script: listed in check-generated-tasks.sh but missing"; exit 1; }
  want "$script" && cmds+="bash ci_checks/check-generated-tasks.sh --one $script $mode"$'\n'
done
[ -z "$cmds" ] && { echo "ok check-generated-tasks.sh: no generator in scope (${only[*]})"; exit 0; }
cd "$root" && printf %s "$cmds" | python3 ci_checks/parallel.py
if [ -f "$root/scripts/robosafe/gen_tasks.py" ]; then   # RoboSafeBench (its tasks pull request adds the generator)
  if out=$(python3 "$root/scripts/robosafe/gen_tasks.py" check 2>&1); then echo "ok scripts/robosafe/gen_tasks.py: ${out##*$'\n'}"
  else echo "FAIL scripts/robosafe/gen_tasks.py check:"; echo "$out" | tail -n 40; rc=1; fi
fi
if [ -f "$root/scripts/robosafe/gen_realtime.py" ]; then   # RoboSafeBench's standard-realtime tasks
  if out=$(python3 "$root/scripts/robosafe/gen_realtime.py" check 2>&1); then echo "ok scripts/robosafe/gen_realtime.py: ${out##*$'\n'}"
  else echo "FAIL scripts/robosafe/gen_realtime.py check:"; echo "$out" | tail -n 40; rc=1; fi
fi
