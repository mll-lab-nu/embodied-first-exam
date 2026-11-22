#!/usr/bin/env python3
"""The Standard-setting ablation variants of the core set's tasks (paper, appendix "Controlled runs"):

    nosignal          no success signal: no success flag, progress or score; the agent ends the episode with
                      POST /finish and the end state is graded (sim switch RCB_HIDE_SUCCESS)
    objpose           object-state query: GET /state/entities and POST /state/query, read only (RCB_STATE_QUERY)
    resetinf          unlimited resets with saved states: reset budget 1000, POST /save_state and /load_state where
                      the service can snapshot (RCB_STATE_OPS, RCB_RESET_BUDGET)
    objpose_resetinf  both of the above

Each variant is one task dir, `ablations/<ablation>/<benchmark folder>/<base>-<ablation>-standard/`, made from the
`<base>-standard` task dir of a core task (docs/core_set.toml) as the ablation's runs used it: the task dir at the
ablation's commit (ABLATIONS, the commits the runs were deployed from), with the ablation's sim switches, its
instruction section and the ablation's files images pinned in its Dockerfiles. The name keeps the mode suffix last
(`-standard`), so the tooling reads the variant as a Standard task; base tasks under tasks/ are not changed.

A task dir that the ablation's commit already holds in the ablation's form is copied as it is. Otherwise the commit's
own tool (scripts/ablation_tasks.py or scripts/ablation_eomatch.py at that commit) writes the switches and the section,
and the base files images are replaced by the ablation's (the pairs read from the task dirs the commit changed, against
the commits' merge base). Then `[task] name` and the monitor's limits files take the variant's name, and DIGEST is
recomputed. The variants are the task versions of these commits, with the files images the runs pinned; they do not
follow later changes to the base tasks under tasks/.

    python3 scripts/ablation_variants.py fetch                 fetch the ABLATIONS commits from FORK (git objects only)
    python3 scripts/ablation_variants.py generate [abl ...]    write ablations/<abl>/ for every core task
    python3 scripts/ablation_variants.py check [abl ...]       exit 1 unless every core task has its variant, in form
"""
from __future__ import annotations

import collections
import functools
import io
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402

FORK = "https://github.com/JamesKrW/embodied-first-exam.git"
ABLATIONS = {
    # name: (commit the runs were deployed from, the commit's tool and its kind)
    "nosignal": ("12080a1d513f521827acee7464314720afa56277", "nosignal"),
    "objpose": ("61c51da36ab3e443e7e8cff78699136ec4bd4fb9", "query"),
    "resetinf": ("40a84d27264ac8ad9fd5ea77709d8c160992b619", "reset"),
    "objpose_resetinf": ("6a8c36b6b54083b0a01bd57567bcb3a776435eb8", "both"),
}
OUT = ROOT / "ablations"
RESET_HEAD = "## This run: unlimited resets, save and load"
QUERY_HEAD = "## This run: privileged state queries"
NOSIGNAL_HEAD = "## This run: no success signal"
BUDGET = r'RCB_RESET_BUDGET: "(\$\{RCB_RESET_BUDGET:-1000\}|1000)"'
FORM = {   # the instruction headings and the compose switches (regular expressions) a variant has
    "nosignal": ([NOSIGNAL_HEAD], [r'RCB_HIDE_SUCCESS: "1"']),
    "objpose": ([QUERY_HEAD], [r'RCB_STATE_QUERY: "1"']),
    "resetinf": ([RESET_HEAD], [r'RCB_STATE_OPS: "1"', BUDGET]),
    "objpose_resetinf": ([RESET_HEAD, QUERY_HEAD], [r'RCB_STATE_QUERY: "1"', r'RCB_STATE_OPS: "1"', BUDGET]),
}
DOCKERFILES = ("environment/Dockerfile", "environment/sim/Dockerfile", "tests/Dockerfile",
               "environment/scorer/Dockerfile")
LIMITS = ("environment/rcb_monitor/limits.json", "tests/rcb_limits.json")
REF = re.compile(r"ghcr\.io/[\w./-]+:[\w.-]+@sha256:[0-9a-f]{64}")
EOMATCH = "embodied-olympics-match"


def git(*args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], input=data, capture_output=True, check=True).stdout


@functools.cache
def base_rev() -> str:
    """The commit all four ablation commits start from (their merge base): the task dirs before any ablation change."""
    revs = [r for r, _ in ABLATIONS.values()]
    return git("merge-base", "--octopus", *revs).decode().strip()


