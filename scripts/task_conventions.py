#!/usr/bin/env python3
"""The conventions of a task directory (docs/protocol/README.md), applied in place and idempotently.

A task's author ends with `normalize(task_dir)`, so a re-rendered task equals the committed one; renaming directories
is the caller's job.

    python3 scripts/task_conventions.py tasks/<benchmark>/<task> [...]     # normalize these tasks
    python3 scripts/task_conventions.py --check tasks/<benchmark>/<task>   # exit 1 if normalizing would change anything
    python3 scripts/task_conventions.py benchmarks [--check]   # every task dir's benchmark label (BENCHMARKS) and folder
    python3 scripts/task_conventions.py task-dir <task> ...    # where a task dir lives: tasks/<benchmark folder>/<task>

What it does:
- `task.toml`: `oracle` (+ `oracle_evidence`) for benchmarks whose oracle level is known from their files.
- `tests/test.sh` clears `/logs/verifier` first.
- no `results/` directory (results are published on the results site, not in the repository).
- the resource caps (docs/protocol/README.md §6), every one an upper bound for one container, from the task's rule in
  `scripts/task_resources.toml` (a task no rule matches keeps the caps its files have): main's in `[environment]`
  (`cpus`, `memory_mb`, `storage_mb`, and `gpu_types` for a task that needs an RTX-class GPU), every other service's and
  main's processes in `environment/docker-compose.yaml` (`cpus`, `mem_limit`, `pids_limit`, and `x-gpu-memory-gb` on
  the service that holds the GPU; images/monitor/rcb_monitor/inject.py writes them). No `[metadata.resources]`.
- `instruction.md` in the v2 skeleton (V2_SECTIONS) ends with `## Limits`, rendered: the Time (§2, §5), Tokens, Network
  (§5) and Resources (§6, the caps of the agent's own container) lines, then the task's own lines.
- `[metadata] dynamics` (`dynamic` when something in the scene other than the robot does work by a force other than the
  robot's and gravity, else `static`) is the task's own declaration: kept as written; a re-render that lost it gets the
  committed task's line back (normalize_dynamics).
- from the agent's time cutoff (§2), the task's own `[agent] timeout_sec`: the standard modes' `RCB_WALL_CLOCK_S` in
  `environment/docker-compose.yaml`, the README's "Agent time budget" row and the Time line of `## Limits`.
- `README.md` in the standard layout (docs/protocol/README.md §1): title, key table, Task, Difficulty, Reference solution,
  Verification, Resources (the caps of every container, rendered), and Details for everything else.
- last, `DIGEST`: the task's content digest (PROTOCOL Appendix H.8; the digest Harbor publishes it under, `digest()`), one
  line `sha256:<hex>`. Each task carries its own, so pull requests that change different tasks never touch a shared file;
  the release manifest `tasks/dataset.toml` is generated from them (`scripts/dataset_manifest.py`, not committed).
"""
from __future__ import annotations

import collections
import fnmatch
import functools
import hashlib
import os
import re
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images/monitor"))   # the monitor image's source (rcb_monitor/)
from rcb_monitor import inject as rcb_monitor_inject  # noqa: E402


def _load_efe_mcp_inject():
    """embodied_first_exam/standard/mcp/inject.py, loaded by path (its directory is not put on sys.path: the server's
    modules there would shadow others)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "efe_mcp_inject", Path(__file__).resolve().parents[1] / "embodied_first_exam/standard/mcp/inject.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


efe_mcp_inject = _load_efe_mcp_inject()   # the robot's MCP tools in every standard and realtime task
service_layer = efe_mcp_inject.service_layer   # a task's service layer: operations | shared | realtime | sidecar

CLEAR_LOGS = "rm -rf /logs/verifier/*"
# The benchmarks, one row each: (task directory name prefix, label, folder). The folder is tasks/<folder>/ and the
# benchmark's embodied_first_exam/benchmarks/<folder>/; BENCHMARKS and BENCHMARK_DIRS below are views of this table, and
# ci_checks/ci_scope.py --check holds its UNITS / FILES_IMAGE to it. A new benchmark adds one row here.
BENCHMARK_TABLE = [
    ("robotwin_2_0_", "RoboTwin 2.0", "robotwin-2"),
    ("dextoolbench_", "DexToolBench", "dextoolbench"),
    ("mujoco_playground_", "MuJoCo Playground", "mujoco-playground"),
    ("kinder-", "KinDER", "kinder"),
    ("humanoidbench-", "HumanoidBench", "humanoidbench"),
    ("metaworldplus-", "MetaWorld+", "metaworldplus"),
    ("robowits-", "RoboWits", "robowits"),
    ("robopaint-", "RoboPaint", "robopaint"),
    ("robolab-", "RoboLab", "robolab"),
    ("behavior-", "BEHAVIOR-1K", "behavior-1k"),
    ("maniguard-", "ManiGuard", "maniguard"),
    ("molmospaces-", "MolmoSpaces", "molmospaces"),
    ("myosuite-", "MyoSuite", "myosuite"),
    ("dexjoco-", "DexJoCo", "dexjoco"),
    ("dexhand-", "DexHand", "dexhand"),
    ("vlabench-", "VLABench", "vlabench"),
    ("robocasa-gr1-", "RoboCasa-GR1", "robocasa-gr1"),  # before "robocasa-": the first matching prefix wins
    ("robocasa-", "RoboCasa", "robocasa"),
    ("robocasa365-", "RoboCasa365", "robocasa365"),
    ("libero-max-", "LIBERO-MAX", "libero-max"),
    ("roboarc-", "RoboARC", "roboarc"),  # with its IKEA furniture-assembly suite, roboarc-ikea-<item>-i00 (tasks/roboarc/README.md)
    ("bigym2-", "BiGym 2.0", "bigym2"),
    ("yamlab-", "YAMLab", "yamlab"),
    ("robodojo-", "RoboDojo", "robodojo"),
    ("embodied-olympics-fun-", "Embodied Olympics - Fun", "embodied-olympics-fun"),  # the single-humanoid sports families
    ("embodied-olympics-match-", "Embodied Olympics - Match", "embodied-olympics-match"),  # the matches Embodied Olympics exports with its own service, and their twins
    ("ese-", "Embodied Safety Exam", "embodied-safety-exam"),
    ("pandadyn-", "Panda Dynamic Scenes", "pandadyn"),
    ("ambench-", "AM-Bench", "ambench"),
    ("ispatialgym-", "iSpatialGym", "ispatialgym"),
    ("roboengineer-", "roboEngineer", "roboengineer"),  # its own multi-round runtime eai-policy/1.x (ci_checks/benchmarks/roboengineer/exported.toml)
    ("labutopia-", "LabUtopia", "labutopia"),
    ("autobio-", "AutoBio", "autobio"),
    ("abc-sim-", "ABC Sim", "abc-sim"),
    ("embodiedswe-", "EmbodiedSWE", "embodiedswe"),
    ("humanclaw-", "HumanCLAW", "humanclaw"),  # find / navigate / sit with a simulated human body (HumanClawBench)
]
BENCHMARKS = [(p, label) for p, label, _ in BENCHMARK_TABLE]   # (directory prefix, label): the first matching prefix wins
# Modes (PROTOCOL §3): a benchmark ships any subset of the modes. A standard or realtime
# task without a privileged twin says why in its README's Twin row ("— (none: ...)"), the task's own declaration:
# no_twin_reason() reads it back, so no list of such tasks is kept here.
# Embodied Olympics' exported tasks (PROTOCOL §3) have a Time line of their own (LIMITS_TIME_TASK below): the
# directories its manifest ci_checks/benchmarks/embodied-olympics-match/exported.toml lists in a mode that serves its own
# protocol (its [protocols] table: their session talks to its own service). The privileged twins listed there
# (`kind = "fullsim-policy"`) run no service: they keep their mode's note.
RO_EXPORTED_FILE = Path(__file__).resolve().parents[1] / "ci_checks/benchmarks/embodied-olympics-match/exported.toml"


def _ro_exported_tasks() -> tuple[str, ...]:
    d = tomllib.loads(RO_EXPORTED_FILE.read_text())
    own = d.get("protocols", {})              # mode -> the protocol its own service serves
    mode = lambda n: max((m for m in (*own, "privileged") if n.endswith("-" + m)), key=len, default=None)
    return tuple(t["name"] for t in d.get("tasks", []) if mode(t["name"]) in own)


RO_EXPORTED_TASKS = _ro_exported_tasks()
# PROTOCOL §3: THE registry of modes. A mode's name is the whole suffix of its task directories
# (`<base>-<mode>`; task.toml keeps no copy of it); everything that parses or branches on a mode reads this table (mode_of,
# base_of, the twins' equal cutoffs, the limits' scope, the checks under ci_checks/, which get it once per run through
# `python3 scripts/task_conventions.py modes`). A new mode is one entry here plus its protocol section, by a mode
# pull request (PROTOCOL §3 lists what it must contain). Fields:
#   short          the column label in tables of the modes (the generated task list)
#   section        the PROTOCOL section that defines the mode
#   sidecar        the simulator runs in a trusted `sim` sidecar the agent's container talks to (robot as a service):
#                  the instance copy is environment/sim/, the agent's image holds no simulator, the service is told the
#                  cutoff (RCB_WALL_CLOCK_S), the verifier collects its evidence from the sidecar
#   limit_scope    whose use the monitor sums against the GPU-memory and disk caps (§6): "trial" (every container the
#                  agent drives) or "agent" (the agent's container); images/monitor/rcb_monitor/inject.py kind_of
#   protocols      the `[metadata] protocol` values a task of the mode may declare (empty: the field is not set)
#   twin           the mode whose task of the same base holds the pair's frozen instance and seeds (None: itself)
#   same_cutoff_as the mode whose cutoff this mode's must equal wherever a benchmark, family or task has both (None: free)
MODE_REGISTRY = {
    "privileged": {"short": "P", "section": "§3", "sidecar": False, "limit_scope": "trial", "protocols": (),
                   "twin": None, "same_cutoff_as": None},
    "standard": {"short": "S", "section": "§3", "sidecar": True, "limit_scope": "agent",
                 "protocols": ("eai-standard/3.0",),
                 "twin": "privileged", "same_cutoff_as": "privileged",   # one cutoff for both modes (Appendix H.7)
                 "agent_end": True},   # v3.0: the agent ends the episode (§3 "Agent-ended episodes", H.3)
    "realtime": {"short": "RT", "section": "§3", "sidecar": True, "limit_scope": "agent",
                          "protocols": ("eai-standard/3.0",), "twin": "privileged", "same_cutoff_as": None,
                          "agent_end": True},
}
MODES = tuple(MODE_REGISTRY)
SIDECAR_MODES = tuple(m for m, d in MODE_REGISTRY.items() if d["sidecar"])   # robot as a service (PROTOCOL §3)
for _m, _d in MODE_REGISTRY.items():   # a registry that cannot parse names is refused at import (every check imports it)
    assert re.fullmatch(r"[a-z]+(?:-[a-z]+)*", _m) and not any(_m.endswith("-" + o) for o in MODE_REGISTRY if o != _m), \
        f"mode {_m!r}: lower-case words joined by '-', not ending in another mode's suffix (PROTOCOL §3)"
    assert _d["limit_scope"] in ("trial", "agent") and _d["twin"] in (None, *MODE_REGISTRY) \
        and _d["same_cutoff_as"] in (None, *MODE_REGISTRY), f"mode {_m!r}: a bad registry field (PROTOCOL §3)"
HEADER_KEYS = {"Benchmark", "Mode", "Twin", "Simulator / robot", "Family / instance", "Oracle", "Agent time budget",
               "Real time", "Base image"}
DROP_ROWS = {"simulator / robot", "family / instance", "base image"}   # header rows another README spelled in lower case
# PROTOCOL §6: the resource caps of every task, as rules (scripts/task_resources.toml); normalize writes them where
# Harbor and docker read them (normalize_resources, images/monitor/rcb_monitor/inject.py)
RESOURCES_FILE = Path(__file__).resolve().parent / "task_resources.toml"
# PROTOCOL §2: a realtime task's slowdown S is its sim service's `RCB_SLOWDOWN` default
# (environment/docker-compose.yaml), its reset budget the `RCB_RESET_BUDGET` default there; task.toml keeps no copy of
# either (ci_checks/check-realtime.py)
SLOWDOWN_RE = re.compile(r'RCB_SLOWDOWN:\s*"?\$\{RCB_SLOWDOWN:-([0-9.]+)\}"?')
# RCB_RESET_BUDGET's default: overridable (`"${RCB_RESET_BUDGET:-N}"`) or fixed (`"N"`); the one rule for the README,
# the recorded configuration (reset_budget_of) and ci_checks/check-realtime.py
RESET_DECL_RE = re.compile(r'^\s*RCB_RESET_BUDGET:\s*"?(?:\$\{RCB_RESET_BUDGET:-([0-9]+)\}|([0-9]+))"?\s*(?:#.*)?$', re.M)
# a task a benchmark exports with its own service (PROTOCOL §3) sets S its own way: Embodied Olympics `RO_SLOWDOWN: "10"`
OWN_SLOWDOWN_RE = re.compile(r'^\s*RO_SLOWDOWN:\s*"?([0-9.]+)"?\s*$', re.M)
# PROTOCOL §6: a rule of scripts/task_resources.toml: `match` and, per compose service, its caps (CAP_KEYS; `disk_gb`
# only for main, `gpu_memory_gb` only for a service that holds a GPU); for the README, `gpu_types` (a task that needs an
# RTX-class GPU: Harbor's `[environment].gpu_types` too), `recommended_gpu`, `measured`, `caps_measured`
CAP_KEYS = {"cpus": float, "memory_gb": float, "pids": int, "gpu_memory_gb": float, "disk_gb": float}
RULE_KEYS = {"match": str, "gpu_types": list, "recommended_gpu": str, "measured": str, "caps_measured": str}
# `gpu_types` names RTX-class models only (ray-tracing cores; Harbor's spelling of the model): a task that runs on any
# NVIDIA GPU sets none (ci_checks/check-resources.py)
RTX_GPU_MODELS = ("L40S", "L40", "L4", "RTX 4090", "RTX 6000 Ada", "RTX PRO 6000 Blackwell", "A40", "RTX A6000")
ENFORCE_ENV = "RCB_LIMITS_ENFORCE"   # §6: run-time switch (compose default 0 = record only; 1 = the monitor's backstop)
RESOURCES_HEADING = "## Resources"   # the README's section (readme_resources)
# PROTOCOL §5 (owner 11-24): the one anti-cheating rule, emphasized, first in Goal's rules (V2_RULE_OWN). Rendered words:
# edit them here, never in a task.
NO_CHEATING = ("**No cheating.** Do not search for, download or use any existing solution (published or reference "
               "solutions, the benchmark's demonstrations, trained policies); trials are reviewed.")
# owner 11-24: wording no task may carry any more (ci_checks/check-resources.py): "Write your own controller." in the No
# cheating rule, a privileged "Only the actions count: ... changes nothing in the replay." line, and "real-robot rules"
# as a rules heading (the rules section is `## Rules` / "Rules:"; Robot Interface says the robot is reached as if it
# were real hardware)
RETIRED_RULES_RE = re.compile(r"\*\*No cheating\.\*\* Write your own controller\.|changes nothing in the (?:replay|grading)\."
                              r"|(?i:real-robot rules)")

# PROTOCOL §2, §5: the agent's time cutoff. Each task sets its own, in `[agent] timeout_sec` of its task.toml (its author
# decides it in the pull request that adds or changes the task), as in Terminal-Bench. There is no table: normalize
# writes from the task's own number the standard modes' RCB_WALL_CLOCK_S and the Time line of instruction.md's
# `## Limits` (limits_time), the last section the agent reads: edit `timeout_sec` or the words of LIMITS_TIME, never the
# line in a task (ci_checks/check-cutoffs.py).
WALL_CLOCK_ENV = "RCB_WALL_CLOCK_S"              # the standard modes' sim service: what its /spec budget and time_left_s report
CUTOFF_CAP = 14400                               # PROTOCOL §2, no benchmark excepted (ci_checks/check-cutoffs.py)
# The repository's task tree: one folder per benchmark, tasks/<folder>/<task>/ (a task dir's name says its benchmark,
# bench_of; GitHub lists at most 1000 entries of a folder). The folder of each label: BENCHMARK_TABLE's third column.
# Everything that finds a task dir in the repository goes through task_dir() / iter_tasks(); `benchmarks --check` holds
# the tree to it.
TASKS_DIR = Path(__file__).resolve().parents[1] / "tasks"
BENCHMARK_DIRS = {label: folder for _, label, folder in BENCHMARK_TABLE}


# ---------------------------------------------------------------------------------------------------------------------
# PROTOCOL §1, §3: each mode of MODE_REGISTRY is the whole suffix of its task directories. A mode is recognised by
# its complete suffix only, longest first: `-realtime` is never `-standard` (it does not end in it).
MODES_LONGEST_FIRST = tuple(sorted(MODES, key=len, reverse=True))


def mode_suffix(name: str) -> str | None:
    """The mode a task dir name ends in (its whole suffix, longest first), None for a name that ends in none."""
    return next((m for m in MODES_LONGEST_FIRST if name.endswith(f"-{m}")), None)


def mode_of(task: Path) -> str:
    mode = mode_suffix(task.name)
    if mode is None:
        raise ValueError(f"{task.name}: task directories end in " + ", ".join(f"-{m}" for m in MODES)
                         + " (docs/protocol/README.md §1, the modes of §3)")
    return mode


def base_of(task: Path) -> str:
    """The name without its mode suffix (`-privileged`, `-standard`, `-realtime`, ...; PROTOCOL §1)."""
    mode = mode_suffix(task.name)
    return task.name[: -len(mode) - 1] if mode else task.name


def canonical_name(name: str) -> str:
    """The task dir name of a task name in a recorded job: a name without a mode suffix is a privileged task's, one
    ending in `-limited` a standard task's."""
    if mode_suffix(name):
        return name
    if name.endswith("-limited"):
        return name[: -len("-limited")] + "-standard"
    return name + "-privileged"


