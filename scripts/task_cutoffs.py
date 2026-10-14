#!/usr/bin/env python3
"""The agent's time cutoffs (docs/PROTOCOL.md §2.12): one table, scripts/task_cutoffs.toml, and this tool.

    python3 scripts/task_cutoffs.py show                 # the table as it is, with the number of tasks per mode, and its exceptions
    python3 scripts/task_cutoffs.py families "<benchmark>"   # the benchmark's families (what a family exception is keyed by)
    python3 scripts/task_cutoffs.py apply [benchmark]    # after editing the table: write it into the tasks
    python3 scripts/task_cutoffs.py check                # what CI checks (ci_checks/check-cutoffs.py)

`apply` passes every task (or the named benchmark's: a label of the table, e.g. "RoboLab") through
scripts/task_conventions.py `normalize`, which writes the task's number (its own exception, else its family's, else its
benchmark's for the mode) into `[agent] timeout_sec`, the closing `## Time limit` section of instruction.md, the README's
"Agent time budget" row and the standard modes' `RCB_WALL_CLOCK_S`; then it renders docs/CUTOFFS.md and refreshes the
changed digests in tasks/dataset.toml. No generator has to run: nothing a generator writes depends on the number
(ci_checks/check-cutoffs.py keeps instructions free of a second statement of it).
Standard library only; run it from a checkout made with `umask 022`.
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import subprocess
import sys
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402

DOC = ROOT / "docs/CUTOFFS.md"
BASELINE = ROOT / "scripts/task_cutoffs.baseline.toml"   # the table on the day it was created: never edited
MANIFEST = ROOT / "tasks/dataset.toml"
SHORT = {"privileged": "P", "standard": "S", "standard-realtime": "RT"}


def all_tasks() -> list[Path]:
    return sorted(p for p in (ROOT / "tasks").iterdir() if (p / "task.toml").is_file())


def _dur(sec: int) -> str:
    return f"{sec} s ({sec / 60:g} min)"


def table_rows(tasks: list[Path]) -> list[str]:
    n = Counter((tc.bench_of(t), tc.mode_of(t)) for t in tasks)
    rows = ["| Benchmark | privileged | standard | standard-realtime | Tasks (P / S / RT) |", "|---|---|---|---|---|"]
    for bench, row in sorted(tc.cutoff_table().items(), key=lambda kv: kv[0].lower()):
        cells = [_dur(row[m]) if m in row else "—" for m in tc.MODES]
        counts = " / ".join(str(n[(bench, m)]) if n[(bench, m)] else "—" for m in tc.MODES)
        rows.append(f"| {bench} | {cells[0]} | {cells[1]} | {cells[2]} | {counts} |")
    return rows


HISTORY_FIELDS = {"date", "benchmark", "family", "modes", "task", "from_sec", "to_sec", "decided_by", "note"}


def _key_name(key: tuple) -> str:
    return (f"task {key[1]}" if key[0] == "task" else f"{key[1]}, family {key[2]}, {key[3]}" if key[0] == "family"
            else f"{key[1]}, {key[2]}")


def _keys(cutoff_sec: dict, families: dict, tasks: dict) -> dict[tuple, int]:
    """Every number of a table under the key its history is kept by."""
    out: dict[tuple, int] = {}
    for bench, row in cutoff_sec.items():
        for mode, sec in row.items():
            out[("bench", bench, mode)] = sec
    for bench, rows in families.items():
        for family, row in rows.items():
            for mode, sec in row.items():
                out[("family", bench, family, mode)] = sec
    for name, sec in tasks.items():
        out[("task", name)] = sec
    return out


def history_errors() -> list[str]:
    """The table's `[[history]]` is the only record of a change (PROTOCOL §2.8, §2.12), so it is required: every number
    of the table equals its last recorded value, which is the `to_sec` of its newest entry dated after the baseline or,
    without one, its number in scripts/task_cutoffs.baseline.toml (the table on the day it was created; a number that
    is in neither, a new row or exception, has no recorded value: 0). Entries are checked for their fields, and an
    entry's `from_sec` is the value recorded before it. Returns what is wrong, [] when nothing is."""
    errs: list[str] = []
    raw = tomllib.loads(tc.CUTOFFS_FILE.read_text(encoding="utf-8"))
    base = tomllib.loads(BASELINE.read_text(encoding="utf-8"))
    families, by_task = tc.cutoff_overrides()
    current = _keys(tc.cutoff_table(), families, by_task)
    recorded = _keys(base.get("cutoff_sec", {}), base.get("family_cutoff_sec", {}), base.get("task_cutoff_sec", {}))
    last = ""
    for n, h in enumerate(raw.get("history", []), 1):
        where = f"{tc.CUTOFFS_FILE.name}: [[history]] entry {n}"
        if not isinstance(h, dict):
            errs.append(f"{where}: not a table"); continue
        bad = sorted(set(h) - HISTORY_FIELDS)
        if bad:
            errs.append(f"{where}: unknown field(s) {', '.join(bad)} (the fields are {', '.join(sorted(HISTORY_FIELDS))})")
        date = h.get("date")
        if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            errs.append(f'{where}: date = "YYYY-MM-DD" is required'); continue
        where += f" ({date})"
        if date < last:
            errs.append(f"{where}: entries are in order of date, oldest first (the one before it is {last})")
        last = max(last, date)
        for f in ("decided_by", "note"):
            if not isinstance(h.get(f), str) or not h[f].strip():
                errs.append(f"{where}: `{f}` is required (who decided; why, and what happens to results under the old number)")
        a, b = h.get("from_sec"), h.get("to_sec")
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in (a, b)) or a == b:
            errs.append(f"{where}: from_sec and to_sec are two different whole numbers of seconds (0 = no entry)"); continue
        modes = h.get("modes")
        if "task" in h:
            keys = [("task", h["task"])] if not ({"benchmark", "family", "modes"} & set(h)) and isinstance(h["task"], str) else None
        elif isinstance(h.get("benchmark"), str) and isinstance(modes, list) and modes and all(m in tc.MODES for m in modes):
            keys = ([("family", h["benchmark"], h["family"], m) for m in modes] if isinstance(h.get("family"), str)
                    else [("bench", h["benchmark"], m) for m in modes] if "family" not in h else None)
        else:
            keys = None
        if keys is None:
            errs.append(f"{where}: name what changed: benchmark + modes (a list of {', '.join(tc.MODES)}), "
                        "benchmark + family + modes, or task alone")
            continue
        if date <= str(base.get("date", "")):
            continue                      # from before the table existed: part of the record, already in the baseline
        for key in keys:
            was = recorded.get(key, 0)
            if was != a:
                errs.append(f"{where}: {_key_name(key)}: from_sec = {a}, but the value recorded before this entry is {was}")
            recorded[key] = b
    for key in sorted(set(current) | set(recorded), key=str):
        now, was = current.get(key, 0), recorded.get(key, 0)
        if now != was:
            errs.append(f"{tc.CUTOFFS_FILE.name}: {_key_name(key)} is {now or 'not in the table'}, its last recorded value is "
                        f"{was or 'none'}: add a [[history]] entry (from_sec = {was}, to_sec = {now}; date, decided_by, note)")
    return errs


