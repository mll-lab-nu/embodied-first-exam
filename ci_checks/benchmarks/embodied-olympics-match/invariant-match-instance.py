#!/usr/bin/env python3
"""INVARIANT hook (docs/protocol/README.md Appendix H.7: twins share one frozen instance), this benchmark's own:
ci_checks/run_invariants.sh runs every ci_checks/benchmarks/*/invariant-* hook with the task directories in scope.

A privileged match's frozen settings are its tests/match_instance.json (sport, level, seed, slowdown); its standard and
realtime twins take the same settings as the sim service's environment (RO_SPORT, RO_LEVEL, RO_SEED, RO_SLOWDOWN in
environment/docker-compose.yaml), not as a copy of the file (ci_checks/check-instance-copies.sh compares byte copies).
Every setting the file names must equal the twin's, both read the way the service reads them (core/serve.py
config_from_env: an empty or missing variable is no value; a level or slowdown of 0 is none either, the duel formats
have no scripted opponent level and the turn-based matches no slowdown). `--selftest` runs the hook's own cases.
Standard library only.
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


NONE_IF_ZERO = ("level", "slowdown")


def norm(key: str, v):
    """A setting as the service sees it: None for no value ("", missing, null, and 0 for level / slowdown); numbers
    compared as numbers ("20" = 20 = 20.0); anything else as its string."""
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    if key in NONE_IF_ZERO and x == 0:
        return None
    return int(x) if x.is_integer() else x


def mismatches(want: dict, env: dict) -> list[tuple[str, str, object, object]]:
    """(key, variable, the twin's value, the file's value) for every setting the file names that the twin's
    environment does not match."""
    return [(k, var, env.get(var), want[k]) for k, var in ENV.items()
            if k in want and norm(k, env.get(var)) != norm(k, want[k])]


def selftest() -> int:
    cases = [  # (file, compose environment, mismatching keys)
        ({"sport": "badminton", "level": 0, "seed": 1001, "slowdown": 20},
         {"RO_SPORT": "badminton", "RO_LEVEL": "", "RO_SEED": "1001", "RO_SLOWDOWN": "20"}, []),   # duel: no level
        ({"sport": "fencing", "level": 2, "seed": 35, "slowdown": None},
         {"RO_SPORT": "fencing", "RO_LEVEL": "2", "RO_SEED": "35"}, []),                          # turn-based: no slowdown
        ({"sport": "soccer", "level": 2, "seed": 7, "slowdown": 5},
         {"RO_SPORT": "soccer", "RO_LEVEL": "2", "RO_SEED": "7", "RO_SLOWDOWN": "5.0"}, []),
        ({"level": 0, "slowdown": 0}, {"RO_LEVEL": "0", "RO_SLOWDOWN": ""}, []),
        ({"sport": "soccer", "level": 2, "seed": 7, "slowdown": 5},
         {"RO_SPORT": "soccer", "RO_LEVEL": "3", "RO_SEED": "8", "RO_SLOWDOWN": "10"}, ["level", "seed", "slowdown"]),
        ({"level": 1, "slowdown": None}, {"RO_LEVEL": "", "RO_SLOWDOWN": "10"}, ["level", "slowdown"]),
        ({"level": 0, "seed": 0}, {"RO_LEVEL": "2"}, ["level", "seed"]),     # seed 0 is a seed, not "none"
        ({"sport": "tabletennis"}, {"RO_SPORT": "badminton"}, ["sport"]),
    ]
    bad = 0
    for want, env, keys in cases:
        got = [m[0] for m in mismatches(want, env)]
        if got != keys:
            print(f"FAIL selftest: {want} vs {env}: mismatches {got}, want {keys}")
            bad = 1
    if not bad:
        print(f"ok embodied-olympics-match match instance selftest: {len(cases)} cases")
    return bad


def main(argv: list[str]) -> int:
    if argv[:1] == ["--selftest"]:
        return selftest()
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
            for k, var, have, wanted in mismatches(want, got):
                errs.append(f"{base.name}-{m}: {var}={have!r} in environment/docker-compose.yaml, but its "
                            f"privileged twin's tests/match_instance.json has {k} = {wanted!r}")
    for e in errs:
        print("FAIL", e)
    if not errs:
        print(f"ok embodied-olympics-match match instance: {n} twin(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
