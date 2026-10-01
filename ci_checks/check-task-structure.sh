#!/usr/bin/env bash
# Harbor task contract: the canonical files exist and scripts are executable. solution/solve.sh is required unless the
# task declares `oracle = "none"` (docs/PROTOCOL.md §2.1, §2.7).
t="$1"; rc=0
for f in task.toml instruction.md README.md environment/Dockerfile tests/test.sh; do
  [ -f "$t/$f" ] || { echo "FAIL $t: missing $f"; rc=1; }
done
[ -x "$t/tests/test.sh" ] || { echo "FAIL $t: tests/test.sh not executable"; rc=1; }
oracle=$(python3 -c 'import sys,tomllib; print(tomllib.load(open(sys.argv[1],"rb")).get("metadata",{}).get("oracle",""))' "$t/task.toml" 2>/dev/null)
if [ "$oracle" != "none" ]; then
  [ -f "$t/solution/solve.sh" ] || { echo "FAIL $t: missing solution/solve.sh (or declare oracle = \"none\")"; rc=1; }
  [ -f "$t/solution/solve.sh" ] && { [ -x "$t/solution/solve.sh" ] || { echo "FAIL $t: solution/solve.sh not executable"; rc=1; }; }
fi
exit $rc
