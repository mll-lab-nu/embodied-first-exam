#!/usr/bin/env python3
"""Image build step (images/molmospaces/Dockerfile, the same layer as the pip install): replace upstream's scripted
experts, molmo_spaces/policy/solvers (reference solutions, PROTOCOL §2.7), by stubs.

Upstream's configs refer to the expert classes by name while they are built (configs/policy_configs.py sets `policy_cls`
in `model_post_init`; evaluation_configs imports those configs), so every module stays importable with the same class
and function names, but each of them only raises: no planning code is left. The compiled copies (__pycache__) go too.
The check at the end fails the build if any other statement survives.

    python scrub_experts.py          # scrub the installed package, then check it
"""

import ast
import shutil
import sys
from pathlib import Path

import molmo_spaces

MSG = "upstream's scripted expert is a reference solution and is not shipped (robot coding bench, PROTOCOL §2.7)"
ROOT = Path(molmo_spaces.__file__).parent / "policy" / "solvers"


def stub(source: str) -> str:
    tree = ast.parse(source)
    out = [f'"""Scrubbed: {MSG}."""', ""]
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            out += [
                f"class {node.name}:",
                "    def __init__(self, *args, **kwargs):",
                f"        raise NotImplementedError({MSG!r})",
                "",
            ]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out += [f"def {node.name}(*args, **kwargs):", f"    raise NotImplementedError({MSG!r})", ""]
    return "\n".join(out)


def is_stub(source: str) -> bool:
    body = ast.parse(source).body
    allowed = (ast.ClassDef, ast.FunctionDef)
    if not all(isinstance(n, allowed) for n in body[1:]) or not (body and isinstance(body[0], ast.Expr)):
        return False
    for n in body[1:]:
        fn = n.body[0] if isinstance(n, ast.ClassDef) else n
        if len(getattr(n, "body", [])) != 1 or not isinstance(fn.body[0], ast.Raise):
            return False
    return True


def main() -> int:
    files = sorted(ROOT.rglob("*.py"))
    for p in files:
        p.write_text(stub(p.read_text()))
    for d in [d for d in ROOT.rglob("__pycache__") if d.is_dir()]:
        shutil.rmtree(d)
    bad = [str(p) for p in sorted(ROOT.rglob("*")) if p.is_file() and (p.suffix != ".py" or not is_stub(p.read_text()))]
    if bad:
        raise SystemExit("[scrub_experts] left in policy/solvers: " + ", ".join(bad))
    print(f"[scrub_experts] {len(files)} modules of {ROOT} replaced by stubs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
