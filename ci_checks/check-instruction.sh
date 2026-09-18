#!/usr/bin/env bash
# instruction.md names the deliverable under /app/output/ and never leaks the verifier's /tests/ copy.
t="$1"; rc=0
grep -q '/app/output/' "$t/instruction.md" || { echo "FAIL $t: instruction.md must state the deliverable under /app/output/"; rc=1; }
grep -q '/tests/' "$t/instruction.md" && { echo "FAIL $t: instruction.md must not reference /tests/"; rc=1; }
exit $rc
