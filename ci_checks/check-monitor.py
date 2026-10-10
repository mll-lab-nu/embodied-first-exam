#!/usr/bin/env python3
"""PROTOCOL §2.10 (v1.2): every task with `[metadata.resources.limits]` runs the resource monitor sidecar and the verifier
step, wired exactly as scripts/rcb_monitor/inject.py writes them (task_conventions.py --check catches any drift from the
generator; this check catches a task the generator never ran on, and hand edits that break the safety properties).

    python3 ci_checks/check-monitor.py [task dirs]      # default: every task; also runs scripts/rcb_monitor/selftest.py
                                                        # and test_monitor.py
"""
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from rcb_monitor import inject  # noqa: E402

SRC = ROOT / "scripts" / "rcb_monitor"


def check(task: Path) -> list[str]:
    cfg = tomllib.loads((task / "task.toml").read_text())
    lim = ((cfg.get("metadata") or {}).get("resources") or {}).get("limits")
    if not isinstance(lim, dict):
        return []                                    # check-resources.py requires the limits; nothing to wire without them
    err = []
    comp = task / "environment" / "docker-compose.yaml"
    text = comp.read_text() if comp.is_file() else ""
    for f in inject.CODE:
        p = task / "environment" / "rcb_monitor" / f
        if not p.is_file() or p.read_bytes() != (SRC / f).read_bytes():
            err.append(f"environment/rcb_monitor/{f} is not a copy of scripts/rcb_monitor/{f}")
    if not (task / "tests" / "rcb_limits.py").is_file() or \
            (task / "tests" / "rcb_limits.py").read_bytes() != (SRC / "rcb_limits.py").read_bytes():
        err.append("tests/rcb_limits.py is not a copy of scripts/rcb_monitor/rcb_limits.py")
    a, b = task / "environment" / "rcb_monitor" / "limits.json", task / "tests" / "rcb_limits.json"
    if not (a.is_file() and b.is_file() and a.read_bytes() == b.read_bytes()):
        err.append("environment/rcb_monitor/limits.json and tests/rcb_limits.json differ (or are missing)")
    # the monitor service and its safety properties
    m = re.search(rf"(?ms)^{re.escape(inject.BEGIN)}.*?^{re.escape(inject.END)}$", text)
    if not m:
        err.append("environment/docker-compose.yaml has no rcb_monitor service")
    else:
        blk = m.group(0)
        for need in ("    pid: host", "    network_mode: none", "    cap_add: [SYS_PTRACE]", f"    image: {inject.IMAGE}",
                     "      - ./rcb_monitor:/opt/rcb_monitor:ro", "      RCB_LIMITS_ENFORCE: ${RCB_LIMITS_ENFORCE:-0}"):
            if need not in blk:
                err.append(f"rcb_monitor service: missing `{need.strip()}`")
    # every other service mounts its beacon read-only, the right one for the mode
    try:
        lines = text.splitlines(keepends=True)
        i, j = inject.services_span(lines)
        mode = inject.mode_of(task)
        for name, k0, k1 in inject.service_blocks(lines, i, j):
            if name == "rcb_monitor":
                continue
            want = ("rcb_limits:/run/rcb-limits:ro" if inject.kind_of(mode, name) == "scope"
                    else "rcb_observe:/run/rcb-observe:ro")
            if not any(want in ln for ln in lines[k0:k1]):
                err.append(f"service {name}: does not mount `{want}`")
            if any("/run/rcb-limits" in ln and ":ro" not in ln for ln in lines[k0:k1]):
                err.append(f"service {name}: mounts the beacon writable")
    except ValueError as e:
        err.append(f"environment/docker-compose.yaml: {e}")
    s = (task / "task.toml").read_text()
    if inject.ARTIFACT not in s:
        err.append("task.toml: the monitor's record is not an artifact of service rcb_monitor")
    hooks = re.findall(r'(?m)^\[\[verifier\.collect\]\]\nservice = "([^"]+)"', s)
    side = [h for h in hooks if h != "main"]
    if not side or side[0] != "rcb_monitor":
        err.append("task.toml: the first sidecar [[verifier.collect]] hook must be rcb_monitor's seal")
    sh = (task / "tests" / "test.sh").read_text() if (task / "tests" / "test.sh").is_file() else ""
    if inject.TRAP not in sh:
        err.append("tests/test.sh: no verifier-step trap")
    if inject.GUARD not in sh or inject.TRAP not in sh or not sh.index(inject.TRAP) < sh.index(inject.GUARD):
        err.append("tests/test.sh: no `rcb_limits.py sanitize /app/output` line after the trap (the agent's files are untrusted input)")
    elif any(re.search(r"grade|/app/output", ln) for ln in sh[:sh.index(inject.GUARD)].splitlines()
             if ln.strip() and not ln.lstrip().startswith("#") and inject.TRAP not in ln):
        err.append("tests/test.sh: something reads the agent's files before the sanitize line")
    if "COPY rcb_limits.py rcb_limits.json /tests/" not in ((task / "tests" / "Dockerfile").read_text()
                                                            if (task / "tests" / "Dockerfile").is_file() else ""):
        err.append("tests/Dockerfile: does not COPY rcb_limits.py rcb_limits.json")
    return err


def main(argv):
    dirs = [Path(a) for a in argv if (Path(a) / "task.toml").is_file()] or sorted(p.parent for p in (ROOT / "tasks").glob("*/task.toml"))
    bad = 0
    for test in ("selftest.py", "test_monitor.py"):      # the violation rule and the verifier step; the monitor's own logic
        r = subprocess.run([sys.executable, str(SRC / test)], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"FAIL scripts/rcb_monitor/{test}:\n" + r.stdout + r.stderr)
            bad = 1
    for d in dirs:
        for e in check(d):
            print(f"FAIL {d.name}: {e}")
            bad = 1
    if not bad:
        print(f"check-monitor: {len(dirs)} tasks ok")
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
