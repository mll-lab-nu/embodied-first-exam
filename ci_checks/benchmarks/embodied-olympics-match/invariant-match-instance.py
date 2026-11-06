#!/usr/bin/env python3
"""INVARIANT hook (docs/protocol/README.md Appendix H.7: twins share one frozen instance), this benchmark's own:
ci_checks/run_invariants.sh runs every ci_checks/benchmarks/*/invariant-* hook with the task directories in scope.

A privileged match's frozen settings are its tests/match_instance.json (sport, level, seed, slowdown); its standard and
realtime twins take the same settings as the sim service's environment (RO_SPORT, RO_LEVEL, RO_SEED, RO_SLOWDOWN in
environment/docker-compose.yaml), not as a copy of the file (ci_checks/check-instance-copies.sh compares byte copies).
Every setting the file names must equal the twin's. Standard library only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PREFIX = "embodied-olympics-match-"
ENV = {"sport": "RO_SPORT", "level": "RO_LEVEL", "seed": "RO_SEED", "slowdown": "RO_SLOWDOWN"}
MODES = ("privileged", "standard", "realtime")


def env_of(compose: Path) -> dict[str, str]:
    """The `KEY: "value"` lines of a compose file (the exporter writes one service environment per sim sidecar)."""
    return dict(re.findall(r'^\s+(RO_[A-Z_]+):\s*"?([^"\n]*)"?\s*$', compose.read_text(), re.M))


def main(argv: list[str]) -> int:
    bases: dict[Path, str] = {}
    for a in argv:
        t = Path(a.rstrip("/"))
        if not t.name.startswith(PREFIX) or not (t / "task.toml").is_file():
            continue
        for m in MODES:
            if t.name.endswith("-" + m):
                bases[t.parent / t.name[: -len(m) - 1]] = m
    errs, n = [], 0
    for base in sorted(bases):
        inst = Path(f"{base}-privileged/tests/match_instance.json")
        if not inst.is_file():
            continue
        try:
            want = json.loads(inst.read_text())
        except (OSError, json.JSONDecodeError) as e:
            errs.append(f"{inst}: unreadable ({e})"); continue
        for m in MODES[1:]:
            compose = Path(f"{base}-{m}/environment/docker-compose.yaml")
            if not compose.parent.parent.is_dir():
                continue
            n += 1
            got = env_of(compose) if compose.is_file() else {}
            for k, var in ENV.items():
                if k in want and got.get(var) != str(want[k]):
                    errs.append(f"{base.name}-{m}: {var}={got.get(var)!r} in environment/docker-compose.yaml, but its "
                                f"privileged twin's tests/match_instance.json has {k} = {want[k]!r}")
    for e in errs:
        print("FAIL", e)
    if not errs:
        print(f"ok embodied-olympics-match match instance: {n} twin(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
