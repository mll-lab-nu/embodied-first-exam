#!/usr/bin/env python3
"""Two tiers (board 0124). INVARIANT (docs/protocol/README.md Appendix H.1; `--tier invariants`, part of the required CI job):
the monitor sidecar that check-verifier-isolation.sh exempts is held to its own isolation (no network, its code from
the pinned image and its limits read-only, the beacons read-only in every other service, its seal the first sidecar collect hook), and tests/test.sh
sanitizes /app/output before anything reads the agent's files, and the monitor image every task pins carries this
repository's monitor code (images/monitor/rcb_monitor/inject.py CONTENTS = the sha256 of images/monitor/rcb_monitor/{monitor,rcb_limits,
selftest}.py). ADVISORY (`--tier advisory`): the task's two copies of the limits, no copy of the code in the task, the
verifier step's trap and COPY lines, and the monitor's own tests. Default: both.

PROTOCOL v1 §2.10 (v1.2): every task with `[metadata.resources.limits]` runs the resource monitor sidecar and the verifier
step, wired exactly as images/monitor/rcb_monitor/inject.py writes them (task_conventions.py --check catches any drift from the
generator; this check catches a task the generator never ran on, and hand edits that break the safety properties).

    python3 ci_checks/check-monitor.py [--tier invariants|advisory|all] [task dirs]   # default: every task, both tiers
                                                        # (advisory: also runs images/monitor/rcb_monitor/selftest.py and test_monitor.py)
"""
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "images/monitor"))
from rcb_monitor import inject  # noqa: E402
import task_conventions as tc  # noqa: E402  (iter_tasks: the task tree)

SRC = ROOT / "images" / "monitor" / "rcb_monitor"


def check(task: Path) -> tuple[list[str], list[str]]:
    """(invariant errors, advisory errors)."""
    cfg = tomllib.loads((task / "task.toml").read_text())
    lim = ((cfg.get("metadata") or {}).get("resources") or {}).get("limits")
    if not isinstance(lim, dict):
        return [], []                                # check-resources.py requires the limits; nothing to wire without them
    err, inv = [], []
    comp = task / "environment" / "docker-compose.yaml"
    text = comp.read_text() if comp.is_file() else ""
    mon = task / "environment" / "rcb_monitor"
    extra = sorted(p.name for p in mon.iterdir() if p.name != "limits.json") if mon.is_dir() else []
    if extra:   # the code is the pinned image's (inject.IMAGE); a copy here would be shadowed by nothing and drift
        err.append(f"environment/rcb_monitor/ holds {', '.join(extra)}: only limits.json (the code is in {inject.IMAGE})")
    if (task / "tests" / "rcb_limits.py").exists():
        err.append("tests/rcb_limits.py: the verifier's copy comes from the monitor image (tests/Dockerfile COPY --from)")
    a, b = task / "environment" / "rcb_monitor" / "limits.json", task / "tests" / "rcb_limits.json"
    if not (a.is_file() and b.is_file() and a.read_bytes() == b.read_bytes()):
        err.append("environment/rcb_monitor/limits.json and tests/rcb_limits.json differ (or are missing)")
    # the monitor service and its safety properties
    m = re.search(rf"(?ms)^{re.escape(inject.BEGIN)}.*?^{re.escape(inject.END)}$", text)
    if not m:
        inv.append("environment/docker-compose.yaml has no rcb_monitor service")
    else:
        blk = m.group(0)
        for need in ("    pid: host", "    network_mode: none", "    cap_add: [SYS_PTRACE]", f"    image: {inject.IMAGE}",
                     f"      - {inject.LIMITS_MOUNT}", "      RCB_LIMITS_ENFORCE: ${RCB_LIMITS_ENFORCE:-0}"):
            if need not in blk:
                (err if "RCB_LIMITS_ENFORCE" in need else inv).append(f"rcb_monitor service: missing `{need.strip()}`")
        # the whole service is the generator's (its code from the pinned image, nothing else mounted, no other command)
        gen = [inject.monitor_block(gpu, observe) for gpu in (False, True) for observe in (False, True)]
        if not any(blk + "\n" == "".join(g) for g in gen):
            inv.append("rcb_monitor service: not the block images/monitor/rcb_monitor/inject.py writes (another image, mount, "
                       "command or entrypoint)")
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
                inv.append(f"service {name}: mounts the beacon writable")
    except ValueError as e:
        inv.append(f"environment/docker-compose.yaml: {e}")
    s = (task / "task.toml").read_text()
    if inject.ARTIFACT not in s:
        err.append("task.toml: the monitor's record is not an artifact of service rcb_monitor")
    hooks = re.findall(r'(?m)^\[\[verifier\.collect\]\]\nservice = "([^"]+)"', s)
    side = [h for h in hooks if h != "main"]
    if not side or side[0] != "rcb_monitor":
        inv.append("task.toml: the first sidecar [[verifier.collect]] hook must be rcb_monitor's seal")
    sh = (task / "tests" / "test.sh").read_text() if (task / "tests" / "test.sh").is_file() else ""
    if inject.TRAP not in sh:
        err.append("tests/test.sh: no verifier-step trap")
    if inject.GUARD not in sh:
        inv.append("tests/test.sh: no `rcb_limits.py sanitize /app/output` line (the agent's files are untrusted input)")
    elif any(re.search(r"grade|/app/output", ln) for ln in sh[:sh.index(inject.GUARD)].splitlines()
             if ln.strip() and not ln.lstrip().startswith("#") and inject.TRAP not in ln):
        inv.append("tests/test.sh: something reads the agent's files before the sanitize line")
    elif inject.TRAP in sh and not sh.index(inject.TRAP) < sh.index(inject.GUARD):
        err.append("tests/test.sh: the sanitize line comes before the verifier-step trap")
    if inject.DOCKER_COPY not in ((task / "tests" / "Dockerfile").read_text()
                                  if (task / "tests" / "Dockerfile").is_file() else ""):
        inv.append(f"tests/Dockerfile: does not COPY rcb_limits.py from {inject.IMAGE} and rcb_limits.json (inject.DOCKER_COPY)")
    return inv, err


