#!/usr/bin/env python3
"""Remove LabUtopia's reference solutions from a checkout (images/labutopia/Dockerfile runs this in the layer that
clones the repository, so no layer of the image holds them).

LabUtopia keeps a task's scripted solution and its success check in one place, `controllers/`: a state machine per
task (`controllers/<task>_controller.py`) on the motion primitives of `controllers/atomic_actions/`. The benchmark's
grader has its own copy of each check (rcb_labutopia.py); the image keeps what builds a scene and reads its state:
`tasks/`, `robots/`, `utils/`, `config/`, `assets/` and the two factories that construct a robot and a task.

    strip_solutions.py DIR            remove
    strip_solutions.py --check DIR    exit 1 unless DIR is a stripped checkout
"""
import os
import re
import shutil
import sys

REMOVE = [
    "controllers",  # the scripted solutions, their motion primitives, the policy-inference engines
    "policy",  # imitation-learning models and training code
    "data_collectors",  # demonstration recording
    "scripts",
    "tests",
    "main.py",  # the collection / evaluation loop that drives a controller
    "train.py",
    "train-muilt.py",
    "factories/controller_factory.py",
    "factories/collector_factory.py",
]
# what a solution file looks like, should one come back under another name
MARKS = re.compile(r"^\s*(?:from|import)\s+(?:controllers|policy|data_collectors)\b|def _step_collect\b|REQUIRED_SUCCESS_STEPS", re.M)


def problems(root: str) -> list:
    out = [f"still there: {p}" for p in REMOVE if os.path.lexists(os.path.join(root, p))]
    for d, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".py"):
                p = os.path.join(d, f)
                m = MARKS.search(open(p, encoding="utf-8", errors="replace").read())
                if m:
                    out.append(f"{os.path.relpath(p, root)}: {m.group(0).strip()!r}")
    for need in ("tasks/base_task.py", "robots/franka/franka.py", "utils/object_utils.py", "factories/task_factory.py", "config", "assets"):
        if not os.path.exists(os.path.join(root, need)):
            out.append(f"missing: {need}")
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--check"]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    root = args[0]
    if "--check" not in sys.argv:
        for p in REMOVE:
            q = os.path.join(root, p)
            if os.path.isdir(q) and not os.path.islink(q):
                shutil.rmtree(q)
            elif os.path.lexists(q):
                os.remove(q)
    bad = problems(root)
    for b in bad:
        print("strip_solutions:", b, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