def cutoff_pairs(task: Path) -> list[tuple[Path, Path]]:
    """(task, its twin) for every mode pair the registry ties together (`same_cutoff_as`), in either direction, where the
    twin exists; sorted so that a pair reached from both sides is the same tuple."""
    mode, base = mode_of(task), base_of(task)
    out = []
    for m, d in MODE_REGISTRY.items():
        o = d["same_cutoff_as"]
        if not o or mode not in (m, o):
            continue
        other = task.with_name(f"{base}-{o if mode == m else m}")
        if (other / "task.toml").is_file():
            out.append(tuple(sorted((task, other))))
    return out


def twin_of(task: Path) -> Path | None:
    """The task of the same base in the mode MODE_REGISTRY names as this mode's twin (the one that holds the pair's frozen
    instance and seeds: `<base>-privileged` for the standard modes), whether it exists or not; None for a mode without one."""
    twin = MODE_REGISTRY[mode_of(task)]["twin"]
    return task.with_name(f"{base_of(task)}-{twin}") if twin else None


def modes_table() -> str:
    """One line per mode, longest name first, for the shell checks (`python3 scripts/task_conventions.py modes`):
    `<mode> <sidecar 0|1> <twin mode or ->`."""
    return "\n".join(f"{m} {int(MODE_REGISTRY[m]['sidecar'])} {MODE_REGISTRY[m]['twin'] or '-'}"
                     for m in MODES_LONGEST_FIRST)


def bench_of(task: Path) -> str:
    """The task's BENCHMARKS label (a task dir or a base): its first matching prefix's label; "" for a name no label
    claims."""
    name = Path(task).name
    return next((label for p, label in BENCHMARKS if name.startswith(p)), "")


def bench_dir(task: "Path | str") -> str:
    """The folder under tasks/ of the task's benchmark (BENCHMARK_DIRS; a task dir or a base), "" for a name no label
    claims."""
    return BENCHMARK_DIRS.get(bench_of(Path(task)), "")


def task_dir(name: "Path | str", tasks_dir: "Path | str | None" = None) -> Path:
    """The task dir of that name in the repository's tree, tasks/<benchmark folder>/<name> (tasks_dir: another tree of
    the same layout, e.g. a deploy checkout). It need not exist. A name no benchmark claims: tasks/<name>, which
    `benchmarks --check` rejects."""
    tasks_dir = Path(tasks_dir) if tasks_dir else TASKS_DIR
    name = Path(name).name
    folder = bench_dir(name)
    return tasks_dir / folder / name if folder else tasks_dir / name


def task_relpath(name: "Path | str") -> str:
    """task_dir() relative to the repository root, as git names it: `tasks/<benchmark folder>/<name>`."""
    return task_dir(name, Path("tasks")).as_posix()


def bench_root(bench: str, tasks_dir: "Path | str | None" = None) -> Path:
    """The folder of a benchmark (a BENCHMARKS label or its BENCHMARK_DIRS folder) under tasks/: where its tasks are
    written and found."""
    folder = BENCHMARK_DIRS.get(bench, bench)
    if folder not in BENCHMARK_DIRS.values():
        raise KeyError(f"{bench!r}: not a BENCHMARKS label or benchmark folder (scripts/task_conventions.py BENCHMARK_DIRS)")
    return (Path(tasks_dir) if tasks_dir else TASKS_DIR) / folder


def iter_tasks(tasks_dir: "Path | str | None" = None) -> list[Path]:
    """Every task dir of the tree (tasks/<folder>/<task>/ with a task.toml), sorted by name."""
    tasks_dir = Path(tasks_dir) if tasks_dir else TASKS_DIR
    return sorted((p.parent for p in tasks_dir.glob("*/*/task.toml")), key=lambda p: p.name)


TASKS_TOP_FILES = ("README.md", "dataset.toml")   # tasks/ holds the benchmark folders and these (dataset.toml: generated)
BENCH_DOC_SUFFIXES = (".md", ".png")              # a benchmark folder's own pages (README.md, <topic>.md) and their figures
FOLDER_MAX = 1000                                 # GitHub's web UI lists at most this many entries of a folder


