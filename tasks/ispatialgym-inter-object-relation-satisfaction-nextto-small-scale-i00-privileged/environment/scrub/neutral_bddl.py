"""Write the start-only BDDL problem of a privileged task: upstream's problem without what states the task.

  python neutral_bddl.py SRC_PROBLEM.bddl OUT_DIR

Kept: the domain, the objects (sorted: upstream lists the moved object first) and the positive :init atoms (where the
objects stand at the start, which the scene shows anyway). Dropped: comments, :variant (it names the relation and the
roles), the negative :init atoms (`(not (inside a b))` names the goal relation), :groups and the :init atoms on them,
:goal and :measure; the goal is
one neutral atom. The result is activity `task`, problem 0, written as OUT_DIR/task/problem0.bddl."""
import re
import sys
from pathlib import Path


def blocks(text: str) -> dict[str, str]:
    """Top-level `(:name ...)` sections of a BDDL problem, by name."""
    out, i = {}, 0
    while (m := re.compile(r"\(:([a-z_]+)").search(text, i)):
        depth, j = 0, m.start()
        for j in range(m.start(), len(text)):
            depth += {"(": 1, ")": -1}.get(text[j], 0)
            if depth == 0:
                break
        out[m.group(1)] = text[m.end():j].strip()
        i = j + 1
    return out


def atoms(body: str) -> list[str]:
    """The top-level parenthesised atoms of a section body."""
    out, depth, start = [], 0, None
    for k, c in enumerate(body):
        if c == "(":
            start = k if depth == 0 else start
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                out.append(" ".join(body[start:k + 1].split()))
    return out


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    text = "\n".join(line.split(";", 1)[0] for line in src.read_text().splitlines())
    b = blocks(text)
    objects = sorted(" ".join(line.split()) for line in b["objects"].splitlines() if line.strip())
    groups = {line.split("-")[-1].strip() for line in b.get("groups", "").splitlines() if "-" in line}     # their names name roles
    init = [a for a in atoms(b["init"]) if not a.startswith("(not") and not any(g in a.split() for g in groups)]
    lines = ["(define (problem task-0)", "    (:domain ispatialgym)", "", "    (:objects"]
    lines += [f"        {o}" for o in objects] + ["    )", "", "    (:init"] + [f"        {a}" for a in sorted(init)]
    # upstream's parser needs one goal atom that is not pose_settled: the robot standing on the floor (the start's own fact);
    # nothing in the agent's container judges it (rcb_ispatialgym.Session without goal.json)
    lines += ["    )", "", "    (:goal", "        (and", "            (ontop ?agent.n.01_1 ?floor.n.01_1)", "        )", "    )", ")", ""]
    (out / "task").mkdir(parents=True, exist_ok=True)
    (out / "task" / "problem0.bddl").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
