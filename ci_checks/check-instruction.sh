#!/usr/bin/env bash
# instruction.md must name the deliverable path and not leak the grader's instance copy.
t="$1"; rc=0
grep -q '/app/output/trajectory.npz' "$t/instruction.md" || { echo "FAIL $t: instruction.md must state the deliverable /app/output/trajectory.npz"; rc=1; }
grep -q '/tests/' "$t/instruction.md" && { echo "FAIL $t: instruction.md must not reference /tests/"; rc=1; }
exit $rc
