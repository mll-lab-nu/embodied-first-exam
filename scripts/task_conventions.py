#!/usr/bin/env python3
"""Protocol v1.0 conventions for a task directory (docs/PROTOCOL.md), applied in place and idempotently.

Every generator ends with `normalize(task_dir)`, so a re-generated task equals the committed one. It also migrates a
pre-v1.0 task (old field names, protocol spelling, README layout); renaming directories is the caller's job.

    python3 scripts/task_conventions.py tasks/<task> [...]     # normalize these tasks
    python3 scripts/task_conventions.py --check tasks/<task>   # exit 1 if normalizing would change anything

What it does:
- `task.toml`: `mode` from the directory suffix (`-privileged` / `-standard` / `-standard-realtime`), no `tier`, `protocol = "eai-standard/2.1"`
  for standard tasks (2.2 / 2.4 and standard-realtime tasks' `eai-standard/2.3` are set by their generators), `oracle` (+ `oracle_evidence`) for benchmarks whose oracle level is known from their files.
- protocol spelling `rcb-limited/2.x` -> `eai-standard/2.x` and "limited mode" -> "standard mode" in the task's text and
  services; the client accepts both spellings.
- `tests/test.sh` clears `/logs/verifier` first; graders write `success` (1/0) to `reward.txt` and only numbers to
  `reward.json`.
- no `results/` directory (results are published on the results site, not in the repository).
- `[metadata.resources]` (docs/PROTOCOL.md §2.9, minimum compute) and `[metadata.resources.limits]` (§2.10, the most a
  trial may use) from `scripts/task_resources.toml` when a rule there matches the task; a task no rule matches keeps the
  values its generator or author wrote.
- `[environment].memory_mb` = `[metadata.resources.caps].main.memory_gb` x 1024 (§2.10: Harbor writes main's kernel
  memory cap from it, and the cap sits above the limit so that the monitor sees a violation before the OOM killer).
- `instruction.md` ends with `## External material` (§2.11: the same text in every task) and `## Resource limits`, rendered
  from `[metadata.resources.limits]` (§2.10).
- the agent's time cutoff (§2.12) from `scripts/task_cutoffs.toml`, the one table: `[agent] timeout_sec`, the standard
  modes' `RCB_WALL_CLOCK_S` in `environment/docker-compose.yaml`, and the last section of `instruction.md`, `## Time
  limit` ("You have N seconds to complete this task. Do not cheat ...", then what the cutoff means in the mode).
- `README.md` in the standard layout (docs/PROTOCOL.md §2.1): title, key table, Task, Difficulty, Reference solution,
  Verification, Compute resources (rendered from `[metadata.resources]`), and Details for everything else.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rcb_monitor import inject as rcb_monitor_inject  # noqa: E402

CLIENT_ASSERT_OLD = 'assert str(self._spec.get("protocol", "")).startswith("rcb-limited/2."), self._spec.get("protocol")'
CLIENT_ASSERT_NEW = ('assert str(self._spec.get("protocol", "")).startswith(("eai-standard/2.", "rcb-limited/2.")), '
                     'self._spec.get("protocol")')
CLEAR_LOGS = "rm -rf /logs/verifier/*"
TEXT_SUFFIXES = {".md", ".toml", ".py", ".sh", ".yaml", ".yml", ".txt", ""}
TEXT_REPLACEMENTS = [  # (old, new), applied to task text files in order
    ("unlimited mode", "privileged mode"), ("Unlimited mode", "Privileged mode"), ("unlimited-mode", "privileged-mode"),
    ("rcb-limited/2.1", "eai-standard/2.1"), ("rcb-limited/2.0", "eai-standard/2.1"), ("rcb-limited/1.0", "eai-standard/2.1"),
    ("LIMITED MODE", "STANDARD MODE"), ("Limited-mode twin", "Standard-mode twin"), ("limited-mode twin", "standard-mode twin"),
    ("Limited-mode", "Standard-mode"), ("limited-mode", "standard-mode"), ("Limited mode", "Standard mode"),
    ("limited mode", "standard mode"), ("limited twin", "standard twin"), ("unlimited task", "privileged task"),
    ("unlimited oracle", "privileged-mode oracle"), ("unlimited expert", "privileged-mode expert"),
]
BENCHMARKS = [  # (directory prefix, label)
    ("robotwin_2_0_", "RoboTwin 2.0"), ("dextoolbench_", "DexToolBench"), ("mujoco_playground_", "MuJoCo Playground"),
    ("kinder-", "KinDER"), ("humanoidbench-", "HumanoidBench"),
    ("metaworldplus-", "MetaWorld+"),
    ("robowits-", "RoboWits"), ("robopaint-", "RoboPaint"), ("robolab-", "RoboLab"),
    ("behavior-", "BEHAVIOR-1K"), ("maniguard-", "ManiGuard"),
    ("molmospaces-", "MolmoSpaces"), ("myosuite-", "MyoSuite"), ("dexjoco-", "DexJoCo"),
    ("labutopia-", "LabUtopia"),
    ("autobio-", "AutoBio"),
    ("vlabench-", "VLABench"),
    ("robocasa-gr1-", "RoboCasa-GR1"),  # before "robocasa-": the first matching prefix wins
    ("robocasa-", "RoboCasa"), ("robocasa365-", "RoboCasa365"),
    ("libero-max-", "LIBERO-MAX"),
    ("robotangle-", "RoboTangle"),
    ("roboolympics-", "RoboOlympics"),
    ("bigym2-", "BiGym 2.0"),
    ("yamlab-", "YAMLab"),
    ("robodojo-", "RoboDojo"),
    ("robofunolympics-", "RoboFunOlympics"),
]
# Documented exceptions: tasks without a privileged twin (the same lists: ci_checks/check-instance-copies.sh NO_TWIN and
# STANDARD_ONLY). RoboOlympics (PROTOCOL §4b, owner 2026-10-08): standard-realtime only. RoboDojo's six tasks whose physics
# does not replay bit for bit (PROTOCOL §4.8 exception, owner 2026-10-11): standard only, graded by the live episode.
NO_TWIN = {"roboolympics-": "— (none: RoboOlympics is standard-realtime only, PROTOCOL §4b)",
           "robodojo-fold-clothes-i00-standard": "— (none: standard only, graded by the live episode; its physics does not replay bit for bit, PROTOCOL §4.8)",
           "robodojo-fold-clothes-random-i00-standard": "— (none: standard only, graded by the live episode; its physics does not replay bit for bit, PROTOCOL §4.8)",
           "robodojo-make-toast-random-i00-standard": "— (none: standard only, graded by the live episode; its physics does not replay bit for bit, PROTOCOL §4.8)",
           "robodojo-pour-by-language-i00-standard": "— (none: standard only, graded by the live episode; its physics does not replay bit for bit, PROTOCOL §4.8)",
           "robodojo-pour-liquid-into-cup-i00-standard": "— (none: standard only, graded by the live episode; its physics does not replay bit for bit, PROTOCOL §4.8)",
           "robodojo-pour-liquid-into-cup-random-i00-standard": "— (none: standard only, graded by the live episode; its physics does not replay bit for bit, PROTOCOL §4.8)"}
HEADER_KEYS = {"Benchmark", "Mode", "Twin", "Simulator / robot", "Family / instance", "Oracle", "Agent time budget",
               "Base image"}
DROP_ROWS = {"simulator / robot", "family / instance", "base image", "agent budget", "task type / tier", "tier / mode",
             "task type / mode"}
CORE = ["Task", "Difficulty", "Reference solution", "Verification"]
# PROTOCOL §2.9: the minimum compute a task needs, `[metadata.resources]` in task.toml (same list: ci_checks/check-resources.py)
RESOURCES_FILE = Path(__file__).resolve().parent / "task_resources.toml"
RESOURCE_KEYS = {  # key -> type; recommended_gpu is optional when gpu_required is false
    "min_cpus": float, "min_memory_gb": float, "min_gpu_memory_gb": float, "gpu_required": bool, "gpu_class": str,
    "recommended_gpu": str, "verifier_min_cpus": float, "verifier_min_memory_gb": float,
    "verifier_min_gpu_memory_gb": float, "measured": str,
}
# PROTOCOL §2.10: the most a trial may use in the agent phase, `[metadata.resources.limits]` (same list: check-resources.py)
LIMIT_KEYS = {  # key -> type (sizes in GiB)
    "scope": str, "max_gpu_memory_gb": float, "max_memory_gb": float, "max_processes": int, "max_disk_gb": float,
    "disk_paths": list, "disk_exclude": list, "sustain_sec": float, "window_sec": float,
    "trial_max_gpu_memory_gb": float, "trial_max_memory_gb": float, "measured": str,
}
CAP_KEYS = {"cpus": float, "memory_gb": float, "pids": int}   # [metadata.resources.caps] per compose service (§2.10)
ENFORCE_ENV = "RCB_LIMITS_ENFORCE"   # §2.10: run-time switch (compose default 0 = record only; 1 = a violation fails)
EMERGENCY_GPU_FACTOR = 1.5           # §2.10: host protection in enforced runs (the same value: rcb_monitor/monitor.py)
LIMIT_SCOPES = {"privileged": "trial", "standard": "agent", "standard-realtime": "agent"}   # §2.10: who the limits bind
LIMITS_HEADING = "## Resource limits"
# PROTOCOL §2.11 (owner, 2026-10-11, board 0072): an honour rule, the same words in every task's instruction.md, just
# before `## Resource limits` (generator-owned: edit it here, never in a task; ci_checks/check-resources.py compares).
# Installing packages is fine; looking the task's solution up is not. No threat: trials are reviewed, the owner decides.
EXTERNAL_HEADING = "## External material"
EXTERNAL_TEXT = (
    "You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution "
    "to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or "
    "policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the "
    "package registries (PyPI, Debian / Ubuntu archives) only.")
# Documented per-benchmark exception (PROTOCOL §2.11; the same prefixes: ci_checks/check-verifier-isolation.sh OPEN_EGRESS):
# the agent's egress is open and finding existing tools and controllers is part of the task. RoboFunOlympics (owner,
# 2026-10-11): single-humanoid sports, where a public walking, jumping or whole-body controller is fair equipment.
EXTERNAL_OPEN = {
    "robofunolympics-": (
        "The network is open. You may install packages (pip, apt), and you may search for, download and use public tools, "
        "robot models and pretrained controllers (for example a published Unitree G1 walking, jumping or whole-body "
        "policy): finding existing work and adapting it to this robot is encouraged. Say in your notes what you used. "
        "The one thing not to look up is a solution to this exact task: this benchmark's own source code and reference "
        "solutions. This is an honour rule; trials are reviewed."),
}

# PROTOCOL §2.12 (owner, 2026-10-11 / 12, board 0080): the agent's time cutoff. One table, scripts/task_cutoffs.toml
# (seconds per benchmark and mode, with optional exceptions per family and per task), from which normalize writes
# `[agent] timeout_sec`, the standard modes' RCB_WALL_CLOCK_S and the last section of every instruction.md, `## Time
# limit`, the last thing the agent reads (owner: at the end, where Terminal-Bench has it): CUTOFF_SENTENCE (one format in
# every task, Terminal-Bench's), then CUTOFF_NOTE, what the cutoff means in the task's mode. Generator-owned like the
# two sections before it: edit the table or these words here, never in a task (ci_checks/check-cutoffs.py compares).
CUTOFFS_FILE = Path(os.environ.get("RCB_CUTOFFS_FILE") or Path(__file__).resolve().parent / "task_cutoffs.toml")
#   (RCB_CUTOFFS_FILE: another table, for a dry run of a change: tests and what-if renders only)
CUTOFF_SENTENCE = ("You have {sec} seconds to complete this task. Do not cheat by using online solutions or hints specific "
                   "to this task.")
CUTOFF_RE = (r"You have (\d+) seconds to complete this task\. Do not cheat by using online solutions or hints specific "
             r"to this task\.")
CUTOFF_HEADING = "## Time limit"
CUTOFF_REF = "the time limit (`## Time limit`)"    # how a benchmark's own text names the limit: never a duration
_CUTOFF_CLOSE = " Installing packages is not cheating (`## External material` above)."
# owner 2026-10-13 (board 0086): agents without a clock in their tool output guessed their elapsed time 2-7 times too
# high and stopped early; every agent gets the same way to know it (a command, not a guess).
_CUTOFF_CLOCK = (" Your session started when you received this task: run `date` now, and again before you decide that time "
                 "is short; work out the time left from those readings, never from a guess.")
CUTOFF_NOTE = {
    "privileged": ("This is wall-clock time from the start of your session; the time a simulator takes to start counts. "
                   "When it is up you are stopped without warning and only what is in `/app/output/` at that moment is "
                   "graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better "
                   "one." + _CUTOFF_CLOCK + _CUTOFF_CLOSE),
    "standard": ("This is wall-clock time from the start of your session; the time you wait for the simulator service "
                 "counts. When it is up you are stopped without warning and the episode is graded as it stands at that "
                 "moment. The service's `time_left_s` counts the same limit from your first request to the service, so "
                 "it never runs out before your time does: your real time left is `time_left_s` minus the time you "
                 "spent before that request. Plan by it." + _CUTOFF_CLOCK + _CUTOFF_CLOSE),
}
CUTOFF_NOTE["standard-realtime"] = CUTOFF_NOTE["standard"]
# A benchmark whose service does not count from the agent's first request keeps the earlier, weaker sentence, and its own
# text says what its service counts (PROTOCOL §2.12). RoboTangle: its service ends the episode on a clock started with
# the service, until its next task update (docs/benchmarks/robotangle.md, "To do").
_CUTOFF_NOTE_OWN_CLOCK = (
    "This is wall-clock time from the start of your session; the time you wait for the simulator service "
    "counts. When it is up you are stopped without warning and the episode is graded as it stands at that "
    "moment. The service's `time_left_s` is its own count of this limit, from the service's start or from "
    "your first request, so it can differ from the time you really have left." + _CUTOFF_CLOCK + _CUTOFF_CLOSE)
CUTOFF_NOTE_OWN = {("RoboTangle", "standard"): _CUTOFF_NOTE_OWN_CLOCK}   # (benchmark label, mode) -> its note
CUTOFF_NOTE_START = "This is wall-clock time from the start of your session;"   # how an earlier note is recognised
WALL_CLOCK_ENV = "RCB_WALL_CLOCK_S"              # the standard modes' sim service: what its /spec budget and time_left_s report
CUTOFF_TABLES = {"cutoff_sec", "family_cutoff_sec", "task_cutoff_sec", "history"}   # scripts/task_cutoffs.toml, top level
CUTOFF_CAP = 14400                               # PROTOCOL D8 / §2.3; the same exceptions: ci_checks/check-task-fields.sh
CUTOFF_CAP_EXCEPTIONS = {"RoboTangle": 21600}    # owner, 2026-10-08 (issue #87)


# ---------------------------------------------------------------------------------------------------------------------
def replace_words(s: str) -> str:
    """TEXT_REPLACEMENTS, each only where it does not continue a longer word (e.g. not inside "unlimited mode")."""
    for a, b in TEXT_REPLACEMENTS:
        s = re.sub(r"(?<![A-Za-z])" + re.escape(a), lambda _m, b=b: b, s)
    return s


# PROTOCOL D12: the three modes, each the whole suffix of its task directories. A mode is recognised by its complete
# suffix only: `-standard-realtime` is never `-standard` (it does not end in it), and `-standard` is never standard-realtime.
MODES = ("privileged", "standard", "standard-realtime")
SIDECAR_MODES = ("standard", "standard-realtime")   # robot as a service: the simulator runs in the `sim` sidecar (§4, §4b)


def mode_of(task: Path) -> str:
    for mode in sorted(MODES, key=len, reverse=True):   # longest suffix first
        if task.name.endswith(f"-{mode}"):
            return mode
    raise ValueError(f"{task.name}: task directories end in -privileged, -standard or -standard-realtime "
                     "(docs/PROTOCOL.md §2.2)")


def base_of(task: Path) -> str:
    """The name without its mode suffix (`-privileged`, `-standard`, `-standard-realtime`; PROTOCOL §2.2)."""
    return re.sub(r"-(standard-realtime|privileged|standard)$", "", task.name)


def bench_of(task: Path) -> str:
    return next((label for prefix, label in BENCHMARKS if task.name.startswith(prefix)), "")


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
    mode = mode_of(task)
    s = re.sub(r'^name = "robot-coding-bench/[^"]*"', f'name = "robot-coding-bench/{task.name}"', s, count=1, flags=re.M)
    s = re.sub(r'(?m)^tier = .*\n', "", s)
    if re.search(r'(?m)^mode = ', s):
        s = re.sub(r'(?m)^mode = "[^"]*"', f'mode = "{mode}"', s)
    else:
        s = re.sub(r'(?m)^(family = .*\n)', rf'\1mode = "{mode}"\n', s, count=1)
    if mode == "standard":
        s = re.sub(r'(?m)^protocol = "rcb-limited/(2\.\d)"', r'protocol = "eai-standard/\1"', s)
    lvl = oracle_level(task)
    meta = tomllib.loads(s).get("metadata", {})
    if lvl and "oracle" not in meta:
        o, ev = lvl
        line = f'oracle = "{o}"\n' + (f'oracle_evidence = "{ev}"\n' if ev else "")
        s = re.sub(r'(?m)^(mode = .*\n(?:protocol = .*\n)?)', lambda m: m.group(1) + line, s, count=1)
    s = replace_words(s)
    s = s.replace('"limited-mode"', '"standard-mode"').replace('"unlimited"', '"privileged"')
    write_if_changed(p, s)


def resources_for(task: Path) -> dict | None:
    """`[metadata.resources]` for a task from scripts/task_resources.toml: every rule whose `match` (a regular expression)
    finds the task directory name applies, in file order, a later rule overriding an earlier one's keys. None: no rule
    matches (the task keeps what its task.toml says)."""
    if not RESOURCES_FILE.is_file():
        return None
    out: dict = {}
    limits: dict = {}
    caps: dict = {}
    rules = tomllib.loads(RESOURCES_FILE.read_text())
    for rule in rules.get("rule", []):
        if re.search(rule["match"], task.name):
            out.update({k: v for k, v in rule.items() if k != "match"})
    for rule in rules.get("limit", []):
        if re.search(rule["match"], task.name):
            limits.update({k: v for k, v in rule.items() if k != "match"})
    for rule in rules.get("cap", []):
        if re.search(rule["match"], task.name):
            caps.update({k: v for k, v in rule.items() if k != "match"})
    if not out:
        return None
    unknown = (set(out) - set(RESOURCE_KEYS)) | (set(limits) - set(LIMIT_KEYS))
    missing = [k for k in RESOURCE_KEYS if k not in out and not (k == "recommended_gpu" and not out.get("gpu_required"))]
    missing += [f"limits.{k}" for k in LIMIT_KEYS if k not in limits]
    missing += ["caps.main"] if "main" not in caps else []
    unknown |= {f"caps.{s}.{k}" for s, c in caps.items() for k in set(c) - set(CAP_KEYS)}
    missing += [f"caps.{s}.{k}" for s, c in caps.items() for k in CAP_KEYS if k not in c]
    if unknown or missing:
        raise RuntimeError(f"{task.name}: scripts/task_resources.toml gives unknown keys {sorted(unknown)} / misses {missing}")
    out["limits"] = {k: LIMIT_KEYS[k](limits[k]) for k in LIMIT_KEYS}
    out["caps"] = {svc: {k: CAP_KEYS[k](c[k]) for k in CAP_KEYS} for svc, c in caps.items()}
    if out["limits"]["scope"] != LIMIT_SCOPES[mode_of(task)]:
        raise RuntimeError(f"{task.name}: limits scope must be {LIMIT_SCOPES[mode_of(task)]!r} (PROTOCOL §2.10)")
    return out


def _toml_value(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(float(v))
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def resources_block(r: dict) -> str:
    lines = ["[metadata.resources]", "# minimum compute to run this task (docs/PROTOCOL.md §2.9)"]
    lines += [f"{k} = {_toml_value(r[k])}" for k in RESOURCE_KEYS if k in r]
    if isinstance(r.get("limits"), dict):
        lines += ["", "[metadata.resources.limits]",
                  "# agent-phase limits in GiB (docs/PROTOCOL.md §2.10); scope: trial = every container, agent = the agent's container;"
                  "", f"# enforced from protocol v1.2 when {ENFORCE_ENV}=1 (a violation fails the trial), otherwise recorded only"]
        lines += [f"{k} = {r['limits'][k] if LIMIT_KEYS[k] is int else _toml_value(r['limits'][k])}"
                  for k in LIMIT_KEYS if k in r["limits"]]
    if isinstance(r.get("caps"), dict):
        lines += ["", "[metadata.resources.caps]",
                  "# docker caps per compose service, applied from protocol v1.2 (docs/PROTOCOL.md §2.10)"]
        lines += [f"{svc} = {{ " + ", ".join(f"{k} = {c[k] if CAP_KEYS[k] is int else _toml_value(c[k])}" for k in CAP_KEYS)
                  + " }" for svc, c in r["caps"].items()]
    return "\n".join(lines) + "\n"


def normalize_main_cap(task: Path) -> None:
    """`[environment].memory_mb` = `[metadata.resources.caps].main.memory_gb` x 1024 (PROTOCOL §2.10). Harbor writes the
    agent container's kernel memory cap (`mem_limit`) from `memory_mb`; the monitor can only see a memory violation
    before the kernel's OOM killer acts when that real cap is the declared one, above the limit. A task without
    declared caps keeps its value."""
    p = task / "task.toml"
    s = p.read_text()
    main = ((tomllib.loads(s).get("metadata", {}).get("resources") or {}).get("caps") or {}).get("main")
    if not isinstance(main, dict) or not main.get("memory_gb"):
        return
    want = int(round(float(main["memory_gb"]) * 1024))
    m = re.search(r"(?ms)^\[environment\]\n(.*?)(?=^\[|\Z)", s)
    if not m:
        raise RuntimeError(f"{task.name}: task.toml has no [environment] table")
    body = m.group(1)
    if re.search(r"(?m)^memory_mb\s*=", body):
        new = re.sub(r"(?m)^memory_mb\s*=\s*[0-9.]+", f"memory_mb = {want}", body, count=1)
    else:
        new = body.rstrip("\n") + f"\nmemory_mb = {want}\n" + ("\n" if body.endswith("\n\n") else "")
    write_if_changed(p, s[:m.start(1)] + new + s[m.end(1):])


def normalize_resources(task: Path) -> None:
    """Writes `[metadata.resources]` right after the `[metadata]` keys (replacing an earlier block) when
    scripts/task_resources.toml has a rule for the task."""
    r = resources_for(task)
    if r is None:
        return
    p = task / "task.toml"
    s = p.read_text()
    s = re.sub(r"(?ms)^\[metadata\.resources(?:\.limits|\.caps)?\]\n.*?(?=^\[|\Z)", "", s)
    m = re.search(r"(?m)^\[metadata\]\n", s)
    if not m:
        raise RuntimeError(f"{task.name}: task.toml has no [metadata] table")
    nxt = re.search(r"(?m)^\[", s[m.end():])
    at = m.end() + nxt.start() if nxt else len(s)
    head = s[:at].rstrip("\n") + "\n\n"
    s = head + resources_block(r) + ("\n" + s[at:] if at < len(s) else "")
    write_if_changed(p, s)


def _num(v) -> str:
    v = float(v)
    return str(int(v)) if v == int(v) else f"{v:g}"


def render_resources(r: dict, observed: list[str] | tuple = ()) -> list[str]:
    """README "## Compute resources" from `[metadata.resources]` (PROTOCOL §2.9); `observed`: observed_of(task)."""
    if r.get("gpu_required"):
        cls = {"rtx": "an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering)",
               "any": "any NVIDIA GPU"}.get(r.get("gpu_class", ""), f"an NVIDIA GPU of class `{r.get('gpu_class', '')}`")
        rec = r.get("recommended_gpu")
        rec = " / ".join(rec) if isinstance(rec, list) else rec
        gpu = f"GPU: required, {cls}" + (f"; recommended: {rec}." if rec else ".")
    else:
        gpu = "GPU: not needed" + (" by the agent phase; the verifier needs one." if float(r.get("verifier_min_gpu_memory_gb", 0)) > 0
                                   else ".")
    return ["## Compute resources",
            "Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent "
            "phase counts every container of the trial at once (the agent's, and in standard modes the simulator "
            "sidecar); the verifier phase runs after it.",
            "", "| | Agent phase | Verifier |", "|---|---|---|",
            f"| CPU cores | {_num(r['min_cpus'])} | {_num(r['verifier_min_cpus'])} |",
            f"| Memory | {_num(r['min_memory_gb'])} GB | {_num(r['verifier_min_memory_gb'])} GB |",
            f"| GPU memory | {_num(r['min_gpu_memory_gb'])} GB | {_num(r['verifier_min_gpu_memory_gb'])} GB |",
            "", f"- {gpu}", f"- Measured: {r.get('measured', '')}"] + (
        [f"- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in "
         f"`instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets "
         f"`{ENFORCE_ENV}=1`), {limits_summary(r['limits'], observed)}."]
        if isinstance(r.get("limits"), dict) else [])


def observed_of(task: Path) -> list[str]:
    """The task's services that are recorded only although the limits' scope is the trial (privileged mode: the
    benchmark's own services, PROTOCOL §2.10)."""
    mode = mode_of(task)
    return [s for s in sidecars_of(task) if mode not in SIDECAR_MODES and rcb_monitor_inject.kind_of(mode, s) == "observe"]


def limits_summary(lim: dict, observed: list[str] | tuple = ()) -> str:
    who = "every container of the trial" if lim["scope"] == "trial" else "the agent's container"
    if lim["scope"] == "trial" and observed:
        who += (" the agent drives (the benchmark's own " + ", ".join(f"`{s}`" for s in observed)
                + f" service{'s are' if len(observed) > 1 else ' is'} recorded only)")
    gpu = f"{_num(lim['max_gpu_memory_gb'])} GiB GPU memory" if float(lim["max_gpu_memory_gb"]) > 0 else "no GPU"
    return (f"{who}: {gpu}, {_num(lim['max_memory_gb'])} GiB memory, {int(lim['max_processes'])} processes, "
            f"{_num(lim['max_disk_gb'])} GiB of new files under {', '.join(f'`{d}`' for d in lim['disk_paths'])}; "
            f"{_num(lim['sustain_sec'])} s within {_num(lim['window_sec'])} s. Expected peak of the whole trial: "
            f"{_num(lim['trial_max_gpu_memory_gb'])} GiB GPU memory, {_num(lim['trial_max_memory_gb'])} GiB memory. "
            f"Limits measured: {lim['measured']}")


def sidecars_of(task: Path) -> list[str]:
    """Compose services next to the agent's container (`main`), cache helpers (`rcb_*`) left out."""
    c = read_text(task / "environment/docker-compose.yaml") or ""
    return [s for s in rcb_monitor_inject.service_names(c) if s != "main" and not s.startswith("rcb_")]


def _paths(ps: list[str]) -> str:
    q = [f"`{p}`" for p in ps]
    return q[0] if len(q) == 1 else ", ".join(q[:-1]) + " and " + q[-1]


def render_limits(lim: dict, mode: str, sidecars: list[str], cpus: float | None = None) -> str:
    """instruction.md's `## Resource limits` from `[metadata.resources.limits]` (PROTOCOL §2.10)."""
    gpu_gb = float(lim["max_gpu_memory_gb"])
    gpu = f"**{_num(gpu_gb)} GiB of GPU memory**, " if gpu_gb > 0 else ""
    amounts = (f"at most {gpu}**{_num(lim['max_memory_gb'])} GiB of memory**, **{int(lim['max_processes'])} processes** "
               f"and **{_num(lim['max_disk_gb'])} GiB** of new files under {_paths(lim['disk_paths'])}")
    if lim["scope"] == "agent":
        text = ("Limits for your agent environment, your own container only (the simulator in the `sim` service is the "
                f"benchmark's and does not count): {amounts}; your container has no GPU." if gpu_gb == 0 else
                "Limits for your agent environment, your own container only (the simulator in the `sim` service is the "
                f"benchmark's and does not count): {amounts}.")
    else:
        owned = [s for s in sidecars if rcb_monitor_inject.kind_of(mode, s) == "observe"]   # the benchmark's own
        sidecars = [s for s in sidecars if s not in owned]
        incl = (f"every simulator you start and the `{sidecars[0]}` service included" if len(sidecars) == 1 else
                "every simulator you start and the task's services included" if sidecars else "every simulator you start included")
        if owned:
            incl += ("; the " + " and ".join(f"`{s}`" for s in owned)
                     + (" service is the benchmark's and does" if len(owned) == 1 else " services are the benchmark's and do")
                     + " not count")
        text = (f"Limits for the whole trial, all its processes together ({incl}): {amounts}"
                + ("." if gpu_gb > 0 else "; the task has no GPU."))
    if gpu_gb > 0:
        text += " GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to)."
    text += (f" These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for "
             f"{_num(lim['sustain_sec'])} s within any {_num(lim['window_sec'] / 60)} minutes, or a process killed for lack of "
             "memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container "
             "measures every few seconds; the current values are in `/run/rcb-limits/usage.json`.")
    if gpu_gb > 0:
        text += (f" When enforcement is on and GPU memory goes above {_num(EMERGENCY_GPU_FACTOR)} times its limit, the "
                 "monitor also kills the process holding the most of it at once, to protect the machine; that alone does "
                 "not fail the trial.")
    if cpus:
        text += f" CPU is capped at {_num(cpus)} cores for your container; the cap only slows you down."
    return LIMITS_HEADING + "\n" + text + "\n"


def render_external(task_name: str = "") -> str:
    """instruction.md's `## External material` (PROTOCOL §2.11): the same words in every task, except the benchmarks of
    EXTERNAL_OPEN, whose agents may download tools and controllers."""
    text = next((v for p, v in EXTERNAL_OPEN.items() if task_name.startswith(p)), EXTERNAL_TEXT)
    return EXTERNAL_HEADING + "\n" + text + "\n"


_CUTOFFS: tuple[dict, dict, dict] | None = None


def _cutoff_value(where: str, bench: str, sec) -> int:
    cap = CUTOFF_CAP_EXCEPTIONS.get(bench, CUTOFF_CAP)
    if isinstance(sec, bool) or not isinstance(sec, int) or sec <= 0:
        raise ValueError(f"{CUTOFFS_FILE.name}: {where}: {sec!r} is not a whole positive number of seconds")
    if sec > cap:
        raise ValueError(f"{CUTOFFS_FILE.name}: {where}: {sec} s is above the {cap} s cap (PROTOCOL D8, §2.3)")
    return sec


def _cutoff_row(where: str, bench: str, row) -> dict[str, int]:
    if not isinstance(row, dict) or not row:
        raise ValueError(f"{CUTOFFS_FILE.name}: {where}: expected {{ <mode> = <seconds>, ... }}")
    for mode, sec in row.items():
        if mode not in MODES:
            raise ValueError(f"{CUTOFFS_FILE.name}: {where}: unknown mode {mode!r} (one of {', '.join(MODES)})")
        _cutoff_value(f"{where} {mode}", bench, sec)
    return row


def _cutoffs() -> tuple[dict, dict, dict]:
    """The table, read once and checked: (`[cutoff_sec]` benchmark -> mode -> seconds, `[family_cutoff_sec]` benchmark ->
    family -> mode -> seconds, `[task_cutoff_sec]` task directory -> seconds). Raises ValueError on a table that is not
    usable: an unknown benchmark or mode, a value that is not a whole positive number of seconds, one above the cap."""
    global _CUTOFFS
    if _CUTOFFS is None:
        raw = tomllib.loads(CUTOFFS_FILE.read_text(encoding="utf-8"))
        unknown = sorted(set(raw) - CUTOFF_TABLES)       # a misspelled table would be an exception that silently does nothing
        if unknown:
            raise ValueError(f"{CUTOFFS_FILE.name}: unknown table {', '.join('[' + k + ']' for k in unknown)} "
                             f"(the tables are {', '.join('[' + k + ']' for k in sorted(CUTOFF_TABLES))})")
        labels = {label for _prefix, label in BENCHMARKS}

        def known(bench: str, where: str) -> None:
            if bench not in labels:
                raise ValueError(f"{CUTOFFS_FILE.name}: {where}: unknown benchmark {bench!r} (the names are the labels of "
                                 f"scripts/task_conventions.py BENCHMARKS: {', '.join(sorted(labels))})")
        table = raw.get("cutoff_sec", {})
        for bench, row in table.items():
            known(bench, "[cutoff_sec]")
            _cutoff_row(bench, bench, row)
        families = raw.get("family_cutoff_sec", {})
        for bench, rows in families.items():
            known(bench, "[family_cutoff_sec]")
            if not isinstance(rows, dict):
                raise ValueError(f"{CUTOFFS_FILE.name}: [family_cutoff_sec.\"{bench}\"]: expected \"<family>\" = {{ <mode> = <seconds> }}")
            for family, row in rows.items():
                _cutoff_row(f"{bench}, family {family!r}", bench, row)
        tasks = raw.get("task_cutoff_sec", {})
        for name, sec in tasks.items():
            bench = next((label for prefix, label in BENCHMARKS if name.startswith(prefix)), "")
            if not bench or not name.endswith(tuple("-" + m for m in MODES)):
                raise ValueError(f"{CUTOFFS_FILE.name}: [task_cutoff_sec]: {name!r} is not a task directory name")
            _cutoff_value(f"task {name}", bench, sec)
        _CUTOFFS = (table, families, tasks)
    return _CUTOFFS


def cutoff_table() -> dict[str, dict[str, int]]:
    """scripts/task_cutoffs.toml `[cutoff_sec]`: benchmark label -> mode -> seconds, the default of every task of the
    benchmark and mode."""
    return _cutoffs()[0]


def cutoff_overrides() -> tuple[dict[str, dict[str, dict[str, int]]], dict[str, int]]:
    """The table's exceptions: (`[family_cutoff_sec]` benchmark -> family -> mode -> seconds, `[task_cutoff_sec]` task
    directory -> seconds)."""
    return _cutoffs()[1], _cutoffs()[2]


def family_of(task: Path) -> str:
    """A task's family: `[metadata] family` in its task.toml (what `[family_cutoff_sec]` is keyed by)."""
    try:
        return str(tomllib.loads((task / "task.toml").read_text()).get("metadata", {}).get("family", ""))
    except (OSError, tomllib.TOMLDecodeError):
        return ""


def cutoff_for(task: Path) -> int | None:
    """The agent's time cutoff of a task in seconds, from the table. The most specific entry wins: the task's own
    (`[task_cutoff_sec]`, by directory name), then its family's for its mode (`[family_cutoff_sec]`, the family being
    `[metadata] family` in task.toml), then the benchmark's for its mode (`[cutoff_sec]`). None when the table has no
    number for the task (ci_checks/check-cutoffs.py fails such a task: every task has one)."""
    table, families, tasks = _cutoffs()
    if task.name in tasks:
        return tasks[task.name]
    bench, mode = bench_of(task), mode_of(task)
    rows = families.get(bench)
    if rows:
        sec = rows.get(family_of(task), {}).get(mode)
        if sec is not None:
            return sec
    return table.get(bench, {}).get(mode)


def cutoff_sec(bench: str, mode: str) -> int:
    """The benchmark's number for a mode (`[cutoff_sec]`): what a generator that still writes the number (task.toml,
    the sim service's wall clock) takes it from, so that no generator keeps a copy of its own. A family's or a task's
    exception is not a generator's business: normalize, which every generator ends with, writes the task's number
    (cutoff_for) over whatever was rendered."""
    try:
        return cutoff_table()[bench][mode]
    except KeyError:
        raise KeyError(f"{CUTOFFS_FILE.name} has no cutoff for {bench!r} in {mode} mode") from None


def render_cutoff(sec: int, mode: str, bench: str = "") -> str:
    """instruction.md's last section (PROTOCOL §2.12): the heading, the cutoff sentence, then what the cutoff means in
    the mode (`bench`, a BENCHMARKS label: a benchmark whose service counts on a clock of its own has its own note)."""
    note = CUTOFF_NOTE_OWN.get((bench, mode), CUTOFF_NOTE[mode])
    return CUTOFF_HEADING + "\n" + CUTOFF_SENTENCE.format(sec=sec) + "\n\n" + note + "\n"


def strip_cutoff(s: str) -> str:
    """An instruction without the cutoff section, and without the cutoff paragraphs wherever an earlier render put them
    (until 2026-10-12 they stood under the title, without a heading)."""
    s = re.sub(rf"(?ms)^{re.escape(CUTOFF_HEADING)}[ \t]*(?:\n.*?)?(?=^## |\Z)", "", s)
    s = re.sub(rf"(?m)^{CUTOFF_RE}[ \t]*\n(?:[ \t]*\n)*", "", s)
    return re.sub(rf"(?m)^{re.escape(CUTOFF_NOTE_START)}[^\n]*\n(?:[ \t]*\n)*", "", s)


def _set_number(old: str, sec: int) -> str:
    """`sec` written the way the old literal was (a float literal stays one: `3600.0`)."""
    return f"{sec}.0" if "." in old else str(sec)


def normalize_cutoff(task: Path) -> None:
    """`[agent] timeout_sec` and, in the standard modes, the sim service's `RCB_WALL_CLOCK_S` (what its `/spec` budget
    and `meta["time_left_s"]` report) are the table's number (PROTOCOL §2.12). A task the table has no number for is
    left as it is."""
    sec = cutoff_for(task)
    if sec is None:
        return
    p = task / "task.toml"
    s = p.read_text()

    def in_agent(m: re.Match) -> str:
        return re.sub(r"(?m)^(timeout_sec\s*=\s*)([0-9][0-9_.]*)", lambda t: t.group(1) + _set_number(t.group(2), sec),
                      m.group(0), count=1)
    s2 = re.sub(r"(?ms)^\[agent\][ \t]*(?:#[^\n]*)?\n.*?(?=^\[|\Z)", in_agent, s, count=1)
    if float(tomllib.loads(s2).get("agent", {}).get("timeout_sec", -1)) != sec:
        raise RuntimeError(f"{task.name}: task.toml has no `[agent] timeout_sec` line that normalize can set to {sec}")
    write_if_changed(p, s2)
    c = task / "environment/docker-compose.yaml"
    if mode_of(task) in SIDECAR_MODES and c.is_file():
        write_if_changed(c, set_wall_clock(c.read_text(), sec, task.name))


def set_wall_clock(compose: str, sec: int, name: str = "") -> str:
    """A standard-mode compose file whose `sim` service is told the agent's cutoff: every `RCB_WALL_CLOCK_S` in the file
    is `sec`, and a `sim` service that does not set it (its code then falls back to a default of its own, which a change
    of the table would not reach) gets the line at the end of its `environment:` mapping."""
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
    """instruction.md ends with three generator-owned sections, each replacing an earlier one: `## External material`
    (PROTOCOL §2.11), `## Resource limits` rendered from `[metadata.resources.limits]` (§2.10; left out without limits
    in task.toml) and, last, `## Time limit` rendered from the cutoff table (§2.12; left out when the table has no
    number for the task): the last thing the agent reads."""
    p = task / "instruction.md"
    md = tomllib.loads((task / "task.toml").read_text()).get("metadata", {})
    lim = (md.get("resources") or {}).get("limits")
    if not p.is_file():
        return
    s = p.read_text(encoding="utf-8")
    sec = cutoff_for(task)
    if sec is not None:
        s = strip_cutoff(s)
    for heading in (EXTERNAL_HEADING, LIMITS_HEADING) if isinstance(lim, dict) else (EXTERNAL_HEADING,):
        s = re.sub(rf"(?ms)^{re.escape(heading)}[ \t]*(?:\n.*?)?(?=^## |\Z)", "", s)
    s = s.rstrip() + "\n\n" + render_external(task.name)
    if isinstance(lim, dict):
        env = tomllib.loads((task / "task.toml").read_text()).get("environment", {})
        s += "\n" + render_limits(lim, md.get("mode", mode_of(task)), sidecars_of(task), env.get("cpus"))
    if sec is not None:
        s += "\n" + render_cutoff(sec, mode_of(task), bench_of(task))
    write_if_changed(p, s)


def _shared_sources() -> set[bytes]:
    """Contents of the files generators copy unchanged from scripts/eai_standard/ (the eai-standard/2.2 layer, and the 2.4
    layer in v2_4/; D9): their copies must stay byte-identical to the source (check-tooling-identity.sh), so normalize never
    rewrites them."""
    src = Path(__file__).resolve().parent / "eai_standard"
    shared = {p.read_bytes() for p in src.rglob("*") if p.is_file() and "__pycache__" not in p.parts} if src.is_dir() else set()
    return shared | rcb_monitor_inject.generated_sources()     # the resource monitor's copies (scripts/rcb_monitor/)


def normalize_text_files(task: Path) -> None:
    shared = _shared_sources()
    for f in sorted(task.rglob("*")):
        if not f.is_file() or f.suffix not in TEXT_SUFFIXES or f.name in ("task.toml", "README.md") or f.stat().st_size > 2_000_000:
            continue
        if f.read_bytes() in shared:
            continue
        s = read_text(f)
        if s is None:
            continue
        t = s
        t = replace_words(t)
        t = t.replace(CLIENT_ASSERT_OLD, CLIENT_ASSERT_NEW)
        if f.name == "grade.py":
            t = normalize_grader(t)
        write_if_changed(f, t)


def normalize_grader(t: str) -> str:
    """reward.txt = success (1/0); partial progress only in reward.json; no string fields in reward.json."""
    t = t.replace('open(f"{LOG}/reward.txt", "w").write(f"{reward:.4f}\\n")',
                  'open(f"{LOG}/reward.txt", "w").write(f"{int(out.get(\'success\', 0))}\\n")')
    t = t.replace("reward.txt = progress when both replays agree bit-exactly (else 0); success = every goal reached.",
                  "reward.txt = success (1/0): every goal reached and both replays agree bit-exactly; progress = goals reached / goals,\n"
                  "in reward.json.")
    t = t.replace("DexToolBench: reward = task progress (goals reached / goals); Playground: reward = success.",
                  "reward.txt = success (1/0); DexToolBench's task progress (goals reached / goals) is in reward.json.")
    old = ('    out.update(infra_error=1, grader_error=int(bool(d.get("finalize_error"))), reason=str(d.get("reason") or ""), '
           'finalize_error=str(d.get("finalize_error") or "")[:300])')
    new = ('    out.update(infra_error=1, grader_error=int(bool(d.get("finalize_error"))))   # reward.json: numbers only\n'
           '    json.dump({"reason": str(d.get("reason") or ""), "finalize_error": str(d.get("finalize_error") or "")[:300]},\n'
           '              open(f"{LOG}/infra_error.json", "w"))')
    return t.replace(old, new)


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
    lines.insert(i, CLEAR_LOGS + "   # verdicts from an earlier run never survive (docs/PROTOCOL.md §2.6)\n")
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
        if title == "Compute resources":   # rendered from task.toml (render_resources), never carried over
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
    if mode_of(task) in SIDECAR_MODES:
        c = read_text(task / "environment/docker-compose.yaml") or ""
        m = re.search(r"^\s*image:\s*(\S+)", c, re.M)
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
    mode = md.get("mode", mode_of(task))
    twin = base_of(task) + ("-privileged" if mode in SIDECAR_MODES else "-standard")
    seed = md.get("instance_seed")
    sd = seeds_of(md)
    oracle = md.get("oracle", "")
    ev = md.get("oracle_evidence", "")
    head = [("Benchmark", bench_of(task) or "—"),
            ("Mode", mode + (f" (`{md['protocol']}`)" if mode in SIDECAR_MODES and md.get("protocol") else ""))]
    # a standard or realtime task always has its privileged twin (PROTOCOL §2.2), even when a generator renders it first
    # (an exempted name whose twin still exists, e.g. before a removal lands, keeps the twin)
    no_twin = None if task.with_name(twin).is_dir() else next((v for p, v in NO_TWIN.items() if task.name.startswith(p)), None)
    head.append(("Twin", no_twin or (f"`{twin}`" if mode in SIDECAR_MODES or task.with_name(twin).is_dir()
                                     else "— (privileged only)")))
    head += [("Simulator / robot", f"`{md.get('simulator', '')}` / `{md.get('robot', '')}`"),
             ("Family / instance", f"`{md.get('family', '')}`" + (f" / seed {seed}" if seed is not None else "")
              + (f" (allowed seeds: {seeds_text(sd['allowed'])}; §2.13)" if sd["allowed"] != [sd["default"]] else "")),
             ("Oracle", f"`{oracle}`" + (f" — {ev}" if ev else "") if oracle else "—"),
             ("Agent time budget", f"{int(float(ag.get('timeout_sec', 0)))} s; tokens: protocol default (PROTOCOL §5)"),
             ("Base image", f"`{image_of(task)}`")]
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
    extra_secs = [(t, b) for t, b in sections if t not in ("Difficulty", "Reference solution", "Verification") and b]
    out = [f"# {task.name}", "", "| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in head]
    out += ["", "## Task", task_text.strip(), "", "## Difficulty", difficulty.strip(), "",
            "## Reference solution", ref.strip(), "", "## Verification", ver.strip()]
    if isinstance(md.get("resources"), dict):
        out += [""] + render_resources(md["resources"], observed_of(task))
    if extra_rows or extra_secs:
        out += ["", "## Details"]
        if extra_rows:
            out += ["| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in extra_rows]
        for t, b in extra_secs:
            out += ["", f"### {t}", b.strip()]
    s = "\n".join(out).rstrip() + "\n"
    s = re.sub(r"reward = goals / (\d+)", r"`reward.txt` = 1 iff every goal is reached (both replays agreeing); `progress` = goals / \1 in `reward.json`", s)
    s = replace_words(s)
    return re.sub(r"\n{3,}", "\n\n", s)


# ---------------------------------------------------------------------------------------------------------------------
def assert_converted(task: Path) -> None:
    """Exact-match rewrites (graders, client) must not silently miss: a surviving pre-v1.0 form is an error."""
    for f in task.rglob("grade.py"):
        if 'reward.txt", "w").write(f"{reward:.4f}' in (read_text(f) or ""):
            raise RuntimeError(f"{f}: grader still writes progress to reward.txt (update normalize_grader)")
    for f in task.rglob("rcb_client.py"):
        t = read_text(f) or ""
        if 'startswith("rcb-limited/2.")' in t and "eai-standard/2." not in t:
            raise RuntimeError(f"{f}: client accepts only rcb-limited/2.x (update CLIENT_ASSERT_OLD)")


def seeds_of(md: dict) -> dict:
    """`[metadata.seeds]` (PROTOCOL §2.13) as the generator wrote it, completed: `default` = the generator's, else
    `instance_seed`, else 0 (then 0 names the task's one frozen instance); `allowed` = [default] unless given (a list,
    a range `{from, to}` with both ends included, or "any"); `oracle` = the seeds the reference solution is for: the
    generator's (else [default]) for an `oracle` of "full" or "partial", [] for "none"; `build` = "frozen" (every
    allowed seed a committed instance) unless the generator says "runtime" (the task builds a seed's instance itself)."""
    given = md.get("seeds") if isinstance(md.get("seeds"), dict) else {}
    default = int(given.get("default", md.get("instance_seed", 0)))
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


def normalize_seeds(task: Path) -> None:
    """Writes `[metadata.seeds]` (PROTOCOL §2.13) after the `[metadata]` keys and their `[metadata.resources*]` tables,
    replacing an earlier block; the values a generator wrote are kept."""
    p = task / "task.toml"
    s = p.read_text()
    sd = seeds_of(tomllib.loads(s).get("metadata", {}))
    s = re.sub(r"(?ms)^\[metadata\.seeds\]\n.*?(?=^\[|\Z)", "", s)
    m = re.search(r"(?m)^\[metadata\]\n", s)
    if not m:
        raise RuntimeError(f"{task.name}: task.toml has no [metadata] table")
    at = len(s)
    for h in re.finditer(r"(?m)^\[([^\]]+)\]", s[m.end():]):
        if not h.group(1).startswith("metadata.resources"):
            at = m.end() + h.start()
            break
    block = ("[metadata.seeds]\n# the instances this task may run from (docs/PROTOCOL.md §2.13): the default, the ones a "
             "runner may draw\n# from (a list, { from = A, to = B } or \"any\"), and the ones the reference solution under "
             "solution/ is for\n"
             f"default = {sd['default']}\nallowed = {seeds_text(sd['allowed'])}\noracle = {seeds_text(sd['oracle'])}\n"
             + (f'build = "{sd["build"]}"\n' if sd["build"] != "frozen" else ""))
    head = s[:at].rstrip("\n") + "\n\n"
    s = head + block + ("\n" + s[at:] if at < len(s) else "")
    write_if_changed(p, s)


def normalize(task: Path) -> None:
    task = Path(task)
    mode_of(task)
    if (task / "results").exists():
        shutil.rmtree(task / "results")
    normalize_toml(task)
    normalize_cutoff(task)
    normalize_resources(task)
    normalize_seeds(task)
    normalize_main_cap(task)
    normalize_text_files(task)
    normalize_instruction(task)
    normalize_test_sh(task)
    write_if_changed(task / "README.md", render_readme(task))
    rcb_monitor_inject.apply(task)   # PROTOCOL §2.10 (v1.2): the resource monitor sidecar, caps, verifier step
    assert_converted(task)


def snapshot(task: Path) -> dict[str, bytes]:
    return {str(p.relative_to(task)): p.read_bytes() for p in sorted(task.rglob("*")) if p.is_file()}


def main(argv: list[str]) -> int:
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
