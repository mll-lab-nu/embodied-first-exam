#!/usr/bin/env bash
# task.toml: required metadata, name matches folder, valid enums.
t="$1"; python3 - "$t" <<'PY'
import sys, tomllib, pathlib
t = pathlib.Path(sys.argv[1]); d = tomllib.load(open(t / "task.toml", "rb")); rc = 0
def fail(m):
    global rc; print(f"FAIL {t}: {m}"); rc = 1
if d.get("task", {}).get("name") != f"robot-coding-bench/{t.name}": fail("[task].name must be robot-coding-bench/<folder>")
m = d.get("metadata", {})
for k in ["author_name", "task_type", "simulator", "robot", "family", "tier", "instance_seed", "instance_sha256", "image", "expert_time_estimate_hours"]:
    if k not in m: fail(f"[metadata].{k} missing")
if m.get("task_type") not in ("trajectory", "policy"): fail("task_type must be trajectory|policy")
if m.get("tier") not in ("privileged", "perception"): fail("tier must be privileged|perception")
if d.get("artifacts") != ["/app/output/"]: fail('top-level artifacts must be ["/app/output/"]')
if not d.get("agent", {}).get("timeout_sec"): fail("[agent].timeout_sec required")
if d["agent"]["timeout_sec"] > 14400: fail("[agent].timeout_sec > 4h cap")
sys.exit(rc)
PY