def check_layout(tasks_dir: Path | None = None) -> list[str]:
    """What is wrong with the tree's layout (`benchmarks --check`): a BENCHMARKS label without its folder (or a folder
    without its label, or two labels on one folder), anything at the top of tasks/ besides the benchmark folders and
    TASKS_TOP_FILES, anything in a benchmark folder besides task dirs and its pages (BENCH_DOC_SUFFIXES), a task dir in
    another benchmark's folder or nested deeper, a folder over FOLDER_MAX entries."""
    tasks_dir = tasks_dir or TASKS_DIR
    labels = {label for _, label in BENCHMARKS}
    bad = [f"BENCHMARKS label {b!r}: no folder in BENCHMARK_DIRS" for b in sorted(labels - set(BENCHMARK_DIRS))]
    bad += [f"BENCHMARK_DIRS {b!r}: not a BENCHMARKS label" for b in sorted(set(BENCHMARK_DIRS) - labels)]
    folders = collections.Counter(BENCHMARK_DIRS.values())
    bad += [f"BENCHMARK_DIRS: folder {f!r} given to {k} labels" for f, k in folders.items() if k > 1]
    bad += [f"BENCHMARK_DIRS: folder {f!r} is not a lowercase slug" for f in folders if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", f)]
    for p in sorted(tasks_dir.iterdir()):
        if p.name in TASKS_TOP_FILES and p.is_file():
            continue
        if not p.is_dir() or p.name not in folders:
            bad.append(f"tasks/{p.name}: not a benchmark folder (scripts/task_conventions.py BENCHMARK_DIRS)"
                       + (" -- a task dir belongs in tasks/<benchmark folder>/" if (p / "task.toml").exists() else ""))
            continue
        entries = sorted(p.iterdir())
        if len(entries) > FOLDER_MAX:
            bad.append(f"tasks/{p.name}: {len(entries)} entries, over {FOLDER_MAX} (GitHub lists no more)")
        for t in entries:
            if t.is_file() and t.suffix in BENCH_DOC_SUFFIXES:
                continue                     # the benchmark's pages, not task dirs
            if not (t / "task.toml").is_file():
                bad.append(f"tasks/{p.name}/{t.name}: not a task dir")
            elif bench_dir(t.name) != p.name:
                bad.append(f"tasks/{p.name}/{t.name}: belongs in tasks/{bench_dir(t.name) or '<no benchmark>'}/")
    return bad


def check_benchmarks(tasks_dir: Path | None = None) -> list[str]:
    """What is wrong with the benchmark labels and the tree (`benchmarks --check`): check_layout(), a task dir no label
    claims, a prefix listed twice."""
    tasks_dir = tasks_dir or TASKS_DIR
    names = sorted(p.name for p in iter_tasks(tasks_dir))
    bad = check_layout(tasks_dir)
    bad += [f"{n}: no benchmark label (scripts/task_conventions.py BENCHMARKS)" for n in names if not bench_of(Path(n))]
    seen = collections.Counter(p for p, _ in BENCHMARKS)
    bad += [f"prefix {p!r} is listed {k} times in BENCHMARKS" for p, k in seen.items() if k > 1]
    return bad


def task_toml(task: Path) -> dict:
    """The task's task.toml, parsed; {} when it is missing or unreadable."""
    try:
        return tomllib.loads((task / "task.toml").read_text())
    except (OSError, ValueError):            # tomllib.TOMLDecodeError and UnicodeDecodeError are ValueErrors
        return {}


def read_text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def write_if_changed(p: Path, s: str) -> None:
    if read_text(p) != s:
        p.write_text(s, encoding="utf-8")


# ---------------------------------------------------------------------------------------------------------------------
def dtb_goals(task: Path) -> tuple[int, int] | None:
    """(goals reached, goals) by the DexToolBench oracle, from the privileged twin's README oracle row."""
    priv = task.with_name(base_of(task) + "-privileged")
    for f in (priv / "README.md", task / "README.md"):
        s = read_text(f) or ""
        m = re.search(r"\*\*(\d+)/(\d+) goals\*\*", s)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def oracle_level(task: Path) -> tuple[str, str] | None:
    """(oracle, oracle_evidence) for benchmarks whose oracle level follows from their own files; None = keep as is."""
    n = task.name
    if n.startswith(("robotwin_2_0_", "mujoco_playground_")):
        return "full", ""
    if n.startswith("dextoolbench_"):
        g = dtb_goals(task)
        if g is None:
            return None
        if g[0] >= g[1]:
            return "full", ""
        return "partial", (f"SimToolReal's pretrained policy, replayed in this scene, reaches {g[0]}/{g[1]} goals "
                           f"(solution/; README of {base_of(task)}-privileged)")
    return None


def normalize_toml(task: Path) -> None:
    p = task / "task.toml"
    s = p.read_text()
    s = re.sub(r'^name = "embodied-first-exam/[^"]*"', f'name = "embodied-first-exam/{task.name}"', s, count=1, flags=re.M)
    lvl = oracle_level(task)
    meta = tomllib.loads(s).get("metadata", {})
    if lvl and "oracle" not in meta:
        o, ev = lvl
        line = f'oracle = "{o}"\n' + (f'oracle_evidence = "{ev}"\n' if ev else "")
        s = metadata_insert(s, line)
    write_if_changed(p, s)


def _metadata_span(s: str) -> tuple[int, int]:
    """The body of task.toml's `[metadata]` table: (start, end) offsets, up to the next table header."""
    m = re.search(r"(?m)^\[metadata\]\n", s)
    if not m:
        raise RuntimeError("task.toml has no [metadata] table")
    h = re.search(r"(?m)^\[", s[m.end():])
    return m.end(), (m.end() + h.start() if h else len(s))


def metadata_body(s: str) -> str:
    a, b = _metadata_span(s)
    return s[a:b]


def metadata_sub(s: str, pattern: str, repl, count: int = 0) -> str:
    """re.sub inside the `[metadata]` table only."""
    a, b = _metadata_span(s)
    return s[:a] + re.sub(pattern, repl, s[a:b], count=count) + s[b:]


def metadata_insert(s: str, line: str, after: str = "") -> str:
    """Inserts `line` (ending in a newline) into `[metadata]`: after the `<after> = ...` line when there is one, else
    before `expert_time_estimate_hours`, else after the table's last key."""
    a, b = _metadata_span(s)
    body = s[a:b]
    m = re.search(rf"(?m)^{re.escape(after)} = .*\n", body) if after else None
    if m:
        at = m.end()
    else:
        m = re.search(r"(?m)^expert_time_estimate_hours = ", body)
        at = m.start() if m else len(body.rstrip("\n")) + 1
    body = body[:at] + line + body[at:]
    return s[:a] + body + s[b:]


def _rules() -> list[dict]:
    return tomllib.loads(RESOURCES_FILE.read_text()).get("cap", []) if RESOURCES_FILE.is_file() else []


def rule_for(task: Path) -> dict | None:
    """The task's rule in scripts/task_resources.toml: the last `[[cap]]` whose `match` (a regular expression) finds the
    task directory name, whole (no merging), as {"services": {name: caps}, "gpu_types", "recommended_gpu", "measured",
    "caps_measured"}. None: no rule matches (the task keeps the caps its files have)."""
    rule = None
    for r in _rules():
        if re.search(r["match"], task.name):
            rule = r
    if rule is None:
        return None
    out: dict = {"services": {}}
    for k, v in rule.items():
        if k in RULE_KEYS:
            if not isinstance(v, RULE_KEYS[k]) or (k == "gpu_types" and not all(isinstance(x, str) and x for x in v)):
                raise RuntimeError(f"{task.name}: scripts/task_resources.toml {k} = {v!r}: a {RULE_KEYS[k].__name__}")
            out[k] = v
        elif isinstance(v, dict):
            bad = sorted(set(v) - set(CAP_KEYS)) + (["disk_gb"] if k != "main" and "disk_gb" in v else [])
            if bad:
                raise RuntimeError(f"{task.name}: scripts/task_resources.toml service {k}: unknown or misplaced keys {bad}")
            out["services"][k] = {f: CAP_KEYS[f](v[f]) for f in CAP_KEYS if f in v}
            for f in ("memory_gb", "disk_gb"):
                mib = out["services"][k].get(f, 0) * 1024
                if abs(mib - round(mib)) > 1e-9:
                    raise RuntimeError(f"{task.name}: scripts/task_resources.toml service {k}: {f} = {v[f]} is not a "
                                       f"whole number of MiB ({mib:g}); the caps are written in MiB (memory_mb, "
                                       "storage_mb, mem_limit), so pick a multiple of 1/1024 GiB")
        else:
            raise RuntimeError(f"{task.name}: scripts/task_resources.toml: unknown key {k!r}")
    main = out["services"].get("main") or {}
    missing = [f for f in ("cpus", "memory_gb", "pids", "disk_gb") if f not in main]
    if missing:
        raise RuntimeError(f"{task.name}: scripts/task_resources.toml: main misses {missing}")
    if main["cpus"] != int(main["cpus"]):
        raise RuntimeError(f"{task.name}: scripts/task_resources.toml: main cpus {main['cpus']} (Harbor's `cpus` is a whole number)")
    return out


def _toml_value(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


ENV_CAP_KEYS = ("cpus", "memory_mb", "storage_mb", "gpu_types")   # what normalize writes into [environment] (Harbor's)


def _key_spans(rows: list[str], where: str) -> list[tuple[str, int, int]]:
    """(key, first row, row after its value) of every `key = value` of a TOML table's rows; a value may span several
    rows (a multi-line array or string): it ends at the first row where `key = value` parses."""
    out, i = [], 0
    while i < len(rows):
        m = re.match(r'\s*("[^"]*"|[A-Za-z0-9_-]+)\s*=', rows[i])
        if not m:
            i += 1
            continue
        j = i + 1
        while True:
            try:
                tomllib.loads("".join(rows[i:j]))
                break
            except tomllib.TOMLDecodeError:
                if j >= len(rows):
                    raise RuntimeError(f"{where}: the value of {m.group(1)} does not parse")
                j += 1
        out.append((m.group(1).strip('"'), i, j))
        i = j
    return out


def set_table_keys(s: str, table: str, values: dict, task_name: str = "") -> str:
    """task.toml text with `values` set in `[table]` (created at the end when missing; a key already there is rewritten
    in place, a one-line value's comment kept, a multi-line value replaced whole; a new key goes after the table's last
    value; None removes the key)."""
    m = re.search(rf"(?ms)^\[{re.escape(table)}\]\n(.*?)(?=^\[|\Z)", s)
    if not m:
        if all(v is None for v in values.values()):
            return s
        s = s.rstrip("\n") + f"\n\n[{table}]\n"
        m = re.search(rf"(?ms)^\[{re.escape(table)}\]\n(.*?)(?=^\[|\Z)", s)
    rows = m.group(1).splitlines(keepends=True)
    if rows and not rows[-1].endswith("\n"):
        rows[-1] += "\n"
    for k, v in values.items():
        spans = _key_spans(rows, f"{task_name}: task.toml [{table}]")
        at = next(((a, b) for key, a, b in spans if key == k), None)
        if v is None:
            if at is not None:
                del rows[at[0]:at[1]]
            continue
        line = f"{k} = {_toml_value(v)}"
        if at is not None:
            c = re.search(r"\s+#.*$", rows[at[0]].rstrip("\n")) if at[1] - at[0] == 1 else None
            rows[at[0]:at[1]] = [line + (c.group(0) if c else "") + "\n"]
        else:
            last = max((b for _, _, b in spans), default=0)
            rows.insert(last, line + "\n")
    return s[:m.start(1)] + "".join(rows) + s[m.end(1):]


def normalize_resources(task: Path) -> None:
    """The caps of main where Harbor reads them, `[environment]` (`cpus`, `memory_mb`, `storage_mb`, `gpu_types`), from
    the task's rule (PROTOCOL §6; the other services' and main's processes: inject.py, in the compose file)."""
    p = task / "task.toml"
    s = p.read_text()
    r = rule_for(task)
    if r is not None:
        main = r["services"]["main"]
        s = set_table_keys(s, "environment", {"cpus": int(main["cpus"]), "memory_mb": int(round(main["memory_gb"] * 1024)),
                                              "storage_mb": int(round(main["disk_gb"] * 1024)),
                                              "gpu_types": r.get("gpu_types")}, task.name)
    write_if_changed(p, s)


def rule_caps(task: Path) -> dict | None:
    """{service: caps} of the task's rule for the compose file (inject.apply), or None (no rule: keep the file's)."""
    r = rule_for(task)
    return None if r is None else {n: {k: v for k, v in c.items() if k != "disk_gb"} for n, c in r["services"].items()}


def task_caps(task: Path) -> dict[str, dict]:
    """The caps docker and Harbor apply, per compose service (images/monitor/rcb_monitor/inject.py applied_caps): main's CPU,
    memory and disk from `[environment]`, the rest from environment/docker-compose.yaml; `gpu`: it holds a GPU."""
    return rcb_monitor_inject.applied_caps(task_toml(task), read_text(task / "environment/docker-compose.yaml"))


def verifier_caps(task: Path) -> dict:
    """The separate verifier's caps as Harbor applies them (harbor/models/task/verifier_mode.py
    resolve_effective_verifier_env_config): the `[verifier.environment]` table alone when the task has one (a cpus or
    memory_mb it lacks is no cap at all, never main's), a copy of main's `[environment]` when it has none; its processes,
    GPU and GPU memory (a recorded cap: nothing measures the verifier phase) from tests/docker-compose.yaml. `own`: the
    table exists."""
    cfg = task_toml(task)
    venv = (cfg.get("verifier") or {}).get("environment")
    env = dict(venv if venv is not None else (cfg.get("environment") or {}))
    tc = read_text(task / "tests/docker-compose.yaml")
    try:
        main = (rcb_monitor_inject.service_caps(tc) if tc else {}).get("main") or {}
    except ValueError:
        main = {}
    return {"cpus": float(env["cpus"]) if isinstance(env.get("cpus"), (int, float)) else None,
            "memory_gb": float(env["memory_mb"]) / 1024 if isinstance(env.get("memory_mb"), (int, float)) else None,
            "disk_gb": float(env["storage_mb"]) / 1024 if isinstance(env.get("storage_mb"), (int, float)) else None,
            "pids": main.get("pids"), "gpu": bool(main.get("gpu")), "gpu_memory_gb": main.get("gpu_memory_gb"),
            "own": venv is not None}


def _num(v) -> str:
    v = float(v)
    return str(int(v)) if v == int(v) else f"{v:g}"


def sidecars_of(task: Path) -> list[str]:
    """Compose services next to the agent's container (`main`), cache helpers (`rcb_*`) left out."""
    c = read_text(task / "environment/docker-compose.yaml") or ""
    return [s for s in rcb_monitor_inject.service_names(c) if s != "main" and not s.startswith("rcb_")]


def _paths(ps) -> str:
    q = [f"`{p}`" for p in ps]
    return q[0] if len(q) == 1 else ", ".join(q[:-1]) + " and " + q[-1]


def _gb(v) -> str:
    return "—" if v is None else f"{_num(v)} GiB"


def readme_resources(task: Path, old_readme: str = "") -> list[str]:
    """README `## Resources` (PROTOCOL §6): the caps of every container, as applied, and the rule's recommended GPU (a task
    no rule matches keeps the `- Measured` / `- Recommended GPU` lines of its README). A rule's `measured` and
    `caps_measured` stay in the rules file: they are the benchmark's, not each task's."""
    caps = task_caps(task)
    r = rule_for(task) or {}
    gpu_types = (task_toml(task).get("environment") or {}).get("gpu_types")
    rows = ["| Container | CPUs | Memory | Processes | GPU memory | Disk |", "|---|---|---|---|---|---|"]
    nocap = lambda v, f: "no cap" if v is None else f(v)   # noqa: E731  (the verifier: a key Harbor lacks is no cap)
    for name, c in caps.items():
        who = f"`{name}`" + (" (the agent's)" if name == "main" else "")
        gm = _gb(c.get("gpu_memory_gb")) if c.get("gpu") else "no GPU"
        rows.append(f"| {who} | {_num(c['cpus']) if c.get('cpus') else '—'} | {_gb(c.get('memory_gb'))} | "
                    f"{c.get('pids') or '—'} | {gm} | {_gb(c.get('disk_gb'))} |")
    cfg = task_toml(task)
    if ((cfg.get("verifier") or {}).get("environment_mode")) == "separate":
        v = verifier_caps(task)
        gm = nocap(v.get("gpu_memory_gb"), _gb) if v["gpu"] else "no GPU"
        rows.append(f"| verifier{'' if v['own'] else ' (as `main`)'} | {nocap(v.get('cpus'), _num)} | "
                    f"{nocap(v.get('memory_gb'), _gb)} | {nocap(v.get('pids'), str)} | {gm} | {nocap(v.get('disk_gb'), _gb)} |")
    held = [n for n, c in caps.items() if c.get("gpu")]
    if gpu_types:
        gpu = (f"an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: {', '.join(gpu_types)}")
    elif held:
        gpu = "any NVIDIA GPU"
    else:
        gpu = None
    notes = [f"- GPU: {gpu}, held by {_paths(held)}." if gpu else "- GPU: not needed."]
    if r:
        notes += [f"- Recommended GPU: {r['recommended_gpu']}."] if r.get("recommended_gpu") else []
    else:
        sec = section(old_readme, RESOURCES_HEADING[3:])
        notes += [ln for ln in (sec.splitlines() if sec else [])
                  if ln.startswith(("- Recommended GPU:", "- Measured:"))]
    return [RESOURCES_HEADING, "Caps per container (PROTOCOL §6).", "", *rows, "", *notes]


VERIFIER_NETWORK_LINE = 'network_mode = "no-network"       # PROTOCOL H.6: the verifier has no network'


def normalize_verifier_network(task: Path) -> None:
    """`[verifier] network_mode = "no-network"` (PROTOCOL Appendix H.6: the verifier has no network; Harbor 0.23 denies the
    separate verifier environment all egress while tests/test.sh runs). A task that lacks it gets the line after
    `environment_mode`; one that sets another policy (or `allowed_hosts`) for its verifier is an error, never rewritten."""
    p = task / "task.toml"
    s = p.read_text()
    ver = tomllib.loads(s).get("verifier") or {}
    if "allowed_hosts" in ver or ver.get("network_mode", "no-network") != "no-network":
        raise RuntimeError(f'{task.name}: [verifier] sets a network policy other than network_mode = "no-network" (PROTOCOL H.6)')
    if ver.get("network_mode") == "no-network":
        return
    m = re.search(r"(?ms)^\[verifier\]\n(.*?)(?=^\[|\Z)", s)
    if not m:
        raise RuntimeError(f"{task.name}: task.toml has no [verifier] table")
    body = m.group(1)
    em = re.search(r"(?m)^environment_mode\s*=.*\n", body)
    at = m.start(1) + (em.end() if em else 0)
    write_if_changed(p, s[:at] + VERIFIER_NETWORK_LINE + "\n" + s[at:])


def cutoff_for(task: Path) -> int | None:
    """The agent's time cutoff of a task in seconds: its own `[agent] timeout_sec` (PROTOCOL §2), the one source of the
    number. None when task.toml has none, or one that is not a whole positive number of seconds (ci_checks/check-cutoffs.py
    fails such a task; normalize then writes nothing from it)."""
    v = task_toml(task).get("agent", {}).get("timeout_sec")
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0 or float(v) != int(v):
        return None
    return int(v)


@functools.cache
def bench_has_mode(bench: str, mode: str) -> bool:
    """Whether the benchmark (a BENCHMARKS label) ships tasks of the mode: a task directory of it under the repository's
    tasks/ (PROTOCOL §2). Read from the repository, not from the directory a task is rendered in."""
    prefixes = tuple(p for p, label in BENCHMARKS if label == bench)
    if not TASKS_DIR.is_dir() or bench not in BENCHMARK_DIRS:  # Source-only generation has no committed task tree.
        return False
    folder = bench_root(bench)
    return any(d.name.startswith(prefixes) and mode_of(d) == mode and bench_of(d) == bench
               for d in folder.iterdir() if (d / "task.toml").is_file()) if prefixes and folder.is_dir() else False


def no_twin_reason(task: Path) -> str | None:
    """Why a standard or realtime task has no privileged twin `<base>-privileged` (PROTOCOL §3), as its
    README's Twin row says it; None for a privileged task and for one that names its twin. The reason is the task's own
    declaration: its README's Twin row ("— (none: ...)"), kept by every render (the committed task's row when a
    task is rendered into a scratch directory); a benchmark without a privileged mode gets the generic reason. Whether
    the twin exists is not looked at: the answer is the same before and after the twin has been rendered."""
    twin = MODE_REGISTRY[mode_of(task)]["twin"]
    if twin is None:
        return None
    committed = task_dir(task.name) / "README.md"
    for f in (task / "README.md", committed):
        m = re.search(r"(?m)^\| Twin \| (— \(none:[^\n]*?\)) \|\s*$", read_text(f) or "")
        if m:
            return m.group(1)
    bench = bench_of(task)
    if bench and not bench_has_mode(bench, twin):
        return f"— (none: {bench} has no {twin} mode, PROTOCOL §2)"
    return None


# PROTOCOL §3 "Agent-ended episodes": a task opts in in its sim service's environment (`RCB_AGENT_END: "1"`, and
# `RCB_STEP_LIMIT: "<N>"` for a step limit; embodied_first_exam/standard/agent_end/). Its instruction then has the
# finish line in `## Robot Interface` (ROBOT_FINISH) and the Finish (and Steps) lines of `## Limits` (render_limits).
AGENT_END_RE = re.compile(r'^\s*RCB_AGENT_END:\s*"?1"?\s*(?:#.*)?$', re.M)
STEP_LIMIT_RE = re.compile(r'^\s*RCB_STEP_LIMIT:\s*"?([0-9]+)"?\s*(?:#.*)?$', re.M)
# a service's own technical episode cap set in its environment (the benchmark-own adapters server_mw / server_casa / server_mj:
# `/spec.max_control_steps`); without RCB_STEP_LIMIT it ends the episode the same way (standard_mode.md "Agent-ended
# episodes"), so the instruction's Limits states it in a Steps line
MAX_CONTROL_STEPS_RE = re.compile(r'^\s*RCB_MAX_CONTROL_STEPS:\s*"?([0-9]+)"?\s*(?:#.*)?$', re.M)


def agent_end_of(task: Path) -> dict | None:
    """A standard-mode task's agent-ended episode (PROTOCOL §3): {"step_limit": N or None}, None when it does not opt
    in (its sim service's RCB_AGENT_END, RCB_STEP_LIMIT)."""
    if not MODE_REGISTRY.get(mode_of(task), {}).get("sidecar"):
        return None
    c = read_text(task / "environment/docker-compose.yaml") or ""
    if not AGENT_END_RE.search(c):
        return None
    m = STEP_LIMIT_RE.search(c)
    return {"step_limit": int(m.group(1)) if m else None}


# Tasks a benchmark exports with its own service inside (PROTOCOL §3): each such benchmark keeps a manifest,
# ci_checks/benchmarks/<bench>/exported.toml, that lists the directories (`[[tasks]] name`) and the protocol(s) each mode
# serves (`[protocols]`, a string or a list); a listed directory may declare one of its manifest's protocols for its mode
# (a task may name its one protocol, `protocol`: then only that one). No per-benchmark table here.
def _own_protocols() -> dict[str, dict[str, set[str]]]:
    out: dict[str, dict[str, set[str]]] = {}
    for man in sorted((Path(__file__).resolve().parents[1] / "ci_checks/benchmarks").glob("*/exported.toml")):
        d = tomllib.loads(man.read_text())
        protos = {m: {p} if isinstance(p, str) else set(p) for m, p in d.get("protocols", {}).items()}
        for t in d.get("tasks", []):
            own = t.get("protocol")
            out[t["name"]] = {m: ps & {own} for m, ps in protos.items()} if own else protos
    return out


OWN_PROTOCOLS = _own_protocols()


def own_protocols(name: str, mode: str | None) -> set[str]:
    """The protocols a benchmark's own exported task may declare instead of its mode's (empty: not such a task)."""
    return OWN_PROTOCOLS.get(name, {}).get(mode or "", set())


def agent_end_required(task: Path) -> bool:
    """PROTOCOL v3.0 §3 / H.3: the task's episode must be agent-ended: its mode says so (MODE_REGISTRY "agent_end"),
    unless it is a task a benchmark exports with a runtime of its own (PROTOCOL §3: Embodied Olympics Match,
    RoboEngineer), listed in that benchmark's exported.toml and declaring one of the protocols it lists for its mode.
    Any other protocol does not exempt a task (check-agent-end.py fails one that is neither its mode's nor its
    manifest's)."""
    mode = mode_of(task)
    if not MODE_REGISTRY.get(mode, {}).get("agent_end"):
        return False
    return str(metadata_of(task).get("protocol") or "") not in own_protocols(task.name, mode)


AGENT_END_ENV_LINE = '      RCB_AGENT_END: "1"                               # agent-ended episodes (PROTOCOL §3)\n'


def set_agent_end(compose: str, name: str = "") -> str:
    """A compose file whose `sim` service ends its episodes the agent's way: `RCB_AGENT_END: "1"` first in its
    `environment:` mapping (a value other than "1" is set to it)."""
    if AGENT_END_RE.search(compose):
        return compose
    if re.search(r'(?m)^\s*RCB_AGENT_END:', compose):
        return re.sub(r'(?m)^(\s*RCB_AGENT_END:)[^\n]*$', lambda m: m.group(1) + ' "1"', compose)
    lines = compose.splitlines(keepends=True)
    i, j = rcb_monitor_inject.services_span(lines)
    for svc, k0, k1 in rcb_monitor_inject.service_blocks(lines, i, j):
        if svc != "sim":
            continue
        e = rcb_monitor_inject.has_key(lines, k0, k1, "environment")
        if e is None or not re.match(r"^    environment:[ \t]*(#.*)?$", lines[e]):
            raise RuntimeError(f"{name}: the sim service has no `environment:` mapping normalize can add RCB_AGENT_END to")
        lines.insert(e + 1, AGENT_END_ENV_LINE)
        return "".join(lines)
    raise RuntimeError(f"{name}: no `sim` service to add RCB_AGENT_END to")


def normalize_agent_end(task: Path) -> None:
    """PROTOCOL v3.0 §3: a task whose episode must be agent-ended (agent_end_required) has RCB_AGENT_END on in its sim
    service (ci_checks/check-agent-end.py)."""
    c = task / "environment/docker-compose.yaml"
    if agent_end_required(task) and c.is_file():
        write_if_changed(c, set_agent_end(c.read_text(), task.name))


def _set_number(old: str, sec: int) -> str:
    """`sec` written the way the old literal was (a float literal stays one: `3600.0`)."""
    return f"{sec}.0" if "." in old else str(sec)


def normalize_cutoff(task: Path) -> None:
    """In the standard modes, the sim service's `RCB_WALL_CLOCK_S` (what its `/spec` budget and `meta["time_left_s"]`
    report) is the task's own cutoff, `[agent] timeout_sec` (PROTOCOL §2). A task without a usable number is left as
    it is."""
    sec = cutoff_for(task)
    if sec is None:
        return
    c = task / "environment/docker-compose.yaml"
    if mode_of(task) in SIDECAR_MODES and c.is_file():
        write_if_changed(c, set_wall_clock(c.read_text(), sec, task.name))


def set_wall_clock(compose: str, sec: int, name: str = "") -> str:
    """A standard-mode compose file whose `sim` service is told the agent's cutoff: every `RCB_WALL_CLOCK_S` in the file
    is `sec`, and a `sim` service that does not set it (its code then falls back to a default of its own, which a change
    of the cutoff would not reach) gets the line at the end of its `environment:` mapping."""
    pat = rf"""({WALL_CLOCK_ENV}:[ \t]*["']?)([0-9][0-9.]*)"""
    if re.search(pat, compose):
        return re.sub(pat, lambda m: m.group(1) + _set_number(m.group(2), sec), compose)
    lines = compose.splitlines(keepends=True)
    try:
        i, j = rcb_monitor_inject.services_span(lines)
    except ValueError:
        return compose
    for svc, k0, k1 in rcb_monitor_inject.service_blocks(lines, i, j):
        if svc != "sim":
            continue
        e = rcb_monitor_inject.has_key(lines, k0, k1, "environment")
        if e is None or not re.match(r"^    environment:[ \t]*(#.*)?$", lines[e]):
            raise RuntimeError(f"{name}: the sim service has no `environment:` mapping normalize can add {WALL_CLOCK_ENV} to")
        last = e
        for k in range(e + 1, k1):
            if re.match(r"^      [A-Za-z_][A-Za-z0-9_]*:", lines[k]):
                last = k
            elif lines[k].strip() and not lines[k].startswith("      "):
                break
        if last == e:
            raise RuntimeError(f"{name}: the sim service's `environment:` is not a mapping of KEY: value lines")
        lines.insert(last + 1, f'      {WALL_CLOCK_ENV}: "{sec}"\n')
        return "".join(lines)
    return compose


# instructions v2 (owner decisions D158-D165, 11-22): every instruction.md is the title line and the H2 sections of
# V2_SECTIONS in this order (`## Others` may be left out; H3s only inside them), and normalize renders the last one,
# `## Limits`, from the task's own numbers: the Time, Tokens, Network and Resources lines (LIMITS_RENDERED). Any other
# line of a task's `## Limits` (Resets, Steps, a game clock: the benchmark's own text writes it) is kept after them, and a
# task without a Resets line gets the default of its mode (limits_resets). `--check` reports a task whose headings are
# not the skeleton (skeleton_errors). The benchmarks' own text names the limit as "the time limit (Limits)".
V2_SECTIONS = ("Task", "Goal", "Robot Interface", "Others", "Limits")
V2_OPTIONAL = ("Others",)
LIMITS_HEADING = "## Limits"
LIMITS_RENDERED = ("Time", "Tokens", "Network", "Resources")
V2_CUTOFF_REF = "the time limit (Limits)"
LIMITS_TOKENS = "no separate limit."
# Agents without a clock in their tool output guess their elapsed time 2-7 times too high and stop early: every agent
# gets the same clock to read, which the resource monitor writes (images/monitor/rcb_monitor/monitor.py clock(): from the
# trial environment's start, so it never overstates the time left; `monitor.py beacon` where the monitor cannot run).
_LIMITS_CLOCK = "Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`)"
# A tool call that writes to a still-running process can return only when its wait is over, even when the answer is
# printed at once (one recorded trial lost ~98 min of a 3 h budget that way): harness-neutral advice, no duration in it.
_LIMITS_WAITS = " A call into a long-running process can block for its whole wait time. Use short waits or one-shot scripts."
LIMITS_TIME = {   # mode -> (what counts and what is graded at the end, the service's own count of the limit)
    "privileged": ("Everything counts, including the simulator's start-up. At the end you are stopped without warning and "
                   "only what is in `/app/output/` at that moment is graded.", ""),
    "standard": ("Everything counts, including waiting for the service. At the end you are stopped without warning and "
                 "the episode is graded as it stands.", ". Trust this file: the `time_left_s` in the service's replies "
                 "starts only at your first request"),
}
LIMITS_TIME["realtime"] = LIMITS_TIME["standard"]
assert set(MODE_REGISTRY) <= set(LIMITS_TIME), "every mode of MODE_REGISTRY needs its LIMITS_TIME (PROTOCOL §5)"
LIMITS_TIME_OWN = {("RoboDojo", "standard"): (   # agent-ended, judged per task (V2_AGENT_END_*): Goal says how
    "Everything counts, including waiting for the service. At the end you are stopped without warning and the episode "
    "ends.", LIMITS_TIME["standard"][1]), ("roboEngineer", "standard"): (
    "Everything counts, including waiting for the deployment service and the deployments. At the end you are stopped "
    "without warning. The evaluator then takes the round you sealed; if you sealed none, it takes the latest deployment "
    "that finished before then. A deployment still running is not graded.", ". The service's own deadline counts the "
    "same limit from your first request to it")}
LIMITS_TIME_TASK = ("Everything counts, including waiting for the service. At the end you are stopped without warning and "
                    "graded on the state at that moment, as Goal says.", ". The clocks the service reports are the game's "
                    "own")
LIMITS_NETWORK = ("your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install "
                  "packages and read anything in your container{readable}.")   # the no-cheating rule: Goal (V2_RULE_OWN)
LIMITS_READABLE = ", including the simulator's and the benchmark's source"
LIMITS_NETWORK_OPEN = ("open. You may install packages and search for, download and use public tools, robot models and "
                       "pretrained controllers (say in your notes what you used); you may read anything in your "
                       "container, the benchmark's source included.")   # the no-cheating rule: Goal (V2_RULE_OWN)
# rendered words a task's own Limits line may still carry from an earlier render (old -> new)
LIMITS_RETIRED = {
    "open. You may install packages and search for, download and use public tools, robot models and pretrained "
    "controllers (say in your notes what you used); you may read anything in your container, the benchmark's source "
    "included. Do not look up an existing solution to this exact task, such as the benchmark's reference solutions; "
    "trials are reviewed.": LIMITS_NETWORK_OPEN,
    "open. You may install packages and search for, download and use public tools, robot models and pretrained "
    "controllers (say in your notes what you used). You may read anything in your container, including the benchmark's "
    "source. Do not look up an existing solution to this exact task, such as the benchmark's reference solutions. "
    "Trials are reviewed.": LIMITS_NETWORK_OPEN,
    "none: one episode.": "none. You get one episode.",
    # owner 11-27: no double colon in a Resets line
    "none: one match.": "none. You get one match.",
    "none: one bout.": "none. You get one bout.",
    "none: one game.": "none. You get one game.",
    "none: deployments are your only runs, each starting its development cases afresh.":
        "none. Deployments are your only runs, each starting its development cases afresh.",
}
LIMITS_STRICTER = " Additional rules for this task (stricter than the above): "
LIMITS_OVER_CAP = ("Going over a cap can get a process killed (the CPU cap only slows you down). Usage: "
                   "`/run/rcb-limits/usage.json`.")


# The fixed wording of the v2 skeleton (TEMPLATE: Task's mode line, Goal's graded-state sentence, the hand-in line and the
# rules blocks): the benchmarks' text generators use these words, never
# their own (a task with the MCP tools: `<mode>+mcp`, _v2_route). `{deliverable}`: what a privileged task hands in ("a trajectory of robot actions").
V2_MODE_LINE = {
    "privileged": "You have the full simulator to develop with; you hand in {deliverable}.",
    "standard": ("The robot runs as a service you reach only through its client, as if it were real hardware: one live "
                 "episode."),
    "realtime": ("The robot runs as a service you reach only through its client, as if it were real hardware, on a clock "
                 "that does not stop while you think: one live episode."),
    # a standard or realtime task with the robot's MCP tools as well (efe_mcp_manifest; owner 11-25: the agent chooses)
    "standard+mcp": ("The robot runs as a service you reach through its client or its MCP tools, as if it were real "
                     "hardware: one live episode."),
    "realtime+mcp": ("The robot runs as a service you reach through its client or its MCP tools, as if it were real "
                     "hardware, on a clock that does not stop while you think: one live episode."),
}
# owner 11-24: the fixed grading words carry each rule once (what is graded and when, who ends the episode), no
# restatement. V2_FINAL_STATE is for a grader that judges the end state. An agent-ended episode closes its Goal with
# how it ends and what is judged (owner 11-25, board 0309 D216 / 0611 D1=B; RoboDojo:
# ci_checks/benchmarks/robodojo/advisory-end-judgement.py checks each task against rcb_robodojo.END_JUDGEMENT, whose
# "history" tasks say what counts as it happens).
V2_FINAL_STATE = {
    "privileged": "Your {deliverable} is replayed from the fixed start. What counts is the state after its last action.",
    "standard": "What counts is how things stand at the end of the episode.",
}
# owner 11-26: plain finish wording, said once in each section. Goal: after the Success sentence, one short paragraph,
# V2_AGENT_END_GOAL then V2_AGENT_END_STATE (a task judged on events, or on what counts as it happens, says only
# V2_AGENT_END_GOAL; a task that counts some steps as they happen and the rest at the end says V2_AGENT_END_REST
# instead of V2_AGENT_END_STATE). Robot Interface: one line for the endpoint (ROBOT_FINISH, rendered after the mode
# line). Limits: one Finish line (LIMITS_FINISH, rendered). Nowhere else.
V2_AGENT_END_GOAL = "When you are done, send `/finish` to end the episode and get it graded."
V2_AGENT_END_STATE = "Only the state at that point counts."
V2_AGENT_END_REST = "Everything else is judged on the state at that point."
# the latched wording of 11-24, retired with D216, and the finish wording retired on 11-26: no Goal may carry it
V2_AGENT_END_RETIRED = ("The episode succeeds if the goal is reached before it ends", "once done, stays counted",
                        "call finish (Limits)", "call finish (Robot Interface)", "ends when you call finish",
                        "if you never call finish", "The robot never tells you whether you have succeeded",
                        "Success is judged on how things stand when the episode ends",
                        "Everything else counts only as it stands at that point")
V2_RULES_HEAD = "Rules:"
V2_RULE_NO_RESET = "One episode, no reset: what you knock over stays knocked over."
V2_RULE_NO_PRIV = ("You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no "
                   "success signal.")
# the one anti-cheating rule (owner 11-24), first in Goal's rules (standard: the first bullet under "Rules:"; privileged:
# its "Rules:" paragraph); Limits' Network line says only what can be reached, read and installed
V2_RULE_OWN = NO_CHEATING


def _fill(t: str, first: str = "", rest: str = "") -> str:
    """`t` as one paragraph wrapped at 120 columns, never inside a code span."""
    import textwrap
    t = re.sub(r"`[^`]*`", lambda m: m.group(0).replace(" ", "\0"), " ".join(t.split()))
    return textwrap.fill(t, 120, initial_indent=first, subsequent_indent=rest, break_long_words=False,
                         break_on_hyphens=False).replace("\0", " ")


def _wrap_bullet(t: str) -> str:
    return _fill(t, "- ", "  ")


def skeleton_errors(text: str) -> list[str]:
    """What breaks the v2 skeleton (V2_SECTIONS): the title line, then exactly these H2s in this order (Others may be
    left out), nothing before the first of them but the title."""
    errs = []
    lines = (text or "").split("\n")
    if not lines or not lines[0].startswith("# "):
        errs.append("does not start with its `# ` title line")
    h2 = re.findall(r"(?m)^## (.+?)[ \t]*$", text or "")
    want = [h for h in V2_SECTIONS if h in h2 or h not in V2_OPTIONAL]
    if h2 != want:
        errs.append("its H2 sections are " + (", ".join(f"`{h}`" for h in h2) or "none") + "; the v2 skeleton is "
                    + ", ".join(f"`{h}`" for h in V2_SECTIONS) + " in this order (`Others` optional), nothing else")
    first = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))
    if any(l.strip() for l in lines[1:first]):
        errs.append("has text between the title and `## Task`")
    if re.search(r"(?m)^#{4,} ", text or ""):
        errs.append("has headings below H3")
    return errs


