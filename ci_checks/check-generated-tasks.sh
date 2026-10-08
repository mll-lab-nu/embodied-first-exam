#!/usr/bin/env bash
# Generated task dirs are what their generator writes from today's sources (PROTOCOL §2.1): runs the check mode of
# every generator that has one (no simulator needed), which compares tasks/ with a fresh render. Whether it also flags
# a task dir the generator no longer writes is up to the generator. Generators without a check mode
# (scripts/robotwin_mk_*.py, dtb_mk_task.py, mj_mk_limited.py, metaworldplus/generate.py) are re-run by hand. RoboPaint's check
# (robopaint_strict/mk_tasks.py) runs robopaint_brush_mk_task.py --refresh into a temporary directory and adds the process rules
# (standard library only). The VLABench and RoboCasa checks also compare file modes, so run them from a checkout made with umask 022.
# Usage: check-generated-tasks.sh   (repo-level; run_all.sh calls it once)
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"; rc=0
for gen in "kinder/gen_tasks.py check" "humanoidbench/gen_tasks.py check" "behavior/mk_tasks.py --check" \
           "robolab/mk_tasks.py --check" "robowits/mk_tasks.py --check" "vlabench/generate.py --check" \
           "robocasa/generate.py --check" "robocasa365/generate.py --check" "robocasa-gr1/generate.py --check" \
           "maniguard/mk_tasks.py --check" "robopaint_strict/mk_tasks.py --check"; do
  read -r script mode <<<"$gen"
  if out=$(python3 "$root/scripts/$script" "$mode" 2>&1); then
    echo "ok scripts/$script: ${out##*$'\n'}"
  else
    echo "FAIL scripts/$gen:"; echo "$out" | tail -n 40; rc=1
  fi
done
if [ -f "$root/scripts/robotangle/mk_tasks.py" ]; then   # RoboTangle (its tasks pull request adds the generator)
  if out=$(python3 "$root/scripts/robotangle/mk_tasks.py" --check 2>&1); then echo "ok scripts/robotangle/mk_tasks.py: ${out##*$'\n'}"
  else echo "FAIL scripts/robotangle/mk_tasks.py --check:"; echo "$out" | tail -n 40; rc=1; fi
fi
exit $rc
