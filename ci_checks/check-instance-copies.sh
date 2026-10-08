#!/usr/bin/env bash
# One frozen instance per task pair (PROTOCOL §2.2: a standard task shares its privileged twin's frozen instance; §3:
# the privileged instance is copied into environment/ and tests/). The verifier's copy, the privileged task's
# tests/instance.{json,npz}, and the copy the task runs from (privileged: environment/; standard: the sim sidecar's
# environment/sim/) are byte-identical, and neither exists without the other. RoboPaint's privileged environment/ copy
# is reduced by design (check-robopaint-leak.sh), so its scorer sidecar's environment/scorer/ copy is compared instead.
# Usage: check-instance-copies.sh tasks/<task-dir>
set -uo pipefail
t="${1%/}"; n="$(basename "$t")"; rc=0
case "$n" in
  *-realtime) ref="${n%-realtime}-privileged/tests"; copy="environment/sim" ;;   # realtime mode: a sim sidecar too
  *-standard) ref="${n%-standard}-privileged/tests"; copy="environment/sim" ;;
  robopaint-*) ref="$n/tests"; copy="environment/scorer" ;;
  *) ref="$n/tests"; copy="environment" ;;
esac
for f in instance.json instance.npz; do
  a="$(dirname "$t")/$ref/$f"; b="$t/$copy/$f"
  [ -f "$a" ] || [ -f "$b" ] || continue
  cmp -s "$a" "$b" 2>/dev/null || { echo "FAIL $t: $copy/$f and $ref/$f differ, or one is missing"; rc=1; }
done
exit $rc
