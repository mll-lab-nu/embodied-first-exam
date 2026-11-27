#!/usr/bin/env python3
"""ADVISORY hook: how RoboDojo's agent-ended (standard) episodes are judged when they end (owner 11-25, board 0309 D216 /
0611 D1=B). Run by ci_checks/run_all.sh with the task directories in scope.

- rcb_robodojo.END_JUDGEMENT classifies every one of RoboDojo's tasks, exactly the 54 the standard tasks run
  (`RCB_TASK` in each tasks/robodojo/*-standard/environment/docker-compose.yaml), as "end" or "history", each with its
  reason; the sim service refuses an agent-ended task the table does not name.
- each standard task in scope closes its Goal as its class says (scripts/task_conventions.py V2_AGENT_END_*): both say
  how to end the episode (V2_AGENT_END_GOAL); an "end" task then says that only the state at that point counts
  (V2_AGENT_END_STATE, or V2_AGENT_END_REST after the steps that count as they happen), a "history" task says what
  counts as it happens and not that; none carries retired wording (V2_AGENT_END_RETIRED).
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402

TOOL = ROOT / "embodied_first_exam/benchmarks/robodojo/privileged/environment/rcb_robodojo.py"
N_TASKS = 54


def table() -> dict:
    for node in ast.parse(TOOL.read_text()).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "END_JUDGEMENT" for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit(f"FAIL advisory-end-judgement: no END_JUDGEMENT in {TOOL.relative_to(ROOT)}")


def family(task: Path) -> str | None:
    p = task / "environment/docker-compose.yaml"
    m = re.search(r"^\s*RCB_TASK:\s*(\S+)", p.read_text(), re.M) if p.is_file() else None
    return m.group(1).strip("\"'") if m else None


def main(args: list[str]) -> int:
    errs: list[str] = []
    tab = table()
    std = sorted(p for p in (ROOT / "tasks/robodojo").glob("robodojo-*-standard") if p.is_dir())
    fams = {}
    for t in std:
        f = family(t)
        if f is None:
            errs.append(f"{t.name}: no RCB_TASK in environment/docker-compose.yaml")
        else:
            fams[t] = f
    if len(tab) != N_TASKS or len(set(fams.values())) != N_TASKS:
        errs.append(f"END_JUDGEMENT has {len(tab)} tasks and the standard tasks run {len(set(fams.values()))}; "
                    f"RoboDojo has {N_TASKS}")
    for f in sorted(set(fams.values()) - set(tab)):
        errs.append(f"{f}: a standard task runs it, but END_JUDGEMENT does not say how its episode is judged at the end")
    for f in sorted(set(tab) - set(fams.values())):
        errs.append(f"{f}: in END_JUDGEMENT, but no standard task runs it")
    for f, v in tab.items():
        if not (isinstance(v, tuple) and len(v) == 2 and v[0] in ("end", "history") and isinstance(v[1], str) and v[1]):
            errs.append(f"END_JUDGEMENT[{f!r}] = {v!r}: (\"end\" | \"history\", the reason)")
    scope = [Path(a).resolve() for a in args if a.strip()] or std
    checked = 0
    for t in std:
        if t.resolve() not in scope or fams.get(t) not in tab:
            continue
        checked += 1
        goal = (t / "instruction.md").read_text().split("\n## Goal\n", 1)[-1].split("\n## ", 1)[0]
        flat = " ".join(goal.split())
        kind = tab[fams[t]][0]
        at_end = any(w in flat for w in (tc.V2_AGENT_END_STATE, tc.V2_AGENT_END_REST,
                                         "judged on how things stand when the episode ends"))
        if not flat.count(tc.V2_AGENT_END_GOAL):
            errs.append(f"{t.name}: Goal does not say how to end the episode ({tc.V2_AGENT_END_GOAL!r})")
        if kind == "end" and not at_end:
            errs.append(f"{t.name}: END_JUDGEMENT says \"end\", but Goal does not say that only the state at the end "
                        f"counts ({tc.V2_AGENT_END_STATE!r})")
        if kind == "history" and (at_end or not re.search(r"\bcounts? as (?:it|they) happens?\b", flat)):
            errs.append(f"{t.name}: END_JUDGEMENT says \"history\": Goal must say what counts as it happens, and not that "
                        "the end state is judged")
        for w in tc.V2_AGENT_END_RETIRED:
            if w in flat:
                errs.append(f"{t.name}: Goal still has the retired wording {w!r}")
    if errs:
        print("FAIL advisory-end-judgement:\n  " + "\n  ".join(errs))
        return 1
    n_end = sum(v[0] == "end" for v in tab.values())
    print(f"ok advisory-end-judgement: END_JUDGEMENT classifies all {len(tab)} RoboDojo tasks ({n_end} end, "
          f"{len(tab) - n_end} history); {checked} standard Goal(s) say so")
    return 0


if __name__ == "__main__":
    sys.exit(main([a for line in sys.argv[1:] for a in line.split("\n")]))