def section_match(text: str, name: str) -> "re.Match[str] | None":
    """The `## <name>` section of a markdown text (an instruction, a README): group(1) is its body, up to the next H2."""
    return re.search(rf"(?ms)^## {re.escape(name)}[ \t]*\n(.*?)(?=^## |\Z)", text or "")


def section(text: str, name: str) -> str | None:
    """The body of the `## <name>` section of a markdown text, None when it has none."""
    m = section_match(text, name)
    return m.group(1) if m else None


def service_block(compose: str, name: str) -> str:
    """The block of compose service `name` ("" when there is none, or no top-level services:), by the monitor
    injector's parser (images/monitor/rcb_monitor/inject.py)."""
    lines = (compose or "").splitlines(keepends=True)
    try:
        i, j = rcb_monitor_inject.services_span(lines)
    except ValueError:
        return ""
    return next(("".join(lines[k0:k1]) for n, k0, k1 in rcb_monitor_inject.service_blocks(lines, i, j) if n == name), "")


def limits_lines(text: str) -> list[tuple[str, str]]:
    """The bullets of an instruction's `## Limits`, as (label, text)."""
    body = section(text, LIMITS_HEADING[3:])
    out = []
    for b in re.split(r"(?m)^- ", body) if body is not None else []:
        b = " ".join(b.split())
        if not b:
            continue
        lab, _, rest = b.partition(": ")
        out.append((lab.strip(), rest.strip()))
    return out


def limits_time(task: Path, sec: int) -> str:
    mode, bench = mode_of(task), bench_of(task)
    a, b = LIMITS_TIME_OWN.get((bench, mode)) or LIMITS_TIME[mode]
    if task.name in RO_EXPORTED_TASKS:
        a, b = LIMITS_TIME_TASK
    if agent_end_of(task) and a in (LIMITS_TIME[mode][0], LIMITS_TIME_OWN.get((bench, mode), ("",))[0]):
        a = re.sub(r" At the end you are stopped without warning\b.*", " At the end you are stopped without warning.", a)
    return f"{sec} s of wall-clock time from the start of your session. {a} {_LIMITS_CLOCK}{b}.{_LIMITS_WAITS}"


def limits_network(task: Path, kept: str | None) -> str:
    if network_of(task) == "open":
        text = kept or LIMITS_NETWORK_OPEN
        text = text.split(LIMITS_STRICTER.strip())[0].strip()
        notes = " (say in your notes what you used)"
        text = next((new for old, new in LIMITS_RETIRED.items() if text in (old, old.replace(notes, ""))), text)
    else:
        text = LIMITS_NETWORK.format(readable=LIMITS_READABLE)
    stricter = (metadata_of(task).get("honour") or {}).get("stricter", "")
    if stricter:
        text = text.rstrip() + LIMITS_STRICTER + str(stricter).strip()
    return text


