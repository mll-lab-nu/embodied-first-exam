#!/usr/bin/env bash
# Run every per-task check on the given task dirs (default: all of tasks/*), then repo-level checks.
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"; rc=0
tasks=("$@"); [ ${#tasks[@]} -eq 0 ] && tasks=("$root"/tasks/*/)
for t in "${tasks[@]}"; do
  t="${t%/}"; [ -f "$t/task.toml" ] || continue
  for c in check-task-structure check-task-fields check-dockerfile check-instruction check-verifier-isolation \
           check-instance-copies check-standard-agent-image; do
    bash "$root/ci_checks/$c.sh" "$t" || rc=1
  done
  bash "$root/ci_checks/check-robopaint-leak.sh" "$t" || rc=1     # RoboPaint tasks only (the script skips others)
  bash "$root/ci_checks/check-maniguard-leak.sh" "$t" || rc=1     # ManiGuard tasks only (the script skips others)
  bash "$root/ci_checks/check-limited-texts.sh" "$t" || rc=1      # D7, declared by BEHAVIOR, RoboLab, RoboWits, RoboPaint, ManiGuard, MolmoSpaces, RoboTangle, YAMLab, LabUtopia, AutoBio: no world coordinates
done
bash "$root/ci_checks/check-dataset-manifest.sh" || rc=1
bash "$root/ci_checks/check-generated-tasks.sh" || rc=1              # generators with a check mode: tasks/ is what they write
bash "$root/ci_checks/check-robopaint-tooling.sh" || rc=1            # RoboPaint: tooling byte-identical within a family / stack
bash "$root/ci_checks/check-tooling-identity.sh" || rc=1             # D9 shared sources; the eai-standard/2.2 layer = scripts/eai_standard/
bash "$root/ci_checks/check-standard-client.sh" || rc=1              # standard agent + verifier images: the pinned client base and pins
# PROTOCOL §2.9 (v1.1.4): [metadata.resources] (minimum compute) in every task.toml, consistent with the GPU reservations and
# caps, and the README's Compute resources section rendered from it
if [ $# -eq 0 ]; then python3 "$root/ci_checks/check-resources.py" || rc=1; else python3 "$root/ci_checks/check-resources.py" "$@" || rc=1; fi
# Protocol v1.0: `legacy:` rules (image move, docs/PROTOCOL.md §7) warn; all other rules fail. RCB_PROTOCOL_STRICT=1 fails on legacy too.
if [ $# -eq 0 ]; then python3 "$root/ci_checks/check-protocol-v1.py" || rc=1; else python3 "$root/ci_checks/check-protocol-v1.py" "$@" || rc=1; fi
# PROTOCOL §2.10 (v1.2): the resource monitor sidecar and the verifier step, wired by scripts/rcb_monitor/inject.py
if [ $# -eq 0 ]; then python3 "$root/ci_checks/check-monitor.py" || rc=1; else python3 "$root/ci_checks/check-monitor.py" "$@" || rc=1; fi
[ $rc -eq 0 ] && echo "all checks passed"; exit $rc
