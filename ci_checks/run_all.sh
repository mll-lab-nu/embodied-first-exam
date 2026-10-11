#!/usr/bin/env bash
# Run every per-task check on the given task dirs (default: all of tasks/*), then repo-level checks.
set -uo pipefail
# Seven generators' check modes compare file modes with a fresh render, which depends on the caller's umask: with 0002
# (a common default) every rendered file is group-writable and 179 checks fail on a clean checkout. The checks run with
# the umask the repository is written with; the checkout itself must be made with umask 022 too.
umask 022
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
  bash "$root/ci_checks/check-standard-texts.sh" "$t" || rc=1      # D7, declared by BEHAVIOR, RoboLab, RoboWits, RoboPaint, ManiGuard, MolmoSpaces, RoboTangle, YAMLab, LabUtopia, AutoBio: no world coordinates
done
bash "$root/ci_checks/check-dataset-manifest.sh" || rc=1
bash "$root/ci_checks/check-generated-tasks.sh" || rc=1              # generators with a check mode: tasks/ is what they write
bash "$root/ci_checks/check-unit-tests.sh" || rc=1                   # graders / collect hooks: the tests that need only the standard library
python3 "$root/ci_checks/check-ci-selftest.py" || rc=1               # the checks themselves: real tasks broken in one way each must fail their rule
bash "$root/ci_checks/check-robopaint-tooling.sh" || rc=1            # RoboPaint: tooling byte-identical within a family / stack
bash "$root/ci_checks/check-tooling-identity.sh" || rc=1             # D9 shared sources; the eai-standard/2.2 layer = scripts/eai_standard/
bash "$root/ci_checks/check-standard-client.sh" || rc=1              # standard agent + verifier images: the pinned client base and pins
# PROTOCOL §2.9 (v1.1.4): [metadata.resources] (minimum compute) in every task.toml, consistent with the GPU reservations and
# caps, and the README's Compute resources section rendered from it
if [ $# -eq 0 ]; then python3 "$root/ci_checks/check-resources.py" || rc=1; else python3 "$root/ci_checks/check-resources.py" "$@" || rc=1; fi
# The task protocol (docs/PROTOCOL.md): the protocol version per mode, oracle fields, the image registry, no results/, no personal paths
if [ $# -eq 0 ]; then python3 "$root/ci_checks/check-protocol.py" || rc=1; else python3 "$root/ci_checks/check-protocol.py" "$@" || rc=1; fi
# PROTOCOL §2.10 (v1.2): the resource monitor sidecar and the verifier step, wired by scripts/rcb_monitor/inject.py
if [ $# -eq 0 ]; then python3 "$root/ci_checks/check-monitor.py" || rc=1; else python3 "$root/ci_checks/check-monitor.py" "$@" || rc=1; fi
# PROTOCOL §2.7: no address of upstream material (repository, dataset, demonstration file, video) in a file the agent reads
if [ $# -eq 0 ]; then python3 "$root/ci_checks/check-agent-pointers.py" || rc=1; else python3 "$root/ci_checks/check-agent-pointers.py" "$@" || rc=1; fi
[ $rc -eq 0 ] && echo "all checks passed"; exit $rc
