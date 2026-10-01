#!/usr/bin/env bash
# task.toml: name matches folder, required metadata (docs/PROTOCOL.md §2.3, docs/TAXONOMY.md), deliverable dir, agent timeout cap.
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
# Protocol v1.0: `mode` (privileged | standard) replaces `tier`. Until the migration PR lands, a task may carry either;
# legacy values are reported by check-protocol-v1.py.
if "mode" not in m and "tier" not in m: fail("[metadata].mode missing (privileged | standard)")
if "mode" in m and m["mode"] not in ("privileged", "standard", "limited"): fail("mode must be privileged|standard")
if "tier" in m and m["tier"] not in ("privileged", "perception"): fail("tier (deprecated) must be privileged|perception")
if "/app/output/" not in d.get("artifacts", []): fail('top-level artifacts must include "/app/output/"')
if not d.get("agent", {}).get("timeout_sec"): fail("[agent].timeout_sec required")
elif d["agent"]["timeout_sec"] > 14400: fail("[agent].timeout_sec > 4h cap")
sys.exit(rc)
PY
