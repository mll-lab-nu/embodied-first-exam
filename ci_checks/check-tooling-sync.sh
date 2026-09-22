#!/usr/bin/env bash
# Harbor tasks are self-contained, so each one carries its own copy of the tooling and the verifier.
# This check is what stops those copies from quietly diverging: every file a task shares with its
# generator must be byte-identical to the one canonical source under scripts/<simulator>/shared/.
# Regenerate instead of hand-editing a copy: scripts/<simulator>/gen_tasks.py render <family>.
t="$1"; root="$(cd "$(dirname "$0")/.." && pwd)"; rc=0
sim=$(sed -n 's/^simulator *= *"\(.*\)"/\1/p' "$t/task.toml")
shared="$root/scripts/$sim/shared"
[ -d "$shared" ] || exit 0          # simulators without a generator are out of scope
for pair in "rcb_hb.py:environment/rcb_hb.py" "rcb_hb.py:tests/rcb_hb.py" "grade.py:tests/grade.py" \
             "rcb_rewards.py:tests/rcb_rewards.py"; do
  src="$shared/${pair%%:*}"; dst="$t/${pair#*:}"
  [ -f "$src" ] || continue
  cmp -s "$src" "$dst" || { echo "FAIL $t: ${pair#*:} differs from scripts/$sim/shared/${pair%%:*}"; rc=1; }
done
cmp -s "$t/environment/instance.npz" "$t/tests/instance.npz" || {
  echo "FAIL $t: tests/instance.npz is not a byte copy of environment/instance.npz"; rc=1; }
exit $rc
