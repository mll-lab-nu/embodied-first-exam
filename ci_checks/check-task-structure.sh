#!/usr/bin/env bash
# Every task must have the canonical files.
t="$1"; rc=0
for f in task.toml instruction.md README.md environment/Dockerfile environment/instance.npz tests/test.sh tests/instance.npz solution/solve.sh; do
  [ -f "$t/$f" ] || { echo "FAIL $t: missing $f"; rc=1; }
done
[ -x "$t/tests/test.sh" ] || { echo "FAIL $t: tests/test.sh not executable"; rc=1; }
[ -x "$t/solution/solve.sh" ] || { echo "FAIL $t: solution/solve.sh not executable"; rc=1; }
exit $rc
