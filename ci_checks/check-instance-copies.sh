#!/usr/bin/env bash
# INVARIANT (docs/protocol/README.md Appendix H.4 identical instance copies, H.7 twins share one frozen instance): part of the
# required CI job `invariants` (ci_checks/run_invariants.sh). The verifier's copy of the frozen instance, the privileged
# task's tests/instance.{json,npz}, and the copy the task runs from (privileged: environment/, or environment/scorer/
# where a scorer sidecar holds the trusted copy and the agent's environment/ copy is reduced by design; standard and
# standard-realtime: the sim sidecar's environment/sim/) are byte-identical, and neither exists without the other. A
# standard or standard-realtime task shares its privileged twin's copy where the twin exists; without a twin (a benchmark
# may ship any subset of the modes; the README's Twin row says why, an advisory check reads it) it carries its own, and
# its sim copy and its tests/ copy, where both exist, are byte-identical.
# Usage: check-instance-copies.sh tasks/<task-dir>
set -uo pipefail
t="${1%/}"; n="$(basename "$t")"; rc=0
root="$(cd "$(dirname "$0")/.." && pwd)"
# the mode registry (PROTOCOL §2.16; run_all.sh reads it once): "<mode> <sidecar 0|1> <twin mode or ->", longest first
modes="${RCB_MODES_TABLE:-$(python3 "$root/scripts/task_conventions.py" modes)}"
base=""; ref="$n/tests"; copy="environment"; twin=""
[ -d "$t/environment/scorer" ] && copy="environment/scorer"   # a scorer sidecar holds the trusted copy
while read -r m sidecar tw; do
  [ -n "$m" ] && [[ "$n" == *"-$m" ]] || continue
  if [ "$tw" != "-" ]; then base="${n%-$m}"; twin="$tw"; ref="$base-$tw/tests"; fi
  [ "$sidecar" = 1 ] && copy="environment/sim"
  break
done <<< "$modes"
if [ -n "$base" ] && [ ! -d "$(dirname "$t")/$base-$twin" ]; then
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
