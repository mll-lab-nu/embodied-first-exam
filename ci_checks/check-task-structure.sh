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
# No agent results in the repository (docs/PROTOCOL.md D3): they are published on the results site.
[ -e "$t/results" ] && { echo "FAIL $t: results/ does not belong in the repository (PROTOCOL D3)"; rc=1; }
# README in the standard layout (docs/PROTOCOL.md §2.1).
python3 - "$t" <<'PY' || rc=1
import re, sys, pathlib
t = pathlib.Path(sys.argv[1]); s = (t / "README.md").read_text() if (t / "README.md").is_file() else ""
bad = []
if not s.startswith(f"# {t.name}\n"): bad.append(f"first line must be '# {t.name}'")
for k in ("Benchmark", "Mode", "Twin", "Simulator / robot", "Family / instance", "Oracle", "Agent time budget", "Base image"):
    if not re.search(rf"^\| {re.escape(k)} \| ", s, re.M): bad.append(f"key table row '{k}' missing")
pos = [s.find(f"\n## {h}\n") for h in ("Task", "Difficulty", "Reference solution", "Verification")]
if -1 in pos or pos != sorted(pos): bad.append("sections ## Task, ## Difficulty, ## Reference solution, ## Verification (in this order) required")
for b in bad: print(f"FAIL {t}: README.md: {b}")
sys.exit(1 if bad else 0)
PY
exit $rc
