#!/usr/bin/env python3
"""The checks check something: mutation self-test of the rules that guard the trust boundary and the resource caps.

A rule that reads compose files or task.toml by pattern can go blind without anyone noticing: the trailing comment that
scripts/rcb_monitor/inject.py writes after `volumes:` once hid every volume of the agent's container from
check-verifier-isolation.sh, and all checks stayed green on a task whose agent container mounted the simulator's trusted
volume (review of 2026-10-10, M5). This script copies a few real tasks into a temporary directory, breaks each copy in one
way a rule exists for, and requires that the rule's check fails with the rule's message -- and that the unbroken copy
passes. A mutation that passes is a blind rule: fix the check, not this list.

    python3 ci_checks/check-ci-selftest.py        # repo-level; run_all.sh calls it once. Standard library only.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISOLATION = ["bash", str(ROOT / "ci_checks/check-verifier-isolation.sh")]
RESOURCES = [sys.executable, str(ROOT / "ci_checks/check-resources.py")]

STD = "behavior-boxing-books-up-for-storage-i00-standard"      # a sim sidecar with a trusted cache volume
PRIV = "behavior-boxing-books-up-for-storage-i00-privileged"   # a verifier compose file with a trusted volume
HEAVY = "labutopia-heat-liquid-i00-standard"                   # an allowlist; a sidecar with a large verifier minimum
RT = "roboolympics-airhockey-match-i00-standard-realtime"      # min_cpus = the sum of its two services' caps


def sub(pattern: str, repl: str, count: int = 1, flags: int = re.M):
    def f(s: str) -> str:
        out, n = re.subn(pattern, repl, s, count=count, flags=flags)
        if n == 0:
            raise AssertionError(f"mutation does not apply: /{pattern}/")
        return out
    return f


def in_service(service: str, lines: str, after: str = ""):
    """Insert `lines` into a compose service: right after its line matching `after` (default: the service line)."""
    def f(s: str) -> str:
        rows = s.splitlines(keepends=True)
        i = next(k for k, r in enumerate(rows) if re.match(rf"^  {service}:\s*(#.*)?$", r))
        j = next((k for k in range(i + 1, len(rows)) if re.match(r"^  \S|^\S", rows[k]) and not rows[k].startswith("  #")), len(rows))
        at = i if not after else next(k for k in range(i, j) if re.match(after, rows[k]))
        rows[at + 1:at + 1] = [x + "\n" for x in lines.split("\n")]
        return "".join(rows)
    return f


COMPOSE, TOML, TEST_COMPOSE = "environment/docker-compose.yaml", "task.toml", "tests/docker-compose.yaml"
VOL = r"^    volumes:.*$"
# (name, task, file, mutation, check, what the check must say)
MUTATIONS = [
    # ---- the agent's container and the trusted volumes (the M5 class: every way of writing the same mount)
    ("the agent container mounts the sim's trusted volume (short form, under the generated `volumes:   # rcb-monitor`)",
     STD, COMPOSE, in_service("main", "      - rcb_behavior_cache_trusted:/cache", VOL), ISOLATION, "mounts trusted volume"),
    ("... long form (type: volume / source:)",
     STD, COMPOSE, in_service("main", "      - type: volume\n        source: rcb_behavior_cache_trusted\n        target: /cache", VOL),
     ISOLATION, "mounts trusted volume"),
    ("... long form, source first",
     STD, COMPOSE, in_service("main", "      - source: rcb_behavior_cache_trusted\n        target: /cache\n        type: volume", VOL),
     ISOLATION, "mounts trusted volume"),
    ("... quoted",
     STD, COMPOSE, in_service("main", '      - "rcb_behavior_cache_trusted:/cache:ro"', VOL), ISOLATION, "mounts trusted volume"),
    ("... with the service line and the volumes line carrying other comments",
     STD, COMPOSE, lambda s: in_service("main", "      - rcb_behavior_cache_trusted:/cache   # cache", r"^    volumes:.*$")(
         sub(r"^  main:\s*$", "  main:   # the agent's container")(s)), ISOLATION, "mounts trusted volume"),
    ("... through volumes_from",
     STD, COMPOSE, in_service("main", "    volumes_from: [sim]"), ISOLATION, "`volumes_from` is not allowed"),
    ("an inline volumes list (which the reader would have to guess at) with the trusted volume",
     STD, COMPOSE, lambda s: sub(r"^      - rcb_limits:/run/rcb-limits:ro.*\n", "")(
         sub(r"^  main:\n((?:    .*\n)*?)    volumes:.*$", r"  main:\n\1    volumes: [rcb_limits:/run/rcb-limits:ro, rcb_behavior_cache_trusted:/cache]")(s)),
     ISOLATION, "mounts trusted volume"),
    ("a volume entry the reader does not understand is a failure, not skipped",
     STD, COMPOSE, in_service("main", "      - *shared_cache", VOL), ISOLATION, "not understood"),
    ("a sidecar mounts a volume that is not *_trusted",
     STD, COMPOSE, in_service("sim", "      - shared_scratch:/scratch", VOL), ISOLATION, "which is not a *_trusted volume"),
    ("the verifier mounts a volume that is not *_trusted",
     PRIV, TEST_COMPOSE, sub(r"rcb_behavior_cache_trusted:/cache", "rcb_behavior_cache:/cache"), ISOLATION,
     "the verifier mounts rcb_behavior_cache"),
    # ---- the agent's container reaches the task's trusted files or the host
    ("the agent container bind-mounts the sidecar's code",
     STD, COMPOSE, in_service("main", "      - ./sim:/sim:ro", VOL), ISOLATION, "bind-mounts ./sim"),
    ("... the verifier's tests", STD, COMPOSE, in_service("main", "      - ../tests:/t:ro", VOL), ISOLATION, "bind-mounts ../tests"),
    ("... the reference solution", STD, COMPOSE, in_service("main", "      - ../solution:/s:ro", VOL), ISOLATION, "bind-mounts ../solution"),
    ("... the monitor's code", STD, COMPOSE, in_service("main", "      - ./rcb_monitor:/m", VOL), ISOLATION, "bind-mounts ./rcb_monitor"),
    ("... the docker socket",
     STD, COMPOSE, in_service("main", "      - /var/run/docker.sock:/var/run/docker.sock", VOL), ISOLATION, "bind-mounts /var/run/docker.sock"),
    ("the agent container is privileged", STD, COMPOSE, in_service("main", "    privileged: true"), ISOLATION, "`privileged` is not allowed"),
    ("the agent container shares the host's PID namespace", STD, COMPOSE, in_service("main", "    pid: host"), ISOLATION, "`pid` is not allowed"),
    ("the agent container mounts the beacon volume writable at another path",
     STD, COMPOSE, in_service("main", "      - rcb_limits:/mnt/beacon", VOL), ISOLATION, "mounts the beacon volume rcb_limits writable"),
    # ---- the sidecar is reachable only on localhost
    ("the sidecar publishes a port", STD, COMPOSE, in_service("sim", '    ports: ["8000:8000"]'), ISOLATION, "`ports` is not allowed"),
    ("the sidecar is on the host's network", STD, COMPOSE, in_service("sim", "    network_mode: host"), ISOLATION, "`network_mode` is not allowed"),
    # ---- the verifier's evidence comes from the sidecar
    ("the evidence is collected from the agent's container",
     STD, TOML, sub(r'\{ source = "(/(?:data|out)/final\.json)", service = "sim" \}', r'"\1"'), ISOLATION,
     "is collected from the agent's container"),
    ("the sidecar's collect hook is gone",
     STD, TOML, sub(r'(?ms)^\[\[verifier\.collect\]\]\nservice = "sim"\n.*?(?=^\[|\Z)', ""), ISOLATION, "no [[verifier.collect]] hook on a sidecar"),
    # ---- the verifier's own sandbox, the allowlist
    ("the verifier shares the agent's container", STD, TOML, sub(r'^environment_mode = "separate"', 'environment_mode = "shared"'),
     ISOLATION, 'environment_mode must be "separate"'),
    ("the allowlist lacks a model API's host",
     HEAVY, TOML, sub(r', "\*\.openai\.azure\.com"', ""), ISOLATION, "allowed_hosts differs from scripts/set_agent_egress.py"),
    ("the allowlist opens another host",
     HEAVY, TOML, sub(r'allowed_hosts = \["chatgpt\.com"', 'allowed_hosts = ["github.com", "chatgpt.com"'), ISOLATION,
     "allowed_hosts differs from scripts/set_agent_egress.py"),
    # ---- caps and minimums (PROTOCOL §2.10)
    ("a sidecar's memory cap below the verifier phase's declared minimum (the kernel would kill it at a cap the task itself says is too low)",
     HEAVY, None, {TOML: sub(r"^(sim = \{ cpus = [0-9.]+, memory_gb = )[0-9.]+", r"\g<1>24.0"),
                   COMPOSE: sub(r"^    mem_limit: \d+m(   # rcb-monitor)$", r"    mem_limit: 24576m\1")},
     RESOURCES, "verifier_min_memory_gb 27.0 > the memory cap of the sidecar"),
    ("the CPU minimum above the CPU caps of all services together",
     RT, TOML, sub(r"^min_cpus = [0-9.]+", "min_cpus = 7.0"), RESOURCES, "min_cpus 7.0 > the CPU caps of all services together 6"),
    ("a declared cap that docker does not apply",
     STD, COMPOSE, sub(r"^    mem_limit: \d+m(   # rcb-monitor)$", r"    mem_limit: 1024m\1"), RESOURCES, "declare the cap that is applied"),
]


def run(cmd: list[str], task: Path) -> tuple[int, str]:
    r = subprocess.run(cmd + [str(task)], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def main() -> int:
    bad = 0
    with tempfile.TemporaryDirectory(prefix="rcb-ci-selftest-") as tmp:
        clean = {}
        for name in sorted({m[1] for m in MUTATIONS}):
            src = ROOT / "tasks" / name
            if not (src / "task.toml").is_file():
                print(f"FAIL check-ci-selftest: the task {name} this self-test mutates is gone (pick another one in MUTATIONS)")
                return 1
            clean[name] = Path(tmp) / "clean" / name
            shutil.copytree(src, clean[name])
            for cmd in (ISOLATION, RESOURCES):
                rc, out = run(cmd, clean[name])
                if rc != 0:
                    print(f"FAIL check-ci-selftest: the unmutated {name} does not pass {Path(cmd[-1]).name}:\n{out[-800:]}")
                    bad += 1
        for k, (what, name, rel, mutate, cmd, expect) in enumerate(MUTATIONS):
            t = Path(tmp) / f"m{k}" / name                      # the directory keeps the task's name (its mode is in it)
            shutil.copytree(clean[name], t)
            try:
                for r, f in (mutate.items() if isinstance(mutate, dict) else [(rel, mutate)]):
                    (t / r).write_text(f((t / r).read_text()))
            except (AssertionError, StopIteration, OSError) as e:
                print(f"FAIL check-ci-selftest [{what}]: the mutation no longer applies to {name} ({e}): update MUTATIONS")
                bad += 1
                continue
            rc, out = run(cmd, t)
            if rc == 0 or expect not in out:
                bad += 1
                print(f"FAIL check-ci-selftest [{what}]: {Path(cmd[-1]).name} "
                      + ("PASSED the broken task: the rule is blind" if rc == 0 else f"failed, but not with `{expect}`:\n{out[-600:]}"))
    if not bad:
        print(f"check-ci-selftest: {len(MUTATIONS)} mutations of real tasks, each caught by its rule")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