def history_rows() -> list[str]:
    rows = []
    for h in tomllib.loads(tc.CUTOFFS_FILE.read_text(encoding="utf-8")).get("history", []):
        what = (f"`{h.get('task')}`" if "task" in h else str(h.get("benchmark", ""))
                + (f": family `{h['family']}`" if "family" in h else "") + (", " + ", ".join(h.get("modes", [])) if h.get("modes") else ""))
        a, b = h.get("from_sec", 0), h.get("to_sec", 0)
        rows.append(f"| {h.get('date', '')} | {what} | {str(a) + ' s' if a else '(none)'} -> {str(b) + ' s' if b else '(removed)'} "
                    f"| {h.get('decided_by', '')} | {h.get('note', '')} |")
    return rows


def source_of(task: Path) -> str:
    """Which entry of the table gives a task its number."""
    families, by_task = tc.cutoff_overrides()
    bench, mode = tc.bench_of(task), tc.mode_of(task)
    if task.name in by_task:
        return f"[task_cutoff_sec] {task.name}"
    family = tc.family_of(task)
    if mode in families.get(bench, {}).get(family, {}):
        return f"[family_cutoff_sec] {bench}, family {family}, {mode}"
    return f"{bench}, {mode}"


def override_rows(tasks: list[Path]) -> list[str]:
    """The table's exceptions as Markdown rows; [] when there is none."""
    families, by_task = tc.cutoff_overrides()
    n = Counter((tc.bench_of(t), tc.family_of(t), tc.mode_of(t)) for t in tasks) if families else Counter()
    rows = []
    for bench, fams in sorted(families.items(), key=lambda kv: kv[0].lower()):
        for family, row in sorted(fams.items()):
            for mode in tc.MODES:
                if mode in row:
                    took = sum(1 for t in tasks if (tc.bench_of(t), tc.mode_of(t)) == (bench, mode) and tc.family_of(t) == family
                               and t.name not in by_task)
                    rows.append(f"| family | {bench}: `{family}` | {mode} | {_dur(row[mode])} | {took} of {n[(bench, family, mode)]} |")
    for name, sec in sorted(by_task.items()):
        rows.append(f"| task | `{name}` | {tc.mode_of(Path(name))} | {_dur(sec)} | 1 |")
    return rows


