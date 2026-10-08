#!/usr/bin/env bash
# One frozen instance per task pair (PROTOCOL §2.2: a standard or standard-realtime task shares its privileged twin's
# frozen instance; §3: the privileged instance is copied into environment/ and tests/). The verifier's copy, the
# privileged task's tests/instance.{json,npz}, and the copy the task runs from (privileged: environment/; standard and
# standard-realtime: the sim sidecar's environment/sim/) are byte-identical, and neither exists without the other.
# RoboPaint's privileged environment/ copy is reduced by design (check-robopaint-leak.sh), so its scorer sidecar's
# environment/scorer/ copy is compared instead. A standard or standard-realtime task's twin <base>-privileged must
# exist, except for the benchmarks PROTOCOL §4b exempts by owner decision (NO_TWIN below; the same list:
# scripts/task_conventions.py NO_TWIN): they have no privileged mode and nothing to compare.
# Usage: check-instance-copies.sh tasks/<task-dir>
set -uo pipefail
t="${1%/}"; n="$(basename "$t")"; rc=0
NO_TWIN=(roboolympics-)   # PROTOCOL §4b: RoboOlympics (owner, 2026-10-08), standard-realtime only
case "$n" in
  *-standard-realtime) base="${n%-standard-realtime}"; ref="$base-privileged/tests"; copy="environment/sim" ;;   # a sim sidecar too
  *-standard) base="${n%-standard}"; ref="$base-privileged/tests"; copy="environment/sim" ;;
  robopaint-*) base=""; ref="$n/tests"; copy="environment/scorer" ;;
  *) base=""; ref="$n/tests"; copy="environment" ;;
esac
if [ -n "$base" ]; then
  for p in "${NO_TWIN[@]}"; do
    if [[ "$n" == "$p"* ]]; then
      for f in instance.json instance.npz; do   # no twin, so no instance copy to keep in step with one
        [ -f "$t/$copy/$f" ] && { echo "FAIL $t: $copy/$f without a privileged twin (PROTOCOL §4b NO_TWIN)"; rc=1; }
      done
      exit $rc
    fi
  done
  [ -d "$(dirname "$t")/$base-privileged" ] || { echo "FAIL $t: its privileged twin $base-privileged is missing (PROTOCOL §2.2)"; exit 1; }
fi
for f in instance.json instance.npz; do
  a="$(dirname "$t")/$ref/$f"; b="$t/$copy/$f"
  [ -f "$a" ] || [ -f "$b" ] || continue
  cmp -s "$a" "$b" 2>/dev/null || { echo "FAIL $t: $copy/$f and $ref/$f differ, or one is missing"; rc=1; }
done
exit $rc
