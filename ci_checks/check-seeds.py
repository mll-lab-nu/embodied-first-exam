#!/usr/bin/env python3
"""ADVISORY. Seeds (docs/protocol/README.md §2): every task names the frozen instances it may run from. For every task:
  - task.toml has `[metadata.seeds]` with `default` (an integer), `allowed` (a list of distinct integers, a range
    `{ from = A, to = B }` with both ends included, or "any"; `default` among them; a range or "any" only with
    `build = "runtime"`: the task builds a seed's instance itself, since they cannot all be committed) and `oracle` (the seeds the reference solution is for: a subset of `allowed`; empty when `oracle = "none"`, not
    empty when it is "full" or "partial"); `instance_seed`, where the task has one, equals `default`;
  - (a standard or standard-realtime task has its privileged twin's seeds: ci_checks/check-twins.py, an invariant);
  - `build = "frozen"` (the default): every listed seed other than the default has its frozen instance under the verifier's files of the task that
    holds the pair's instance (the privileged twin; a task without one: itself): `tests/seeds/<seed>/instance.json` or
    `instance.npz`, of the same kind as the default instance; and `tests/seeds/` holds nothing for a seed that is not
    allowed;
  - nothing under `environment/` is in a directory named `seeds` (another seed's instance where the agent, or the
    agent's image, could reach it: the runner puts the drawn seed's instance in the usual place, scripts/task_seed.py).

    python3 ci_checks/check-seeds.py [task dirs]      # default: every task
Fix: the generator writes `[metadata.seeds]` (scripts/task_conventions.py `normalize` completes it) and the seeds'
instances. Standard library only.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402  (mode_of, base_of)


def seeds_table(task: Path) -> tuple[dict, dict]:
    md = tomllib.loads((task / "task.toml").read_text()).get("metadata", {})
    return md, md.get("seeds")


def holder(task: Path) -> Path:
    """The task whose tests/ holds the pair's instances: the privileged twin of a standard task, else the task."""
    twin = tc.twin_of(task)          # the mode registry's twin mode (PROTOCOL §2.16)
    return twin if twin is not None and twin.is_dir() else task


def instance_kinds(d: Path) -> set[str]:
    return {f for f in ("instance.json", "instance.npz") if (d / f).is_file()}


def check(task: Path) -> list[str]:
    errs = []
    md, sd = seeds_table(task)
    if not isinstance(sd, dict):
        return ["task.toml has no [metadata.seeds] (run scripts/task_conventions.py on it)"]
    default, allowed, oracle, build = sd.get("default"), sd.get("allowed"), sd.get("oracle"), sd.get("build", "frozen")
    isint = lambda x: isinstance(x, int) and not isinstance(x, bool)  # noqa: E731
    ints = lambda xs: isinstance(xs, list) and all(isint(x) for x in xs)  # noqa: E731
    if not isint(default):
        return ["seeds.default is not an integer"]
    if build not in ("frozen", "runtime"):
        errs.append(f'seeds.build is "{build}", not "frozen" or "runtime"')
    if isinstance(allowed, list):
        if not ints(allowed) or len(set(allowed)) != len(allowed):
            errs.append("seeds.allowed is not a list of distinct integers")
    elif isinstance(allowed, dict):
        if set(allowed) != {"from", "to"} or not (isint(allowed["from"]) and isint(allowed["to"])) \
                or allowed["from"] > allowed["to"]:
            errs.append("seeds.allowed as a range is { from = A, to = B } with integers A <= B")
        elif build != "runtime":
            errs.append('seeds.allowed is a range: the task must build the instance of each seed itself (build = "runtime")')
    elif allowed == "any":
        if build != "runtime":
            errs.append('seeds.allowed is "any": the task must build the instance of each seed itself (build = "runtime")')
    else:
        errs.append('seeds.allowed is a list, { from = A, to = B } or "any"')
    if errs:
        return errs
    ok = lambda x: tc.seed_allowed({"allowed": allowed}, x)  # noqa: E731
    if not ok(default):
        errs.append(f"seeds.default {default} is not in seeds.allowed {allowed}")
    if not ints(oracle):
        errs.append("seeds.oracle is not a list of integers")
    elif not all(ok(x) for x in oracle):
        errs.append(f"seeds.oracle {oracle} names a seed that is not allowed ({allowed})")
    elif md.get("oracle") == "none" and oracle:
        errs.append(f'oracle = "none" but seeds.oracle is {oracle}')
    elif md.get("oracle") in ("full", "partial") and not oracle:
        errs.append(f'oracle = "{md.get("oracle")}" but seeds.oracle is empty: name the seed(s) its solution is for')
    if "instance_seed" in md and md["instance_seed"] != default:
        errs.append(f"instance_seed {md['instance_seed']} differs from seeds.default {default}")
    if errs:
        return errs
    h = holder(task)     # the twins' equal seeds: ci_checks/check-twins.py (an invariant, PROTOCOL Appendix H.7)
    kinds = instance_kinds(h / "tests")
    if build == "frozen":                      # a list: every listed seed is a committed instance
        for s in allowed:
            if s == default:
                continue
            d = h / "tests" / "seeds" / str(s)
            have = instance_kinds(d)
            if not have:
                errs.append(f"allowed seed {s} has no frozen instance ({d.relative_to(h.parent)}/instance.json or .npz)")
            elif kinds and have != kinds:
                errs.append(f"seed {s}'s instance is {sorted(have)}, the default's {sorted(kinds)}")
    sdir = h / "tests" / "seeds"
    if sdir.is_dir():
        for d in sorted(sdir.iterdir()):
            if not d.name.isdigit() or not ok(int(d.name)) or int(d.name) == default:
                errs.append(f"{d.relative_to(h.parent)} is not the instance of an allowed non-default seed")
    env = task / "environment"
    if env.is_dir():
        for d in sorted(env.rglob("seeds")):
            if d.is_dir():
                errs.append(f"{d.relative_to(task)}: a `seeds` directory where the agent's image is built from "
                            "(another seed's instance belongs under tests/seeds/, PROTOCOL §2.13)")
    return errs


def main(argv: list[str]) -> int:
    dirs = [Path(a) for a in argv] or sorted(p for p in (ROOT / "tasks").iterdir() if (p / "task.toml").is_file())
    bad = 0
    for t in dirs:
        if not (t / "task.toml").is_file():
            continue
        for e in check(t):
            print(f"FAIL {t}: {e}")
            bad += 1
    if not bad:
        print(f"check-seeds: {len(dirs)} task(s) name their seeds (PROTOCOL §2.13)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
