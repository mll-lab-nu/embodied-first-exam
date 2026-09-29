#!/usr/bin/env bash
# Harbor tasks are self-contained, so each one carries its own copy of the tooling and the verifier.
# This check is what stops those copies from quietly diverging: every file a task shares with its
# generator must be byte-identical to the one canonical source under scripts/<simulator>/shared/.
# Regenerate instead of hand-editing a copy: scripts/<simulator>/gen_tasks.py render <family>.
t="$1"; root="$(cd "$(dirname "$0")/.." && pwd)"; rc=0
sim=$(sed -n 's/^simulator *= *"\(.*\)"/\1/p' "$t/task.toml")
shared="$root/scripts/$sim/shared"
[ -d "$shared" ] || exit 0          # simulators without a generator are out of scope
# <source>:<copy>. A source lives under scripts/<sim>/shared/, or, marked @, under scripts/limited/ (the parts of
# limited mode that are the same for every simulator).
pairs="rcb_hb.py:environment/rcb_hb.py rcb_hb.py:tests/rcb_hb.py rcb_rewards.py:tests/rcb_rewards.py
  rcb_kinder.py:environment/rcb_kinder.py rcb_kinder.py:tests/rcb_kinder.py grade.py:tests/grade.py"
# Limited mode (docs/LIMITED_MODE_1_1.md): the tooling runs only in the sim sidecar, from environment/sim/, and the
# verifier just reads that sidecar's log -- so the copies to keep in sync live there, next to the one instance.
limited=$(grep -c '^mode *= *"limited"' "$t/task.toml")
[ "$limited" -gt 0 ] && pairs="rcb_hb.py:environment/sim/rcb_hb.py rcb_rewards.py:environment/sim/rcb_rewards.py
  rcb_kinder.py:environment/sim/rcb_kinder.py limited/server.py:environment/sim/server.py
  limited/rcb_client.py:environment/rcb_client.py @rcb_service.py:environment/sim/rcb_service.py @grade.py:tests/grade.py"
for pair in $pairs; do
  src="${pair%%:*}"; dst="$t/${pair#*:}"
  case "$src" in @*) src="$root/scripts/limited/${src#@}" ;; *) src="$shared/$src" ;; esac
  [ -f "$src" ] || continue
  cmp -s "$src" "$dst" || { echo "FAIL $t: ${pair#*:} differs from ${src#"$root"/}"; rc=1; }
done
# The limited client is one implementation under each simulator's docstring (its agents' API reference): the code
# below the docstring must be scripts/limited/rcb_client.py's.
body() { python3 -c 'import ast, sys; s = open(sys.argv[1]).read(); print("\n".join(s.splitlines()[ast.parse(s).body[0].end_lineno:]))' "$1"; }
[ "$limited" -gt 0 ] && [ "$(body "$t/environment/rcb_client.py")" != "$(body "$root/scripts/limited/rcb_client.py")" ] && {
  echo "FAIL $t: environment/rcb_client.py's code differs from scripts/limited/rcb_client.py's"; rc=1; }
# One instance per task, byte for byte in every place it is read; a limited twin runs its unlimited twin's scene.
found=0
for inst in instance.npz instance.json; do
  if [ "$limited" -gt 0 ]; then
    twin="${t%-limited}"
    [ -f "$twin/environment/$inst" ] || continue
    found=1; cmp -s "$twin/environment/$inst" "$t/environment/sim/$inst" || {
      echo "FAIL $t: environment/sim/$inst is not a byte copy of $(basename "$twin")/environment/$inst"; rc=1; }
  elif [ -f "$t/environment/$inst" ]; then
    found=1; cmp -s "$t/environment/$inst" "$t/tests/$inst" || {
      echo "FAIL $t: tests/$inst is not a byte copy of environment/$inst"; rc=1; }
  fi
done
[ "$limited" -gt 0 ] || [ "$found" -eq 1 ] || { echo "FAIL $t: no environment/instance.npz or instance.json"; rc=1; }
exit $rc
