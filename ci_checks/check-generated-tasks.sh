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
# Usage: check-generated-tasks.sh   (repo-level; run_all.sh calls it once)
set -uo pipefail
umask 022   # the renders these checks compare with: never the caller's umask (a checkout is made with umask 022)
root="$(cd "$(dirname "$0")/.." && pwd)"; rc=0
for gen in "kinder/gen_tasks.py check" "humanoidbench/gen_tasks.py check" "behavior/mk_tasks.py --check" \
           "robolab/mk_tasks.py --check" "robowits/mk_tasks.py --check" "vlabench/generate.py --check" \
           "robocasa/generate.py --check" "robocasa365/generate.py --check" "robocasa-gr1/generate.py --check" \
           "maniguard/mk_tasks.py --check" "robopaint_strict/mk_tasks.py --check" \
           "mujoco-playground/generate.py --check" "libero-max/generate.py --check" \
           "myosuite/generate.py --check" "dexjoco/generate.py --check"; do
  read -r script mode <<<"$gen"
  if out=$(python3 "$root/scripts/$script" "$mode" 2>&1); then
    echo "ok scripts/$script: ${out##*$'\n'}"
  else
    echo "FAIL scripts/$gen:"; echo "$out" | tail -n 40; rc=1
  fi
done
if [ -f "$root/scripts/roboolympics/gen_tasks.py" ]; then   # RoboOlympics (its tasks pull request adds the generator)
  if out=$(python3 "$root/scripts/roboolympics/gen_tasks.py" check 2>&1); then echo "ok scripts/roboolympics/gen_tasks.py: ${out##*$'\n'}"
  else echo "FAIL scripts/roboolympics/gen_tasks.py check:"; echo "$out" | tail -n 40; rc=1; fi
fi
if [ -f "$root/scripts/robotangle/mk_tasks.py" ]; then   # RoboTangle (its tasks pull request adds the generator)
  if out=$(python3 "$root/scripts/robotangle/mk_tasks.py" --check 2>&1); then echo "ok scripts/robotangle/mk_tasks.py: ${out##*$'\n'}"
  else echo "FAIL scripts/robotangle/mk_tasks.py --check:"; echo "$out" | tail -n 40; rc=1; fi
fi
if [ -f "$root/scripts/yamlab/mk_tasks.py" ]; then   # YAMLab (its tasks pull request adds the generator)
  if out=$(python3 "$root/scripts/yamlab/mk_tasks.py" --check 2>&1); then echo "ok scripts/yamlab/mk_tasks.py: ${out##*$'\n'}"
  else echo "FAIL scripts/yamlab/mk_tasks.py --check:"; echo "$out" | tail -n 40; rc=1; fi
fi
if [ -f "$root/scripts/robodojo/mk_tasks.py" ]; then   # RoboDojo (its tasks pull request adds the generator)
  if out=$(python3 "$root/scripts/robodojo/mk_tasks.py" --check 2>&1); then echo "ok scripts/robodojo/mk_tasks.py: ${out##*$'\n'}"
  else echo "FAIL scripts/robodojo/mk_tasks.py --check:"; echo "$out" | tail -n 40; rc=1; fi
fi
if [ -f "$root/scripts/bigym2/gen_tasks.py" ]; then   # BiGym 2.0 (its tasks pull request adds the generator)
  if out=$(python3 "$root/scripts/bigym2/gen_tasks.py" check 2>&1); then echo "ok scripts/bigym2/gen_tasks.py: ${out##*$'\n'}"
  else echo "FAIL scripts/bigym2/gen_tasks.py check:"; echo "$out" | tail -n 40; rc=1; fi
fi
if [ -f "$root/scripts/labutopia/generate.py" ]; then   # LabUtopia (its tasks pull request adds the generator)
  if out=$(python3 "$root/scripts/labutopia/generate.py" --check 2>&1); then echo "ok scripts/labutopia/generate.py: ${out##*$'\n'}"
  else echo "FAIL scripts/labutopia/generate.py --check:"; echo "$out" | tail -n 40; rc=1; fi
fi
if [ -f "$root/scripts/molmospaces/mk_tasks.py" ]; then   # MolmoSpaces
  if out=$(python3 "$root/scripts/molmospaces/mk_tasks.py" --check 2>&1); then echo "ok scripts/molmospaces/mk_tasks.py: ${out##*$'\n'}"
  else echo "FAIL scripts/molmospaces/mk_tasks.py --check:"; echo "$out" | tail -n 40; rc=1; fi
fi
if [ -f "$root/scripts/autobio/generate.py" ]; then   # AutoBio (its tasks pull request adds the generator)
  if out=$(python3 "$root/scripts/autobio/generate.py" --check 2>&1); then echo "ok scripts/autobio/generate.py: ${out##*$'\n'}"
  else echo "FAIL scripts/autobio/generate.py --check:"; echo "$out" | tail -n 40; rc=1; fi
fi
if [ -f "$root/scripts/robotwin_sync_shared.py" ]; then   # RoboTwin 2.0: every task's shared files are the template tasks' (no simulator needed)
  if out=$(python3 "$root/scripts/robotwin_sync_shared.py" --check 2>&1); then echo "ok scripts/robotwin_sync_shared.py: ${out##*$'\n'}"
  else echo "FAIL scripts/robotwin_sync_shared.py --check:"; echo "$out" | tail -n 40; rc=1; fi
fi
exit $rc