def main(argv):
    tier = "all"
    if argv[:1] == ["--tier"]:
        tier, argv = argv[1], argv[2:]
        if tier not in ("invariants", "advisory", "all"):
            raise SystemExit("--tier invariants|advisory|all")
    dirs = [Path(a) for a in argv if (Path(a) / "task.toml").is_file()] or tc.iter_tasks()
    bad = 0
    if tier != "advisory":   # the image every task pins carries this repository's monitor code (inject.CONTENTS)
        drift = {f: h for f, h in inject.contents().items() if inject.CONTENTS.get(f) != h}
        if drift or set(inject.CONTENTS) != set(inject.CODE):
            print(f"FAIL images/monitor/rcb_monitor: {', '.join(sorted(drift)) or 'CONTENTS'} differ from inject.CONTENTS, i.e. from "
                  f"what {inject.IMAGE} carries: build and push a new images/monitor/ version, then update IMAGE and CONTENTS "
                  "(images/monitor/rcb_monitor/inject.py contents; verify-image) and re-run scripts/task_conventions.py on every task")
            bad = 1
    if tier != "invariants":   # what the pinned image really carries (anonymous registry read; a network failure warns)
        try:
            bad_img = inject.registry_contents_problems()
        except Exception as e:   # noqa: BLE001  (no network on this runner, registry down)
            bad_img = [f"could not read {inject.IMAGE} from the registry: {e}"]
        for e in bad_img:
            print(f"FAIL {inject.IMAGE}: {e}")
            bad = 1
        for test in ("selftest.py", "test_monitor.py"):      # the violation rule and the verifier step; the monitor's own logic
            r = subprocess.run([sys.executable, str(SRC / test)], capture_output=True, text=True)
            if r.returncode != 0:
                print(f"FAIL images/monitor/rcb_monitor/{test}:\n" + r.stdout + r.stderr)
                bad = 1
    for d in dirs:
        inv, adv = check(d)
        for e in (inv if tier != "advisory" else []) + (adv if tier != "invariants" else []):
            print(f"FAIL {d.name}: {e}")
            bad = 1
    if not bad:
        print(f"check-monitor ({tier}): {len(dirs)} tasks ok")
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