def limits_resources(task: Path) -> str:
    caps = task_caps(task)
    m = caps["main"]
    gpu = bool(m.get("gpu"))
    lim = rcb_monitor_inject.rcb_limits
    parts = []
    if m.get("cpus"):
        parts.append(f"{_num(m['cpus'])} CPU{'' if float(m['cpus']) == 1 else 's'}")
    if m.get("memory_gb"):
        parts.append(f"{_num(m['memory_gb'])} GiB memory")
    if m.get("pids"):
        parts.append(f"{int(m['pids'])} processes and threads")
    if m.get("disk_gb"):
        parts.append(f"{_num(m['disk_gb'])} GiB disk (new files under " + ", ".join(f"`{x}`" for x in lim.DISK_PATHS) + ")")
    if gpu:
        parts.append(f"one GPU ({_num(m['gpu_memory_gb'])} GiB of its memory)" if m.get("gpu_memory_gb") else "one GPU")
    else:
        parts.append("no GPU")
    text = ", ".join(parts) if parts else "no declared caps"
    side = sidecars_of(task) if mode_of(task) in SIDECAR_MODES else []
    if side == ["sim"] or (side and "sim" not in side and len(side) == 1):
        text += "; the simulator runs in its own container and does not count"
    elif side:
        rest = [n for n in side if n != "sim"]
        text += (f"; the simulator (`sim`) and {_paths(rest)} run in containers of their own and do not count"
                 if "sim" in side else f"; {_paths(side)} run in containers of their own and do not count")
    for n in [n for n in caps if n != "main" and rcb_monitor_inject.kind_of(mode_of(task), n) == "scope"]:
        c = caps[n]
        own = [f"{_num(c['cpus'])} CPU{'' if float(c['cpus']) == 1 else 's'}" if c.get("cpus") else None,
               f"{_num(c['memory_gb'])} GiB memory" if c.get("memory_gb") else None,
               f"one GPU ({_num(c['gpu_memory_gb'])} GiB of its memory)" if c.get("gpu") and c.get("gpu_memory_gb") else None]
        own = [x for x in own if x]
        text += f"; `{n}` runs in its own container" + (f" ({', '.join(own)})" if own else "")
    return text + ". " + LIMITS_OVER_CAP


def limits_resets(task: Path) -> str:
    """The default Resets line of a task whose own text writes none."""
    n = reset_budget_of(task)
    if n is None:
        return "as many as you like while you develop."
    if n == 0:
        return LIMITS_RETIRED["none: one episode."]
    return f"at most {n} (`spec()[\"budget\"][\"reset\"]`), each a new episode from the same starting state."


def _limits_reworded(label: str, v: str) -> str:
    """A task's own Limits line `v` with rendered words of an earlier render replaced (LIMITS_RETIRED) and, in a Steps
    line, the plain end of a step limit ("…, then the episode ends.", never "ends by itself")."""
    v = LIMITS_RETIRED.get(v, v)
    if label == "Steps":
        v = re.sub(r"^at most ([\d,]+) control steps \((.+?) gives what is left\); at the [\d,]+(?:st|nd|rd|th) the "
                   r"episode ends by itself\.$", lambda m: f"at most {m.group(1)} control steps, then the episode ends. "
                   f"{m.group(2)[0].upper() + m.group(2)[1:]} gives what is left.", v)
        v = re.sub(r"; at the [\d,]+(?:st|nd|rd|th) the episode ends by itself\.", ", then the episode ends.", v)
        v = v.replace(" ends by itself", " ends")
        # owner 11-27: every step or time limit in the one pattern "at most N control steps (...), then the episode
        # ends." / "at most N s of robot time, then the episode ends."
        v = re.sub(r"^(?:each|an|the) episode ends after ([\d,]+) control steps( \([^)]*\))?(?: as a failure)?\.",
                   lambda m: f"at most {int(m.group(1).replace(',', '')):,} control steps{m.group(2) or ''}, then the "
                             "episode ends.", v)
        v = re.sub(r"^(?:an attempt|each episode|an episode|the episode) ends after ([\d.,]+ (?:s|min|h) of (?:robot|"
                   r"simulated) time)\.", r"at most \1, then the episode ends.", v)
        v = re.sub(r"^at most ([\d,]+) steps, RoboDojo's own limit for this task, then the episode ends\. One step is ",
                   r"at most \1 control steps, then the episode ends. One control step is ", v)
        v = v.replace("Everything that lets simulated time pass uses steps:",
                      "Everything that lets simulated time pass uses control steps:")
    return v


def render_limits(task: Path, text: str = "") -> str:
    """instruction.md's `## Limits` (v2): Time (PROTOCOL §2, §5; left out when the task has no usable number), Tokens,
    Network (§5, H.6), Resources (§6), then the task's own lines of `text`'s `## Limits` (a default Resets line where it
    has none, and for an agent-ended task with a step limit, or a cap its service's environment sets, a default Steps
    line), and an agent-ended task's Finish line (limits_finish)."""
    have = limits_lines(text)
    kept = [(k, _limits_reworded(k, v)) for k, v in have if k not in LIMITS_RENDERED and k != "Finish"]   # Finish: rendered
    net = next((v for k, v in have if k == "Network"), None)
    out = []
    sec = cutoff_for(task)
    if sec is not None:
        out.append("Time: " + limits_time(task, sec))
    out.append("Tokens: " + LIMITS_TOKENS)
    out.append("Network: " + limits_network(task, net))
    out.append("Resources: " + limits_resources(task))
    labels = {k for k, _ in kept}
    if "Resets" not in labels:
        kept.insert(0, ("Resets", limits_resets(task)))
    ae = agent_end_of(task)
    if ae and ae.get("step_limit") and "Steps" not in labels:
        n = ae["step_limit"]
        kept.append(("Steps", f"at most {n:,} control steps, then the episode ends. `meta[\"steps_left\"]` gives "
                              "what is left."))
    elif ae and "Steps" not in labels:
        m = MAX_CONTROL_STEPS_RE.search(read_text(task / "environment/docker-compose.yaml") or "")
        if m:   # the service's own cap (RCB_MAX_CONTROL_STEPS), which the task's text does not state
            n = int(m.group(1))
            kept.append(("Steps", f"at most {n:,} control steps, then the episode ends."))
    if ae:
        kept.append(("Finish", limits_finish(task, next((v for k, v in kept if k == "Steps"), ""))))
    out += [f"{k}: {v}" for k, v in kept]
    return LIMITS_HEADING + "\n" + "\n".join(_wrap_bullet(x) for x in out) + "\n"


# the Finish line of an agent-ended task's `## Limits` (PROTOCOL §3; rendered; owner 11-26: one line): [a Steps line
# with a step limit or a cap that ends the episode (a technical cap or a runaway guard that "ends the episode at / after
# N control steps", even in a line that says there is no step budget: the cap ends and grades the episode too); no
# Steps line, or one with no step budget and no such cap; a reset budget (after the cap, a failure end too, /reset is
# still allowed and only the last episode is graded: standard_mode.md "Agent-ended episodes")]
LIMITS_FINISH = ("if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.",
                 "if you never send `/finish`, the episode is graded when your session ends.",
                 "if you never send `/finish`, the last episode is graded when your session ends.")
LIMITS_NO_STEP_BUDGET = re.compile(r"(?:there is )?(?:no step budget|unlimited|no (?:step )?limit)\b", re.I)
LIMITS_CAP_ENDS = re.compile(r"\bends the episode (?:at|after) [\d,]+ control steps\b")


def limits_finish(task: Path, steps: str) -> str:
    """The Finish line (LIMITS_FINISH) of an agent-ended task whose Limits' Steps line is `steps` ("": none)."""
    if reset_budget_of(task):
        return LIMITS_FINISH[2]
    no_cap = not steps or (LIMITS_NO_STEP_BUDGET.match(steps) and not LIMITS_CAP_ENDS.search(steps))
    return LIMITS_FINISH[1 if no_cap else 0]


# the endpoint's line in an agent-ended task's `## Robot Interface`, its own paragraph after the mode line (rendered):
# [client only, client and MCP tools]
ROBOT_FINISH = ("`POST /finish` (client `r.finish()`): ends the episode; it is graded right away.",
                "`POST /finish` (client `r.finish()`, MCP tool `finish`): ends the episode; it is graded right away.")
# earlier renders of that line (owner 11-27: it names the client's call too), dropped where they stand (_v2_finish)
ROBOT_FINISH_RETIRED = ("`POST /finish`: ends the episode; it is graded right away.",
                        "`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.")


def robot_finish(task: Path) -> str:
    """The finish line of an agent-ended task's `## Robot Interface` (ROBOT_FINISH): with the MCP tools where it has
    them (efe_mcp_manifest)."""
    return ROBOT_FINISH[1] if efe_mcp_manifest(task) else ROBOT_FINISH[0]


# a task with resets (a reset budget N > 0; Goal and `## Limits` state them): its mode line without "one live episode"
V2_MODE_LINE_RESETS = {m: t.replace(": one live episode.", ".") for m, t in V2_MODE_LINE.items() if m != "privileged"}


def _v2_episodes(task: Path, s: str) -> str:
    """`s` with the mode line that fits the task's reset budget (V2_MODE_LINE or V2_MODE_LINE_RESETS), however it was
    wrapped; the paragraph it stands in is wrapped again (one under a heading is left as it is)."""
    n = reset_budget_of(task)
    if n is None:
        return s
    for m, short in V2_MODE_LINE_RESETS.items():
        old, new = (V2_MODE_LINE[m], short) if n else (short, V2_MODE_LINE[m])
        if not n and V2_MODE_LINE[m] in " ".join(s.split()):
            continue
        pat = re.compile(r"\s+".join(re.escape(w) for w in old.split()) + (r"(?!\S)" if not n else ""))
        s = _sub_prose(s, pat, new, wrap_headed=False)
    return s


def efe_mcp_manifest(task: Path) -> dict | None:
    """The manifest of the task's MCP tool server (embodied_first_exam/standard/mcp/inject.py), None for a task without
    one (a privileged task; RoboEngineer and the matchlow matches keep only their own interface: inject.EXCEPTIONS)."""
    mode = mode_of(task)
    if mode not in ("standard", "realtime"):
        return None
    return efe_mcp_inject.manifest(task, bench_dir(task), mode, str(metadata_of(task).get("protocol") or ""),
                                   reset_budget_of(task))


def _v2_route(task: Path, s: str) -> str:
    """`s` with the mode line that names the task's routes to the robot: its client, and its MCP tools where it has
    them (V2_MODE_LINE `<mode>` / `<mode>+mcp`, each with or without "one live episode"), and `### MCP tools` after
    `### Client` there (inject.place_section)."""
    m = efe_mcp_manifest(task)
    for mode in ("standard", "realtime"):
        for full in (True, False):
            pick = V2_MODE_LINE if full else V2_MODE_LINE_RESETS
            old, new = (pick[mode], pick[mode + "+mcp"]) if m else (pick[mode + "+mcp"], pick[mode])
            s = _sub_prose(s, re.compile(r"\s+".join(re.escape(w) for w in old.split()) + r"(?!\S)"), new)
    return efe_mcp_inject.place_section(s, m)


def _sub_prose(s: str, pat: "re.Pattern", new: str, wrap_headed: bool = True) -> str:
    """`s` with `pat` replaced by `new` in each paragraph it occurs in; a prose paragraph is wrapped again (120), below
    the heading over it (wrap_headed=False: a paragraph that starts with a heading is only replaced)."""
    paras = re.split(r"(\n[ \t]*\n)", s)
    for i in range(0, len(paras), 2):
        if not pat.search(paras[i]):
            continue
        q = pat.sub(lambda _: new, paras[i])
        head = re.match(r"\n*(?:#[^\n]*\n)*", q).group(0)        # a heading over the paragraph stays as it is
        body = q[len(head):]
        if not body.strip() or re.match(r"\s*(- |\d+\. |\||```|#)", body.strip("\n")) \
                or re.search(r"(?m)^\s*(?:```|\|)", body) \
                or (not wrap_headed and q.lstrip("\n").startswith("#")):
            paras[i] = q
            continue
        paras[i] = head + _fill(body) + body[len(body.rstrip("\n")):]
    return "".join(paras)


def _v2_finish(task: Path, s: str) -> str:
    """`s` with the finish line of an agent-ended task's `## Robot Interface` (ROBOT_FINISH: client only, client and MCP
    tools, MCP tools only) as its own paragraph right after the paragraph with the mode line; an earlier copy of it is
    dropped first, and a task that is not agent-ended has none."""
    s = re.sub(r"(?m)^(?:" + "|".join(re.escape(x) for x in ROBOT_FINISH + ROBOT_FINISH_RETIRED)
               + r")[ \t]*\n(?:[ \t]*\n)?", "", s)
    if not agent_end_of(task):
        return s
    line = robot_finish(task)
    m = section_match(s, "Robot Interface")
    if not m:
        return s
    modes = {" ".join(v.split()) for d in (V2_MODE_LINE, V2_MODE_LINE_RESETS) for k, v in d.items() if k != "privileged"}
    paras = re.split(r"(\n[ \t]*\n)", m.group(1))
    for i in range(0, len(paras), 2):
        if any(x in " ".join(paras[i].split()) for x in modes):
            paras[i] = paras[i].rstrip("\n") + "\n\n" + line + ("\n" if paras[i].endswith("\n") else "")
            return s[:m.start(1)] + "".join(paras) + s[m.end(1):]
    return s


def _ws(t: str) -> str:
    """A regex for `t` with any run of white space between its words (a wrapped paragraph)."""
    return r"\s+".join(re.escape(w) for w in t.split())


# where a task's own text states its service's technical step cap outside a Steps line (PROTOCOL §3: the Limits' Steps
# line states how the episode ends on its own, and the Finish line names it): (pattern, Steps line) and what stays.
# A cap in the Resets line ("none: one episode, at most N control steps (...)"):
_CAP_IN_RESETS = re.compile(r"(?m)^- Resets:\s+none:\s+one\s+episode,\s+at\s+most\s+([\d,]+)\s+(control\s+steps\b[^\n]*"
                            r"(?:\n(?![ \t]*(?:- |\n|#))[^\n]*)*?)\.[ \t]*$")
# a sentence in Robot Interface ("There is no step budget: the one technical cap is `spec["max_control_steps"]`, ..."):
_CAP_SENTENCE = re.compile(r"\s*" + _ws('There is no step budget: the one technical cap is `spec["max_control_steps"]`,')
                           + r"\s+([\d,]+)\s+\(([^)]*)\),\s+" + _ws("at which the episode ends."))
# a list of the episode's other ends that closes with the cap ("The episode also ends ..., and after N control steps
# (...).")
_CAP_IN_ENDS = re.compile(_ws("The episode also ends") + r"\s+((?:[^.]|\.\d)+?),\s+and\s+after\s+([\d,]+)\s+control\s+steps\s+"
                          r"\(([^)]*)\)\.")


def _v2_steps(task: Path, s: str) -> str:
    """`s` with the technical step cap its own text states outside `## Limits` (or inside the Resets line) moved into a
    Steps line of `## Limits` (render_limits keeps it), for an agent-ended task without a step limit or a Steps line."""
    ae = agent_end_of(task)
    if not ae or ae.get("step_limit") or any(k == "Steps" for k, _ in limits_lines(s)):
        return s
    steps = None
    m = _CAP_IN_RESETS.search(s)
    if m:
        n, rest = int(m.group(1).replace(",", "")), " ".join(m.group(2).split())
        steps = f"at most {n:,} {rest}, then the episode ends."
        s = s[:m.start()] + "- Resets: " + LIMITS_RETIRED["none: one episode."] + s[m.end():]
    elif _CAP_SENTENCE.search(s):
        m = _CAP_SENTENCE.search(s)
        n = int(m.group(1).replace(",", ""))
        steps = f"at most {n:,} control steps ({' '.join(m.group(2).split())}), then the episode ends."
        s = _sub_prose(s, _CAP_SENTENCE, "")
    elif _CAP_IN_ENDS.search(s):
        m = _CAP_IN_ENDS.search(s)
        n, ends = int(m.group(2).replace(",", "")), " ".join(m.group(1).split())
        ends = " and ".join(ends.rsplit(", ", 1))
        steps = f"at most {n:,} control steps ({' '.join(m.group(3).split())}), then the episode ends."
        s = _sub_prose(s, _CAP_IN_ENDS, f"The episode also ends {ends}.")
    if steps is None:
        return s
    lim = section_match(s, LIMITS_HEADING[3:])
    if not lim:
        return s
    body = lim.group(1).rstrip("\n")
    return s[:lim.start(1)] + body + "\n- Steps: " + steps + "\n" + s[lim.end(1):]


def normalize_instruction(task: Path) -> None:
    """instruction.md (v2, V2_SECTIONS) with the mode line that fits its reset budget (_v2_episodes), its routes to the
    robot (_v2_route), an agent-ended task's finish line (_v2_finish) and its step cap in a Steps line (_v2_steps), and
    last its `## Limits` rendered (render_limits), replacing the one it had."""
    p = task / "instruction.md"
    if not p.is_file():
        return
    s = p.read_text(encoding="utf-8")
    s = _v2_steps(task, _v2_finish(task, _v2_route(task, _v2_episodes(task, s))))
    body = re.sub(rf"(?ms)^{re.escape(LIMITS_HEADING)}[ \t]*(?:\n.*?)?(?=^## |\Z)", "", s)
    write_if_changed(p, body.rstrip() + "\n\n" + render_limits(task, s))


