"""Remove VLABench's reference solutions from the image (every task, every mode, the verifier too).

- every method named `get_expert_skill_sequence` (the scripted expert for each task) is replaced by a comment;
- `configs/task2code.json` (an operation sequence per task: which skills to call on which objects) is deleted; no
  runtime code reads it;
- the evaluation code and configs (`evaluation/`, `configs/evaluation/`) and any `policies/` are deleted.
VLABench's general skill library (VLABench.utils.skill_lib) and its task success predicates are kept: the privileged
mode offers the skills as planning primitives, and the verifier grades with the predicates.

    python strip_experts.py /opt/VLABench/VLABench
"""

import ast
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1])
count = 0
for path in sorted(root.rglob("*.py")):
    text = path.read_text()
    spans = [
        (node.lineno, node.end_lineno)
        for node in ast.walk(ast.parse(text))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "get_expert_skill_sequence"
    ]
    if not spans:
        continue
    lines = text.splitlines(keepends=True)
    for start, end in sorted(spans, reverse=True):
        indent = lines[start - 1][: len(lines[start - 1]) - len(lines[start - 1].lstrip())]
        lines[start - 1 : end] = [indent + "# The task's expert skill sequence is not part of this image.\n"]
    result = "".join(lines)
    ast.parse(result)  # every class keeps other members, so the module still parses
    path.write_text(result)
    count += len(spans)
for rel in ("configs/task2code.json", "configs/evaluation", "evaluation", "policies"):
    p = root / rel
    if p.is_dir():
        shutil.rmtree(p)
    elif p.exists():
        p.unlink()
for p in list(root.rglob("__pycache__")):
    shutil.rmtree(p)
left = [str(p) for p in root.rglob("*.py") if "def get_expert_skill_sequence" in p.read_text()]
assert not left, left
print(f"removed {count} expert methods")
