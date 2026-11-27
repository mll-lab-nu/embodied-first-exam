#!/usr/bin/env python3
"""Agent-ended episodes (docs/protocol/README.md §3 "Agent-ended episodes", required from protocol v3.0; Appendix H.3:
the service never shows the task's success). Two tiers:

  --tier invariants (the required CI job `invariants`, ci_checks/run_invariants.sh): every standard and realtime task
      served by an eai-standard service of its mode (scripts/task_conventions.py agent_end_required: MODE_REGISTRY
      "agent_end"; tasks a benchmark exports with a runtime of its own, Embodied Olympics Match and RoboEngineer, keep
      their own rules) has RCB_AGENT_END "1" in its sim service (that service's block of the compose file: the same
      line on another service, `main` say, does not count), the rendered finish line in its `## Robot Interface`
      (ROBOT_FINISH) and the rendered Finish line in its `## Limits` (LIMITS_FINISH);
  --tier advisory (ci_checks/run_all.sh): such a task's Goal says how to end the episode (V2_AGENT_END_GOAL; the
      Embodied Safety Exam's exits instead: an exit is the same as `/finish`), none of the retired finish wording
      (V2_AGENT_END_RETIRED and RETIRED_FINISH below) anywhere in the instruction but `## Limits`, which renders the
      Finish line, none of the wording of an episode that a success ends in its Goal, and nothing in its Goal on how
      the episode ends on its own (a time-out or step limit: Limits' Steps line).

    python3 ci_checks/check-agent-end.py [--tier invariants|advisory] [task dirs]    # default: invariants, every task
Standard library only; `normalize` writes the environment line, the Robot Interface finish line and the Finish line.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402

# Goal wording of an episode that a success ends (retired with v3.0 for every agent-ended task)
RETIRED = (r"ends as soon as", r"ends the moment", r"ends at the first success", r"a success ends the (?:run|trial)",
           r"the episode ends when the task is done", r"ends by itself as soon as", r"the service tells you that it ended",
           r"ends, as a success,")
# Finish wording retired on 11-26 besides task_conventions.V2_AGENT_END_RETIRED (which normalize's generator owns): the
# endpoint is named once, by the rendered lines (Robot Interface's finish line, Limits' Finish line)
RETIRED_FINISH = ("call finish (Robot Interface)", "ends when you call finish")
# Goal wording of how an episode ends on its own (owner 11-26): the time-out and the step limit are Limits' Steps line
GOAL_ENDS_ITSELF = (r"ends by itself", r"(?:judged|graded) as it stands", r"reason `", r"\bstep (?:limit|cap)\b",
                    r"horizon is reached", r"\btime-?out\b", r"runs out, the episode")


def goal_of(text: str) -> str:
    m = re.search(r"(?ms)^## Goal[ \t]*\n(.*?)(?=^## |\Z)", text or "")
    return " ".join(m.group(1).split()) if m else ""


def sim_service(compose: str) -> str:
    """The `sim` service's block of a compose file ("" when it has none, or the file has no top-level services:)."""
    lines = compose.splitlines(keepends=True)
    try:
        i, j = tc.rcb_monitor_inject.services_span(lines)
    except ValueError:
        return ""
    for name, k0, k1 in tc.rcb_monitor_inject.service_blocks(lines, i, j):
        if name == "sim":
            return "".join(lines[k0:k1])
    return ""


def without_limits(text: str) -> str:
    """The instruction without its `## Limits` section (the rendered Finish line lives there), whitespace folded."""
    return " ".join(re.sub(r"(?ms)^## Limits[ \t]*\n.*?(?=^## |\Z)", "", text or "").split())


def errors(tasks: list[Path], tier: str) -> list[str]:
    errs = []
    for t in tasks:
        if not (t / "task.toml").is_file() or not tc.agent_end_required(t):
            continue
        rel = t.relative_to(ROOT) if t.is_relative_to(ROOT) else t
        text = (t / "instruction.md").read_text(encoding="utf-8") if (t / "instruction.md").is_file() else ""
        if tier == "invariants":
            compose = tc.read_text(t / "environment/docker-compose.yaml") or ""
            if not tc.AGENT_END_RE.search(sim_service(compose)):
                errs.append(f"{rel}: its sim service does not set RCB_AGENT_END: \"1\" (agent-ended episodes are required "
                            "in standard and realtime mode, PROTOCOL §3; normalize writes it)")
            if not any(k == "Finish" for k, _ in tc.limits_lines(text)):
                errs.append(f"{rel}: instruction.md's `## Limits` has no Finish line (normalize renders it)")
            if not any(re.search(rf"(?m)^{re.escape(x)}$", text) for x in tc.ROBOT_FINISH):
                errs.append(f"{rel}: instruction.md's `## Robot Interface` has no finish line (normalize renders it)")
        else:
            g = goal_of(text)
            if tc.V2_AGENT_END_GOAL not in g and "An exit is the same as `/finish`" not in g:
                errs.append(f"{rel}: Goal does not say how to end the episode (V2_AGENT_END_GOAL)")
            rest = without_limits(text)
            for w in dict.fromkeys((*tc.V2_AGENT_END_RETIRED, *RETIRED_FINISH)):
                if w in rest:
                    errs.append(f"{rel}: instruction.md still has the retired finish wording {w!r} (outside `## Limits`)")
            for pat in RETIRED:
                if re.search(pat, g, re.I):
                    errs.append(f"{rel}: Goal says a success ends the episode ({pat!r}): an agent-ended episode ends at finish")
            for pat in GOAL_ENDS_ITSELF:
                if re.search(pat, g, re.I):
                    errs.append(f"{rel}: Goal says how the episode ends on its own ({pat!r}): that is Limits' Steps line")
    return errs


def main(argv: list[str]) -> int:
    tier = "invariants"
    if argv[:1] == ["--tier"]:
        tier, argv = argv[1], argv[2:]
    if tier not in ("invariants", "advisory"):
        print(__doc__)
        return 2
    tasks = [Path(a).resolve() for a in argv] if argv else [Path(p).resolve() for p in tc.iter_tasks()]
    errs = errors(tasks, tier)
    for e in errs:
        print(("FAIL " if tier == "invariants" else "WARN ") + e)
    n = sum(1 for t in tasks if (t / "task.toml").is_file() and tc.agent_end_required(t))
    if errs:
        print(f"check-agent-end ({tier}): {len(errs)} problem(s) in {n} agent-ended task(s)")
        return 1 if tier == "invariants" else 3
    print(f"ok check-agent-end ({tier}): {n} agent-ended task(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
