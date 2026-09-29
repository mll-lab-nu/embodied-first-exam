#!/usr/bin/env bash
# Harbor task contract: the canonical files exist and scripts are executable.
t="$1"; rc=0
for f in task.toml instruction.md README.md environment/Dockerfile tests/test.sh solution/solve.sh; do
  [ -f "$t/$f" ] || { echo "FAIL $t: missing $f"; rc=1; }
done
[ -x "$t/tests/test.sh" ] || { echo "FAIL $t: tests/test.sh not executable"; rc=1; }
[ -x "$t/solution/solve.sh" ] || { echo "FAIL $t: solution/solve.sh not executable"; rc=1; }
exit $rc