def core_bases() -> list[str]:
    return [t["task"] for t in tomllib.loads((ROOT / "docs" / "core_set.toml").read_text())["task"]]


def variant_name(base: str, abl: str) -> str:
    return f"{base}-{abl}-standard"


def variant_dir(base: str, abl: str) -> Path:
    src = tc.task_relpath(f"{base}-standard")          # tasks/<benchmark folder>/<base>-standard
    return OUT / abl / src.split("/")[1] / variant_name(base, abl)


def export(rev: str, paths: list[str], dest: Path) -> None:
    """`git archive` of the paths at rev, unpacked into dest (modes kept)."""
    raw = git("archive", "--format=tar", rev, "--", *paths)
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        tar.extractall(dest, filter="tar")


def in_form(d: Path, abl: str) -> bool:
    heads, switches = FORM[abl]
    ins = (d / "instruction.md").read_text()
    comp = (d / "environment" / "docker-compose.yaml").read_text()
    return all(h in ins for h in heads) and all(re.search(s, comp) for s in switches)


def dockerfile_refs(rev: str, d: str) -> dict[str, list[str]]:
    out = {}
    for f in DOCKERFILES:
        try:
            out[f] = REF.findall(git("show", f"{rev}:{d}/{f}").decode())
        except subprocess.CalledProcessError:
            pass
    return out


def changed_task_dirs(base: str, rev: str) -> list[str]:
    names = git("diff", "--no-renames", "--name-only", base, rev, "--", "tasks/").decode().split("\n")
    return sorted({"/".join(n.split("/")[:3]) for n in names if n.count("/") >= 3})


@functools.cache
def _changed(abl: str) -> tuple[str, ...]:
    return tuple(changed_task_dirs(base_rev(), ABLATIONS[abl][0]))


def pin_map(abl: str, bench_folders: set[str]) -> dict[str, str]:
    """base files image -> the ablation's, from the task dirs of these benchmarks that the ablation's commit changed:
    the refs at the same place of the same Dockerfile before (base_rev) and after."""
    rev, _ = ABLATIONS[abl]
    pairs: dict[str, set[str]] = collections.defaultdict(set)
    for d in _changed(abl):
        if d.split("/")[1] not in bench_folders or not d.endswith("-standard"):
            continue
        old, new = dockerfile_refs(base_rev(), d), dockerfile_refs(rev, d)
        for f in old.keys() & new.keys():
            if len(old[f]) == len(new[f]):
                for a, b in zip(old[f], new[f]):
                    if a != b:
                        pairs[a].add(b)
    bad = {a: b for a, b in pairs.items() if len(b) > 1}
    if bad:
        raise SystemExit(f"{abl}: a base image maps to more than one ablation image: {bad}")
    return {a: next(iter(b)) for a, b in pairs.items()}


def ablation_refs(abl: str) -> set[str]:
    """Every files image the ablation's commit pins in a task dir it holds in the ablation's form."""
    rev, _ = ABLATIONS[abl]
    refs: set[str] = set()
    for d in _changed(abl):
        if d.endswith("-standard"):
            try:
                ins = git("show", f"{rev}:{d}/instruction.md").decode()
            except subprocess.CalledProcessError:
                continue
            if all(h in ins for h in FORM[abl][0]):
                for v in dockerfile_refs(rev, d).values():
                    refs.update(v)
    return refs


def apply_tool(abl: str, d: Path, tool_root: Path) -> None:
    """The ablation commit's own tool on one task dir (switches, instruction section, the match layer)."""
    _, kind = ABLATIONS[abl]
    if d.parent.name == EOMATCH:
        cmd = [sys.executable, str(tool_root / "scripts" / "ablation_eomatch.py"), "apply",
               {"query": "query", "reset": "reset", "both": "both", "nosignal": "nosignal"}[kind], str(d)]
    elif kind == "nosignal":
        cmd = [sys.executable, str(tool_root / "scripts" / "ablation_tasks.py"), "apply", str(d)]
    else:
        cmd = [sys.executable, str(tool_root / "scripts" / "ablation_tasks.py"), "apply", kind, str(d)]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=tool_root)
    if r.returncode != 0:
        raise SystemExit(f"{abl} {d.name}: the ablation's tool failed:\n{r.stdout}{r.stderr}")


