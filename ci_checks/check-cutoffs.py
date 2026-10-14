#!/usr/bin/env python3
"""The agent's time cutoff (docs/PROTOCOL.md §2.12): one table, and every task says what the table says.

scripts/task_cutoffs.toml gives the seconds per benchmark and mode, with optional exceptions per family and per task
(the most specific wins). For every task:
  - the table has a number for it;
  - `[agent] timeout_sec` in task.toml is that number (Harbor enforces it);
  - instruction.md ends with the section scripts/task_conventions.py renders, the last thing the agent reads:
    `## Time limit`, "You have N seconds to complete this task. Do not cheat by using online solutions or hints specific
    to this task." with the same N, then what the cutoff means in the task's mode; nothing follows it, and the heading
    and the sentence stand there once;
  - nothing else in instruction.md states the agent's limit as a duration (the wordings tasks used before 2026-10-11:
    "wall-clock budget is 90 min (5400 s)", "You have 60 minutes of wall-clock time", "Time limit: one hour", ...; and
    the obvious other shapes: "You have one hour.", "The limit is 3600 seconds.", "Finish within 60 minutes."): a second
    statement goes stale at the next change of the table, and two limits in one instruction are worse than none;
  - the README's "Agent time budget" row has the number;
  - standard modes: the `sim` service is told the same number (`RCB_WALL_CLOCK_S` in environment/docker-compose.yaml,
    what its `/spec` budget and `meta["time_left_s"]` report; PROTOCOL §2.3).
Repository level (no task given): the table itself is usable, has a number for exactly the benchmark-mode pairs that
have tasks, privileged and standard (any mode with `same_cutoff_as` in the mode registry) have one number wherever
both exist (a benchmark's row, a family's entry, a task and its counterpart), every exception names a family or a task that exists, every number equals its last recorded value (its
newest `[[history]]` entry, else scripts/task_cutoffs.baseline.toml: a change without its entry fails), and
docs/CUTOFFS.md is what `python3 scripts/task_cutoffs.py apply` renders from it.

    python3 ci_checks/check-cutoffs.py [task dirs]      # default: every task and the repository-level rules
Fix: edit scripts/task_cutoffs.toml (never a task), then `python3 scripts/task_cutoffs.py apply`. Standard library only.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402  (one table reader, one renderer)
import task_cutoffs  # noqa: E402

DUR = r"\d[\d,.]*\s*(?:s|sec|secs|seconds?|min|mins|minutes?|h|hrs?|hours?)\b"
WORD_DUR = (r"(?:(?:an|one|two|three|four|six|half an) hours?|(?:ten|fifteen|twenty|thirty|forty[- ]five|sixty|ninety|"
            r"a hundred and twenty|one hundred and twenty) minutes)\b")
ANY_DUR = rf"(?:{DUR}|{WORD_DUR})"
# Other statements of the agent's limit, searched in each sentence of the instruction's own text (outside the three
# closing sections). The first five are the wordings tasks used before 2026-10-11.
OTHER_LIMIT = [
    ("a wall-clock or time budget with a duration", rf"(?:wall[- ]clock|time) budget\b.*?{ANY_DUR}"),
    ("'You have <duration> ... of wall-clock time / in all / in total'",
     rf"\byou have\b.*?{ANY_DUR}.*?(?:wall[- ]clock|\bin all\b|\bin total\b)"),
    ("'your <duration> are up'", rf"\byour\s+{DUR}\s+(?:are|is)\s+up\b"),
    ("'<minutes or hours> of wall clock'", r"\d[\d,.]*\s*(?:min|mins|minutes?|h|hrs?|hours?) of wall[- ]clock"),
    ("'Time limit: <duration>'", rf"\btime limit:\**\s*{ANY_DUR}"),
]
# Wider shapes of the same thing, for wordings nobody has used yet ("You have one hour.", "The limit is 3600 seconds.",
# "Finish within 60 minutes.", "The session lasts 5400 s."). They would also catch durations that are not the agent's
# limit, so a sentence that is plainly about something else (NOT_THE_LIMIT) is not searched with them. A heuristic: it
# finds the obvious second statement, a reviewer still reads the text.
OTHER_LIMIT_WIDE = [
    ("'You have / are given <duration>'", rf"\byou (?:have|are given|get|are allowed)\b(?: \w+){{0,3}}? (?:\*\*)?{ANY_DUR}"),
    ("a limit, budget, cutoff, timeout or deadline with a duration",
     rf"\b(?:limit|budget|cutoff|timeout|deadline)\b(?:\*\*)?(?: is| of|:)(?: \w+){{0,2}}? (?:\*\*)?{ANY_DUR}"),
    ("'finish / complete ... within <duration>'", rf"\b(?:finish|complete|solve|be done)\b[^,;:()]{{0,40}}?\bwithin (?:\*\*)?{ANY_DUR}"),
    ("'the session / trial / run lasts <duration>'",
     rf"\b(?:session|trial|run)\b (?:lasts|is limited to|is cut off after|times out after|ends after) (?:\*\*)?{ANY_DUR}"),
]
NOT_THE_LIMIT = (r"simulated time|robot time|of play\b|control steps?|physics|per (?:call|goal|row|step|request)|each (?:goal|call|request)|"
                 r"replay|Robot\(|gives up after|connection|start-?up|starts?\b|launch|reset|rows?\b|mm\b|path budget|step budget|"
                 r"\bHz\b|its own time limit|challenge")


def own_text(instruction: str) -> str:
    """The instruction without the generated parts: the three closing sections (and cutoff paragraphs anywhere)."""
    s = tc.strip_cutoff(instruction)
    for heading in (tc.EXTERNAL_HEADING, tc.LIMITS_HEADING):
        s = re.sub(rf"(?ms)^{re.escape(heading)}[ \t]*(?:\n.*?)?(?=^## |\Z)", "", s)
    return s


def other_limits(instruction: str) -> list[str]:
    out = []
    for para in re.split(r"\n[ \t]*\n", own_text(instruction)):
        flat = " ".join(para.split())
        for sentence in re.split(r"(?<=[.;!?])\s+", flat):
            wide = [] if re.search(NOT_THE_LIMIT, sentence, re.I) else OTHER_LIMIT_WIDE
            for what, pat in OTHER_LIMIT + wide:
                if re.search(pat, sentence, re.I):
                    out.append(f"{what}: \"{sentence[:160]}\"")
                    break
    return out


def check_task(task: Path) -> list[str]:
    errs: list[str] = []
    try:
        mode = tc.mode_of(task)
    except ValueError as e:
        return [str(e)]
    bench = tc.bench_of(task)
    sec = tc.cutoff_for(task)
    if sec is None:
        return [f"scripts/task_cutoffs.toml has no cutoff for {bench or 'this benchmark'!s} in {mode} mode "
                "(add the number to the benchmark's row in [cutoff_sec]; a new benchmark also needs its label in "
                "task_conventions.py BENCHMARKS)"]
    meta = tomllib.loads((task / "task.toml").read_text())
    have = meta.get("agent", {}).get("timeout_sec")
    if have is None or float(have) != sec:
        errs.append(f"[agent] timeout_sec = {have!r}, the table says {sec} ({task_cutoffs.source_of(task)})")
    ins = (task / "instruction.md").read_text(encoding="utf-8") if (task / "instruction.md").is_file() else ""
    want = tc.render_cutoff(sec, mode, bench)
    if not ins.startswith("# "):
        errs.append("instruction.md does not start with its `# ` title line")
    if not ins.endswith("\n\n" + want):
        stated = re.findall(tc.CUTOFF_RE, ins)
        errs.append(f"instruction.md does not end with the `{tc.CUTOFF_HEADING}` section rendered for {sec} s in {mode} mode "
                    "(the last thing the agent reads; nothing after it)"
                    + (f" (it says {', '.join(stated)} seconds)" if stated else " (the sentence is missing)"))
    if len(re.findall(tc.CUTOFF_RE, ins)) > 1 or len(re.findall(rf"(?m)^{re.escape(tc.CUTOFF_HEADING)}[ \t]*$", ins)) > 1:
        errs.append(f"instruction.md has the cutoff sentence or the `{tc.CUTOFF_HEADING}` heading more than once")
    errs += [f"instruction.md states the agent's limit a second time, outside `{tc.CUTOFF_HEADING}` ({x}); say "
             f"\"{tc.CUTOFF_REF}\" instead of a number" for x in other_limits(ins)]
    readme = (task / "README.md").read_text(encoding="utf-8") if (task / "README.md").is_file() else ""
    if f"| Agent time budget | {sec} s;" not in readme:
        errs.append(f"README.md's `Agent time budget` row does not say {sec} s")
    if mode in tc.SIDECAR_MODES:
        c = task / "environment/docker-compose.yaml"
        text = c.read_text() if c.is_file() else ""
        vals = re.findall(rf"""{tc.WALL_CLOCK_ENV}:[ \t]*["']?([^"'\s#]+)""", text)
        if not vals:
            errs.append(f"environment/docker-compose.yaml does not give the sim service {tc.WALL_CLOCK_ENV} (the "
                        "service would report a default of its own as the budget)")
        for v in vals:
            try:
                ok = float(v) == sec
            except ValueError:
                ok = False
            if not ok:
                errs.append(f"environment/docker-compose.yaml: {tc.WALL_CLOCK_ENV} = {v}, the table says {sec}")
    return errs


def check_repo(tasks: list[Path]) -> list[str]:
    errs: list[str] = []
    table = tc.cutoff_table()
    families, by_task = tc.cutoff_overrides()
    have = {(tc.bench_of(t), tc.mode_of(t)) for t in tasks}
    for bench, row in sorted(table.items()):
        for mode in row:
            if (bench, mode) not in have:
                errs.append(f"scripts/task_cutoffs.toml: {bench} has a cutoff for {mode} mode but no task in that mode")
    # an exception that reaches no task is a typo (a family is `[metadata] family` in task.toml) or a leftover
    fam = {(tc.bench_of(t), tc.family_of(t), tc.mode_of(t)) for t in tasks} if families else set()
    for bench, rows in sorted(families.items()):
        for family, row in sorted(rows.items()):
            for mode in row:
                if (bench, family, mode) not in fam:
                    known = sorted({f for b, f, _m in fam if b == bench})
                    errs.append(f"scripts/task_cutoffs.toml: [family_cutoff_sec] {bench} has no task of family {family!r} in "
                                f"{mode} mode (its families, `[metadata] family` in task.toml: {', '.join(known[:12])}"
                                + (", ..." if len(known) > 12 else "") + ")")
    names = {t.name for t in tasks}
    for name in sorted(by_task):
        if name not in names:
            errs.append(f"scripts/task_cutoffs.toml: [task_cutoff_sec] names {name!r}, which is not a task directory")
    # a benchmark may ship any subset of the modes (PROTOCOL §2.15), but a mode whose registry entry names
    # `same_cutoff_as` has that mode's number wherever both exist (§2.16; standard = privileged, owner 2026-10-12):
    # in a benchmark's row, in a family's entry, and for a task and its counterpart of the same base
    pairs = [(m, d["same_cutoff_as"]) for m, d in tc.MODE_REGISTRY.items() if d["same_cutoff_as"]]
    for m, other in pairs:
        for bench, row in sorted(table.items()):
            if m in row and other in row and row[m] != row[other]:
                errs.append(f"scripts/task_cutoffs.toml: {bench} gives {other} {row[other]} s and {m} {row[m]} s; the two "
                            "modes have the same cutoff (PROTOCOL §2.12, §2.16)")
        for bench, rows in sorted(families.items()):
            for family, row in sorted(rows.items()):
                if m in row and other in row and row[m] != row[other]:
                    errs.append(f"scripts/task_cutoffs.toml: [family_cutoff_sec] {bench} {family!r} gives {other} "
                                f"{row[other]} s and {m} {row[m]} s; the two modes have the same cutoff")
        for t in tasks:
            if tc.mode_of(t) != m:
                continue
            o = t.with_name(f"{tc.base_of(t)}-{other}")
            if (o / "task.toml").is_file() and tc.cutoff_for(t) != tc.cutoff_for(o):
                errs.append(f"{t.name} has a cutoff of {tc.cutoff_for(t)} s and {o.name} {tc.cutoff_for(o)} s; the two "
                            "modes have the same cutoff (PROTOCOL §2.12, §2.16)")
    errs += task_cutoffs.history_errors()     # every number equals its last recorded value: a change has its [[history]] entry
    doc = ROOT / "docs/CUTOFFS.md"
    if not doc.is_file() or doc.read_text(encoding="utf-8") != task_cutoffs.render_doc(tasks):
        errs.append("docs/CUTOFFS.md is not what scripts/task_cutoffs.toml renders (run python3 scripts/task_cutoffs.py apply)")
    return errs


def main(argv: list[str]) -> int:
    try:
        tc.cutoff_table()
    except (ValueError, tomllib.TOMLDecodeError, OSError) as e:
        print(f"FAIL scripts/task_cutoffs.toml: {e}")
        return 1
    every = sorted(p for p in (ROOT / "tasks").iterdir() if (p / "task.toml").is_file())
    tasks = [Path(a) for a in argv if (Path(a) / "task.toml").is_file()] if argv else every
    rc = 0
    for t in tasks:
        for e in check_task(t):
            rc = 1
            print(f"FAIL {t}: {e}")
    if not argv:
        for e in check_repo(every):
            rc = 1
            print(f"FAIL {e}")
        if rc == 0:
            print(f"check-cutoffs: {len(tasks)} tasks state the cutoff of scripts/task_cutoffs.toml "
                  "(task.toml, instruction.md, README, sim service)")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
