#!/usr/bin/env python3
"""What a change can affect: the scope of the checks on a pull request (CI, `run_all.sh --changed`).

A pull request that touches only one benchmark's tasks, image sources, CI hooks or docs page cannot break
another benchmark's tasks, so its CI runs the per-task checks on that benchmark's tasks (plus the repo-level checks, which are cheap and always run on everything). Anything else --
the checks themselves, the workflows, the shared modules (scripts/task_conventions.py, retry_policy,
embodied_first_exam/standard, images/monitor, ...), the shared images, the protocol documents, a path this table does not know -- runs the
FULL suite. Pushes to main always run the full suite (.github/workflows/static-checks.yml), so nothing that slips past
a scoped run stays unnoticed for longer than one merge.

A benchmark B is affected by a changed path P when P is one of B's own paths (UNITS below: its task-name prefix,
images/<b>/, its pages tasks/<folder>/*.md, ci_checks/benchmarks/<b>/, extra files) or when B's and P's benchmark refer to each other's
paths (`scripts/<x>` / `images/<x>` in a .py / .sh file under the other's own directories: shared layers that one
benchmark copies from another, e.g. MyoSuite and HumanoidBench's realtime service).

    python3 ci_checks/ci_scope.py                       # vs the merge base with origin/main
    python3 ci_checks/ci_scope.py --diff-from HEAD^1    # CI on a pull request: GitHub's merge commit vs main
    python3 ci_checks/ci_scope.py --paths a b ...       # explain the scope of the given paths

Output: shell assignments (`eval "$(python3 ci_checks/ci_scope.py ...)"`): RCB_SCOPE=full|benchmarks|none,
RCB_SCOPE_REASON, RCB_SCOPE_BENCHES (labels, `;`-separated), RCB_SCOPE_PATHS (the affected benchmarks' own path
prefixes, for check-unit-tests.sh `--only`), RCB_SCOPE_TASKS (their task dirs). A new
benchmark without a row here makes every pull request that touches it run the full suite: add its row.
"""
from __future__ import annotations

import functools
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402  (BENCHMARKS: (task dir prefix, label); bench_of)

# label -> the benchmark's own path prefixes besides its task dirs (tasks/<folder>/<task>/, the folder BENCHMARK_DIRS
# names; its pages tasks/<folder>/*.md are its own through owners()). Default for a label not listed with a key here: none
# (full suite). `d` = the directory name under images/.
def _own(d: str, *extra: str) -> list[str]:
    return [f"images/{d}/", *extra]


