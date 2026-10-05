#!/usr/bin/env bash
# PROTOCOL §2.9: the agent's clock starts once the simulator is ready. Every task declares [environment.healthcheck], which
# Harbor runs in the agent's container before it sets up the agent:
# - standard mode: exactly the client's readiness test (scripts/task_conventions.py READY_COMMAND: Robot() connects once
#   the service has built the scene and begun the episode), with a start period;
# - privileged mode: the benchmark's warm-up (task_conventions.py WARMUP): one launch of the simulator through the task's
#   tooling, its session log off, its start and end times in /logs/artifacts/rcb_warmup.log.
# scripts/task_conventions.py writes both (normalize); `task_conventions.py --check` compares the whole table.
# Usage: check-start-gate.sh <task_dir>
set -uo pipefail
t="${1%/}"
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 - "$t" "$root/scripts" <<'PY'
import re, sys, tomllib
from pathlib import Path
task, scripts = Path(sys.argv[1]), sys.argv[2]
sys.path.insert(0, scripts)
from task_conventions import READY_COMMAND  # noqa: E402
cfg = tomllib.loads((task / "task.toml").read_text())
mode = cfg.get("metadata", {}).get("mode") or ("standard" if task.name.endswith("-standard") else "privileged")
hc = cfg.get("environment", {}).get("healthcheck")
bad = []
if not isinstance(hc, dict) or not str(hc.get("command", "")).strip():
    bad.append("no [environment.healthcheck] command: the simulator must be ready before the agent's clock starts "
               "(PROTOCOL §2.9; add the benchmark to WARMUP in scripts/task_conventions.py and normalize the task)")
elif mode == "standard":
    if hc["command"] != READY_COMMAND:
        bad.append(f"standard-mode healthcheck must be the client's readiness test: {READY_COMMAND}")
    if float(hc.get("start_period_sec", 0)) < 600:
        bad.append("standard-mode healthcheck needs start_period_sec >= 600 (the service's start-up)")
else:
    c = hc["command"]
    for need, why in (("/logs/artifacts/rcb_warmup.log", "the warm-up logs to /logs/artifacts/rcb_warmup.log"),
                      ("warm-up start", "the log has the warm-up's start time"), ("warm-up done", "and its end time"),
                      ("RCB_SESSION_LOG= ", "the warm-up writes no session log")):
        if need not in c:
            bad.append(f"privileged warm-up: {why} (missing {need!r})")
    if not re.search(r"\bSession\(", c):
        bad.append("privileged warm-up: it opens the tooling's Session")
    if float(hc.get("timeout_sec", 0)) < 600:
        bad.append("privileged warm-up needs timeout_sec >= 600")
for b in bad:
    print(f"FAIL {task}: {b}")
sys.exit(1 if bad else 0)
PY
