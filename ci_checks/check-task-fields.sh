#!/usr/bin/env bash
# ADVISORY. task.toml: name matches folder, required metadata (docs/PROTOCOL.md §1, §2, docs/TAXONOMY.md), deliverable
# dir, agent timeout cap (14400 s for every task), the task's declared scene dynamics (no central table, board 0124).
t="$1"; python3 - "$t" "$(cd "$(dirname "$0")/.." && pwd)" <<'PY'
import sys, tomllib, pathlib
t = pathlib.Path(sys.argv[1]); d = tomllib.load(open(t / "task.toml", "rb")); rc = 0
def fail(m):
    global rc; print(f"FAIL {t}: {m}"); rc = 1
if d.get("task", {}).get("name") != f"robot-coding-bench/{t.name}": fail("[task].name must be robot-coding-bench/<folder>")
m = d.get("metadata", {})
for k in ["author_name", "task_type", "simulator", "robot", "family", "expert_time_estimate_hours"]:
    if k not in m: fail(f"[metadata].{k} missing")
if m.get("task_type") not in ("trajectory", "policy"): fail("task_type must be trajectory|policy")
# Protocol v1.1.1 (§2.2, §2.3, D12): the directory ends in its mode (-privileged, -standard, -standard-realtime, or a mode
# added to the registry, §2.16) and `mode` says the same; no `tier`. The suffix is the whole mode name, longest first:
# -standard-realtime is not -realtime. The modes: RCB_MODES_TABLE (run_all.sh) or scripts/task_conventions.py MODE_REGISTRY.
import os
table = os.environ.get("RCB_MODES_TABLE", "")
if not table:
    sys.path.insert(0, str(pathlib.Path(sys.argv[2]) / "scripts")); import task_conventions as tc; table = tc.modes_table()
MODES = tuple(l.split()[0] for l in table.splitlines() if l.strip())   # longest first
suffix = next((x for x in MODES if t.name.endswith("-" + x)), t.name.rsplit("-", 1)[-1])
if suffix not in MODES: fail("directory name must end in " + ", ".join("-" + x for x in MODES))
if m.get("mode") not in MODES: fail("[metadata].mode must be " + "|".join(MODES))
elif m["mode"] != suffix: fail(f"[metadata].mode = {m['mode']!r} but the directory ends in -{suffix}")
if "tier" in m: fail("[metadata].tier was removed in protocol v1.0 (use mode)")
if m.get("dynamics") not in ("static", "dynamic"):
    fail(f'[metadata].dynamics must be declared, "static" or "dynamic" (PROTOCOL §2), got {m.get("dynamics")!r}')
if "/app/output/" not in d.get("artifacts", []): fail('top-level artifacts must include "/app/output/"')
if not d.get("agent", {}).get("timeout_sec"): fail("[agent].timeout_sec required")
else:
    # PROTOCOL D8 / §2.3: 14400 s cap, no benchmark excepted (the same cap: scripts/task_conventions.py CUTOFF_CAP)
    if d["agent"]["timeout_sec"] > 14400:
        fail("[agent].timeout_sec > 14400 s cap (4h, PROTOCOL §2.3)")
sys.exit(rc)
PY
