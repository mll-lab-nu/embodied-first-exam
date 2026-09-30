#!/usr/bin/env bash
# Run exactly five pending checks through the existing evidence-producing runner.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'HELP'
Usage: bash scripts/run_pending_simulator_checks.sh [NEW_OUTPUT_DIRECTORY]

Runs: Panda lifecycle stability; ALOHA output invariance; Panda output
invariance; installed-wheel runtime; same-process task switching.
Runs serially, continues after a failed case, stops on Ctrl+C.
Does not run the 13 base tasks or the already-passed FEM checkpoint probe.

Defaults: .venv-gs121-nyx/bin/python, .external/nyx-assets, 3600 seconds/case.
Overrides: TOPOGYM_TEST_PYTHON, TOPOGYM_VISUAL_ASSET_ROOT, TOPOGYM_TEST_TIMEOUT.
Creates a source/model snapshot and README.md + summary.json with evidence links.
Nyx external visual resources and installed engine dependencies are shared.
HELP
    exit 0
fi
if (( $# > 1 )); then
    echo "Expected at most one new output directory; see --help." >&2
    exit 2
fi
PYTHON="${TOPOGYM_TEST_PYTHON:-$ROOT/.venv-gs121-nyx/bin/python}"
VISUAL_ROOT="${TOPOGYM_VISUAL_ASSET_ROOT:-$ROOT/.external/nyx-assets}"
CASE_TIMEOUT="${TOPOGYM_TEST_TIMEOUT:-3600}"
OUT="${1:-$ROOT/runs/test_results/pending_five_$(date -u +%Y%m%dT%H%M%SZ)_$$}"
[[ -x "$PYTHON" ]] || { echo "Python not executable: $PYTHON" >&2; exit 2; }
[[ -d "$VISUAL_ROOT" ]] || { echo "Missing Nyx visual assets: $VISUAL_ROOT" >&2; exit 2; }
[[ "$CASE_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || { echo "Timeout must be a positive integer." >&2; exit 2; }

# No simulator imports in preparation. Refuse to reuse any previous output.
OUT="$OUT" "$PYTHON" - "$ROOT" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

root, out = Path(sys.argv[1]).resolve(), Path(os.environ["OUT"]).resolve()
out.mkdir(parents=True, exist_ok=False)
snapshot = out / "source"
snapshot.mkdir()
ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "agents")
for name in ("topogym", "tests", "scripts", "configs", "assets"):
    shutil.copytree(root / name, snapshot / name, ignore=ignore)
shutil.copy2(root / "pyproject.toml", snapshot / "pyproject.toml")
hashes = {}
changed = []
for path in sorted(snapshot.rglob("*")):
    if not path.is_file():
        continue
    relative = path.relative_to(snapshot)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    hashes[str(relative)] = digest
    original = root / relative
    if not original.is_file() or hashlib.sha256(original.read_bytes()).hexdigest() != digest:
        changed.append(str(relative))
(out / "snapshot_manifest.json").write_text(json.dumps(dict(
    source_root=str(root), snapshot_root=str(snapshot), sha256=hashes,
    changed_during_copy=changed,
    scope="Source and repository model assets copied; Nyx external assets and engine libraries shared",
), indent=2) + "\n")
if changed:
    raise SystemExit("Source changed during snapshot; no tests started. Retry with a new output directory.")
print(f"Frozen source/model assets: {snapshot}", flush=True)
PY
OUT="$(cd -- "$OUT" && pwd)"
VISUAL_ROOT="$(cd -- "$VISUAL_ROOT" && pwd)"
export TOPOGYM_ASSET_ROOT="$OUT/source/assets"
export PYTHONFAULTHANDLER=1
interrupted=0
trap 'interrupted=130' INT
trap 'interrupted=143' TERM
stability_rc=125
others_rc=125

echo "Results: $OUT"
echo "[1/5] Panda repeated reset / rewind / fault recovery / close"
if "$PYTHON" -u "$OUT/source/scripts/test_base_tasks.py" \
    --checks stability --robots panda_robotiq \
    --visual-asset-root "$VISUAL_ROOT" --timeout "$CASE_TIMEOUT" \
    --output "$OUT/panda_g2"; then
    stability_rc=0
else
    stability_rc=$?
fi

# The existing driver isolates each case, preserves crashes, and continues.
# Switching within task_switch and rebuilding within G2 still share one process.
if (( interrupted == 0 )) && [[ ! -f "$OUT/panda_g2/driver_interruption.json" ]]; then
    echo "[2–5/5] Both output checks, installed wheel, same-process task switching"
    if "$PYTHON" -u "$OUT/source/scripts/test_base_tasks.py" \
        --checks outputs installation --robots aloha panda_robotiq \
        --mechanisms-only --mechanisms task-switch \
        --visual-asset-root "$VISUAL_ROOT" --timeout "$CASE_TIMEOUT" \
        --output "$OUT/outputs_install_switch"; then
        others_rc=0
    else
        others_rc=$?
    fi
fi

# Missing/incomplete reports never count as a pass. Summarize even after failure.
if "$PYTHON" - "$OUT" "$stability_rc" "$others_rc" "$interrupted" <<'PY'
import json
from pathlib import Path
import sys

out = Path(sys.argv[1])
batch_codes = dict(zip(("panda_g2", "outputs_install_switch"), map(int, sys.argv[2:4])))
expected = {
    "stability_panda_robotiq": "panda_g2",
    "outputs_aloha": "outputs_install_switch",
    "outputs_panda_robotiq": "outputs_install_switch",
    "installation": "outputs_install_switch",
    "task_switch": "outputs_install_switch",
}
found, errors = {}, []
for batch in batch_codes:
    path = out / batch / "summary.json"
    try:
        data = json.loads(path.read_text())
        for row in data["results"]:
            name = row["task_id"]
            if name not in expected or expected[name] != batch or name in found:
                errors.append(f"Unexpected/duplicate case: {batch}/{name}")
            found[name] = dict(row, batch=batch)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"{batch}: {exc}")
rows = [found.get(name, dict(task_id=name, batch=batch, status="not_completed"))
        for name, batch in expected.items()]
passed = (not errors and int(sys.argv[4]) == 0
          and all(code == 0 for code in batch_codes.values())
          and all(row["status"] == "passed" for row in rows))
summary = dict(scope="Five pending common simulator checks; no base-task RGB retest or solvability claim",
               status="passed" if passed else "not_passed", results=rows,
               batch_exit_codes=batch_codes, interrupted=int(sys.argv[4]), errors=errors,
               source_manifest="snapshot_manifest.json")
(out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
lines = ["# Five pending simulator checks", "", f"Overall: **{summary['status']}**", "",
         "Nyx + compact_lab; frozen source/model assets: `source/`; hashes: `snapshot_manifest.json`.",
         "Nyx external visual assets and installed engine libraries are shared, not copied.",
         "These are mechanism tests, not solved-task demos or the 13-task RGB recheck.", "",
         "| Check | Status | Evidence | Representative video |", "|---|---|---|---|"]
for row in rows:
    batch, name = row["batch"], row["task_id"]
    links = []
    for label, relative in (("report", f"{batch}/{name}/report.json"),
                            ("log", f"{batch}/{name}.log"), ("batch index", f"{batch}/README.md")):
        if (out / relative).exists():
            links.append(f"[{label}]({relative})")
    video = f"[{name} MP4]({batch}/{row['video']})" if row.get("video") else "unavailable (see report/log)"
    lines.append(f"| {name} | {row['status']} | {' · '.join(links) or 'not produced'} | {video} |")
lines += ["", "Per-case reports list every camera/episode/branch recording and physical checkpoints.",
          "A native crash may leave partial or undecodable video; it is not a passing recording.",
          "A log entry `Timeout (0:02:00)!` is the periodic faulthandler stack dump, not the case timeout."]
if errors:
    lines += ["", "Aggregation issues:", ""] + [f"- {error}" for error in errors]
(out / "README.md").write_text("\n".join(lines) + "\n")
print(f"\nOverall: {summary['status']}\nRead: {out / 'README.md'}\nSend: {out / 'summary.json'}")
raise SystemExit(0 if passed else 1)
PY
then
    exit 0
else
    if (( interrupted != 0 )); then exit "$interrupted"; fi
    exit 1
fi