def finish(d: Path, name: str) -> None:
    """`[task] name` and the monitor's limits take the variant's name; DIGEST last (task_conventions.digest)."""
    toml = d / "task.toml"
    s = toml.read_text()
    s, n = re.subn(r'(?m)^name = "embodied-first-exam/[^"]+"$', f'name = "embodied-first-exam/{name}"', s, count=1)
    if n != 1:
        raise SystemExit(f"{toml}: no [task] name line")
    toml.write_text(s)
    for f in LIMITS:                                   # the monitor's limits name the task its evidence is from
        p = d / f
        if p.is_file():
            t, n = re.subn(r'"task": "[^"]+"', f'"task": "{name}"', p.read_text(), count=1)
            if n != 1:
                raise SystemExit(f"{p}: no task field")
            p.write_text(t)
    (d / tc.DIGEST_FILE).write_text(tc.digest(d) + "\n")


def generate(abls: list[str]) -> int:
    bases = core_bases()
    for abl in abls:
        rev, _ = ABLATIONS[abl]
        if (OUT / abl).exists():
            shutil.rmtree(OUT / abl)
        pmaps: dict[str, dict[str, str]] = {}
        counts = collections.Counter()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            tool_root = tmp / "tool"
            export(rev, ["scripts", "ci_checks", "images/monitor", "docs/core_set.toml"], tool_root)
            for base in bases:
                src = tc.task_relpath(f"{base}-standard")
                stage = tmp / "stage"
                export(rev, [src], stage)
                d = stage / src
                if in_form(d, abl):
                    counts["as run"] += 1
                else:
                    # the tool writes into a tree laid out as the commit's (tasks/<folder>/<dir>)
                    work = tool_root / src
                    work.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(d), str(work))
                    apply_tool(abl, work, tool_root)
                    shutil.move(str(work), str(d))
                    folder = src.split("/")[1]
                    if folder not in pmaps:
                        pmaps[folder] = pin_map(abl, {folder})
                    pmap = pmaps[folder]
                    for f in DOCKERFILES:
                        p = d / f
                        if p.is_file():
                            s = p.read_text()
                            t = REF.sub(lambda m: pmap.get(m.group(0), m.group(0)), s)
                            if t != s:
                                p.write_text(t)
                    if not in_form(d, abl):
                        raise SystemExit(f"{abl} {base}: not in the ablation's form after its tool")
                    counts["written by the tool"] += 1
                out = variant_dir(base, abl)
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(d), str(out))
                finish(out, out.name)
                shutil.rmtree(stage)
        print(f"{abl}: {sum(counts.values())} variants ({', '.join(f'{v} {k}' for k, v in sorted(counts.items()))})")
    return 0


def check(abls: list[str]) -> int:
    bases = core_bases()
    bad: list[str] = []
    for abl in abls:
        refs = ablation_refs(abl)
        want = {variant_dir(b, abl) for b in bases}
        have = {p.parent for p in (OUT / abl).glob("*/*/task.toml")}
        bad += [f"{abl}: missing {p.relative_to(ROOT)}" for p in sorted(want - have)]
        bad += [f"{abl}: not a core variant {p.relative_to(ROOT)}" for p in sorted(have - want)]
        for d in sorted(want & have):
            rel = d.relative_to(ROOT)
            if not in_form(d, abl):
                bad.append(f"{rel}: not in the ablation's form")
            name = tomllib.loads((d / "task.toml").read_text())["task"]["name"]
            if name != f"embodied-first-exam/{d.name}":
                bad.append(f"{rel}: [task] name {name}")
            for f in LIMITS:
                p = d / f
                if p.is_file() and f'"task": "{d.name}"' not in p.read_text():
                    bad.append(f"{rel}/{f}: task field is not {d.name}")
            if tc.mode_of(d) != "standard":
                bad.append(f"{rel}: not a standard task name")
            if (d / tc.DIGEST_FILE).read_text().strip() != tc.digest(d):
                bad.append(f"{rel}: DIGEST out of date")
            for f in DOCKERFILES:
                p = d / f
                if p.is_file():
                    stray = [r for r in REF.findall(p.read_text()) if r not in refs]
                    if stray:
                        bad.append(f"{rel}/{f}: images the ablation's runs did not use: {stray}")
        print(f"{abl}: {len(want & have)} of {len(want)} core variants")
    for b in bad:
        print(b)
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("fetch", "generate", "check"):
        print(__doc__)
        return 2
    abls = argv[1:] or list(ABLATIONS)
    unknown = [a for a in abls if a not in ABLATIONS]
    if unknown:
        print(f"unknown ablation(s): {unknown}; one of {list(ABLATIONS)}")
        return 2
    if argv[0] == "fetch":
        git("fetch", "--no-tags", FORK, *[r for r, _ in ABLATIONS.values()])
        return 0
    return generate(abls) if argv[0] == "generate" else check(abls)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