UNITS: dict[str, list[str]] = {
    "RoboTwin 2.0": _own("robotwin"),
    "DexToolBench": ["images/mujoco/"],   # serves server_mj.py
    "MuJoCo Playground": _own("mujoco-playground", "images/mujoco/", "embodied_first_exam/benchmarks/dextoolbench/standard/", "images/dextoolbench-files/"),   # ALOHA / Panda: DexToolBench's grader
    "KinDER": _own("kinder"),
    "HumanoidBench": _own("humanoidbench"),
    "MetaWorld+": _own("metaworldplus", "images/metaworld/"),
    "RoboWits": _own("robowits"),
    "RoboPaint": ["images/robopaint/", "images/robopaint-files/"],
    "RoboLab": _own("robolab", "images/robolab-files/"),
    "TactileLab": _own("tactilelab", "images/tactilelab-files/", "images/tactilelab-assets-files/"),
    "BEHAVIOR-1K": _own("behavior", "images/behavior-files/"),
    "ManiGuard": _own("maniguard"),
    "MolmoSpaces": _own("molmospaces"),
    "MyoSuite": _own("myosuite"),
    "DexJoCo": _own("dexjoco"),
    "DexHand": _own("dexhand"),
    "VLABench": _own("vlabench"),
    "RoboCasa-GR1": _own("robocasa-gr1", "images/robocasa/standard/", "embodied_first_exam/benchmarks/robocasa/", "images/robocasa-files/"),   # RoboCasa's service, tooling, graders
    "RoboCasa": _own("robocasa"),
    "RoboCasa365": _own("robocasa365", "images/robocasa/standard/", "embodied_first_exam/benchmarks/robocasa/", "images/robocasa-files/"),   # RoboCasa's service and graders
    "LIBERO-MAX": _own("libero-max"),
    "RoboARC": _own("roboarc", "images/roboarc-files/", "images/ikea-mujoco/", "images/ikea-mujoco-files/"),   # the IKEA suite's images keep their name
    "Embodied Olympics - Fun": _own("embodied-olympics-fun", "images/embodied-olympics-fun-files/"),
    "Embodied Olympics - Match": ["images/embodied-olympics-match-files/"],   # its simulator images are built from Embodied Olympics' tree, not here
    "BiGym 2.0": _own("bigym2"),
    "YAMLab": _own("yamlab"),
    "LabUtopia": _own("labutopia"),
    "AutoBio": _own("autobio"),
    "RoboDojo": _own("robodojo"),
    "Panda Dynamic Scenes": _own("pandadyn"),
    "AM-Bench": _own("ambench"),
    "iSpatialGym": _own("ispatialgym"),
    "roboEngineer": _own("roboengineer",
                         "images/control-transfer/", "images/quadrotor-landing/",
                         "images/roboengineer-files/"),
    "ABC Sim": _own("abc-sim"),
}
# the benchmark's shared task code, embodied_first_exam/benchmarks/<folder>/ (embodied_first_exam/README.md), its CI
# hooks, ci_checks/benchmarks/<folder>/, and its files-only image, images/<folder>-files/ (task images and sidecars): the folder of its
# task dirs, tasks/<folder>/ (task_conventions.BENCHMARK_DIRS)
FILES_IMAGE = {"behavior-1k": "behavior-files", "embodied-safety-exam": "ese-files"}   # folders whose files image has another name
for _label, _folder in tc.BENCHMARK_DIRS.items():
    UNITS.setdefault(_label, []).extend([f"embodied_first_exam/benchmarks/{_folder}/", f"ci_checks/benchmarks/{_folder}/",
                                         f"images/{FILES_IMAGE.get(_folder, _folder + '-files')}/"])   # its files-only image
# changes that no check reads: they need only the repo-level checks (which always run). Everything not listed here and
# not a benchmark's own path runs the full suite.
NO_TASK_EFFECT = ("README.md", "CONTRIBUTING.md", "AGENTS.md", "CLAUDE.md", "LICENSE", "SECURITY.md", "CODE_OF_CONDUCT.md", "docs/protocol/running.md",
                  "docs/REVIEWING.md", ".gitignore",
                  "docs/core_set.toml")   # read by reports only; its own check (run_all.sh) and test (run_invariants.sh) always run
# tasks/dataset.toml: no longer committed (generated for a release; check-dataset-manifest.sh fails when it is tracked)
REPO_LEVEL_ONLY = ("tasks/dataset.toml",)
REF = re.compile(r"\b(scripts|images)/([A-Za-z0-9_.-]+)")


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True).stdout


def changed_paths(diff_from: str | None, base: str) -> list[str]:
    rng = [diff_from, "HEAD"] if diff_from else [f"{base}...HEAD"]
    out = git("diff", "--name-only", "--no-renames", *rng)
    # uncommitted / untracked work counts too when run by hand (CI's checkout is clean)
    out += git("diff", "--name-only", "--no-renames", "HEAD")
    out += git("ls-files", "--others", "--exclude-standard")
    return sorted({p for p in out.splitlines() if p})


def label_of_task(name: str) -> str | None:
    return tc.bench_of(Path(name)) or None


def task_name_of(path: str) -> str | None:
    """The task dir a repository path is in: tasks/<folder>/<task>/... -> <task>; None for a path in no task dir (a
    file directly in tasks/ or in a benchmark folder). A path of the flat layout before the benchmark folders
    (tasks/<task>/..., the old side of the move in a diff) names its task one level up."""
    parts = path.split("/")
    if parts[0] != "tasks" or len(parts) < 3:
        return None
    if parts[1] in tc.BENCHMARK_DIRS.values():
        return parts[2] if len(parts) >= 4 else None
    return parts[1]


def owners(path: str) -> set[str]:
    """Every benchmark that owns `path` (images/mujoco/ is DexToolBench's and MuJoCo Playground's)."""
    parts = path.split("/")
    if len(parts) == 3 and parts[0] == "tasks" and parts[1] in tc.BENCHMARK_DIRS.values():   # a benchmark's page
        return {lab for lab, f in tc.BENCHMARK_DIRS.items() if f == parts[1]}
    if path.startswith("tasks/") and path.count("/") >= 2:   # a task's file: the task's name says its benchmark
        name = task_name_of(path)
        lab = label_of_task(name) if name else None
        return {lab} if lab else set()
    return {label for label, own in UNITS.items() if any(path.startswith(p) for p in own)}


