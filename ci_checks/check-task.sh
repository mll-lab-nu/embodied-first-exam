#!/usr/bin/env bash
# The per-task checks on each given task dir (run_all.sh runs this on chunks of tasks/ concurrently). Exit 1 when any
# check failed on any of them. RCB_MODES_TABLE (`python3 scripts/task_conventions.py modes`) is read once by the caller;
# set here when missing.
# Usage: check-task.sh <task dir>...
set -uo pipefail
umask 022
root="$(cd "$(dirname "$0")/.." && pwd)"; rc=0
if [ -z "${RCB_MODES_TABLE:-}" ]; then
  RCB_MODES_TABLE="$(python3 "$root/scripts/task_conventions.py" modes)" || { echo "FAIL scripts/task_conventions.py modes"; exit 1; }
  export RCB_MODES_TABLE
fi
for t in "$@"; do
  t="${t%/}"; [ -f "$t/task.toml" ] || continue
  for c in check-task-structure check-task-fields check-dockerfile check-instruction check-verifier-isolation \
           check-instance-copies check-standard-agent-image; do
    bash "$root/ci_checks/$c.sh" "$t" || rc=1
  done
  bash "$root/ci_checks/check-robopaint-leak.sh" "$t" || rc=1     # RoboPaint tasks only (the script skips others)
  bash "$root/ci_checks/check-maniguard-leak.sh" "$t" || rc=1     # ManiGuard tasks only (the script skips others)
  bash "$root/ci_checks/check-standard-texts.sh" "$t" || rc=1      # D7, declared by BEHAVIOR, RoboLab, RoboWits, RoboPaint, ManiGuard, MolmoSpaces, RoboARC, YAMLab, LabUtopia, AutoBio: no world coordinates
done
exit $rc
