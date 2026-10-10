#!/usr/bin/env python3
"""Remove AutoBio's scripted experts from a checkout (images/autobio/Dockerfile runs this in the layer that clones it).

Every AutoBio task module defines its task (`class X(Task)`: scene, reset, the success check `check()`), then its
scripted expert (`class XExpert(X, Expert)`: the motion sequence that solves it), binds it (`X.Expert = XExpert`) and
ends with a `__main__` block that runs the expert to generate demonstrations. The experts are this benchmark's reference
solutions (PROTOCOL §2.7): this script deletes, from every module, each top-level class that derives from `Expert`, the
`X.Expert = ...` binding and the `__main__` block, and leaves every other line of the file as it is. `task.py` keeps its
empty `Expert` base class (the task modules import it); its `create_expert` goes.

    python strip_experts.py /opt/AutoBio/autobio          # edits in place, prints what it removed
    python strip_experts.py --check /opt/AutoBio/autobio   # exit 1 if anything is left to remove
"""

import ast
import pathlib
import sys


def is_main_guard(node: ast.AST) -> bool:
    t = getattr(node, "test", None)
    return (
        isinstance(node, ast.If)
        and isinstance(t, ast.Compare)
        and isinstance(t.left, ast.Name)
        and t.left.id == "__name__"
    )


def spans(tree: ast.Module, is_task_py: bool) -> list:
    """(first line, last line, what) of every top-level statement to delete."""
    out = []
    for node in tree.body:
        what = None
        if isinstance(node, ast.ClassDef):
            bases = {b.id if isinstance(b, ast.Name) else getattr(b, "attr", "") for b in node.bases}
            if "Expert" in bases:
                what = f"class {node.name}"
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Attribute) and t.attr == "Expert":
                    what = f"{ast.unparse(t)} = ..."
        elif isinstance(node, ast.FunctionDef) and is_task_py and node.name == "create_expert":
            what = "def create_expert"
        elif is_main_guard(node):
            what = "__main__ block"
        if what:
            first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
            out.append((first, node.end_lineno, what))
    return out


def main() -> int:
    check = "--check" in sys.argv
    root = pathlib.Path([a for a in sys.argv[1:] if not a.startswith("--")][0])
    left = 0
    for path in sorted(root.glob("*.py")):
        src = path.read_text()
        todo = spans(ast.parse(src), path.name == "task.py")
        if not todo:
            continue
        left += len(todo)
        if check:
            print(f"{path.name}: still has " + ", ".join(w for _, _, w in todo))
            continue
        lines = src.splitlines(keepends=True)
        for first, last, _ in sorted(todo, reverse=True):
            del lines[first - 1 : last]
        path.write_text("".join(lines))
        ast.parse(path.read_text())  # still a valid module
        print(f"{path.name}: removed " + ", ".join(f"{w} ({last - first + 1} lines)" for first, last, w in todo))
    for cache in root.rglob("__pycache__"):
        for f in cache.iterdir():
            f.unlink()
        cache.rmdir()
    if check and left:
        return 1
    if not check and not left:
        print("nothing to remove: is this an AutoBio checkout?", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
