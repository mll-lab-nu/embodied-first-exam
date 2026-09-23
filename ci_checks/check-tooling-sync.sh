#!/usr/bin/env bash
# Harbor tasks are self-contained, so each one carries its own copy of the tooling and the verifier.
# This check is what stops those copies from quietly diverging: every file a task shares with its
# generator must be byte-identical to the one canonical source under scripts/<simulator>/shared/.
# Regenerate instead of hand-editing a copy: scripts/<simulator>/gen_tasks.py render <family>.
t="$1"; root="$(cd "$(dirname "$0")/.." && pwd)"; rc=0
sim=$(sed -n 's/^simulator *= *"\(.*\)"/\1/p' "$t/task.toml")
shared="$root/scripts/$sim/shared"
[ -d "$shared" ] || exit 0          # simulators without a generator are out of scope
pairs="rcb_hb.py:environment/rcb_hb.py rcb_hb.py:tests/rcb_hb.py grade.py:tests/grade.py rcb_rewards.py:tests/rcb_rewards.py"
# Limited mode (docs/LIMITED_MODE_1_1.md): the tooling runs only in the sim sidecar, from environment/sim/, and the
# verifier just reads that sidecar's log -- so the copies to keep in sync live there, next to the one instance.
limited=$(grep -c '^mode *= *"limited"' "$t/task.toml")
[ "$limited" -gt 0 ] && pairs="rcb_hb.py:environment/sim/rcb_hb.py rcb_rewards.py:environment/sim/rcb_rewards.py"
for pair in $pairs; do
  src="$shared/${pair%%:*}"; dst="$t/${pair#*:}"
  [ -f "$src" ] || continue
  cmp -s "$src" "$dst" || { echo "FAIL $t: ${pair#*:} differs from scripts/$sim/shared/${pair%%:*}"; rc=1; }
done
[ "$limited" -gt 0 ] || cmp -s "$t/environment/instance.npz" "$t/tests/instance.npz" || {
  echo "FAIL $t: tests/instance.npz is not a byte copy of environment/instance.npz"; rc=1; }
exit $rc
