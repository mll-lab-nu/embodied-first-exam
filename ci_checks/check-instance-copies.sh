#!/usr/bin/env bash
# One frozen instance per task pair (PROTOCOL §2.2: a standard or standard-realtime task shares its privileged twin's
# frozen instance; §3: the privileged instance is copied into environment/ and tests/). The verifier's copy, the
# privileged task's tests/instance.{json,npz}, and the copy the task runs from (privileged: environment/; standard and
# standard-realtime: the sim sidecar's environment/sim/) are byte-identical, and neither exists without the other.
# RoboPaint's privileged environment/ copy is reduced by design (check-robopaint-leak.sh), so its scorer sidecar's
# environment/scorer/ copy is compared instead. A standard or standard-realtime task's twin <base>-privileged must
# exist, except for the benchmarks PROTOCOL §4b exempts by owner decision (NO_TWIN below; the same list:
# scripts/task_conventions.py NO_TWIN): they have no privileged mode and nothing to compare. STANDARD_ONLY: standard tasks
# without a twin that carry their own frozen instance (PROTOCOL §4.8, physics that does not replay bit for bit: graded by
# the live episode); their generator checks that copy against the benchmark's frozen instance (mk_tasks.py --check).
# Usage: check-instance-copies.sh tasks/<task-dir>
set -uo pipefail
t="${1%/}"; n="$(basename "$t")"; rc=0
NO_TWIN=(roboolympics-)   # PROTOCOL §4b: RoboOlympics (owner, 2026-10-08), standard-realtime only
STANDARD_ONLY=(robodojo-fold-clothes-i00-standard robodojo-fold-clothes-random-i00-standard robodojo-make-toast-random-i00-standard robodojo-pour-by-language-i00-standard robodojo-pour-liquid-into-cup-i00-standard robodojo-pour-liquid-into-cup-random-i00-standard)   # PROTOCOL §4.8 exception (owner, 2026-10-11)
case "$n" in
  *-standard-realtime) base="${n%-standard-realtime}"; ref="$base-privileged/tests"; copy="environment/sim" ;;   # a sim sidecar too
  *-standard) base="${n%-standard}"; ref="$base-privileged/tests"; copy="environment/sim" ;;
  robopaint-*) base=""; ref="$n/tests"; copy="environment/scorer" ;;
  *) base=""; ref="$n/tests"; copy="environment" ;;
esac
if [ -n "$base" ]; then
  for s in "${STANDARD_ONLY[@]}"; do   # while its twin still exists (until the tasks change lands) the pair rules below apply
    if [ "$n" = "$s" ] && [ ! -e "$(dirname "$t")/$base-privileged" ]; then
      [ -f "$t/$copy/instance.json" ] || { echo "FAIL $t: a standard-only task carries its frozen instance ($copy/instance.json)"; exit 1; }
      exit 0
    fi
  done
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