def render_doc(tasks: list[Path]) -> str:
    """docs/CUTOFFS.md: the table for reading, how to change it, what follows a number and what does not."""
    raw = tomllib.loads(tc.CUTOFFS_FILE.read_text(encoding="utf-8"))
    ex = tc.render_cutoff(3600, "privileged").split("\n", 1)[1].split("\n\n")
    over = override_rows(tasks)
    out = [
        "# Agent time cutoffs",
        "",
        "<!-- Generated from scripts/task_cutoffs.toml by `python3 scripts/task_cutoffs.py apply`. Do not edit this file: "
        "edit the table and run the command. -->",
        "",
        "Every task gives the agent a fixed wall-clock time, its **cutoff**: Harbor's `[agent] timeout_sec`. At the cutoff "
        "the agent is stopped and the trial is graded as it stands ([PROTOCOL.md](PROTOCOL.md) §2.12). The numbers live in "
        "one file, [`scripts/task_cutoffs.toml`](../scripts/task_cutoffs.toml): seconds per benchmark and mode, with "
        "optional exceptions per family and per task. This page shows that table and is rendered from it.",
        "",
        "**When the clock starts.** Harbor counts the cutoff around the agent's run only (`asyncio.wait_for(agent.run(...), "
        "timeout=...)` in its trial's agent phase): after the environment has been built and started and after the agent's "
        "harness has been installed, each of which has a timeout of its own. It does not count from the container's start. "
        "In the standard modes the `sim` service starts with the environment, so whatever start-up it has not finished by "
        "then is waited out inside the agent's time.",
        "",
        "## The table",
        "",
        *table_rows(tasks),
        "",
        f"{len(tasks)} task directories. P / S / RT: privileged, standard, standard-realtime. A cutoff is a whole number "
        f"of seconds, at most {tc.CUTOFF_CAP} (PROTOCOL D8"
        + "".join(f"; {b}'s exception: {c}" for b, c in sorted(tc.CUTOFF_CAP_EXCEPTIONS.items())) + ").",
        "",
        "## Exceptions (per family, per task)",
        "",
        "A benchmark's row is the default of all its tasks in a mode. The table may give one family, or one task, another "
        "number; the most specific entry wins: **task > family > benchmark and mode**. A family is `[metadata] family` in "
        "`task.toml` (`python3 scripts/task_cutoffs.py families \"<benchmark>\"` lists a benchmark's). Like every cutoff, "
        "an exception is an owner decision with a `[[history]]` entry, and results are compared only under the same cutoff "
        "(PROTOCOL D8).",
        "",
        "```toml",
        "[family_cutoff_sec.\"RoboTangle\"]              # benchmark; then one line per family, a number per mode",
        "\"cast_coil\" = { privileged = 14400, standard = 14400 }",
        "",
        "[task_cutoff_sec]                              # one line per task directory",
        "\"robotangle-cast-coil-hard-i00-standard\" = 10800",
        "```",
        "",
    ]
    if over:
        out += ["| Kind | Applies to | Mode | Cutoff | Tasks that take it |", "|---|---|---|---|---|", *over, ""]
    else:
        out += ["No exception is in use: every task takes its benchmark's number.", ""]
    out += [
        "## What the agent is told",
        "",
        f"Every `instruction.md` ends with the same section, written by `scripts/task_conventions.py` from the table: the "
        f"last thing the agent reads (here for 3600 s; the first paragraph is the same in every mode):",
        "",
        "> " + tc.CUTOFF_HEADING,
        "> " + ex[0],
        ">",
        "> " + ex[1].strip(),
        "",
        "In the standard and standard-realtime modes the second paragraph is:",
        "",
        "> " + tc.CUTOFF_NOTE["standard"],
        "",
        "(" + ", ".join(sorted({b for b, _ in tc.CUTOFF_NOTE_OWN})) + ", whose service counts on a clock of its own, keeps "
        "the earlier sentence there: \"The service's `time_left_s` is its own count of this limit, from the service's "
        "start or from your first request, so it can differ from the time you really have left.\")",
        "",
        "What a benchmark adds about its own time (a simulator's start-up, what its service counts) stands in its own "
        f"text and names no number: it says \"{tc.CUTOFF_REF}\".",
        "",
        "## Changing a cutoff",
        "",
        "1. Edit the number in [`scripts/task_cutoffs.toml`](../scripts/task_cutoffs.toml) (the benchmark's row, or an "
        "exception) and add a `[[history]]` entry at its end (date, who decided, from -> to, why). It is required: CI and "
        "`apply` refuse a number that differs from its last recorded value.",
        "2. `python3 scripts/task_cutoffs.py apply` (about three minutes; `apply \"<benchmark>\"` for one benchmark).",
        "3. Commit everything it changed and open a pull request. CI (`ci_checks/check-cutoffs.py`) fails when a task's "
        "`task.toml`, its instruction or its sim service disagrees with the table.",
        "",
        "Never edit the number in a task, a template or a generator. `apply` writes, in every task concerned: "
        "`[agent] timeout_sec`, the number in the closing section of `instruction.md`, the README's `Agent time budget` "
        "row, the sim service's `RCB_WALL_CLOCK_S` (standard modes), the task's digest in `tasks/dataset.toml`, and this page.",
        "",
        "A change of a cutoff changes the task in place: the scene, the frozen instance, the success rule and the "
        "verifier are the same, so the task keeps its name (PROTOCOL §2.8, §2.12). The record of the change is its "
        "`[[history]]` entry (below), not a Change Log entry in each task's README. A number's last recorded value is its "
        "newest entry's, or, if it never changed, the table of 2026-10-11 "
        "([`scripts/task_cutoffs.baseline.toml`](../scripts/task_cutoffs.baseline.toml), never edited). Results recorded under another cutoff "
        "are reported separately (PROTOCOL D8), and trials already running keep the cutoff they started with.",
        "",
        "## What follows the number, and what does not",
        "",
        "- **Follows by itself** (`apply`): everything listed above, and a scheduler's estimate of a trial's length, which "
        "reads `task.toml`.",
        "- **The sim service's clock** (`RCB_WALL_CLOCK_S`) only reports: `spec[\"budget\"][\"wall_clock_s\"]` and "
        "`meta[\"time_left_s\"]`, counted from the agent's first request to the service (any endpoint; kept through a "
        "restart of the service), never from the service's start: the service is up before the agent's phase begins, so a "
        "clock started with it ran ahead of Harbor's (a median of 79 s over the recorded trials). Harbor's timeout is "
        "what stops the agent. RoboTangle's service is the exception today: it ends the episode itself when its own count, "
        "running since the service started, reaches 0 (to become report-only at RoboTangle's next task update: "
        "`docs/benchmarks/robotangle.md`).",
        "- **Look at these when you raise a cutoff** (lowering one is safe): the collect-hook and verifier budgets that "
        "were sized for an episode as long as the agent's time (RoboCasa, RoboCasa365 and RoboCasa-GR1 "
        "`COLLECT_TIMEOUT_S`; RoboLab, YAMLab, DexJoCo and BEHAVIOR-1K, see their `docs/benchmarks/` pages), and the "
        f"cap of {tc.CUTOFF_CAP} s.",
        "- **RoboOlympics**: the cutoff has to stay above a match's wall time (5 to 60 minutes at slowdown 10).",
        "- **Not derived from it**: the token budget (PROTOCOL §5), the resource limits (§2.10), reset budgets, step "
        "caps, verifier timeouts.",
        "",
        "## History",
        "",
        "The table started on 2026-10-11 with the number every task had on that day; each change since has an entry.",
        "",
        "| Date | What | Change | Decided by | Note |",
        "|---|---|---|---|---|",
        *history_rows(),
    ]
    return "\n".join(out) + "\n"


