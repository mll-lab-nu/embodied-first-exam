#!/usr/bin/env python3
"""The agent's time cutoff (docs/protocol/README.md §2.12): each task sets its own, and says it once, at the end of its instruction.

The number is the task's `[agent] timeout_sec` in task.toml, set by its author (or its benchmark's generator) in the
pull request that adds or changes the task, as in Terminal-Bench; there is no table. For every task given (default:
every task):
  - `[agent] timeout_sec` is a whole positive number of seconds, at most 14400 (PROTOCOL D8; no benchmark is excepted);
  - instruction.md ends with the section scripts/task_conventions.py renders from that number, the last thing the agent
    reads: `## Time limit`, "You have N seconds to complete this task. Do not cheat by using online solutions or hints
    specific to this task." with the same N (Terminal-Bench's sentence), then what the cutoff means in the task's mode;
    nothing follows it, and the heading and the sentence stand there once;
  - nothing else in instruction.md states the agent's limit as a duration (the wordings tasks used before 2026-10-11:
    "wall-clock budget is 90 min (5400 s)", "You have 60 minutes of wall-clock time", "Time limit: one hour", ...; and
    the obvious other shapes: "You have one hour.", "The limit is 3600 seconds.", "Finish within 60 minutes."): two
    limits in one instruction are worse than none;
  - the README's "Agent time budget" row has the number;
  - standard modes: the `sim` service is told the same number (`RCB_WALL_CLOCK_S` in environment/docker-compose.yaml,
    what its `/spec` budget and `meta["time_left_s"]` report; PROTOCOL §2.3);
ADVISORY (the required CI job runs the twins' equal cutoffs, an invariant, in ci_checks/check-twins.py).

    python3 ci_checks/check-cutoffs.py [task dirs]      # default: every task
Fix: set `[agent] timeout_sec` in task.toml (or the generator's constant, then regenerate) and run
`python3 scripts/task_conventions.py tasks/<benchmark>/<task>`, which renders the rest from it. Standard library only.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402  (one renderer)

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


def number_errors(task: Path) -> list[str]:
    """What is wrong with the task's own number, `[agent] timeout_sec`; [] when it is usable."""
    try:
        v = tomllib.loads((task / "task.toml").read_text()).get("agent", {}).get("timeout_sec")
    except (OSError, tomllib.TOMLDecodeError) as e:
        return [f"task.toml: {e}"]
    if v is None:
        return ["task.toml has no `[agent] timeout_sec` (the agent's cutoff, set by the task's author; PROTOCOL §2.12)"]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0 or float(v) != int(v):
        return [f"[agent] timeout_sec = {v!r} is not a whole positive number of seconds"]
    if v > tc.CUTOFF_CAP:
        return [f"[agent] timeout_sec = {v:g} is above the {tc.CUTOFF_CAP} s cap (PROTOCOL D8, §2.3; no benchmark is excepted)"]
    return []


def check_task(task: Path) -> list[str]:
    try:
        mode = tc.mode_of(task)
    except ValueError as e:
        return [str(e)]
    errs = number_errors(task)
    if errs:
        return errs
    sec = tc.cutoff_for(task)
    bench = tc.bench_of(task)
    ins = (task / "instruction.md").read_text(encoding="utf-8") if (task / "instruction.md").is_file() else ""
    want = tc.render_cutoff(sec, mode, bench, task.name)
    if not ins.startswith("# "):
        errs.append("instruction.md does not start with its `# ` title line")
    if not ins.endswith("\n\n" + want):
        stated = re.findall(tc.CUTOFF_RE, ins)
        errs.append(f"instruction.md does not end with the `{tc.CUTOFF_HEADING}` section rendered for its {sec} s in {mode} mode "
                    "(the last thing the agent reads; nothing after it; run scripts/task_conventions.py on the task)"
                    + (f" (it says {', '.join(stated)} seconds)" if stated else " (the sentence is missing)"))
    if len(re.findall(tc.CUTOFF_RE, ins)) > 1 or len(re.findall(rf"(?m)^{re.escape(tc.CUTOFF_HEADING)}[ \t]*$", ins)) > 1:
        errs.append(f"instruction.md has the cutoff sentence or the `{tc.CUTOFF_HEADING}` heading more than once")
    errs += [f"instruction.md states the agent's limit a second time, outside `{tc.CUTOFF_HEADING}` ({x}); say "
             f"\"{tc.CUTOFF_REF}\" instead of a number" for x in other_limits(ins)]
    readme = (task / "README.md").read_text(encoding="utf-8") if (task / "README.md").is_file() else ""
    if f"| Agent time budget | {sec} s;" not in readme:
        errs.append(f"README.md's `Agent time budget` row does not say {sec} s")
    c = task / "environment/docker-compose.yaml"
    text = c.read_text() if c.is_file() else ""
    if mode in tc.SIDECAR_MODES and re.search(r"(?m)^  sim:", text):   # a task without a sim service has no budget to tell
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
                errs.append(f"environment/docker-compose.yaml: {tc.WALL_CLOCK_ENV} = {v}, the task's cutoff is {sec}")
    return errs


def main(argv: list[str]) -> int:
    every = tc.iter_tasks()
    tasks = [Path(a).resolve() for a in argv if (Path(a) / "task.toml").is_file()] if argv else every
    rc = 0
    for t in tasks:
        for e in check_task(t):
            rc = 1
            print(f"FAIL {t}: {e}")
    if rc == 0:
        print(f"check-cutoffs: {len(tasks)} tasks state their own cutoff (task.toml, instruction.md, README, sim service; "
              "the twins: check-twins.py)")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
