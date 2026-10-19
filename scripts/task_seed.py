#!/usr/bin/env python3
"""Run a task from one of its allowed seeds (docs/protocol/README.md §2.13). The runner chooses the seed, never the agent:

    python3 scripts/task_seed.py list tasks/<benchmark>/<task>                      # default, allowed, oracle
    python3 scripts/task_seed.py pick tasks/<benchmark>/<task> [--rng N]            # a seed drawn uniformly from `allowed`
    python3 scripts/task_seed.py materialize tasks/<benchmark>/<task> --seed S --out DIR   # -> DIR/<task>, run that with Harbor

`materialize` copies the task directory and, for a seed other than the default, puts that seed's frozen instance
(`tests/seeds/<S>/instance.{json,npz}` of the task that holds the pair's instances: the privileged twin of a standard
task, else the task itself) in every place the task runs and grades from: privileged `environment/` (or a scorer
sidecar's `environment/scorer/`) and `tests/`; standard and standard-realtime `environment/sim/` and, without a twin,
their own `tests/`; each also in an `instance/` folder one level down (ManiGuard). The copy's `[metadata.seeds]`
`default` (and `instance_seed`, where present) say the seed it runs from, so a result records it; its `tests/seeds/`
is removed, and every file gets its content-derived mtime (scripts/stamp_mtimes.py, issue #258). A seed without a
committed instance, of a task with `build = "runtime"`, is written instead as a file `seed` (the integer) in each of
those places, from which the task builds the seed's instance itself. A seed that is
not allowed (a list, a range `{ from, to }` or "any") is refused. `--seed draw` draws one uniformly (with `--rng`;
"any" draws from 0 to 2**31 - 1). Standard library only.
"""
from __future__ import annotations

import argparse
import random
import re
import shutil
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stamp_mtimes  # noqa: E402
import task_conventions as tc  # noqa: E402


def seeds(task: Path) -> dict:
    return tc.seeds_of(tomllib.loads((task / "task.toml").read_text()).get("metadata", {}))


def holder(task: Path) -> Path:
    twin = tc.twin_of(task)          # the mode registry's twin mode (PROTOCOL §2.16)
    return twin if twin is not None and twin.is_dir() else task


def places(task: Path) -> list[str]:
    """Where a task's instance copies are (the mapping of ci_checks/check-instance-copies.sh): the copy it runs from and the
    verifier's tests/ copy (a standard task without a privileged twin carries its own), each also one level down in an
    `instance/` folder (ManiGuard)."""
    if tc.mode_of(task) in tc.SIDECAR_MODES:
        run = "environment/sim"
    else:
        run = "environment/scorer" if (task / "environment" / "scorer").is_dir() else "environment"
    return [d for p in (run, "tests") for d in (p, f"{p}/instance")]


ANY = 2 ** 31                                   # "any": a seed is drawn from 0 .. ANY - 1


def pick(task: Path, rng: int | None) -> int:
    a, r = seeds(task)["allowed"], random.Random(rng)
    if a == "any":
        return r.randrange(ANY)
    if isinstance(a, dict):
        return r.randint(a["from"], a["to"])
    return r.choice(a)


def materialize(task: Path, seed: int, out: Path) -> Path:
    sd = seeds(task)
    if not tc.seed_allowed(sd, seed):
        raise SystemExit(f"{task.name}: seed {seed} is not allowed ({sd['allowed']})")
    dst = out / task.name
    if dst.exists():
        raise SystemExit(f"{dst} exists: materialize into a new directory")
    shutil.copytree(task, dst, symlinks=True)
    src = holder(task) / "tests" / "seeds" / str(seed)
    files = [f for f in ("instance.json", "instance.npz") if (src / f).is_file()]
    if seed != sd["default"] and files:            # a committed instance of that seed
        copied = 0
        for place in places(task):
            for f in ("instance.json", "instance.npz"):
                if (dst / place / f).is_file():
                    if f not in files:
                        raise SystemExit(f"{task.name}: seed {seed} has no {f} (the default instance has one)")
                    shutil.copyfile(src / f, dst / place / f); copied += 1
        if not copied:                             # never a copy that says seed S and runs the default instance
            raise SystemExit(f"{task.name}: no instance copy found to replace with seed {seed}'s ({', '.join(places(task))})")
    elif seed != sd["default"]:
        if sd["build"] != "runtime":
            raise SystemExit(f"{task.name}: seed {seed} has no frozen instance under {src}")
        for place in places(task):                 # the task builds that seed's instance itself from this file
            if (dst / place).is_dir():
                (dst / place / "seed").write_text(f"{seed}\n")
    shutil.rmtree(dst / "tests" / "seeds", ignore_errors=True)
    p = dst / "task.toml"
    s = p.read_text()
    s = re.sub(r"(?m)^(\[metadata\.seeds\](?:\n#.*)*\ndefault = )-?\d+", rf"\g<1>{seed}", s, count=1)
    s = re.sub(r"(?m)^instance_seed = -?\d+", f"instance_seed = {seed}", s, count=1)
    p.write_text(s)
    if stamp_mtimes.stamp_tree(str(dst), full=True)["err"]:     # Harbor builds from this copy: content-derived mtimes (issue #258)
        raise SystemExit(f"{dst}: could not stamp its files (scripts/stamp_mtimes.py)")
    return dst


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a_list = sub.add_parser("list")
    a_list.add_argument("task", type=Path)
    a_pick = sub.add_parser("pick")
    a_pick.add_argument("task", type=Path)
    a_pick.add_argument("--rng", type=int)
    a_mat = sub.add_parser("materialize")
    a_mat.add_argument("task", type=Path)
    a_mat.add_argument("--seed", required=True, help="an allowed seed, or `draw`")
    a_mat.add_argument("--rng", type=int)
    a_mat.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    task = a.task.resolve()
    if a.cmd == "list":
        print(seeds(task))
    elif a.cmd == "pick":
        print(pick(task, a.rng))
    else:
        seed = pick(task, a.rng) if a.seed == "draw" else int(a.seed)
        print(materialize(task, seed, a.out.resolve()), seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
