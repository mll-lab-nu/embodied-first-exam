"""Remove complete task solvers from the agent simulator installation.

This reduces accidental answer exposure; it is not a security boundary for root.
General SkillLib and native task success predicates are deliberately unchanged.
"""
import ast
from pathlib import Path
import shutil
import sys

root = Path(sys.argv[1])
count = 0
for path in root.rglob("*.py"):
    text = path.read_text()
    tree = ast.parse(text)
    spans = [(node.lineno, node.end_lineno) for node in ast.walk(tree)
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name == "get_expert_skill_sequence"]
    lines = text.splitlines(keepends=True)
    for start, end in sorted(spans, reverse=True):
        indent = lines[start-1][:len(lines[start-1])-len(lines[start-1].lstrip())]
        lines[start-1:end] = [indent+"# Complete task oracle omitted from agent runtime.\n"]
    if spans:
        # All affected native classes contain other methods.
        result = "".join(lines)
        ast.parse(result)
        path.write_text(result)
        count += len(spans)
for rel in ("configs/evaluation", "evaluation", "policies"):
    path = root / rel
    if path.exists(): shutil.rmtree(path)
for path in root.rglob("__pycache__"):
    shutil.rmtree(path)
print(f"Removed {count} complete task oracle methods")
