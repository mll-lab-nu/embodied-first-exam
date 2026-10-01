#!/usr/bin/env bash
# task.toml: name matches folder, required metadata (docs/TAXONOMY.md), deliverable dir, agent timeout cap.
# TopoGym (adapted from robot_coding_bench fa59c1a6): [task].name = robot-coding-bench/<folder> (docs/rcb/TAXONOMY.md); the
# first frozen instances (tasks/topogym-<family>-i00[-limited]) keep their original topogym/<folder>. Agent cap 10 h
# (knot_untying's budget; every other family 6 h).
t="$1"; python3 - "$t" <<'PY'
import sys, tomllib, pathlib
t = pathlib.Path(sys.argv[1]); d = tomllib.load(open(t / "task.toml", "rb")); rc = 0
def fail(m):
    global rc; print(f"FAIL {t}: {m}"); rc = 1
if d.get("task", {}).get("name") not in (f"robot-coding-bench/{t.name}", f"topogym/{t.name}"):
    fail("[task].name must be robot-coding-bench/<folder> (or topogym/<folder> for the original i00 dirs)")
m = d.get("metadata", {})
for k in ["author_name", "task_type", "simulator", "robot", "family", "tier", "expert_time_estimate_hours"]:
    if k not in m: fail(f"[metadata].{k} missing")
if m.get("task_type") not in ("trajectory", "policy"): fail("task_type must be trajectory|policy")
if m.get("tier") not in ("privileged", "perception"): fail("tier must be privileged|perception")
if "/app/output/" not in d.get("artifacts", []): fail('top-level artifacts must include "/app/output/"')
if not d.get("agent", {}).get("timeout_sec"): fail("[agent].timeout_sec required")
elif d["agent"]["timeout_sec"] > 36000: fail("[agent].timeout_sec > 10h cap")
sys.exit(rc)
PY
