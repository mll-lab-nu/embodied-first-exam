#!/usr/bin/env python3
"""Agent-ended episodes (docs/protocol/README.md §3 "Agent-ended episodes", required from protocol v3.0; Appendix H.3:
the service never shows the task's success). Two tiers:

  --tier invariants (the required CI job `invariants`, ci_checks/run_invariants.sh): every standard and realtime task
      served by an eai-standard service of its mode (scripts/task_conventions.py agent_end_required: MODE_REGISTRY
      "agent_end"; tasks a benchmark exports with a runtime of its own, Embodied Olympics Match and RoboEngineer, keep
      their own rules) has RCB_AGENT_END "1" in its sim service and the rendered Finish line in its `## Limits`;
  --tier advisory (ci_checks/run_all.sh): such a task's Goal says how the episode is judged and ends
      (V2_AGENT_END_GOAL, or RoboDojo's V2_AGENT_END_ENDS) and none of the wording of an episode that a success ends.

    python3 ci_checks/check-agent-end.py [--tier invariants|advisory] [task dirs]    # default: invariants, every task
Standard library only; `normalize` writes the environment line and the Finish line.
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


def goal_of(text: str) -> str:
    m = re.search(r"(?ms)^## Goal[ \t]*\n(.*?)(?=^## |\Z)", text or "")
    return " ".join(m.group(1).split()) if m else ""


def errors(tasks: list[Path], tier: str) -> list[str]:
    errs = []
    for t in tasks:
        if not (t / "task.toml").is_file() or not tc.agent_end_required(t):
            continue
        rel = t.relative_to(ROOT) if t.is_relative_to(ROOT) else t
        text = (t / "instruction.md").read_text(encoding="utf-8") if (t / "instruction.md").is_file() else ""
        if tier == "invariants":
            compose = tc.read_text(t / "environment/docker-compose.yaml") or ""
            if not tc.AGENT_END_RE.search(compose):
                errs.append(f"{rel}: its sim service does not set RCB_AGENT_END: \"1\" (agent-ended episodes are required "
                            "in standard and realtime mode, PROTOCOL §3; normalize writes it)")
            if not any(k == "Finish" for k, _ in tc.limits_lines(text)):
                errs.append(f"{rel}: instruction.md's `## Limits` has no Finish line (normalize renders it)")
        else:
            g = goal_of(text)
            if tc.V2_AGENT_END_GOAL not in g and " ".join(tc.V2_AGENT_END_ENDS.split()) not in g:
                errs.append(f"{rel}: Goal does not end with how the episode is judged and ends (V2_AGENT_END_GOAL)")
            for pat in RETIRED:
                if re.search(pat, g, re.I):
                    errs.append(f"{rel}: Goal says a success ends the episode ({pat!r}): an agent-ended episode ends at finish")
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
