#!/usr/bin/env python3
"""ADVISORY. Seeds (docs/protocol/README.md §2): every task names the frozen instances it may run from. For every task:
  - `[metadata] instance_seed` (an integer) is the default seed, the one field that names it; `[metadata.seeds]`, only
    where they are not the defaults, has `allowed` (default [instance_seed]: a list of distinct integers, a range
    `{ from = A, to = B }` with both ends included, or "any"; the default seed among them; a range or "any" only with
    `build = "runtime"`: the task builds a seed's instance itself, since they cannot all be committed) and `oracle` (the
    seeds the reference solution is for, default [instance_seed] with an oracle, else []: a subset of `allowed`; empty
    when `oracle = "none"`, not empty when it is "full" or "partial"), and no `default` (a second copy of instance_seed);
  - (a standard or realtime task has its privileged twin's seeds: ci_checks/check-twins.py, an invariant);
  - `build = "frozen"` (the default): every listed seed other than the default has its frozen instance under the verifier's files of the task that
    holds the pair's instance (the privileged twin; a task without one: itself): `tests/seeds/<seed>/instance.json` or
    `instance.npz`, of the same kind as the default instance (a task whose instance is other files: at least one file);
    and `tests/seeds/` holds nothing for a seed that is not allowed;
  - a seed's files land somewhere (scripts/task_seed.py materialize): a file directly in `tests/seeds/<seed>/` is named
    like a file in an instance place of one of the pair's tasks, a file further down sits at a path one of them has
    (not task.toml, DIGEST or tests/seeds/), and `seed.toml` has only `[[replace]]` tables of two different strings
    `old` and `new`, each `old` found in a text file of one of them;
  - nothing under `environment/` is in a directory named `seeds` (another seed's instance where the agent, or the
    agent's image, could reach it: the runner puts the drawn seed's instance in the usual place, scripts/task_seed.py).

    python3 ci_checks/check-seeds.py [task dirs]      # default: every task
Fix: the generator writes `instance_seed` and, where a task allows more, `[metadata.seeds]` (scripts/task_conventions.py
`normalize` keeps only the keys that are not the defaults) and the seeds' instances. Standard library only.
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
    return md, md.get("seeds", {})


def holder(task: Path) -> Path:
    """The task whose tests/ holds the pair's instances: the privileged twin of a standard task, else the task."""
    twin = tc.twin_of(task)          # the mode registry's twin mode (PROTOCOL §3)
    return twin if twin is not None and twin.is_dir() else task


def pair(task: Path) -> list[Path]:
    """The tasks that run from the holder's instances: the holder and every task whose twin it is."""
    h = holder(task)
    out = [h] if (h / "task.toml").is_file() else []
    for m in tc.MODES:
        t = h.with_name(f"{tc.base_of(h)}-{m}")
        if t != h and (t / "task.toml").is_file() and tc.twin_of(t) == h:
            out.append(t)
    return out or [task]


