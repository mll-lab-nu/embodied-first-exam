#!/usr/bin/env python3
"""The conventions of a task directory (docs/protocol/README.md), applied in place and idempotently.

A task's author ends with `normalize(task_dir)`, so a re-rendered task equals the committed one. It also rewrites a task
written to the fields the protocol's v2.1 text first named (`[metadata] network`, `mode`, `reset_budget`, `slowdown`,
`[metadata.seeds] default`, `[metadata.resources]`, the `## Resource limits` and `## Compute resources` sections) into
the current form; renaming directories is the caller's job.

    python3 scripts/task_conventions.py tasks/<benchmark>/<task> [...]     # normalize these tasks
    python3 scripts/task_conventions.py --check tasks/<benchmark>/<task>   # exit 1 if normalizing would change anything
    python3 scripts/task_conventions.py benchmarks [--check]   # every task dir's benchmark label (BENCHMARKS) and folder
    python3 scripts/task_conventions.py task-dir <task> ...    # where a task dir lives: tasks/<benchmark folder>/<task>

What it does:
- `task.toml`: no copies of what another source says (the mode, the reset budget, the slowdown S, the network: below),
  `oracle` (+ `oracle_evidence`) for benchmarks whose oracle level is known from their files.
- the words of the protocol (`eai-standard/2.x`, "standard mode", the documents under docs/protocol/) in the task's
  text files, also in files copied from an image source that still spells them otherwise (TEXT_REPLACEMENTS).
- `tests/test.sh` clears `/logs/verifier` first.
- no `results/` directory (results are published on the results site, not in the repository).
- the resource caps (docs/protocol/README.md §6), every one an upper bound for one container, from the task's rule in
  `scripts/task_resources.toml` (a task no rule matches keeps the caps its files have): main's in `[environment]`
  (`cpus`, `memory_mb`, `storage_mb`, and `gpu_types` for a task that needs an RTX-class GPU), every other service's and
  main's processes in `environment/docker-compose.yaml` (`cpus`, `mem_limit`, `pids_limit`, and `x-gpu-memory-gb` on
  the service that holds the GPU; images/monitor/rcb_monitor/inject.py writes them). No `[metadata.resources]`.
- `instruction.md` ends with `## External material` (§5: the same text in every task) and `## Resources`, the caps of
  the agent's own container, rendered from those.
- `[metadata] dynamics` (`dynamic` when something in the scene other than the robot does work by a force other than the
  robot's and gravity, else `static`) is the task's own declaration: kept as written; a re-render that lost it gets the
  committed task's line back (normalize_dynamics).
- from the agent's time cutoff (§2), the task's own `[agent] timeout_sec`: the standard modes' `RCB_WALL_CLOCK_S` in
  `environment/docker-compose.yaml`, the README's "Agent time budget" row and the last section of `instruction.md`,
  `## Time limit` (CUTOFF_SENTENCE, then what the cutoff means in the mode).
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

CLEAR_LOGS = "rm -rf /logs/verifier/*"
TEXT_SUFFIXES = {".md", ".toml", ".py", ".sh", ".yaml", ".yml", ".txt", ""}
TEXT_REPLACEMENTS = [  # (old, new), applied to task text files in order (a task's copy of an image source spelled otherwise)
    ("unlimited mode", "privileged mode"), ("Unlimited mode", "Privileged mode"), ("unlimited-mode", "privileged-mode"),
    ("rcb-limited/2.1", "eai-standard/2.1"), ("rcb-limited/2.0", "eai-standard/2.1"), ("rcb-limited/1.0", "eai-standard/2.1"),
    ("LIMITED MODE", "STANDARD MODE"), ("Limited-mode twin", "Standard-mode twin"), ("limited-mode twin", "standard-mode twin"),
    ("Limited-mode", "Standard-mode"), ("limited-mode", "standard-mode"), ("Limited mode", "Standard mode"),
    ("limited mode", "standard mode"), ("limited twin", "standard twin"), ("unlimited task", "privileged task"),
    ("unlimited oracle", "privileged-mode oracle"), ("unlimited expert", "privileged-mode expert"),
    *((f"docs/{old}.md", f"docs/protocol/{new}") for old, new in   # the protocol documents' folder
      (("PROTOCOL", "README.md"), ("STANDARD_MODE", "standard_mode.md"), ("RUNNING", "running.md"), ("LEAKAGE", "leakage.md"),
       ("rcb/PROTOCOL", "README.md"), ("rcb/STANDARD_MODE_2_2", "standard_mode.md"))),   # (rcb/: RoboARC's released texts)
]
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
# Modes (PROTOCOL §3): a benchmark ships any subset of the modes. A standard or standard-realtime
# task without a privileged twin says why in its README's Twin row ("— (none: ...)"), the task's own declaration:
# no_twin_reason() reads it back, so no list of such tasks is kept here.
# Embodied Olympics' exported tasks (PROTOCOL §3) have a cutoff note of their own (CUTOFF_NOTE_TASK below): the
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
                 "protocols": ("eai-standard/2.1", "eai-standard/2.2", "eai-standard/2.4"),
                 "twin": "privileged", "same_cutoff_as": "privileged"},   # one cutoff for both modes (Appendix H.7)
    "standard-realtime": {"short": "RT", "section": "§3", "sidecar": True, "limit_scope": "agent",
                          "protocols": ("eai-standard/2.3",), "twin": "privileged", "same_cutoff_as": None},
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
# PROTOCOL §2: a standard-realtime task's slowdown S is its sim service's `RCB_SLOWDOWN` default
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
RESOURCES_HEADING = "## Resources"
OLD_RESOURCES_HEADINGS = ("## Resource limits",)   # another name of the section (normalize replaces it)
# PROTOCOL §5: an honour rule, the same words in every task's instruction.md, just before `## Resources` (rendered
# by normalize: edit it here, never in a task;
# ci_checks/check-resources.py compares). Installing packages and reading whatever is installed in the container (the
# simulator's and the benchmark's own source included) are fine; searching the web for, or downloading, a ready-made
# solution to the task is not. No threat: trials are reviewed, the maintainers decide.
EXTERNAL_HEADING = "## External material"
EXTERNAL_TEXT = (
    "You may install packages you need (pip, apt), and you may read anything installed in your container, the "
    "simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web "
    "for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, "
    "or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and "
    "the package registries (PyPI, Debian / Ubuntu archives) only.")
# Open network (PROTOCOL §2, Appendix H.6): the task author's choice, declared as
# `[agent] network_mode = "public"` in task.toml (network_of). Such a task carries its own `## External material` paragraph (the author
# says what may be used); normalize keeps it, and writes EXTERNAL_TEXT_OPEN where it has none.
EXTERNAL_TEXT_OPEN = (
    "The network is open. You may install packages (pip, apt), and you may search for, download and use public tools, "
    "robot models and pretrained controllers: finding existing work and adapting it to this task is encouraged. Say in "
    "your notes what you used. You may read anything installed in your container, this benchmark's own source code "
    "included. The one thing not to look up is a ready-made solution to this exact task, such as this benchmark's "
    "reference solutions. This is an honour rule; trials are reviewed.")

# PROTOCOL §2, §5: the agent's time cutoff. Each task sets its own, in `[agent] timeout_sec` of its task.toml (its author
# decides it in the pull request that adds or changes the task), as in Terminal-Bench. There is no table: normalize
# writes from the task's own number the standard modes' RCB_WALL_CLOCK_S and the last section of instruction.md, `## Time
# limit`, the last thing the agent reads: CUTOFF_SENTENCE (one format in every task, Terminal-Bench's), then CUTOFF_NOTE,
# what the cutoff means in the task's mode. Rendered like the two sections before it: edit `timeout_sec` or these words
# here, never the section in a task (ci_checks/check-cutoffs.py).
CUTOFF_SENTENCE = ("You have {sec} seconds to complete this task. Do not cheat by using online solutions or hints specific "
                   "to this task.")
CUTOFF_RE = (r"You have (\d+) seconds to complete this task\. Do not cheat by using online solutions or hints specific "
             r"to this task\.")
CUTOFF_HEADING = "## Time limit"
CUTOFF_REF = "the time limit (`## Time limit`)"    # how a benchmark's own text names the limit: never a duration
_CUTOFF_CLOSE = " Installing packages is not cheating (`## External material` above)."
# Agents without a clock in their tool output guess their elapsed time 2-7 times too high and stop early, and a sentence
# asking for `date` is not enough: every agent gets the same clock to read, which the resource monitor shows
# (images/monitor/rcb_monitor/monitor.py clock(): from the trial environment's start, so it never overstates the time
# left; `monitor.py beacon` keeps it on runners that cannot run the monitor).
_CUTOFF_CLOCK = (" Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few "
                 "seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a "
                 "little before your session started, so it never gives you more time than you have: read it (or run "
                 "`date`) before you decide that time is short, never guess.")
# Agents that keep a simulator open as an interactive REPL send each command with Codex's
# write_stdin(yield_time_ms=30000); Codex 0.160.1 returns from a write to a still-running process only when the
# yield is over (196 of 196 such calls in one recorded RoboARC trial took 30.0 s; ~98 min of a 3 h budget), and has no
# config knob to cap it (background_terminal_max_timeout caps only empty polls). Harness-neutral advice, same text for
# every agent; no duration in it (ci_checks/check-cutoffs.py).
_CUTOFF_WAITS = (" Waiting counts too: a tool call that sends input to a process that keeps running (an interactive "
                 "interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for "
                 "example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short "
                 "wait and poll again if the output is not complete, or run one-shot scripts that exit when they are "
                 "done.")
CUTOFF_NOTE = {
    "privileged": ("This is wall-clock time from the start of your session; the time a simulator takes to start counts. "
                   "When it is up you are stopped without warning and only what is in `/app/output/` at that moment is "
                   "graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better "
                   "one." + _CUTOFF_CLOCK + _CUTOFF_WAITS + _CUTOFF_CLOSE),
    "standard": ("This is wall-clock time from the start of your session; the time you wait for the simulator service "
                 "counts. When it is up you are stopped without warning and the episode is graded as it stands at that "
                 "moment. The service's `time_left_s` counts the same limit from your first request to the service, so "
                 "it never runs out before your time does: your real time left is `time_left_s` minus the time you "
                 "spent before that request. Plan by it." + _CUTOFF_CLOCK + _CUTOFF_WAITS + _CUTOFF_CLOSE),
}
CUTOFF_NOTE["standard-realtime"] = CUTOFF_NOTE["standard"]
assert set(CUTOFF_NOTE) == set(MODE_REGISTRY), "every mode of MODE_REGISTRY needs its CUTOFF_NOTE (PROTOCOL §5)"
# A benchmark whose service counts the limit its own way has a note of its own (PROTOCOL §5).
CUTOFF_NOTE_OWN = {}   # (benchmark label, mode) -> its note
# roboEngineer: its own multi-round runtime (ci_checks/benchmarks/roboengineer/exported.toml) grades a deployed policy, not an
# episode that stands at the cutoff, and its service reports a deadline, not `time_left_s`
CUTOFF_NOTE_OWN[("roboEngineer", "standard")] = (
    "This is wall-clock time from the start of your session; the time you wait for the deployment service counts, "
    "deployments included. When it is up you are stopped without warning and the evaluator takes the round you sealed "
    "or, if you sealed none, the latest deployment that completed before that moment; a deployment still running then "
    "is not graded. The service's own deadline counts the same limit from your first request to it, so it never runs "
    "out before your time does." + _CUTOFF_CLOCK + _CUTOFF_WAITS + _CUTOFF_CLOSE)
# Embodied Olympics' exported tasks (PROTOCOL §3): their own service reports no `time_left_s` and does not read
# RCB_WALL_CLOCK_S (its clocks are the game's own), and a skill task has no episode
CUTOFF_NOTE_TASK = {n: (
    "This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When "
    "it is up you are stopped without warning and graded on what stands at that moment, as the sections above say. The "
    "service does not count this limit for you: the clocks it reports are the game's own." + _CUTOFF_CLOCK + _CUTOFF_WAITS + _CUTOFF_CLOSE)
    for n in RO_EXPORTED_TASKS}
CUTOFF_NOTE_START = "This is wall-clock time from the start of your session;"   # how an earlier note is recognised
WALL_CLOCK_ENV = "RCB_WALL_CLOCK_S"              # the standard modes' sim service: what its /spec budget and time_left_s report
CUTOFF_CAP = 14400                               # PROTOCOL §2, no benchmark excepted (ci_checks/check-cutoffs.py)
# The repository's task tree: one folder per benchmark, tasks/<folder>/<task>/ (a task dir's name says its benchmark,
# bench_of; at most FOLDER_MAX entries a folder). The folder of each label: BENCHMARK_TABLE's third column.
# Everything that finds a task dir in the repository goes through task_dir() / iter_tasks(); `benchmarks --check` holds
# the tree to it.
TASKS_DIR = Path(__file__).resolve().parents[1] / "tasks"
BENCHMARK_DIRS = {label: folder for _, label, folder in BENCHMARK_TABLE}


# ---------------------------------------------------------------------------------------------------------------------
def replace_words(s: str) -> str:
    """TEXT_REPLACEMENTS, each only where it does not continue a longer word (e.g. not inside "unlimited mode")."""
    for a, b in TEXT_REPLACEMENTS:
        s = re.sub(r"(?<![A-Za-z])" + re.escape(a), lambda _m, b=b: b, s)
    return s


# PROTOCOL §1, §3: each mode of MODE_REGISTRY is the whole suffix of its task directories. A mode is recognised by
# its complete suffix only, longest first: `-standard-realtime` is never `-standard` (it does not end in it).
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
    """The name without its mode suffix (`-privileged`, `-standard`, `-standard-realtime`, ...; PROTOCOL §1)."""
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
FOLDER_MAX = 5000                                 # entries of one benchmark folder at most (GitHub's web UI lists the
                                                  # first 1000; the rest are reached by path or the file finder)


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
            bad.append(f"tasks/{p.name}: {len(entries)} entries, over {FOLDER_MAX} (task_conventions.FOLDER_MAX)")
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
    # Copies of what another source says are not kept in [metadata]: the mode is the directory's suffix (mode_of), the
    # reset budget and the slowdown S the sim service's RCB_RESET_BUDGET and RCB_SLOWDOWN defaults (reset_budget_of,
    # slowdown_of), the agent's egress [agent] network_mode (network_of: an open task's `network = "open"` becomes
    # `network_mode = "public"` there)
    open_net = re.search(r'(?m)^network = "open"', metadata_body(s)) is not None
    s = metadata_sub(s, r'(?m)^(mode|reset_budget|slowdown) = .*\n', "")
    s = metadata_sub(s, r'(?m)^network = "(open|allowlist)".*\n', "")
    if open_net:
        s = set_open_egress(s, task.name)
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


OPEN_EGRESS_LINE = 'network_mode = "public"'
OPEN_EGRESS_COMMENT = "# open egress, the task author's choice (docs/protocol/README.md Appendix H.6)"


def set_open_egress(s: str, task_name: str = "") -> str:
    """An open task's [agent] egress: `network_mode = "public"` (Harbor's own field; network_of reads it), replacing
    the table's network policy lines (an `allowed_hosts` has no meaning there)."""
    m = re.search(r"(?m)^\[agent\]\n", s)
    if not m:
        raise RuntimeError(f"{task_name}: task.toml has no [agent] table")
    h = re.search(r"(?m)^\[", s[m.end():])
    b = m.end() + h.start() if h else len(s)
    body = re.sub(r"(?m)^(network_mode|allowed_hosts)\s*=.*\n", "", s[m.end():b])
    body = body.replace("Egress: open (Harbor's default), as `[metadata] network` declares.",
                        'Egress: open, `network_mode = "public"` below (the author\'s choice).')
    rest = body.rstrip("\n")
    body = (rest + "\n" if rest else "") + OPEN_EGRESS_LINE + " " * 8 + OPEN_EGRESS_COMMENT + "\n" + body[len(rest):].lstrip("\n")
    if not body.endswith("\n\n") and h:
        body += "\n"
    return s[:m.end()] + body + s[b:]


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
    the task's rule (PROTOCOL §6; the other services' and main's processes: inject.py, in the compose file). Removes the
    `[metadata.resources]` tables (resources are caps per container only: no minimums, soft limits or copies)."""
    p = task / "task.toml"
    s = p.read_text()
    s = re.sub(r"(?ms)^\[metadata\.resources(?:\.limits|\.caps)?\]\n.*?(?=^\[|\Z)", "", s)
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


RESOURCES_RULE = ("CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: "
                  "`/run/rcb-limits/usage.json`.")


def _and(xs: list[str]) -> str:
    return ", ".join(xs[:-1]) + " and " + xs[-1] if len(xs) > 1 else "".join(xs)


def render_resources(task: Path) -> str:
    """instruction.md's `## Resources` (PROTOCOL §6): the numbers of the agent's own container, as applied (task_caps),
    and of a service it drives, then RESOURCES_RULE. Who enforces what is PROTOCOL §6's, never repeated here."""
    caps = task_caps(task)
    m = caps["main"]
    gpu = bool(m.get("gpu"))
    lim = rcb_monitor_inject.rcb_limits
    parts = []
    if m.get("cpus"):
        parts.append(f"**{_num(m['cpus'])} CPUs**")
    if m.get("memory_gb"):
        parts.append(f"**{_num(m['memory_gb'])} GiB of memory**")
    if m.get("pids"):
        parts.append(f"**{int(m['pids'])} processes and threads**")
    if m.get("disk_gb"):
        parts.append(f"**{_num(m['disk_gb'])} GiB** of disk (new files under {_paths(lim.DISK_PATHS)})")
    if gpu and m.get("gpu_memory_gb"):
        parts.append(f"**one GPU, {_num(m['gpu_memory_gb'])} GiB of its memory**")
    elif gpu:
        parts.append("**one GPU**")
    text = "Your container: " + _and(parts) + "." if parts else "Your container has no declared caps."
    if not gpu:
        text += " Your container has no GPU."
    side = sidecars_of(task) if mode_of(task) in SIDECAR_MODES else []   # a standard task without a sim service (a
    # policy task, PROTOCOL §3) has no simulator to leave out
    if side == ["sim"] or (side and "sim" not in side and len(side) == 1):
        text += " The simulator runs in its own container and does not count against these."
    elif side:
        rest = [n for n in side if n != "sim"]
        text += (f" The simulator (`sim`) and {_paths(rest)} run in containers of their own and do not count against "
                 "these." if "sim" in side else f" {_paths(side)} run in containers of their own and do not count against these.")
    drive = [n for n in caps if n != "main" and rcb_monitor_inject.kind_of(mode_of(task), n) == "scope"]
    for n in drive:   # privileged: a service the agent drives runs in a container of its own, with caps of its own
        c = caps[n]
        own = [f"{_num(c['cpus'])} CPU{'' if float(c['cpus']) == 1 else 's'}" if c.get("cpus") else None,
               f"{_num(c['memory_gb'])} GiB of memory" if c.get("memory_gb") else None,
               f"{int(c['pids'])} processes and threads" if c.get("pids") else None,
               f"one GPU, {_num(c['gpu_memory_gb'])} GiB of its memory" if c.get("gpu") and c.get("gpu_memory_gb") else None]
        own = [x for x in own if x]
        text += f" `{n}` runs in its own container" + (f": {_and(own)}" if own else "") + "."
    text += " " + RESOURCES_RULE
    return RESOURCES_HEADING + "\n" + text + "\n"


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
        sec = re.search(rf"(?ms)^{re.escape(RESOURCES_HEADING)}\n(.*?)(?=^## |\Z)", old_readme or "")
        notes += [ln for ln in (sec.group(1).splitlines() if sec else [])
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


def external_paragraph(text: str) -> str | None:
    """The body of an instruction's `## External material` section (without the heading and a stricter-rules addition),
    or None."""
    m = re.search(rf"(?ms)^{re.escape(EXTERNAL_HEADING)}[ \t]*\n(.*?)(?=^## |\Z)", text or "")
    if not m:
        return None
    body = m.group(1).split("\n\nAdditional rules for this task (stricter than the above): ")[0].strip()
    return body or None


def render_external(task: "Path | str" = "") -> str:
    """instruction.md's `## External material` (PROTOCOL §5): the same words in every allowlist task (EXTERNAL_TEXT); a
    task with open egress (`[agent] network_mode = "public"`, network_of) keeps its own paragraph (EXTERNAL_TEXT_OPEN
    when it has none)."""
    text = EXTERNAL_TEXT
    if isinstance(task, Path) and network_of(task) == "open":
        text = external_paragraph(read_text(task / "instruction.md") or "") or EXTERNAL_TEXT_OPEN
    # the words above are the baseline every task carries; a task may add STRICTER requirements of
    # its own on top (never looser), as `[metadata.honour] stricter = "..."` in its task.toml, rendered after them
    stricter = ((metadata_of(task).get("honour") or {}).get("stricter", "")) if isinstance(task, Path) else ""
    if stricter:
        text = text.rstrip() + "\n\nAdditional rules for this task (stricter than the above): " + str(stricter).strip()
    return EXTERNAL_HEADING + "\n" + text + "\n"


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
    """Why a standard or standard-realtime task has no privileged twin `<base>-privileged` (PROTOCOL §3), as its
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


def render_cutoff(sec: int, mode: str, bench: str = "", name: str = "") -> str:
    """instruction.md's last section (PROTOCOL §5): the heading, the cutoff sentence, then what the cutoff means in
    the mode (`bench`, a BENCHMARKS label: a benchmark whose service counts on a clock of its own has its own note;
    `name`, the task directory's name: a task exported with its own service, CUTOFF_NOTE_TASK)."""
    note = CUTOFF_NOTE_TASK.get(name) or CUTOFF_NOTE_OWN.get((bench, mode), CUTOFF_NOTE[mode])
    return CUTOFF_HEADING + "\n" + CUTOFF_SENTENCE.format(sec=sec) + "\n\n" + note + "\n"


def strip_cutoff(s: str) -> str:
    """An instruction without the cutoff section, and without the cutoff sentence or note anywhere else in it (a
    second statement of the limit)."""
    s = re.sub(rf"(?ms)^{re.escape(CUTOFF_HEADING)}[ \t]*(?:\n.*?)?(?=^## |\Z)", "", s)
    s = re.sub(rf"(?m)^{CUTOFF_RE}[ \t]*\n(?:[ \t]*\n)*", "", s)
    return re.sub(rf"(?m)^{re.escape(CUTOFF_NOTE_START)}[^\n]*\n(?:[ \t]*\n)*", "", s)


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


def normalize_instruction(task: Path) -> None:
    """instruction.md ends with three sections normalize renders, each replacing an earlier one: `## External material`
    (PROTOCOL §5), `## Resources`, the caps of the agent's own container (§6, render_resources) and, last, `## Time
    limit` rendered from the task's `[agent] timeout_sec` (§2; left out when it has no usable number): the last thing
    the agent reads."""
    p = task / "instruction.md"
    if not p.is_file():
        return
    s = p.read_text(encoding="utf-8")
    sec = cutoff_for(task)
    if sec is not None:
        s = strip_cutoff(s)
    for heading in (EXTERNAL_HEADING, RESOURCES_HEADING, *OLD_RESOURCES_HEADINGS):
        s = re.sub(rf"(?ms)^{re.escape(heading)}[ \t]*(?:\n.*?)?(?=^## |\Z)", "", s)
    s = s.rstrip() + "\n\n" + render_external(task) + "\n" + render_resources(task)
    if sec is not None:
        s += "\n" + render_cutoff(sec, mode_of(task), bench_of(task), task.name)
    write_if_changed(p, s)


def _shared_sources() -> set[bytes]:
    """Contents of the files tasks copy unchanged from embodied_first_exam/standard/ (the eai-standard/2.2 layer, and the 2.4
    layer in v2_4/): their copies must stay byte-identical to the source (check-tooling-identity.sh), so normalize never
    rewrites them."""
    src = Path(__file__).resolve().parents[1] / "embodied_first_exam/standard"
    shared = {p.read_bytes() for p in src.rglob("*") if p.is_file() and "__pycache__" not in p.parts} if src.is_dir() else set()
    return shared | rcb_monitor_inject.generated_sources()     # the resource monitor's copies (images/monitor/rcb_monitor/)


def _is_layer_copy(f: Path) -> bool:
    """A copy of some version of embodied_first_exam/standard/rcb_limited.py or v2_4/rcb_limited.py (its PROTOCOL line and COMPAT
    list): a benchmark's tasks keep the version they were rendered with until they are rendered again."""
    t = read_text(f) or ""
    return bool(re.search(r'(?m)^PROTOCOL = "eai-standard/2\.\d"', t)) and bool(re.search(r"(?m)^COMPAT = \[", t))


def normalize_text_files(task: Path) -> None:
    shared = _shared_sources()
    for f in sorted(task.rglob("*")):
        if not f.is_file() or f.suffix not in TEXT_SUFFIXES or f.name in ("task.toml", "README.md") or f.stat().st_size > 2_000_000:
            continue
        if f.read_bytes() in shared:
            continue
        if f.name == "rcb_limited.py" and _is_layer_copy(f):
            continue                    # an earlier version of the shared layer (a benchmark's tasks rendered with it):
                                        # never rewritten either (its COMPAT list names rcb-limited/2.x on purpose)
        s = read_text(f)
        if s is None:
            continue
        t = s
        t = replace_words(t)
        write_if_changed(f, t)


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
        if title in ("Compute resources", RESOURCES_HEADING[3:]):   # rendered (readme_resources), never carried over
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
    """The task's seeds (PROTOCOL §2): `default` = `[metadata] instance_seed` (the one field that names it; normalize
    moves a `[metadata.seeds] default` there), else 0 (then 0 names the task's one frozen instance); from
    `[metadata.seeds]`, written only where they are not the defaults: `allowed` = [default] unless given (a list, a range
    `{from, to}` with both ends included, or "any"); `oracle` = the seeds the reference solution is for: the task's (else
    [default]) for an `oracle` of "full" or "partial", [] for "none"; `build` = "frozen" (every allowed seed a committed
    instance) unless the task says "runtime" (the task builds a seed's instance itself)."""
    given = md.get("seeds") if isinstance(md.get("seeds"), dict) else {}
    default = int(md.get("instance_seed", given.get("default", 0)))
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
    """A standard-realtime task's (slowdown S, reset budget) as its sim service starts by default: the `RCB_SLOWDOWN`
    and `RCB_RESET_BUDGET` defaults in environment/docker-compose.yaml (PROTOCOL §2). None: not a standard-realtime task,
    or a service without `RCB_SLOWDOWN` (ci_checks/check-realtime.py fails a 2.3 one)."""
    if mode_of(task) != "standard-realtime":
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
PROTOCOL_VERSION = "2.1"                         # docs/protocol/README.md


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
    """A standard-realtime task's slowdown S, its sim service's default (realtime_of); None otherwise."""
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
# results recorded against it stay as they are. One entry per task: `task` (the task dir name without its mode suffix,
# base_of()) and `default_mode`, the mode `harbor run --core` runs; another mode of the same tasks can be forced.
CORE_SET_FILE = Path(os.environ.get("RCB_CORE_SET_FILE") or Path(__file__).resolve().parents[1] / "docs" / "core_set.toml")
# RCB_CORE_SET_FILE: tests only (scripts/tests: a summary test whose fixed tasks must not move with the list)
CORE_FIELDS = ("task", "default_mode")


@functools.lru_cache(maxsize=8)
def _core_set(path: Path, mtime: int) -> dict[str, str]:
    d = tomllib.loads(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for e in d.get("task", []):
        t = e.get("task") if isinstance(e, dict) else None
        if not isinstance(t, str) or not t:
            raise ValueError(f"{path.name}: an entry without a task: {e!r}")
        if t in out:
            raise ValueError(f"{path.name}: {t} listed twice")
        out[t] = str(e.get("default_mode") or "")
    return out


def core_set(path: Path = CORE_SET_FILE) -> dict[str, str]:
    """docs/core_set.toml as {task: default mode}; empty when the file is absent. ValueError on a malformed file
    (ci_checks: `task_conventions.py core-set --check`). Parsed once per version of the file (its mtime), so a
    long-running reader sees an edited list."""
    try:
        mtime = path.stat().st_mtime_ns
    except FileNotFoundError:
        return {}
    return dict(_core_set(path, mtime))


def core_tasks(modes: "set[str] | None" = None, path: Path = CORE_SET_FILE, tasks_dir: Path | None = None,
               missing: "dict[str, list[str]] | None" = None) -> list[str]:
    """The task dirs of the core tasks: no modes, each task's default_mode dir; with modes, each task's dir of each of
    those modes that exists (a task without that mode is skipped and added to missing[mode] when given)."""
    out = []
    for t, dm in core_set(path).items():
        for m in sorted(modes) if modes else [dm]:
            d = f"{t}-{m}"
            if modes and not (task_dir(d, tasks_dir) / "task.toml").is_file():
                if missing is not None:
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
    core = len(core_tasks(tasks_dir=tasks_dir))
    priv = len(core_tasks({"privileged"}, tasks_dir=tasks_dir))
    bases = len({base_of(p) for p in dirs})
    benches = len({p.parent.name for p in dirs})
    arc = sum(1 for p in dirs if p.parent.name == "roboarc")
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
        "redistributed. That build accepts the licences of what it installs on your behalf: read them in the linked "
        "section. Organization members logged in to ghcr.io pull the prebuilt layers instead (on podman, after "
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
        block(f"# the core set: {core} tasks, each in its default mode", f"{d} {m}"),
        block(f"# the core tasks in another mode: --privileged ({priv} tasks), --standard, --standard-realtime",
              f"{d} --privileged {m}"),
        block(f"# every task: {len(dirs)} task dirs ({bases} tasks in their modes, {benches} benchmarks)",
              f"{d}@all {m}"),
        block(f"# one benchmark, here RoboARC ({arc} task dirs)", f"{d}@all -p tasks/roboarc {m}"),
        block("# one task (-y skips Harbor's confirmation prompt, e.g. in a script)",
              f"{d}@all -p tasks/<benchmark>/<task> -a oracle"),
        "### 3. Or use a subscription instead of an API key", "",
        block("# ChatGPT: log in once", "codex login", f"CODEX_FORCE_AUTH_JSON=1 {d} {m}"),
        block("# Claude: put the token it prints in .env as CLAUDE_CODE_OAUTH_TOKEN", "claude setup-token",
              f"CLAUDE_FORCE_OAUTH=1 {d} \\", "  -a claude-code -m anthropic/claude-opus-5-5"),
    ])


TAXONOMY_FILE = Path(__file__).resolve().parents[1] / "docs/TAXONOMY.md"
TAXONOMY_PROTOCOL_ROW = re.compile(r"(?m)^\| `protocol` \| .* \|$")
# what a protocol value adds to its row in docs/TAXONOMY.md (the benchmarks that serve it come from the tasks)
PROTOCOL_NOTES = {"eai-standard/2.4": "the operations capability",
                  "eai-policy/1.0": "a benchmark's own runtime", "eai-policy/1.1": "a benchmark's own runtime",
                  "eai-standard-turn/1.0": "a benchmark's own runtime", "eai-standard-realtime/1.0": "a benchmark's own runtime"}


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
    return ("| `protocol` | standard and standard-realtime modes only; the benchmarks that serve each value (generated: "
            "`python3 scripts/task_conventions.py taxonomy --write`). " + ". ".join(parts) + ". The `eai-standard` "
            "versions are specified in [protocol/standard_mode.md](protocol/standard_mode.md); a benchmark's own runtime "
            "names its protocol (PROTOCOL §3) |")


def check_core_set(tasks_dir: Path | None = None, path: Path = CORE_SET_FILE) -> list[str]:
    """What is wrong with the core set: no file, an unknown top-level key or field, a task that is not a plain task name
    without a mode suffix, a default_mode that is not a mode, or no task dir of the task in its default_mode."""
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
    for t, dm in cs.items():
        if t != Path(t).name or base_of(Path(t)) != t:
            bad.append(f"{t}: not a task name (a task dir name without its mode suffix)")
            continue
        if dm not in MODES:
            bad.append(f"{t}: default_mode {dm!r} is not one of {', '.join(MODES)}")
            continue
        if not (task_dir(f"{t}-{dm}", tasks_dir) / "task.toml").is_file():
            bad.append(f"{t}: no task directory {t}-{dm} under tasks/")
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
    normalize_resources(task)
    normalize_seeds(task)
    normalize_verifier_network(task)
    caps = rule_caps(task)
    rcb_monitor_inject.write_compose(task, caps)   # the caps first: the instruction and the README show them
    normalize_text_files(task)
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
        if "--check" in argv:            # list the core tasks' default-mode dirs, or their dirs of those modes (core_tasks())
            bad = check_core_set()
            for b in bad:
                print(f"FAIL docs/core_set.toml: {b}")
            if not bad:
                print(f"ok docs/core_set.toml: {len(core_set())} core tasks")
            return 1 if bad else 0
        for t in core_tasks({a[2:] for a in argv[1:] if a[2:] in MODES}):
            print(t)
        return 0
    check = "--check" in argv
    dirs = [Path(a) for a in argv if a != "--check" and (Path(a) / "task.toml").is_file()]
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
        else:
            normalize(d)
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
