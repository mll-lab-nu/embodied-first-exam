#!/usr/bin/env bash
# One frozen instance per task pair (PROTOCOL §2.2: a standard or standard-realtime task shares its privileged twin's
# frozen instance; §3: the privileged instance is copied into environment/ and tests/). The verifier's copy, the
# privileged task's tests/instance.{json,npz}, and the copy the task runs from (privileged: environment/; standard and
# standard-realtime: the sim sidecar's environment/sim/) are byte-identical, and neither exists without the other.
# RoboPaint's privileged environment/ copy is reduced by design (check-robopaint-leak.sh), so its scorer sidecar's
# environment/scorer/ copy is compared instead.
# A benchmark ships any subset of the three modes (PROTOCOL §2.15, owner 2026-10-14). A standard or standard-realtime
# task without its twin <base>-privileged is accepted when scripts/task_conventions.py no_twin_reason() gives a reason:
# its benchmark has no privileged mode (no privileged task under tasks/), or the task is listed in
# NO_TWIN (e.g. RoboDojo's six standard-only tasks, PROTOCOL §4.8). Such a task carries its own frozen instance, if it
# has one: its sim sidecar's copy and its verifier's tests/ copy, where both exist, are byte-identical (a generator's
# --check compares them with the benchmark's frozen instance). Any other missing twin fails.
# Usage: check-instance-copies.sh tasks/<task-dir>
set -uo pipefail
t="${1%/}"; n="$(basename "$t")"; rc=0
root="$(cd "$(dirname "$0")/.." && pwd)"
# the mode registry (PROTOCOL §2.16; run_all.sh reads it once): "<mode> <sidecar 0|1> <twin mode or ->", longest first
modes="${RCB_MODES_TABLE:-$(python3 "$root/scripts/task_conventions.py" modes)}"
base=""; ref="$n/tests"; copy="environment"; twin=""
case "$n" in robopaint-*) copy="environment/scorer" ;; esac
while read -r m sidecar tw; do
  [ -n "$m" ] && [[ "$n" == *"-$m" ]] || continue
  if [ "$tw" != "-" ]; then base="${n%-$m}"; twin="$tw"; ref="$base-$tw/tests"; fi
  [ "$sidecar" = 1 ] && copy="environment/sim"
  break
done <<< "$modes"
if [ -n "$base" ] && [ ! -d "$(dirname "$t")/$base-$twin" ]; then
  why="$(python3 -c 'import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import task_conventions as tc; print(tc.no_twin_reason(Path(sys.argv[2])) or "")' "$root/scripts" "$t")" \
    || { echo "FAIL $t: scripts/task_conventions.py no_twin_reason() failed"; exit 1; }
  [ -n "$why" ] || { echo "FAIL $t: its twin $base-$twin is missing; its benchmark has a $twin mode, so a task without a twin is listed in scripts/task_conventions.py NO_TWIN with the reason (PROTOCOL §2.15)"; exit 1; }
  for f in instance.json instance.npz; do   # no twin: its own two copies, where both exist, agree
    a="$t/tests/$f"; b="$t/$copy/$f"
    [ -f "$a" ] && [ -f "$b" ] && ! cmp -s "$a" "$b" && { echo "FAIL $t: $copy/$f and tests/$f differ"; rc=1; }
  done
  exit $rc
fi
for f in instance.json instance.npz; do
  a="$(dirname "$t")/$ref/$f"; b="$t/$copy/$f"
  [ -f "$a" ] || [ -f "$b" ] || continue
  cmp -s "$a" "$b" 2>/dev/null || { echo "FAIL $t: $copy/$f and $ref/$f differ, or one is missing"; rc=1; }
done
exit $rc