def seed_dir_errors(h: Path, d: Path, tasks: list[Path]) -> list[str]:
    """A seed's files (scripts/task_seed.py materialize): each lands in one of the pair's tasks."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import task_seed  # noqa: E402
    errs, where = [], d.relative_to(h.parent)
    _, top, deep, _ = task_seed.seed_files(h, int(d.name))
    for f in top:
        if not any((t / p / f).is_file() for t in tasks for p in task_seed.places(t)):
            errs.append(f"{where}/{f}: no task of the pair has a file {f} in an instance place ({', '.join(task_seed.places(h))})")
    for rel in deep:
        if rel.split("/")[0] in task_seed.NOT_OVERLAID or rel.startswith("tests/seeds/"):
            errs.append(f"{where}/{rel}: not a per-seed file (the seeds come from task.toml)")
        elif not any((t / rel).is_file() for t in tasks):
            errs.append(f"{where}/{rel}: no task of the pair has {rel} to replace")
    st = d / task_seed.SEED_TOML
    if st.is_file():
        try:
            t = tomllib.loads(st.read_text())
        except tomllib.TOMLDecodeError as e:
            return errs + [f"{where}/{task_seed.SEED_TOML}: {e}"]
        rs = t.get("replace", [])
        if set(t) - {"replace"} or not isinstance(rs, list) or not all(
                isinstance(r, dict) and set(r) == {"old", "new"} and all(isinstance(r[k], str) for k in r)
                and r["old"] and r["old"] != r["new"] for r in rs):
            errs.append(f"{where}/{task_seed.SEED_TOML}: only [[replace]] tables of two different strings `old` and `new`")
        else:
            texts = [f.read_text() for t in tasks for f in task_seed.text_files(t, {"DIGEST", "task.toml"})
                     if "tests/seeds/" not in f.relative_to(t).as_posix()]
            for r in rs:
                if not any(r["old"] in x for x in texts):
                    errs.append(f"{where}/{task_seed.SEED_TOML}: {r['old'][:60]!r} is in no text file of the pair")
    return errs


def instance_kinds(d: Path) -> set[str]:
    return {f for f in ("instance.json", "instance.npz") if (d / f).is_file()}


def check(task: Path) -> list[str]:
    errs = []
    md, sd = seeds_table(task)
    isint = lambda x: isinstance(x, int) and not isinstance(x, bool)  # noqa: E731
    ints = lambda xs: isinstance(xs, list) and all(isint(x) for x in xs)  # noqa: E731
    if not isinstance(sd, dict):
        return ["[metadata.seeds] is not a table"]
    if "instance_seed" not in md:
        return ["task.toml has no `instance_seed` in [metadata] (the default seed; run scripts/task_conventions.py on it)"]
    if not isint(md["instance_seed"]):
        return ["instance_seed is not an integer"]
    if "default" in sd:
        return ["[metadata.seeds] has `default`: the default seed is `instance_seed` alone (run scripts/task_conventions.py on it)"]
    default = md["instance_seed"]          # the defaults of the table's keys: scripts/task_conventions.py seeds_of
    allowed, build = sd.get("allowed", [default]), sd.get("build", "frozen")
    oracle = sd.get("oracle", [default] if md.get("oracle") in ("full", "partial") else [])
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
        errs.append(f"the default seed (instance_seed) {default} is not in seeds.allowed {allowed}")
    if not ints(oracle):
        errs.append("seeds.oracle is not a list of integers")
    elif not all(ok(x) for x in oracle):
        errs.append(f"seeds.oracle {oracle} names a seed that is not allowed ({allowed})")
    elif md.get("oracle") == "none" and oracle:
        errs.append(f'oracle = "none" but seeds.oracle is {oracle}')
    elif md.get("oracle") in ("full", "partial") and not oracle:
        errs.append(f'oracle = "{md.get("oracle")}" but seeds.oracle is empty: name the seed(s) its solution is for')
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
            if kinds and not have:
                errs.append(f"allowed seed {s} has no frozen instance ({d.relative_to(h.parent)}/instance.json or .npz)")
            elif kinds and have != kinds:
                errs.append(f"seed {s}'s instance is {sorted(have)}, the default's {sorted(kinds)}")
            elif not kinds and not (d.is_dir() and any(f.is_file() for f in d.rglob("*"))):
                errs.append(f"allowed seed {s} has no frozen files ({d.relative_to(h.parent)}/)")
    sdir = h / "tests" / "seeds"
    if sdir.is_dir():
        for d in sorted(sdir.iterdir()):
            if not d.name.isdigit() or not ok(int(d.name)) or int(d.name) == default:
                errs.append(f"{d.relative_to(h.parent)} is not the instance of an allowed non-default seed")
            elif task == h:
                errs += seed_dir_errors(h, d, pair(h))
    env = task / "environment"
    if env.is_dir():
        for d in sorted(env.rglob("seeds")):
            if d.is_dir():
                errs.append(f"{d.relative_to(task)}: a `seeds` directory where the agent's image is built from "
                            "(another seed's instance belongs under tests/seeds/, PROTOCOL §2)")
    return errs


def main(argv: list[str]) -> int:
    dirs = [Path(a) for a in argv] or tc.iter_tasks()
    bad = 0
    for t in dirs:
        if not (t / "task.toml").is_file():
            continue
        for e in check(t):
            print(f"FAIL {t}: {e}")
            bad += 1
    if not bad:
        print(f"check-seeds: {len(dirs)} task(s) name their seeds (PROTOCOL §2)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
