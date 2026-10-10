#!/usr/bin/env bash
# Unit tests of benchmark tooling that need only the Python standard library and a shell (no numpy, no simulator, no
# image): the graders and collect hooks that decide a verdict from files. Tests that need numpy or more
# (scripts/*/tests/test_*server*.py, the eai-standard selftests) are run by hand: see each benchmark's
# docs/benchmarks/<bench>.md. The resource monitor's own tests are run by check-monitor.py.
# Usage: check-unit-tests.sh   (repo-level; run_all.sh calls it once)
set -uo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"; rc=0
for t in robolab/tests/test_grade_standard.py labutopia/tests/test_grade_standard.py labutopia/tests/test_finalize.py; do
  [ -f "$root/scripts/$t" ] || continue
  if out=$(cd "${TMPDIR:-/tmp}" && timeout 300 python3 "$root/scripts/$t" 2>&1); then echo "ok scripts/$t: ${out##*$'\n'}"
  else echo "FAIL scripts/$t:"; echo "$out" | tail -n 40; rc=1; fi
done
exit $rc