# The digest Harbor publishes a task under (harbor.publisher.packager.Packager.compute_content_hash, Harbor 0.23.0); the
# same computation as ci_checks/check-dataset-manifest.sh, which checks what this writes.
IGNORE_NAMES = ("*.pyc", ".DS_Store", "*.swp", "*.swo", "*~")


def digest(task: Path) -> str:
    files = [task / n for n in ("task.toml", "instruction.md", "README.md", "trajectory.json") if (task / n).exists()]
    for sub in ("environment", "tests", "solution", "steps"):
        if (task / sub).exists():
            files += [p for p in (task / sub).rglob("*") if p.is_file()]
    rels = sorted({p.relative_to(task).as_posix() for p in files})
    rels = [r for r in rels if "__pycache__" not in Path(r).parts[:-1]
            and not any(fnmatch.fnmatchcase(Path(r).name, pat) for pat in IGNORE_NAMES)]
    outer = hashlib.sha256()
    for rel in rels:
        h = hashlib.sha256()
        with (task / rel).open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        outer.update(f"{rel}\0{h.hexdigest()}\n".encode())
    return "sha256:" + outer.hexdigest()


def refresh_manifest(tasks: list[Path]) -> int:
    """tasks/dataset.toml: the digest of each given task as its files are now. Returns how many changed."""
    s = MANIFEST.read_text(encoding="utf-8")
    changed = 0
    for t in tasks:
        d = digest(t)
        pat = re.compile(rf'(name = "robot-coding-bench/{re.escape(t.name)}"\ndigest = ")(sha256:[0-9a-f]+)(")')
        m = pat.search(s)
        if m is None:
            raise SystemExit(f"tasks/dataset.toml does not list {t.name} (cd tasks && harbor add --scan .)")
        if m.group(2) != d:
            s = s[:m.start(2)] + d + s[m.end(2):]
            changed += 1
    if changed:
        MANIFEST.write_text(s, encoding="utf-8")
    return changed


