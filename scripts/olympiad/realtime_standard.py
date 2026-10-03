"""README of a real-time sports task in the protocol v1.0 standard layout (docs/PROTOCOL.md §2.1).

Real-time sports tasks are standard-mode tasks (robot as a service) whose wire protocol is `eai-standard-realtime/1.0`
(docs/EAI_STANDARD_REALTIME_1_0.md); their task.toml sources already carry `mode = "standard"`, the protocol and the
oracle fields. This module renders the README: title, key table, Task, Difficulty, Reference solution, Verification,
Details.
"""

from api_errors import MAX_TRANSIENT_API_ERRORS

PROTOCOL = "eai-standard-realtime/1.0"
# The validity rule for model-API errors, the same in every task (docs/EAI_STANDARD_REALTIME_1_0.md, "Validity").
API_RULE = (f"Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model "
            f"call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; "
            f"`A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a "
            f"seat had an unrecovered error (no successful model call after it) or more than {MAX_TRANSIENT_API_ERRORS} "
            f"transient errors in the match.")


def readme(name, *, protocol=PROTOCOL, benchmark, family, oracle, oracle_evidence, budget_s, base_image, task, difficulty,
           reference, verification, details):
    rows = [("Benchmark", benchmark), ("Mode", f"standard (`{protocol}`)"),
            ("Twin", "— (standard only: real-time sports have no privileged twin)"),
            ("Simulator / robot", "`mujoco` / `franka-panda`"), ("Family / instance", family),
            ("Oracle", f"`{oracle}` — {oracle_evidence}"),
            ("Agent time budget", f"{budget_s} s; tokens: protocol default (PROTOCOL §5)"),
            ("Base image", f"`{base_image}`")]
    out = [f"# {name}", "", "| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows]
    for title, text in (("Task", task), ("Difficulty", difficulty), ("Reference solution", reference),
                        ("Verification", verification), ("Details", details)):
        out += ["", f"## {title}", text.strip()]
        if title == "Verification":
            out.append(API_RULE)
    return "\n".join(out) + "\n"
