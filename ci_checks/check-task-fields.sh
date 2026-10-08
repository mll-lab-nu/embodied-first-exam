#!/usr/bin/env bash
# task.toml: name matches folder, required metadata (docs/PROTOCOL.md §2.3, docs/TAXONOMY.md), deliverable dir, agent timeout cap (with per-benchmark exceptions).
t="$1"; python3 - "$t" <<'PY'
import sys, tomllib, pathlib
t = pathlib.Path(sys.argv[1]); d = tomllib.load(open(t / "task.toml", "rb")); rc = 0
def fail(m):
    global rc; print(f"FAIL {t}: {m}"); rc = 1
if d.get("task", {}).get("name") != f"robot-coding-bench/{t.name}": fail("[task].name must be robot-coding-bench/<folder>")
m = d.get("metadata", {})
for k in ["author_name", "task_type", "simulator", "robot", "family", "expert_time_estimate_hours"]:
    if k not in m: fail(f"[metadata].{k} missing")
if m.get("task_type") not in ("trajectory", "policy"): fail("task_type must be trajectory|policy")
# Protocol v1.1 (§2.2, §2.3, D12): the directory ends in its mode (-privileged, -standard, -realtime) and `mode` says the
# same; no `tier`.
MODES = ("privileged", "standard", "realtime")
suffix = t.name.rsplit("-", 1)[-1]
if suffix not in MODES: fail("directory name must end in -privileged, -standard or -realtime")
if m.get("mode") not in MODES: fail("[metadata].mode must be privileged|standard|realtime")
elif m["mode"] != suffix: fail(f"[metadata].mode = {m['mode']!r} but the directory ends in -{suffix}")
if "tier" in m: fail("[metadata].tier was removed in protocol v1.0 (use mode)")
if "/app/output/" not in d.get("artifacts", []): fail('top-level artifacts must include "/app/output/"')
if not d.get("agent", {}).get("timeout_sec"): fail("[agent].timeout_sec required")
else:
    # PROTOCOL §2.3: 14400 s cap; per-benchmark exceptions by owner decision, recorded in PROTOCOL §2.3 (task-directory prefix -> cap)
    BUDGET_EXCEPTIONS = {"robotangle-": 21600}   # RoboTangle, owner 2026-10-08 (issue #87)
    cap = next((c for p, c in BUDGET_EXCEPTIONS.items() if t.name.startswith(p)), 14400)
    if d["agent"]["timeout_sec"] > cap:
        fail(f"[agent].timeout_sec > {cap} s cap" + (" (4h, PROTOCOL §2.3)" if cap == 14400 else " (documented exception, PROTOCOL §2.3)"))
sys.exit(rc)
PY