def apply(only: str | None) -> int:
    table = tc.cutoff_table()
    if only is not None and only not in table:
        raise SystemExit(f"no benchmark {only!r} in {tc.CUTOFFS_FILE.name} (one of: {', '.join(sorted(table))})")
    every = all_tasks()
    tasks = [t for t in every if only is None or tc.bench_of(t) == only]
    missing = sorted({f"{tc.bench_of(t) or t.name} ({tc.mode_of(t)})" for t in tasks if tc.cutoff_for(t) is None})
    if missing:
        raise SystemExit(f"{tc.CUTOFFS_FILE.name} has no cutoff for: {', '.join(missing)}")
    hist = history_errors()
    if hist and not os.environ.get("RCB_CUTOFFS_FILE"):      # a what-if run with another table needs no record
        raise SystemExit("\n".join(["A changed number needs its [[history]] entry (the only record of the change):"] + hist))
    os.umask(0o022)
    for k, t in enumerate(tasks, 1):
        tc.normalize(t)
        if k % 200 == 0:
            print(f"  {k} / {len(tasks)} tasks", flush=True)
    DOC.write_text(render_doc(every), encoding="utf-8")
    n = refresh_manifest(tasks)
    print(f"applied {tc.CUTOFFS_FILE.name} to {len(tasks)} tasks; {n} digest(s) changed in tasks/dataset.toml; "
          f"docs/CUTOFFS.md rendered.\nNext: git status, then commit. CI: python3 ci_checks/check-cutoffs.py")
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "show"
    if cmd == "show":
        tasks = all_tasks()
        print("\n".join(table_rows(tasks)))
        over = override_rows(tasks)
        print("\nExceptions (task > family > benchmark and mode): " + ("" if over else "none"))
        if over:
            print("\n".join(["| Kind | Applies to | Mode | Cutoff | Tasks that take it |", "|---|---|---|---|---|", *over]))
        return 0
    if cmd == "families":
        if len(argv) < 2 or argv[1] not in tc.cutoff_table():
            raise SystemExit(f"usage: task_cutoffs.py families \"<benchmark>\"   (one of: {', '.join(sorted(tc.cutoff_table()))})")
        n = Counter((tc.family_of(t), tc.mode_of(t)) for t in all_tasks() if tc.bench_of(t) == argv[1])
        for family in sorted({f for f, _m in n}):
            print(f'"{family}"   ' + ", ".join(f"{m}: {n[(family, m)]}" for m in tc.MODES if n[(family, m)]))
        return 0
    if cmd == "apply":
        return apply(argv[1] if len(argv) > 1 else None)
    if cmd == "check":
        return subprocess.call([sys.executable, str(ROOT / "ci_checks/check-cutoffs.py")])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