def top(path: str) -> str | None:
    """`scripts/<x>` / `images/<x>` of a path (a file directly under scripts/: its stem with the dir, e.g. scripts/efe)."""
    m = REF.match(path)
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2).removesuffix('.py').removesuffix('.sh')}"


@functools.cache
def refs_of(label: str) -> frozenset[str]:
    """`scripts/<x>` / `images/<x>` named in the .py / .sh files under a benchmark's own paths."""
    out: set[str] = set()
    for prefix in UNITS[label]:
        p = ROOT / prefix
        cands = [p] if p.is_file() else list(p.rglob("*")) if p.is_dir() else list(p.parent.glob(p.name + "*"))
        for f in cands:
            if f.is_dir():
                cands += [x for x in f.rglob("*") if x.is_file()]
            elif f.suffix in (".py", ".sh"):
                out |= {f"{a}/{b.removesuffix('.py').removesuffix('.sh')}" for a, b in REF.findall(f.read_text(errors="replace"))}
    return frozenset(out)


def scope(paths: list[str]) -> dict:
    if not paths:
        return {"scope": "none", "reason": "no changed paths", "benches": []}
    benches: set[str] = set()
    for p in paths:
        if p in NO_TASK_EFFECT or p in REPO_LEVEL_ONLY:
            continue
        own = owners(p)
        if not own or any(o not in UNITS for o in own):
            why = "not one benchmark's path" if not own else f"benchmark {sorted(own)} has no row in ci_checks/ci_scope.py UNITS"
            return {"scope": "full", "reason": f"{p}: {why}", "benches": []}
        benches |= own
    if not benches:
        return {"scope": "none", "reason": "only documents / tasks/dataset.toml changed", "benches": []}
    # benchmarks that share code with a changed one (either side names the other's scripts/<x> or images/<x>)
    tops = {t for p in paths if (t := top(p))}
    own_tops = {lab: {t for pre in UNITS[lab] if (t := top(pre))} for lab in UNITS}
    changed_tops = {t for lab in benches for t in own_tops[lab]} | tops
    for lab in UNITS:
        if lab in benches:
            continue
        mine = own_tops[lab]
        if refs_of(lab) & changed_tops or any(mine & refs_of(b) for b in list(benches)):
            benches.add(lab)
    return {"scope": "benchmarks", "reason": f"{len(paths)} changed path(s) in {len(benches)} benchmark(s)",
            "benches": sorted(benches)}


def main(argv: list[str]) -> int:
    diff_from, base, paths = None, "origin/main", None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--diff-from":
            diff_from, i = argv[i + 1], i + 2
        elif a == "--base":
            base, i = argv[i + 1], i + 2
        elif a == "--paths":
            paths, i = argv[i + 1:], len(argv)
        else:
            raise SystemExit(f"usage: ci_scope.py [--diff-from REV | --base REF] [--paths P...]; got {a!r}")
    if paths is None:
        try:
            paths = changed_paths(diff_from, base)
        except subprocess.CalledProcessError as e:   # no history to diff against: be safe
            paths, err = None, (e.stderr or "").strip().splitlines()[-1:] or ["git diff failed"]
    if paths is None:
        s = {"scope": "full", "reason": f"cannot diff ({err[0]})", "benches": []}
    else:
        s = scope(paths)
    benches = s["benches"]
    prefixes = sorted({p for b in benches for p in UNITS[b]})
    tprefixes = tuple(pre for pre, lab in tc.BENCHMARKS if lab in benches)
    tasks = [t.relative_to(ROOT).as_posix() for t in tc.iter_tasks()
             if label_of_task(t.name) in benches] if tprefixes else []
    print(f"RCB_SCOPE={s['scope']}")
    print(f"RCB_SCOPE_REASON={shlex.quote(s['reason'])}")
    print(f"RCB_SCOPE_BENCHES={shlex.quote(';'.join(benches))}")
    print(f"RCB_SCOPE_PATHS={shlex.quote(' '.join(prefixes))}")
    print(f"RCB_SCOPE_TASKS={shlex.quote(' '.join(tasks))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
