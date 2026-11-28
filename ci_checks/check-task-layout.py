#!/usr/bin/env python3
"""ADVISORY (docs/protocol/tasks.md, resources.md; docs/TAXONOMY.md). The task layout, in one pass over the given task dirs:

  files     the Harbor task contract: the canonical files exist and the scripts are executable; solution/solve.sh is
            required unless the task declares `oracle = "none"` (§1, §4); no results/ (agent results are published on
            the results site, §1);
  README    the per-task format (§1, §6; task_conventions.readme_format_errors): the instruction's title, the key table
            rows and the sections in order; a standard or realtime task without its privileged twin says why
            (`no_twin` in its benchmark's readme.toml, §3);
  task.toml the name matches the folder, the required metadata, the deliverable dir, the task's declared scene dynamics
            (no central table); no copies of what another source says (mode, reset_budget, slowdown, tier). The agent's
            timeout: check-cutoffs.py.

    python3 ci_checks/check-task-layout.py <task dir>...     (check-task.sh, advisory tier)
Standard library only. Exit 1 when any task has a finding."""
from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ("task.toml", "instruction.md", "README.md", "environment/Dockerfile", "tests/test.sh")
_TC = None


def tc():
    global _TC
    if _TC is None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import task_conventions
        _TC = task_conventions
    return _TC


def modes() -> tuple[str, ...]:
    """The mode names, longest first: RCB_MODES_TABLE (run_all.sh) or scripts/task_conventions.py MODE_REGISTRY."""
    table = os.environ.get("RCB_MODES_TABLE", "") or tc().modes_table()
    return tuple(ln.split()[0] for ln in table.splitlines() if ln.strip())


def structure(t: str) -> list[str]:
    p = Path(t)
    out = [f"missing {f}" for f in CANONICAL if not (p / f).is_file()]
    if not os.access(p / "tests/test.sh", os.X_OK):
        out.append("tests/test.sh not executable")
    try:
        oracle = tomllib.loads((p / "task.toml").read_text()).get("metadata", {}).get("oracle", "")
    except (OSError, ValueError):
        oracle = ""
    if oracle != "none":
        sol = p / "solution/solve.sh"
        if not sol.is_file():
            out.append('missing solution/solve.sh (or declare oracle = "none")')
        elif not os.access(sol, os.X_OK):
            out.append("solution/solve.sh not executable")
    if os.path.lexists(p / "results"):
        out.append("results/ does not belong in the repository (docs/protocol/tasks.md)")
    return out


def readme(t: str) -> list[str]:
    p = Path(t)
    s = (p / "README.md").read_text() if (p / "README.md").is_file() else ""
    bad = tc().readme_format_errors(p, s)
    try:   # docs/protocol/tasks.md#modes: a standard or realtime task without its privileged twin says why (readme.toml `no_twin`)
        tw = tc().twin_of(p)
    except ValueError:
        tw = None
    if tw is not None and not (tw / "task.toml").is_file() and not tc().no_twin_reason(p):
        bad.append(f"its twin {tw.name} is missing and nothing says why (`no_twin` in tasks/{tc().bench_dir(p)}/"
                   f"{tc().README_DATA}, docs/protocol/tasks.md#modes)")
    return [f"README.md: {b}" for b in bad]


def fields(t: str, mode_names: tuple[str, ...]) -> list[str]:
    p = Path(t)
    try:
        d = tomllib.loads((p / "task.toml").read_text())
    except (OSError, ValueError) as e:
        return [f"task.toml: {e}"]
    out = []
    if d.get("task", {}).get("name") != f"embodied-first-exam/{p.name}":
        out.append("[task].name must be embodied-first-exam/<folder>")
    m = d.get("metadata", {})
    out += [f"[metadata].{k} missing" for k in ("task_type", "simulator", "robot", "family", "expert_time_estimate_hours")
            if k not in m]
    if m.get("task_type") not in ("trajectory", "policy"):
        out.append("task_type must be trajectory|policy")
    # docs/protocol/tasks.md, tasks.md#modes: the directory ends in its mode (-privileged, -standard, -realtime, or a mode added to the
    # registry), the one place that says it; no `tier`. The suffix is the whole mode name, longest first.
    suffix = next((x for x in mode_names if p.name.endswith("-" + x)), p.name.rsplit("-", 1)[-1])
    if suffix not in mode_names:
        out.append("directory name must end in " + ", ".join("-" + x for x in mode_names))
    # no copies of what another source says (removed by hand: normalize does not touch them): the mode is the
    # directory's suffix, the reset budget and the slowdown S the sim service's RCB_RESET_BUDGET and RCB_SLOWDOWN
    # defaults (ci_checks/check-realtime.py), the egress [agent] network_mode (ci_checks/check-verifier-isolation.sh)
    for k, src in (("mode", "the directory's suffix"), ("reset_budget", "the sim service's RCB_RESET_BUDGET default"),
                   ("slowdown", "the sim service's RCB_SLOWDOWN default")):
        if k in m:
            out.append(f"[metadata].{k} copies {src}: delete the `{k} = ...` line from task.toml's [metadata] by hand")
    if "tier" in m:
        out.append("[metadata].tier is not a task field (the mode is the directory name's suffix)")
    if m.get("dynamics") not in ("static", "dynamic"):
        out.append(f'[metadata].dynamics must be declared, "static" or "dynamic" (docs/protocol/tasks.md), got {m.get("dynamics")!r}')
    if "/app/output/" not in d.get("artifacts", []):
        out.append('top-level artifacts must include "/app/output/"')
    return out


def main(argv: list[str]) -> int:
    mode_names = modes()
    rc = 0
    for a in argv:
        t = a.rstrip("/")
        if not (Path(t) / "task.toml").is_file():
            continue
        bad = structure(t) + readme(t) + fields(t, mode_names)
        for b in bad:
            print(f"FAIL {t}: {b}")
        rc |= 1 if bad else 0
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
