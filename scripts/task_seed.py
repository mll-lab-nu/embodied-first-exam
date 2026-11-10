#!/usr/bin/env python3
"""Run a task from one of its allowed seeds (docs/protocol/README.md §2). The runner chooses the seed, never the agent:

    python3 scripts/task_seed.py list tasks/<benchmark>/<task>                      # default, allowed, oracle
    python3 scripts/task_seed.py pick tasks/<benchmark>/<task> [--rng N]            # a seed drawn uniformly from `allowed`
    python3 scripts/task_seed.py materialize tasks/<benchmark>/<task> --seed S --out DIR   # -> DIR/<task>, run that with Harbor

`materialize` copies the task directory and, for a seed other than the default, puts that seed's files in every place
the task runs and grades from. The seed's files are `tests/seeds/<S>/` of the task that holds the pair's instances (the
privileged twin of a standard task, else the task itself):
  - a file directly in it (`instance.json`, `instance.npz`, or any other per-instance file, such as a goal image) replaces
    the file of that name in every instance place: privileged `environment/` (or a scorer sidecar's
    `environment/scorer/`) and `tests/`; standard and realtime `environment/sim/` and, without a twin, their own `tests/`;
    each also in an `instance/` folder one level down (ManiGuard);
  - a file further down (`tests/seeds/<S>/solution/oracle.npz`) replaces the file at that path in the task, where the
    task has one (the seed's reference solution, a per-seed file outside the instance places);
  - `seed.toml`, if there, lists the text that differs on this seed (`[[replace]]` tables with `old` and `new`: the
    seed's instance hashes pinned in compose, the instruction's description of the scene): every occurrence in the
    task's other text files is replaced.
The copy's `instance_seed` says the seed it runs from, so a result records it, and its `[metadata.seeds]` keeps the
task's allowed and oracle seeds explicitly (their defaults follow instance_seed); its `tests/seeds/`
is removed, and every file gets its content-derived mtime (scripts/stamp_mtimes.py, issue #258). A seed without
committed files, of a task with `build = "runtime"`, is written instead as a file `seed` (the integer) in each of
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
    twin = tc.twin_of(task)          # the mode registry's twin mode (PROTOCOL §3)
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


SEED_TOML = "seed.toml"                         # tests/seeds/<S>/seed.toml: the seed's text replacements
NOT_OVERLAID = ("task.toml", "DIGEST")           # the seeds come from [metadata]; the DIGEST is the committed task's


def seed_files(task: Path, seed: int) -> tuple[Path, list[str], list[str], list[tuple[str, str]]]:
    """The seed's committed files: (their directory, the names directly in it (every instance place), the paths further
    down (that path in the task), the text replacements of its seed.toml)."""
    src = holder(task) / "tests" / "seeds" / str(seed)
    top, deep, repl = [], [], []
    if src.is_dir():
        for f in sorted(p for p in src.rglob("*") if p.is_file() or p.is_symlink()):
            rel = f.relative_to(src).as_posix()
            if rel == SEED_TOML:
                t = tomllib.loads(f.read_text())
                repl = [(r["old"], r["new"]) for r in t.get("replace", [])]
            elif "/" in rel:
                deep.append(rel)
            else:
                top.append(rel)
    return src, top, deep, repl


def text_files(root: Path, skip: set[str]) -> list[Path]:
    out = []
    for f in sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink()):
        if f.relative_to(root).as_posix() in skip:
            continue
        try:
            f.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        out.append(f)
    return out


def materialize(task: Path, seed: int, out: Path) -> Path:
    sd = seeds(task)
    if not tc.seed_allowed(sd, seed):
        raise SystemExit(f"{task.name}: seed {seed} is not allowed ({sd['allowed']})")
    dst = out / task.name
    if dst.exists():
        raise SystemExit(f"{dst} exists: materialize into a new directory")
    shutil.copytree(task, dst, symlinks=True)
    shutil.rmtree(dst / "tests" / "seeds", ignore_errors=True)
    src, top, deep, repl = seed_files(task, seed)
    if seed != sd["default"] and (top or deep or repl):     # the seed's committed files
        done: set[str] = set()
        for place in places(task):
            for f in ("instance.json", "instance.npz"):
                if (dst / place / f).is_file() and f not in top:
                    raise SystemExit(f"{task.name}: seed {seed} has no {f} (the default instance has one)")
            for f in top:
                if (dst / place / f).is_file():
                    shutil.copyfile(src / f, dst / place / f); done.add(f"{place}/{f}")
        for rel in deep:
            if rel.split("/")[0] in NOT_OVERLAID or rel.startswith("tests/seeds/"):
                raise SystemExit(f"{task.name}: seed {seed}'s {rel} would replace {rel} (not a per-seed file)")
            if (dst / rel).is_file():
                shutil.copyfile(src / rel, dst / rel); done.add(rel)
        changed = 0
        for f in text_files(dst, done | set(NOT_OVERLAID)):
            s = t = f.read_text()
            for old, new in repl:
                t = t.replace(old, new)
            if t != s:
                f.write_text(t); changed += 1
        if not done and not changed:               # never a copy that says seed S and runs the default instance
            raise SystemExit(f"{task.name}: none of seed {seed}'s files or text found a place in this task "
                             f"({', '.join(places(task))})")
    elif seed != sd["default"]:
        if sd["build"] != "runtime":
            raise SystemExit(f"{task.name}: seed {seed} has no frozen instance under {src}")
        for place in places(task):                 # the task builds that seed's instance itself from this file
            if (dst / place).is_dir():
                (dst / place / "seed").write_text(f"{seed}\n")
    p = dst / "task.toml"
    s = p.read_text()
    s, n = re.subn(r"(?m)^instance_seed = -?\d+", f"instance_seed = {seed}", s, count=1)   # the one field that names it
    if n != 1:
        raise SystemExit(f"{task.name}: task.toml has no `instance_seed` (run scripts/task_conventions.py on the task)")
    if seed != sd["default"]:                      # the task's seeds stay the task's, whatever instance_seed now says
        s = re.sub(r"(?ms)^\[metadata\.seeds\]\n.*?(?=^\[|\Z)", "", s)
        s = s.rstrip("\n") + "\n\n[metadata.seeds]\n" + f"allowed = {tc.seeds_text(sd['allowed'])}\noracle = {tc.seeds_text(sd['oracle'])}\n" \
            + (f'build = "{sd["build"]}"\n' if sd["build"] != "frozen" else "")
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