# A base image a task builds itself when it cannot pull it: the task's Dockerfile (environment/, tests/, or a sidecar's
# under environment/) starts with the image's recipe between `# >>> images/<name>/Dockerfile` and
# `# <<< images/<name>/Dockerfile` (its first FROM names the stage, `... AS <name>-base`, and later stages are
# `FROM <name>-base`), and the compose service's `build.cache_from` names the prebuilt image. normalize writes the current
# images/<name>/Dockerfile into the block byte for byte: the build's cache keys are then the prebuilt image's, so a
# runner that can pull it takes its layers and any other runner builds the same recipe from public sources.
BASE_STAGE_RE = re.compile(r"(?ms)^# >>> (images/[A-Za-z0-9_.-]+/Dockerfile)\n.*?^# <<< \1\n")


def normalize_base_stages(task: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    for df in sorted(p for sub in ("environment", "tests") if (task / sub).is_dir() for p in (task / sub).rglob("Dockerfile")):
        s = read_text(df)
        if s is None or "# >>> images/" not in s:
            continue
        def block(m: "re.Match[str]") -> str:
            src = root / m.group(1)
            if not src.is_file():
                raise ValueError(f"{df}: base stage {m.group(1)}: no such file")
            body = src.read_text()
            return f"# >>> {m.group(1)}\n{body}{'' if body.endswith(chr(10)) else chr(10)}# <<< {m.group(1)}\n"
        write_if_changed(df, BASE_STAGE_RE.sub(block, s))


def normalize_test_sh(task: Path) -> None:
    p = task / "tests/test.sh"
    if not p.is_file():
        return
    lines = p.read_text().splitlines(keepends=True)
    cmds = [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")
            and not re.match(r"(set\s|mkdir\s+-p\s+/logs/verifier\s*$)", ln.strip())]
    if cmds and re.match(r"rm\s+-[rRf]+\s+/logs/verifier/\*", cmds[0]):
        return
    i = next((k for k, ln in enumerate(lines) if ln.strip() and not ln.lstrip().startswith("#")), len(lines))
    lines.insert(i, CLEAR_LOGS + "   # verdicts from an earlier run never survive (docs/protocol/README.md Appendix H.1)\n")
    write_if_changed(p, "".join(lines))


# ---------------------------------------------------------------------------------------------------------------------
def parse_readme(s: str) -> tuple[str, list[tuple[str, str]], list[tuple[str, str]]]:
    """(intro text, table rows, sections) of a README; understands both the old layouts and the standard one."""
    lines = s.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    sections: list[tuple[str, list[str]]] = [("", [])]
    in_details = False
    for ln in lines:
        m = re.match(r"^(##|###) (.+)$", ln)
        if m and m.group(1) == "##":
            in_details = m.group(2).strip() == "Details"
            sections.append((m.group(2).strip(), []))
        elif m and in_details:
            sections.append((m.group(2).strip(), []))
        else:
            sections[-1][1].append(ln)
    rows: list[tuple[str, str]] = []
    out: list[tuple[str, str]] = []
    intro = ""
    for title, body in sections:
        if title == RESOURCES_HEADING[3:]:   # rendered (readme_resources), never carried over
            continue
        text = "\n".join(body)
        body_rows, rest = [], []
        for ln in body:
            m = re.match(r"^\| ([^|]*?) \| (.*) \|$", ln)
            if m and m.group(1).strip() and set(m.group(1).strip()) != {"-"}:
                body_rows.append((m.group(1).strip(), m.group(2).strip()))
            elif ln.strip() in ("| | |", "|---|---|"):
                continue
            else:
                rest.append(ln)
        rest_text = "\n".join(rest).strip()
        if title in ("", "Task"):
            rows += body_rows
            intro = (intro + "\n\n" + rest_text).strip() if rest_text else intro
        elif title == "Details":
            rows += body_rows
            if rest_text:
                out.append(("Notes", rest_text))
        else:
            if body_rows and not rest_text:
                rows += body_rows
            else:
                out.append((title, text.strip()))
    return intro, rows, out


def image_of(task: Path) -> str:
    c = read_text(task / "environment/docker-compose.yaml") or ""
    m = re.search(r"""^\s*cache_from:\s*(?:\[\s*|\n\s*-\s*)["']?([^"',\]\s]+)""", c, re.M)
    if m:                       # the prebuilt image of a base stage the task builds when it cannot pull it (normalize_base_stages)
        return m.group(1)
    if mode_of(task) in SIDECAR_MODES:
        imgs = [i for i in re.findall(r"^\s*image:\s*(\S+)", c, re.M) if not re.search(r"/(?:eai|efe)-monitor[:@]|/efe:monitor-", i)]   # not the monitor's
        if imgs:
            return imgs[0]
        for sub in ("sim", "scorer"):   # a sidecar built from its own directory: the base image of its Dockerfile
            m = re.search(r"^FROM\s+(\S+)", read_text(task / "environment" / sub / "Dockerfile") or "", re.M)
            if m:
                return m.group(1)
    d = read_text(task / "environment/Dockerfile") or ""
    m = re.search(r"^FROM\s+(\S+)", d, re.M)
    return m.group(1) if m else ""


def default_difficulty(task: Path, rows: dict[str, str]) -> str:
    twin = base_of(task) + "-privileged"
    if mode_of(task) == "standard":
        return (f"Same scene, instance and success rule as `{twin}` (see its Difficulty). In standard mode the agent "
                "loses resets, privileged state and planning primitives: it sees camera images and proprioception only, "
                "acts through the client, and gets one episode, so it has to estimate the scene from images and "
                "recover from its own mistakes without starting over.")
    if task.name.startswith("dextoolbench_"):
        g = dtb_goals(task)
        ref = f" SimToolReal's pretrained policy reaches {g[0]}/{g[1]} goals here." if g else ""
        return ("Dexterous tool use: a KUKA iiwa 14 arm with a 22-DoF Sharpa HA4 hand (29 position-controlled joints) "
                "must carry the tool along DexToolBench's goal trajectory, every goal within 1.5 cm on all keypoints, "
                f"and success needs every goal.{ref}")
    if task.name.startswith("mujoco_playground_"):
        return ("MuJoCo Playground defines only a shaped RL reward; this task scores a binary success defined from it "
                f"({re.sub(r'^Playground has only a shaped RL reward(?: [(][^)]*[)])?; defined here[^:]*: ', '', rows.get('success', 'see Verification'))}), so a trajectory has to actually finish the manipulation "
                "rather than collect partial reward.")
    return "Not documented yet."


def render_readme(task: Path) -> str:
    meta = tomllib.loads((task / "task.toml").read_text())
    md, ag = meta.get("metadata", {}), meta.get("agent", {})
    old = read_text(task / "README.md") or ""
    intro, rows, sections = parse_readme(old)
    rows = [(k, v) for k, v in rows if k not in HEADER_KEYS and k.lower() not in DROP_ROWS]
    rowd = {k.lower(): v for k, v in rows}
    secd = {t: b for t, b in sections}
    mode = mode_of(task)
    twin = base_of(task) + ("-privileged" if mode in SIDECAR_MODES else "-standard")
    if mode not in SIDECAR_MODES and not task.with_name(twin).is_dir():   # a privileged twin of a realtime task
        twin = next((base_of(task) + f"-{m}" for m in SIDECAR_MODES if task.with_name(base_of(task) + f"-{m}").is_dir()),
                    twin)
    sd = seeds_of(md)
    seed = sd["default"]
    oracle = md.get("oracle", "")
    ev = md.get("oracle_evidence", "")
    head = [("Benchmark", bench_of(task) or "—"),
            ("Mode", mode + (f" (`{md['protocol']}`)" if mode in SIDECAR_MODES and md.get("protocol") else ""))]
    # a standard or realtime task has its privileged twin unless no_twin_reason() says why not (PROTOCOL §3), even
    # when it is rendered first (an exempted name whose twin still exists, e.g. before a removal lands, keeps it)
    no_twin = None if task.with_name(twin).is_dir() else no_twin_reason(task)
    head.append(("Twin", no_twin or (f"`{twin}`" if mode in SIDECAR_MODES or task.with_name(twin).is_dir()
                                     else "— (privileged only)")))
    head += [("Simulator / robot", f"`{md.get('simulator', '')}` / `{md.get('robot', '')}`"),
             ("Family / instance", f"`{md.get('family', '')}` / seed {seed}"
              + (f" (allowed seeds: {seeds_text(sd['allowed'])}; PROTOCOL §2)" if sd["allowed"] != [sd["default"]] else "")),
             ("Oracle", f"`{oracle}`" + (f" — {ev}" if ev else "") if oracle else "—"),
             ("Agent time budget", f"{int(float(ag.get('timeout_sec', 0)))} s; tokens: protocol default (docs/protocol/running.md \"Official runs\")")]
    rt = realtime_of(task)
    if rt is not None:
        head.append(("Real time", f"slowdown S = {slowdown_text(rt[0])} (the world runs at 1/S of real speed: one control "
                                  f"step every S x control_dt s of wall time; `{slowdown_var(task)}`'s default)"
                                  + (f"; reset budget {rt[1]} (`RCB_RESET_BUDGET`'s default)" if rt[1] is not None else "")
                                  + " (PROTOCOL §3)"))
    head.append(("Base image", f"`{image_of(task)}`"))
    used = set()
    task_text = intro or meta.get("task", {}).get("description", "")
    difficulty = secd.get("Difficulty") or default_difficulty(task, rowd)
    ref = secd.get("Reference solution")
    if not ref:
        ref = rowd.get("oracle", "")
        used.add("oracle")
    ver = secd.get("Verification")
    if not ver:
        parts = [rowd[k] for k in ("verification", "grading", "metric", "success") if k in rowd]
        ver = "\n\n".join(parts)
        used.update({"verification", "grading", "metric", "success"})
    ref = ref or "See `solution/`."
    ver = ver or "See `tests/grade.py`."
    extra_rows = [(k, v) for k, v in rows if k.lower() not in used]
    # (a task's history is not kept in its README: git log and the pull requests have it; docs describe the current state)
    extra_secs = [(t, b) for t, b in sections if t not in ("Difficulty", "Reference solution", "Verification", "Change Log") and b]
    out = [f"# {task.name}", "", "| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in head]
    out += ["", "## Task", task_text.strip(), "", "## Difficulty", difficulty.strip(), "",
            "## Reference solution", ref.strip(), "", "## Verification", ver.strip()]
    out += [""] + readme_resources(task, old)
    if extra_rows or extra_secs:
        out += ["", "## Details"]
        if extra_rows:
            out += ["| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in extra_rows]
        for t, b in extra_secs:
            out += ["", f"### {t}", b.strip()]
    s = "\n".join(out).rstrip() + "\n"
    return re.sub(r"\n{3,}", "\n\n", s)


# ---------------------------------------------------------------------------------------------------------------------
def seeds_of(md: dict) -> dict:
    """The task's seeds (PROTOCOL §2): `default` = `[metadata] instance_seed` (the one field that names it), else 0 (then 0 names the task's one frozen instance); from
    `[metadata.seeds]`, written only where they are not the defaults: `allowed` = [default] unless given (a list, a range
    `{from, to}` with both ends included, or "any"); `oracle` = the seeds the reference solution is for: the task's (else
    [default]) for an `oracle` of "full" or "partial", [] for "none"; `build` = "frozen" (every allowed seed a committed
    instance) unless the task says "runtime" (the task builds a seed's instance itself)."""
    given = md.get("seeds") if isinstance(md.get("seeds"), dict) else {}
    default = int(md.get("instance_seed", 0))
    allowed = given.get("allowed", [default])
    if isinstance(allowed, list):
        allowed = [int(x) for x in allowed]
    elif isinstance(allowed, dict):
        allowed = {"from": int(allowed["from"]), "to": int(allowed["to"])}
    if md.get("oracle") in ("full", "partial"):
        oracle = [int(x) for x in given.get("oracle", [])] or [default]
    else:                                  # (a task copied from a template with a reference solution keeps none of it)
        oracle = []
    return {"default": default, "allowed": allowed, "oracle": oracle, "build": given.get("build", "frozen")}


def seed_allowed(sd: dict, seed: int) -> bool:
    a = sd["allowed"]
    if a == "any":
        return True
    if isinstance(a, dict):
        return a["from"] <= seed <= a["to"]
    return seed in a


def seeds_text(allowed) -> str:
    """`allowed` as task.toml writes it: a list, `{ from = A, to = B }` or "any"."""
    if isinstance(allowed, dict):
        return f"{{ from = {allowed['from']}, to = {allowed['to']} }}"
    if isinstance(allowed, str):
        return f'"{allowed}"'
    return "[" + ", ".join(str(x) for x in allowed) + "]"


def seeds_nondefault(md: dict) -> dict:
    """The keys of `[metadata.seeds]` whose value is not what seeds_of() gives when the key is left out."""
    sd = seeds_of({k: v for k, v in md.items() if k != "seeds"})
    full = seeds_of(md)
    return {k: full[k] for k in ("allowed", "oracle", "build") if full[k] != sd[k]}


def normalize_seeds(task: Path) -> None:
    """The seeds (PROTOCOL §2): `instance_seed = <default>` in `[metadata]` (kept where it is, with its comment; else
    written before `expert_time_estimate_hours`), and a `[metadata.seeds]` table only with the keys that are not the
    defaults (`allowed`, `oracle`, `build`: seeds_nondefault); the values the task gives are kept."""
    p = task / "task.toml"
    s = p.read_text()
    md = tomllib.loads(s).get("metadata", {})
    sd, extra = seeds_of(md), seeds_nondefault(md)
    s = re.sub(r"(?ms)^\[metadata\.seeds\]\n.*?(?=^\[|\Z)", "", s)
    if re.search(r"(?m)^instance_seed = ", metadata_body(s)):
        s = metadata_sub(s, r"(?m)^instance_seed = -?\d+", f"instance_seed = {sd['default']}", count=1)
    else:
        s = metadata_insert(s, f"instance_seed = {sd['default']}\n")
    if extra:
        a, b = _metadata_span(s)
        block = ("[metadata.seeds]\n# the seeds a runner may draw from (a list, { from = A, to = B } or \"any\") and the ones the "
                 "reference solution\n# under solution/ is for, where they are not the default seed alone (docs/protocol/README.md §2)\n"
                 + "".join(f"{k} = " + (f'"{v}"' if k == "build" else seeds_text(v)) + "\n" for k, v in extra.items()))
        s = s[:b].rstrip("\n") + "\n\n" + block + ("\n" + s[b:] if b < len(s) else "")
    else:
        s = re.sub(r"\n{3,}(?=\[)", "\n\n", s)
    write_if_changed(p, s)


def committed_line(task: Path, key: str) -> str | None:
    """The `key = ...` line of the committed task of the same name (a task rendered into a scratch directory, or over
    the task in tasks/: what the task declared is kept): the repository's task dir's task.toml when that is
    another file and has the line, else the version committed at HEAD. None when neither has it."""
    rx = re.compile(rf"(?m)^{re.escape(key)} = .*\n")
    root = Path(__file__).resolve().parents[1]
    p = task_dir(task.name) / "task.toml"
    if p.is_file() and p.resolve() != (task / "task.toml").resolve():
        m = rx.search(read_text(p) or "")
        if m:
            return m.group(0)
    try:
        import subprocess
        r = subprocess.run(["git", "-C", str(root), "show", f"HEAD:{task_relpath(task.name)}/task.toml"], capture_output=True,
                           text=True, timeout=30)
        m = rx.search(r.stdout) if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        m = None
    return m.group(0) if m else None


def normalize_dynamics(task: Path) -> None:
    """`[metadata] dynamics` (static / dynamic; PROTOCOL §2) is the task's own declaration and is kept as written. A
    task.toml without it (a fresh render) gets the committed task's line back, right after `family`; a new task
    declares it itself (ci_checks/check-task-fields.sh warns when it is missing)."""
    p = task / "task.toml"
    s = p.read_text()
    if re.search(r"(?m)^dynamics = ", s):
        return
    line = committed_line(task, "dynamics")
    if line is None:
        return
    write_if_changed(p, metadata_insert(s, line, after="family"))


def realtime_of(task: Path) -> tuple[float, int | None] | None:
    """A realtime task's (slowdown S, reset budget) as its sim service starts by default: the `RCB_SLOWDOWN`
    and `RCB_RESET_BUDGET` defaults in environment/docker-compose.yaml (PROTOCOL §2). None: not a realtime task,
    or a service without `RCB_SLOWDOWN` (ci_checks/check-realtime.py fails one on the realtime layer)."""
    if mode_of(task) != "realtime":
        return None
    c = read_text(task / "environment/docker-compose.yaml") or ""
    m, r = SLOWDOWN_RE.search(c) or OWN_SLOWDOWN_RE.search(c), RESET_DECL_RE.search(c)
    if not m:
        return None
    return float(m.group(1)), (int(r.group(1) or r.group(2)) if r else None)


def slowdown_var(task: Path) -> str:
    """The setting S comes from: `RCB_SLOWDOWN`, or that of a benchmark's own service (PROTOCOL §3; Embodied Olympics
    `RO_SLOWDOWN`)."""
    c = read_text(task / "environment/docker-compose.yaml") or ""
    return "RCB_SLOWDOWN" if SLOWDOWN_RE.search(c) or not OWN_SLOWDOWN_RE.search(c) else "RO_SLOWDOWN"


def slowdown_text(S: float) -> str:
    return f"{S:g}"


# ---------------------------------------------------------------------------------------------------------------------
# PROTOCOL §2: the settings a task declares, and the effective configuration of a trial, recorded with every result
# so that results are ranked only within one comparable configuration (docs/protocol/running.md "Results"). Standard
# library only: scripts/write_task_results.py, scripts/dataset_manifest.py and a runner's scheduler read these.
PROTOCOL_VERSION = "3.0"                         # docs/protocol/README.md; the wire's name: EAI_STANDARD
EAI_STANDARD = f"eai-standard/{PROTOCOL_VERSION}"   # standard_mode.md: observe reads, submit (and hold chunks) move time, /finish


def metadata_of(task: Path) -> dict:
    return task_toml(task).get("metadata", {}) or {}


def network_of(task: Path) -> str:
    """The agent's egress the task declares, from Harbor's own field, `[agent] network_mode`: "open" for "public" (the
    author's choice, PROTOCOL Appendix H.6), else "allowlist" (the default: the model APIs and the package registries;
    ci_checks/check-verifier-isolation.sh fails a task whose [agent] is not on it)."""
    return "open" if (task_toml(task).get("agent") or {}).get("network_mode") == "public" else "allowlist"


def reset_budget_of(task: Path) -> int | None:
    """The reset budget N a standard-mode task declares (its sim service's `RCB_RESET_BUDGET` default, else 0: no
    reset); None for a mode without a sim service (privileged: resets are free)."""
    if not MODE_REGISTRY[mode_of(task)]["sidecar"]:
        return None
    m = RESET_DECL_RE.search(read_text(task / "environment/docker-compose.yaml") or "")
    return int(m.group(1) or m.group(2)) if m else 0


def slowdown_of(task: Path) -> float | None:
    """A realtime task's slowdown S, its sim service's default (realtime_of); None otherwise."""
    rt = realtime_of(task)
    return rt[0] if rt is not None else None


def validated_of(task: Path) -> bool:
    """Whether the task counts as validated (PROTOCOL §2, docs/protocol/running.md "Results"): `[metadata] validated` where the task
    declares it (e.g. after the human review of §4), else `oracle = "full"` (its reference solution scores 1 and `nop`
    0). A marker recorded with each result: validated and unvalidated tasks are ranked together."""
    md = metadata_of(task)
    if isinstance(md.get("validated"), bool):
        return md["validated"]
    return md.get("oracle") == "full"


# The core set (PROTOCOL §4, docs/protocol/running.md "Results"): the tasks the headline statistics are computed on, one
# central list, docs/core_set.toml, not a task field: listing a task changes none of its files, so its DIGEST and the
# results recorded against it stay as they are. One entry per task: `task`, the task dir name without its mode suffix
# (base_of()); every mode dir of a listed task is core.
CORE_SET_FILE = Path(os.environ.get("RCB_CORE_SET_FILE") or Path(__file__).resolve().parents[1] / "docs" / "core_set.toml")
# RCB_CORE_SET_FILE: tests only (scripts/tests: a summary test whose fixed tasks must not move with the list)
CORE_FIELDS = ("task",)


@functools.lru_cache(maxsize=8)
def _core_set(path: Path, mtime: int) -> frozenset[str]:
    d = tomllib.loads(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for e in d.get("task", []):
        t = e.get("task") if isinstance(e, dict) else None
        if not isinstance(t, str) or not t:
            raise ValueError(f"{path.name}: an entry without a task: {e!r}")
        if t in out:
            raise ValueError(f"{path.name}: {t} listed twice")
        out.add(t)
    return frozenset(out)


def core_set(path: Path = CORE_SET_FILE) -> frozenset[str]:
    """docs/core_set.toml as its set of tasks; empty when the file is absent. ValueError on a malformed file
    (ci_checks: `task_conventions.py core-set --check`). Parsed once per version of the file (its mtime), so a
    long-running reader sees an edited list."""
    try:
        mtime = path.stat().st_mtime_ns
    except FileNotFoundError:
        return frozenset()
    return _core_set(path, mtime)


def core_tasks(modes: "set[str] | None" = None, path: Path = CORE_SET_FILE, tasks_dir: Path | None = None,
               missing: "dict[str, list[str]] | None" = None) -> list[str]:
    """The task dirs of the core tasks: every mode dir of each core task; with modes, its dir of each of those modes
    (a task without that mode is skipped and added to missing[mode] when given)."""
    out = []
    for t in core_set(path):
        for m in sorted(modes) if modes else MODES:
            d = f"{t}-{m}"
            if not (task_dir(d, tasks_dir) / "task.toml").is_file():
                if modes and missing is not None:
                    missing.setdefault(m, []).append(t)
                continue
            out.append(d)
    return sorted(out)


def set_of(task: Path) -> str:
    """`core` when the task dir is a mode of a task listed in docs/core_set.toml, else `excluded`. A marker like
    `validated`, never part of config_key: the headline statistics count `core` tasks only. Recorded with each result
    as the value when it was written; reports re-derive it from the list at the commit they publish. A malformed list
    never stops a result from being written: a missing or malformed list gives a warning and `core`; `core-set --check`
    reports it."""
    try:
        cs = _core_set(CORE_SET_FILE, CORE_SET_FILE.stat().st_mtime_ns)
    except (ValueError, OSError) as e:                  # tomllib.TOMLDecodeError and UnicodeDecodeError are ValueErrors
        if str(e) not in _CORE_WARNED:
            _CORE_WARNED.add(str(e))
            print(f"WARN {CORE_SET_FILE.name}: {e} (every task counts as core; task_conventions.py core-set --check)",
                  file=sys.stderr)
        return "core"
    return "core" if base_of(Path(task)) in cs else "excluded"


_CORE_WARNED: set[str] = set()


README_FILE = Path(__file__).resolve().parents[1] / "README.md"
README_QUICK = re.compile(r"(<!-- quick-start: generated by `python3 scripts/task_conventions.py readme --write` -->\n)"
                          r"(.*?)(<!-- /quick-start -->)", re.S)


# The README's "Before you run" (readme_quick_start): per benchmark, what a user does by hand once and what its first run
# does (an image it builds itself: time, free disk, the licences the build accepts), from that benchmark's README, whose
# heading named here must exist (`readme --check`); "<file>#<heading>": a heading in that file (relative to the
# repository). A benchmark without a row needs nothing beyond the host requirements.
ISAAC = "accepts NVIDIA's Isaac Sim terms"
BEFORE_YOU_RUN = {
    "AM-Bench": ("Before you run", "", f"Builds its image ({ISAAC}): about 25 min, 60 GB free disk."),
    "BEHAVIOR-1K": ("Before you run",
                    "Download the BEHAVIOR dataset (its downloader asks you to accept the BEHAVIOR Data Bundle licence; "
                    "about 32 GB, 40 GB on disk) and export `RCB_BEHAVIOR_DATA`.",
                    f"Builds its image ({ISAAC}): about 20 min, 30 GB free disk."),
    "iSpatialGym": ("Before you run", "The BEHAVIOR-1K dataset, `RCB_BEHAVIOR_DATA` (the same directory).",
                    f"Builds its image ({ISAAC}): about 20 min, 31 GB free disk."),
    "LIBERO-MAX": ("Task definition", "A CPU with AVX-512 (Intel Ice Lake or newer Xeon, AMD Zen 4 or newer).", ""),
    "ManiGuard": ("Before you run",
                  "Prepare the data root `RCB_MANIGUARD_DATA` (3.4 GB; its key asks you to accept the BEHAVIOR Data "
                  "Bundle licence). NVIDIA driver 580.x: newer drivers crashed at start.",
                  f"Builds its image ({ISAAC}): about 20 min, 50 GB free disk."),
    "RoboARC": ("images/roboarc/README.md#Host",
                "NVIDIA driver 580 or newer, one GPU per container; knot_untying and rope_threading need a 24 GB GPU of "
                "their own.", ""),
    "RoboDojo": ("Before you run", "",
                 f"Builds its image with 41 GB of assets ({ISAAC} and cuRobo's): 30-90 min, 150 GB free disk."),
    "roboEngineer": ("Getting the images",
                     "Build the evaluator images with its scripts; the eight Neural Fly tasks also need the force fit made "
                     "locally (`fetch_assets.sh --fit-fly`).", ""),
    "RoboLab": ("Before you run", "", f"Builds its image ({ISAAC}): 20-60 min, 60 GB free disk."),
    "RoboWits": ("Getting the images",
                 "24 of its 30 tasks need BlenderKit models in `RCB_ROBOWITS_BLENDERKIT`: from the gated Hugging Face "
                 "dataset (accept its terms, `hf auth login`) or with your own BlenderKit Full Plan key.", ""),
    "VLABench": ("What you need before running", "", "Builds its image (CPU only): 5-20 min, 40 GB free disk."),
    "YAMLab": ("Before you run", "", f"Builds its image ({ISAAC}): about 25 min, 60 GB free disk."),
    "LabUtopia": ("Before you run", "",
                  f"Builds its image ({ISAAC}; LabUtopia's assets are CC BY-NC 4.0): about 25 min, 90 GB free disk."),
    "HumanCLAW": ("Before you run",
                  "Without access to the organization's packages: request access to the gated Hugging Face dataset "
                  "`HumanCLAW/HumanCLAW-HSSD`, accept the `hssd/hssd-hab` terms, export `HF_TOKEN` and build its "
                  "image once (HSSD is CC BY-NC 4.0; the body model and motion weights carry SMPL-X / AMASS research "
                  "terms): about 30 min, 40 GB free disk.", ""),
    "EmbodiedSWE": ("Before you run",
                    "Build its image from `images/embodiedswe/` (it accepts NVIDIA's Isaac Sim terms and the licences of "
                    "its assets, some CC BY-NC): 20-60 min, 60 GB free disk.", ""),
    "AutoBio": ("Before you run", "",
                "Builds its image from AutoBio's repository, which states no licence (CPU only): a few minutes, 3 GB free disk."),
}
# Benchmarks whose README asks for RT cores although their tasks set no `gpu_types` (RoboARC: its renderer Nyx).
RT_CORES_BY_README = {"RoboARC"}


def before_you_run_link(lab: str) -> tuple[str, str]:
    """A BEFORE_YOU_RUN row's file (relative to the repository) and heading."""
    head = BEFORE_YOU_RUN[lab][0]
    f, _, h = head.rpartition("#")
    return (f, h) if f else (f"tasks/{BENCHMARK_DIRS[lab]}/README.md", head)


def gh_anchor(heading: str) -> str:
    """GitHub's anchor of a Markdown heading: lower case, punctuation dropped, spaces as hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def check_before_you_run(tasks_dir: Path | None = None) -> list[str]:
    """What is wrong with BEFORE_YOU_RUN: a label that is not a benchmark, or a heading its README does not have."""
    tasks_dir = tasks_dir or TASKS_DIR
    bad = []
    for lab in BEFORE_YOU_RUN:
        if lab not in BENCHMARK_DIRS:
            bad.append(f"{lab}: not a benchmark label")
            continue
        f, head = before_you_run_link(lab)
        heads = {gh_anchor(m) for m in re.findall(r"^#+ (.+)$", read_text(tasks_dir.parent / f) or "", re.M)}
        if gh_anchor(head) not in heads:
            bad.append(f"{lab}: {f} has no heading {head!r}")
    return bad


def gpu_class_of(task: Path) -> str:
    """"rtx" (`[environment].gpu_types`: an RTX-class GPU), "any" (a compose service holds an NVIDIA GPU) or "none"."""
    if (task_toml(task).get("environment") or {}).get("gpu_types"):
        return "rtx"
    return "any" if any(c.get("gpu") for c in task_caps(task).values()) else "none"


def gpu_classes(tasks_dir: Path | None = None) -> dict[str, list[str]]:
    """The benchmarks by the GPUs their tasks hold (gpu_class_of): "rtx" (some task needs an RTX-class GPU), "any"
    (every task needs some NVIDIA GPU), "some" (some tasks do), "none" (no task does)."""
    need: dict[str, set] = {}
    for t in iter_tasks(tasks_dir or TASKS_DIR):
        need.setdefault(bench_of(t), set()).add(gpu_class_of(t))
    out: dict[str, list[str]] = {"rtx": [], "any": [], "some": [], "none": []}
    for lab, n in sorted(need.items(), key=lambda kv: kv[0].lower()):
        out["rtx" if "rtx" in n or lab in RT_CORES_BY_README else "none" if n == {"none"} else "some" if "none" in n else "any"].append(lab)
    return out


def readme_quick_start(tasks_dir: Path | None = None) -> str:
    """The README's header counts and quick start (core_tasks(), iter_tasks()): one command per line, its comment on
    the line above, so no line needs a horizontal scroll on GitHub."""
    tasks_dir = tasks_dir or TASKS_DIR
    dirs = iter_tasks(tasks_dir)
    core = len(core_set())
    core_dirs = len(core_tasks(tasks_dir=tasks_dir))
    per = {m: len(core_tasks({m}, tasks_dir=tasks_dir)) for m in MODES}
    bases = len({base_of(p) for p in dirs})
    benches = len({p.parent.name for p in dirs})
    arc = sum(1 for p in dirs if p.parent.name == "roboarc")
    paper = [p for p in dirs if p.parent.name != "humanclaw"]
    m = "-a codex -m openai/gpt-6-astra"
    d = "harbor run -d embodied-first-exam"

    def block(*lines: str) -> str:
        return "```bash\n" + "\n".join(lines) + "\n```\n"
    g = gpu_classes(tasks_dir)
    rows = []
    for lab, (_, hand, first) in sorted(BEFORE_YOU_RUN.items(), key=lambda kv: kv[0].lower()):
        f, head = before_you_run_link(lab)
        rows.append(f"| [{lab}]({f}#{gh_anchor(head)}) | {hand or '-'} | {first or '-'} |")
    return "\n".join([
        "### Before you run", "",
        "- **Host:** Linux x86_64 with git, [uv](https://docs.astral.sh/uv/) (it fetches a Python 3.12-3.14 for "
        "Harbor if needed) and Docker Engine with Compose v2 and BuildKit (the `buildx` plugin). Without Docker, e.g. on a Slurm cluster: rootless podman "
        "with `-e podman` ([docs/protocol/running.md](docs/protocol/running.md#without-docker-rootless-podman-eg-a-slurm-cluster)).",
        "- **GPU:** the NVIDIA driver and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/"
        "container-toolkit/latest/install-guide.html) for every task that uses a GPU. An RTX-class GPU (with RT cores; "
        f"not A100 or H100): {', '.join(g['rtx'])}. Any NVIDIA GPU: {', '.join(g['any'])}. Some tasks: "
        f"{', '.join(g['some'])}. No GPU: {', '.join(g['none'])}.",
        "- **Disk:** a benchmark's public images take 1-30 GB, pulled on its first run; a benchmark that builds its "
        "image needs the free disk its row below states.",
        "- **API keys** for the agent's model in `.env` (step 1), or a subscription (step 3).", "",
        "These benchmarks need a step by hand, or build their image on their first run because it may not be "
        "redistributed. Running that build means you accept the licences of what it installs; the linked section "
        "lists them. Organization members logged in to ghcr.io pull the prebuilt layers instead (on podman, after "
        "`podman login ghcr.io`, `harbor run -e podman` pulls the prebuilt image and uses it in place of the recipe; "
        "[docs/protocol/running.md](docs/protocol/running.md#without-docker-rootless-podman-eg-a-slurm-cluster)).", "",
        "| Benchmark | By hand, once | First run |", "|---|---|---|", *rows, "",
        "### 1. Install", "",
        block("# clone with the submodules; install Harbor 0.23.0 with this repository's flags",
              "git clone --recurse-submodules https://github.com/mll-lab-nu/embodied-first-exam.git",
              "cd embodied-first-exam",
              "uv tool install --force -e . --with-executables-from harbor",
              "# your API keys go in .env",
              "cp .env.example .env"),
        block("# or without a clone: install from PyPI (or pip install embodied-first-exam);",
              "# the tasks are cloned on first use; API keys: in the shell or a .env in the working directory",
              "uv tool install embodied-first-exam --with-executables-from harbor"),
        "### 2. Run", "",
        block(f"# the core set: {core} tasks in every mode they have ({core_dirs} task dirs)", f"{d} {m}"),
        block("# the core tasks in one mode: " + ", ".join(f"--{k} ({n} tasks)" for k, n in per.items()),
              f"{d} --privileged {m}"),
        block(f"# every task: {len(dirs)} task dirs ({bases} tasks in their modes, {benches} benchmarks); the paper and "
              f"leaderboard count {len({base_of(p) for p in paper})} tasks / {len(paper)} tests / "
              f"{len({p.parent.name for p in paper})} suites, without HumanCLAW", f"{d}@all {m}"),
        block(f"# one benchmark, here RoboARC ({arc} task dirs)", f"{d}@all -p tasks/roboarc {m}"),
        block("# one task (add -y to skip Harbor's confirmation prompt, e.g. in a script)",
              f"{d}@all -p tasks/<benchmark>/<task> -a oracle"),
        "### 3. Or use a subscription instead of an API key", "",
        block("# ChatGPT: log in once", "codex login", f"CODEX_FORCE_AUTH_JSON=1 {d} {m}"),
        block("# Claude: put the token it prints in .env as CLAUDE_CODE_OAUTH_TOKEN", "claude setup-token",
              f"CLAUDE_FORCE_OAUTH=1 {d} \\", "  -a claude-code -m anthropic/claude-opus-5-5"),
    ])


TAXONOMY_FILE = Path(__file__).resolve().parents[1] / "docs/TAXONOMY.md"
TAXONOMY_PROTOCOL_ROW = re.compile(r"(?m)^\| `protocol` \| .* \|$")
# what a protocol value adds to its row in docs/TAXONOMY.md (the benchmarks that serve it come from the tasks)
PROTOCOL_NOTES = {"eai-policy/1.0": "a benchmark's own runtime", "eai-policy/1.1": "a benchmark's own runtime"}


def taxonomy_protocol_row(tasks_dir: Path | None = None) -> str:
    """docs/TAXONOMY.md's `protocol` row, from the tasks: per sidecar mode, each value of `[metadata] protocol` and the
    benchmarks whose tasks declare it (BENCHMARK_TABLE order; "some tasks" where a benchmark's tasks of that mode
    declare more than one)."""
    use: dict = {}
    for t in iter_tasks(tasks_dir):
        m = mode_of(t)
        if m in SIDECAR_MODES:
            use.setdefault(m, {}).setdefault(str(metadata_of(t).get("protocol", "")), set()).add(bench_of(t))
    order = {lab: i for i, (_, lab, _) in enumerate(BENCHMARK_TABLE)}
    parts = []
    for m in SIDECAR_MODES:
        per = use.get(m, {})
        vals = []
        for proto in sorted(per, key=lambda p: (p.startswith("eai-standard/") is False, p)):
            benches = sorted(per[proto], key=lambda b: order.get(b, len(order)))
            names = [b + (" (some tasks)" if sum(b in bs for bs in per.values()) > 1 else "") for b in benches]
            note = PROTOCOL_NOTES.get(proto)
            vals.append(f"`{proto}` ({(note + ': ') if note else ''}{', '.join(names)})")
        parts.append(f"{m[0].upper() + m[1:]}: " + " · ".join(vals))
    return ("| `protocol` | standard and realtime modes only; the benchmarks that serve each value (generated: "
            "`python3 scripts/task_conventions.py taxonomy --write`). " + ". ".join(parts) + ". `eai-standard/3.0` is "
            "specified in [protocol/standard_mode.md](protocol/standard_mode.md) (a service's capabilities, such as "
            "operations, realtime or the match extension, are in its `/spec`); a benchmark's own runtime names its "
            "protocol (PROTOCOL §3) |")


def check_core_set(tasks_dir: Path | None = None, path: Path = CORE_SET_FILE) -> list[str]:
    """What is wrong with the core set: no file, an unknown top-level key or field, a task that is not a plain task name
    without a mode suffix, or a task with no task dir in any mode."""
    tasks_dir = tasks_dir or TASKS_DIR
    if not path.is_file():
        return [f"{path.name}: no such file"]
    try:
        cs = core_set(path)
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        return [str(e)]
    bad = []
    unknown = set(raw) - {"task"}
    if unknown:
        bad.append(f"{path.name}: unknown top-level key(s) {', '.join(sorted(unknown))}")
    for e in raw.get("task", []):
        u = set(e) - set(CORE_FIELDS)
        if u:
            bad.append(f"{e.get('task')}: unknown field(s) {', '.join(sorted(u))}")
    for t in sorted(cs):
        if t != Path(t).name or base_of(Path(t)) != t:
            bad.append(f"{t}: not a task name (a task dir name without its mode suffix)")
            continue
        if not any((task_dir(f"{t}-{m}", tasks_dir) / "task.toml").is_file() for m in MODES):
            bad.append(f"{t}: no task directory {t}-<mode> under tasks/")
    return bad


def effective_config(task: Path, seed: int | None = None, env: dict | None = None) -> dict:
    """The configuration a trial of `task` runs under: what the task declares, with the run-time overrides a runner
    passes in `env` (RCB_RESET_BUDGET, RCB_SLOWDOWN) and the seed it chose (None: the default seed). Recorded with each
    result (`config.json`); `config_key` groups comparable ones."""
    env = env or {}
    md = metadata_of(task)
    mode = mode_of(task)
    resets, S = reset_budget_of(task), slowdown_of(task)
    if resets is not None and str(env.get("RCB_RESET_BUDGET", "")).isdigit():
        resets = int(env["RCB_RESET_BUDGET"])
    if S is not None and env.get("RCB_SLOWDOWN"):
        try:
            S = float(env["RCB_SLOWDOWN"])
        except ValueError:
            pass
    dg = read_text(task / DIGEST_FILE)
    cfg = {"protocol_version": PROTOCOL_VERSION, "mode": mode, "cutoff_s": cutoff_for(task), "reset_budget": resets,
           "slowdown": S, "seed": seeds_of(md)["default"] if seed is None else int(seed), "network": network_of(task),
           "validated": validated_of(task), "set": set_of(task), "oracle": md.get("oracle", ""),
           "service_protocol": md.get("protocol", ""), "digest": (dg or "").strip()}
    if md.get("verifier_wall_clock"):   # the verifier plays a wall-clock match: its CPUs are part of the configuration
        cfg["verifier_cpus"] = verifier_cpus_of(task)
    return cfg


def verifier_cpus_of(task: Path) -> float | None:
    """The verifier's pinned CPUs ([verifier.environment] cpus) of a task
    whose verifier plays a live wall-clock match ([metadata] verifier_wall_clock; Embodied Olympics' privileged twins)."""
    try:
        return float(task_toml(task)["verifier"]["environment"]["cpus"])
    except (KeyError, TypeError, ValueError):
        return None


CONFIG_KEYS = ("protocol_version", "mode", "cutoff_s", "reset_budget", "slowdown", "network")


def config_key(cfg: dict) -> tuple:
    """What two results must share to be ranked together (the seed is drawn per trial and is not part of it, nor is the
    `validated` marker). Missing fields of a legacy record are "legacy"."""
    key = tuple(cfg.get(k, "legacy") if cfg.get(k, "legacy") is not None else "-" for k in CONFIG_KEYS)
    # a verifier that plays a wall-clock match: its pinned CPUs too (only such tasks record them; others are unchanged)
    return key + ((("verifier_cpus", cfg["verifier_cpus"]),) if cfg.get("verifier_cpus") is not None else ())


def config_label(cfg: dict) -> str:
    k = dict(zip(CONFIG_KEYS, config_key(cfg)))
    return (f"protocol {k['protocol_version']}, {k['mode']}, cutoff {k['cutoff_s']} s, resets {k['reset_budget']}, "
            f"S {k['slowdown']}, network {k['network']}")


def normalize(task: Path) -> None:
    task = Path(task)
    mode_of(task)
    if (task / "results").exists():
        shutil.rmtree(task / "results")
    normalize_toml(task)
    normalize_dynamics(task)
    normalize_cutoff(task)
    normalize_agent_end(task)
    normalize_resources(task)
    normalize_seeds(task)
    normalize_verifier_network(task)
    efe_mcp_inject.apply(task, efe_mcp_manifest(task))   # the robot's MCP tools: server files, Dockerfile, task.toml
    caps = rule_caps(task)
    rcb_monitor_inject.write_compose(task, caps)   # the caps first: the instruction and the README show them
    normalize_base_stages(task)
    normalize_instruction(task)
    normalize_test_sh(task)
    write_if_changed(task / "README.md", render_readme(task))
    rcb_monitor_inject.apply(task, caps)   # PROTOCOL §6: the resource monitor sidecar, the compose caps, the verifier step
    write_if_changed(task / DIGEST_FILE, digest(task) + "\n")   # last: the digest of everything above (PROTOCOL Appendix H.8)


# The digest Harbor publishes a task under (harbor.publisher.packager.Packager.compute_content_hash, Harbor 0.23.0):
# sha256 over "<relative path>\0<sha256 of the file>\n" of task.toml, instruction.md, README.md, trajectory.json and every
# file under environment/, tests/, solution/ and steps/, sorted by path, with Harbor's default ignores. DIGEST itself is
# not one of these files. ci_checks/check-dataset-manifest.sh recomputes it on its own and compares with DIGEST.
DIGEST_FILE = "DIGEST"
DIGEST_IGNORE_NAMES = ("*.pyc", ".DS_Store", "*.swp", "*.swo", "*~")


def digest(task: Path) -> str:
    task = Path(task)
    files = [task / n for n in ("task.toml", "instruction.md", "README.md", "trajectory.json") if (task / n).exists()]
    for sub in ("environment", "tests", "solution", "steps"):
        if (task / sub).exists():
            files += [p for p in (task / sub).rglob("*") if p.is_file()]
    rels = sorted({p.relative_to(task).as_posix() for p in files})
    rels = [r for r in rels if "__pycache__" not in Path(r).parts[:-1]
            and not any(fnmatch.fnmatchcase(Path(r).name, pat) for pat in DIGEST_IGNORE_NAMES)]
    outer = hashlib.sha256()
    for rel in rels:
        h = hashlib.sha256()
        with (task / rel).open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        outer.update(f"{rel}\0{h.hexdigest()}\n".encode())
    return "sha256:" + outer.hexdigest()


def snapshot(task: Path) -> dict[str, bytes]:
    return {str(p.relative_to(task)): p.read_bytes() for p in sorted(task.rglob("*")) if p.is_file()}


def main(argv: list[str]) -> int:
    if argv[:1] == ["modes"]:          # the mode registry for the shell checks (PROTOCOL §3)
        print(modes_table())
        return 0
    if argv[:1] == ["task-dir"]:       # `task-dir <name>...`: each task dir's path in this tree (task_dir), one per line
        for n in argv[1:]:
            print(task_dir(n))
        return 0
    if argv[:1] == ["benchmarks"]:     # `benchmarks --check`: every task dir has its label (BENCHMARKS); `benchmarks`: the labels
        if "--check" in argv:
            bad = check_benchmarks(TASKS_DIR)
            for b in bad:
                print(f"FAIL benchmark labels: {b}")
            if not bad:
                n = len(iter_tasks())
                print(f"ok benchmark labels: {n} task dirs, each with its label, in its benchmark's folder")
            return 1 if bad else 0
        for t in iter_tasks():
            print(f"{t.name}\t{bench_of(t)}\t{t.parent.name}")
        return 0
    if argv[:1] == ["readme"]:         # `readme --check` / `--write`: README.md's quick start (readme_quick_start())
        text = README_FILE.read_text(encoding="utf-8")
        q = README_QUICK.search(text)
        if not q:
            print("FAIL README.md: no quick-start markers"); return 1
        want_q = readme_quick_start()
        if "--write" in argv:
            README_FILE.write_text(text[:q.start(2)] + want_q + text[q.end(2):], encoding="utf-8"); return 0
        for b in check_before_you_run():
            print(f"FAIL README.md Before you run: {b}"); return 1
        if q.group(2) != want_q:
            print("FAIL README.md: the quick start is stale (python3 scripts/task_conventions.py readme --write)"); return 1
        print("ok README.md quick start"); return 0
    if argv[:1] == ["taxonomy"]:       # `taxonomy --check` / `--write`: docs/TAXONOMY.md's protocol row (taxonomy_protocol_row())
        text = TAXONOMY_FILE.read_text(encoding="utf-8")
        row, want = TAXONOMY_PROTOCOL_ROW.search(text), taxonomy_protocol_row()
        if not row:
            print("FAIL docs/TAXONOMY.md: no `protocol` row"); return 1
        if "--write" in argv:
            TAXONOMY_FILE.write_text(text[:row.start()] + want + text[row.end():], encoding="utf-8"); return 0
        if row.group(0) != want:
            print("FAIL docs/TAXONOMY.md: the protocol row is stale (python3 scripts/task_conventions.py taxonomy --write)"); return 1
        print("ok docs/TAXONOMY.md protocol row"); return 0
    if argv[:1] == ["core-set"]:       # `core-set --check`: docs/core_set.toml (PROTOCOL §4); `core-set [--<mode>...]`:
        if "--check" in argv:            # list the core tasks' dirs, or their dirs of those modes (core_tasks())
            bad = check_core_set()
            for b in bad:
                print(f"FAIL docs/core_set.toml: {b}")
            if not bad:
                per = {m: len(core_tasks({m})) for m in MODES}
                print(f"ok docs/core_set.toml: {len(core_set())} core tasks, {sum(per.values())} task dirs ("
                      + ", ".join(f"{m} {n}" for m, n in per.items()) + ")")
            return 1 if bad else 0
        for t in core_tasks({a[2:] for a in argv[1:] if a[2:] in MODES}):
            print(t)
        return 0
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    nodir = [a for a in args if not (Path(a) / "task.toml").is_file()]
    if not args or nodir:            # a typo, or no task at all, must not pass as nothing to normalize
        print("usage: task_conventions.py [--check] <task dir>...  (or modes | task-dir | benchmarks | readme | taxonomy | "
              "core-set)" + (f"; not a task directory: {', '.join(nodir)}" if nodir else ""), file=sys.stderr)
        return 2
    dirs = [Path(a) for a in args]
    bad = 0
    for d in dirs:
        if check:
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td) / d.name
                shutil.copytree(d, tmp, symlinks=True)
                for sib in d.resolve().parent.glob(base_of(d) + "-*"):   # the twin, read for the README's key table
                    if sib.name != d.name:
                        (Path(td) / sib.name).symlink_to(sib)
                normalize(tmp)
                if snapshot(tmp) != snapshot(d):
                    print(f"FAIL {d}: not normalized (run scripts/task_conventions.py {d})")
                    bad = 1
            txt = read_text(d / "instruction.md") or ""
            for e in skeleton_errors(txt):             # instructions v2 (V2_SECTIONS)
                print(f"FAIL {d}: instruction.md {e}")
                bad = 1
        else:
            normalize(d)
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
