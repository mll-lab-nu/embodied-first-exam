#!/usr/bin/env bash
# task.toml: name matches folder, required metadata (docs/rcb/PROTOCOL.md §2.3, docs/rcb/TAXONOMY.md), deliverable dir, agent
# timeout cap.
# TopoGym (adapted from robot_coding_bench ad9f251e): the tier dirs topogym-<family>-{easy,medium,hard}-i00-{privileged,standard}
# follow protocol v1.0 (the directory ends in -privileged or -standard and `mode` says the same; no `tier`; agent cap 4 h).
# Jianwen's original frozen instances topogym-<family>-i00[-limited] are pre-v1.0 (legacy, superseded by the tier dirs; not
# migrated): they keep [task].name = topogym/<folder>, `tier`, and the 10 h cap of their knot_untying budget.
t="$1"; python3 - "$t" <<'PY'
import re, sys, tomllib, pathlib
t = pathlib.Path(sys.argv[1]); d = tomllib.load(open(t / "task.toml", "rb")); rc = 0
def fail(m):
    global rc; print(f"FAIL {t}: {m}"); rc = 1
legacy = bool(re.fullmatch(r"topogym-[a-z0-9-]+-i\d\d(-limited)?", t.name)) and not re.search(r"-(easy|medium|hard)-i\d\d", t.name)
m = d.get("metadata", {})
for k in ["author_name", "task_type", "simulator", "robot", "family", "expert_time_estimate_hours"]:
    if k not in m: fail(f"[metadata].{k} missing")
if m.get("task_type") not in ("trajectory", "policy"): fail("task_type must be trajectory|policy")
if "/app/output/" not in d.get("artifacts", []): fail('top-level artifacts must include "/app/output/"')
if not d.get("agent", {}).get("timeout_sec"): fail("[agent].timeout_sec required")
if legacy:
    if d.get("task", {}).get("name") not in (f"robot-coding-bench/{t.name}", f"topogym/{t.name}"):
        fail("[task].name must be robot-coding-bench/<folder> (or topogym/<folder> for the original i00 dirs)")
    if m.get("tier") not in ("privileged", "perception"): fail("tier must be privileged|perception (pre-v1.0 original dir)")
    if d.get("agent", {}).get("timeout_sec", 0) > 36000: fail("[agent].timeout_sec > 10h cap")
    sys.exit(rc)
if d.get("task", {}).get("name") != f"robot-coding-bench/{t.name}": fail("[task].name must be robot-coding-bench/<folder>")
# Protocol v1.0 (§2.2, §2.3): the directory ends in -privileged or -standard and `mode` says the same; no `tier`.
suffix = t.name.rsplit("-", 1)[-1]
if suffix not in ("privileged", "standard"): fail("directory name must end in -privileged or -standard")
if m.get("mode") not in ("privileged", "standard"): fail("[metadata].mode must be privileged|standard")
elif m["mode"] != suffix: fail(f"[metadata].mode = {m['mode']!r} but the directory ends in -{suffix}")
if "tier" in m: fail("[metadata].tier was removed in protocol v1.0 (use mode)")
if d.get("agent", {}).get("timeout_sec", 0) > 14400: fail("[agent].timeout_sec > 4h cap")
sys.exit(rc)
PY
