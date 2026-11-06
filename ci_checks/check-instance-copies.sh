#!/usr/bin/env bash
# INVARIANT (docs/protocol/README.md Appendix H.4 identical instance copies, H.7 twins share one frozen instance): part of the
# required CI job `invariants` (ci_checks/run_invariants.sh). The verifier's copy of the frozen instance, the privileged
# task's tests/<instance>, and the copy the task runs from (privileged: environment/, or environment/scorer/ where a
# scorer sidecar holds the trusted copy and the agent's environment/ copy is reduced by design; standard and realtime:
# the sim sidecar's environment/sim/, and their own tests/ copy where they carry one) are byte-identical. A standard or
# realtime task shares its privileged twin's copy where the twin exists; without a twin (a benchmark may ship any subset
# of the modes; the README's Twin row says why, an advisory check reads it) it carries its own, and its sim copy and its
# tests/ copy, where both exist, are byte-identical.
# The instance files (the names the suites freeze an instance under):
#   instance.json, instance.npz   the frozen instance; neither copy exists without the other
#   runtime_binding.json          an instance's lock (file hashes of an instance staged from the image)
#   match_instance.json           a match's frozen settings
#   instance/                     a directory of instance files, compared file by file
# For the last three, a copy the task runs from needs the reference copy (tests/ of the task or its privileged twin); a
# reference copy alone is allowed (a task whose environment stages the instance from its image, or takes its settings in
# another form, checked against the reference by the verifier).
# Usage: check-instance-copies.sh tasks/<benchmark>/<task-dir>
set -uo pipefail
t="${1%/}"; n="$(basename "$t")"; rc=0
root="$(cd "$(dirname "$0")/.." && pwd)"
# the mode registry (PROTOCOL §3; run_all.sh reads it once): "<mode> <sidecar 0|1> <twin mode or ->", longest first
modes="${RCB_MODES_TABLE:-$(python3 "$root/scripts/task_conventions.py" modes)}"
STRICT="instance.json instance.npz"; LOOSE="runtime_binding.json match_instance.json instance"
base=""; ref="$n/tests"; copy="environment"; twin=""
[ -d "$t/environment/scorer" ] && copy="environment/scorer"   # a scorer sidecar holds the trusted copy
while read -r m sidecar tw; do
  [ -n "$m" ] && [[ "$n" == *"-$m" ]] || continue
  if [ "$tw" != "-" ]; then base="${n%-$m}"; twin="$tw"; ref="$base-$tw/tests"; fi
  [ "$sidecar" = 1 ] && copy="environment/sim"
  break
done <<< "$modes"
same() { if [ -d "$1" ] || [ -d "$2" ]; then diff -rq "$1" "$2" >/dev/null 2>&1; else cmp -s "$1" "$2" 2>/dev/null; fi; }
if [ -n "$base" ] && [ ! -d "$(dirname "$t")/$base-$twin" ]; then
  for f in $STRICT $LOOSE; do   # no twin: its own two copies, where both exist, agree
    a="$t/tests/$f"; b="$t/$copy/$f"
    [ -e "$a" ] && [ -e "$b" ] && ! same "$a" "$b" && { echo "FAIL $t: $copy/$f and tests/$f differ"; rc=1; }
  done
  exit $rc
fi
for f in $STRICT $LOOSE; do
  a="$(dirname "$t")/$ref/$f"; b="$t/$copy/$f"
  copies=("$b"); [ "$ref" != "$n/tests" ] && copies+=("$t/tests/$f")   # a twin's own tests/ copy, where it has one
  if [[ " $STRICT " == *" $f "* ]] && { [ -e "$a" ] || [ -e "$b" ]; }; then
    same "$a" "$b" || { echo "FAIL $t: $copy/$f and $ref/$f differ, or one is missing"; rc=1; }
    copies=("${copies[@]:1}")
  fi
  for c in "${copies[@]}"; do
    [ -e "$c" ] || continue
    same "$a" "$c" || { echo "FAIL $t: ${c#"$t/"} and $ref/$f differ, or $ref/$f is missing"; rc=1; }
  done
done
exit $rc
