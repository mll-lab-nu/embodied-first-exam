#!/usr/bin/env bash
# ADVISORY. task.toml: name matches folder, required metadata (docs/protocol/README.md §1, §2, docs/TAXONOMY.md), deliverable
# dir, the task's declared scene dynamics (no central table). The agent's timeout: check-cutoffs.py.
t="$1"; python3 - "$t" "$(cd "$(dirname "$0")/.." && pwd)" <<'PY'
import sys, tomllib, pathlib
t = pathlib.Path(sys.argv[1]); d = tomllib.load(open(t / "task.toml", "rb")); rc = 0
def fail(m):
    global rc; print(f"FAIL {t}: {m}"); rc = 1
if d.get("task", {}).get("name") != f"embodied-first-exam/{t.name}": fail("[task].name must be embodied-first-exam/<folder>")
m = d.get("metadata", {})
for k in ["task_type", "simulator", "robot", "family", "expert_time_estimate_hours"]:
    if k not in m: fail(f"[metadata].{k} missing")
if m.get("task_type") not in ("trajectory", "policy"): fail("task_type must be trajectory|policy")
# PROTOCOL §1, §3: the directory ends in its mode (-privileged, -standard, -realtime, or a mode added to the
# registry), the one place that says it; no `tier`. The suffix is the whole mode name, longest first (no mode
# name ends in another's). The modes: RCB_MODES_TABLE (run_all.sh) or scripts/task_conventions.py MODE_REGISTRY.
import os
table = os.environ.get("RCB_MODES_TABLE", "")
if not table:
    sys.path.insert(0, str(pathlib.Path(sys.argv[2]) / "scripts")); import task_conventions as tc; table = tc.modes_table()
MODES = tuple(l.split()[0] for l in table.splitlines() if l.strip())   # longest first
suffix = next((x for x in MODES if t.name.endswith("-" + x)), t.name.rsplit("-", 1)[-1])
if suffix not in MODES: fail("directory name must end in " + ", ".join("-" + x for x in MODES))
# no copies of what another source says (scripts/task_conventions.py normalize removes them): the mode is the directory's
# suffix, the reset budget and the slowdown S the sim service's RCB_RESET_BUDGET and RCB_SLOWDOWN defaults
# (ci_checks/check-realtime.py), the egress [agent] network_mode (ci_checks/check-verifier-isolation.sh)
for k, src in (("mode", "the directory's suffix"), ("reset_budget", "the sim service's RCB_RESET_BUDGET default"),
               ("slowdown", "the sim service's RCB_SLOWDOWN default")):
    if k in m: fail(f"[metadata].{k} copies {src}: drop it (scripts/task_conventions.py normalize)")
if "tier" in m: fail("[metadata].tier is not a task field (the mode is the directory name's suffix)")
if m.get("dynamics") not in ("static", "dynamic"):
    fail(f'[metadata].dynamics must be declared, "static" or "dynamic" (PROTOCOL §2), got {m.get("dynamics")!r}')
if "/app/output/" not in d.get("artifacts", []): fail('top-level artifacts must include "/app/output/"')
sys.exit(rc)
PY
