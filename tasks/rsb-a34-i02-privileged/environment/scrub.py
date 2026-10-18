"""Remove RoboSafeBench's scripted solutions from the privileged agent image (PROTOCOL H.2, docs/protocol/leakage.md).

The eai-robosafe image holds every family's scripted strategies: the reference handling of each member, the literal
execution, the named wrong and alternative trajectories (`Family.reference`, `comply`, `negatives`, `alternatives`, their
`_control` / `_pose` versions and `control_scripts`), which the standard tasks' references are compiled from. A
privileged agent reads the image, so before its container starts this script rewrites the installed package:

  - every function or method of those names in the families and prototypes keeps its signature and raises instead,
    and so does every function there that only they use (their private helpers: an AST call graph over the families'
    and prototypes' modules, to a fixed point; a name used anywhere else in the package, or outside a function, is kept);
  - the entry points that turn a scripted strategy into rows (`verify.scripted`, `verify.solver_named`, `verify.run`,
    `verify.compile.compile_strategy` / `_compile_strategy` / `oracle`) raise too;
  - the families' and prototypes' modules lose their comments and docstrings (they describe the scripted handling in
    prose); the code is re-emitted by `ast.unparse`, which changes no behaviour;
  - the compiled bytecode (__pycache__) and the source tree and wheel the image was built from are removed.

Scene building, physics, rendering, the hazard rules, the operator's answers and the verdict are untouched:
scripts/robosafe/privileged_oracles.py replays every privileged task's reference trajectory with the scrubbed package
and with the image's own, and requires the same end state and verdict.

    python scrub.py [PACKAGE_DIR]     # default: the installed robosafebench package
"""
from __future__ import annotations

import ast
import pathlib
import shutil
import sys

STRATEGIES = {"reference", "reference_control", "reference_pose", "comply", "comply_control", "comply_pose",
              "negatives", "negatives_pose", "alternatives", "alternatives_pose", "control_scripts",
              "label_control_scripts", "_reference_rung"}
# the package's own entry points from a strategy name to rows: {module path: names}
ENTRY_POINTS = {"verify/__init__.py": {"scripted", "solver_named", "run"},
                "verify/compile.py": {"compile_strategy", "_compile_strategy", "oracle"}}
PROSE_DIRS = ("families", "prototypes")          # modules whose comments and docstrings describe the solutions
BUILD_LEFTOVERS = ("/opt/rsb_final_wheels", "/opt/robosafe/tools")
MESSAGE = "RoboSafeBench's scripted solutions are not in the privileged image"


class Scrub(ast.NodeTransformer):
    def __init__(self, prose: bool, names: set):
        self.prose, self.names, self.removed = prose, names, 0

    def _body(self, node):
        if self.prose and node.body and isinstance(node.body[0], ast.Expr) and \
                isinstance(getattr(node.body[0], "value", None), ast.Constant) and isinstance(node.body[0].value.value, str):
            node.body = node.body[1:] or [ast.Pass()]
        return node

    def visit_FunctionDef(self, node):
        if node.name in self.names:
            self.removed += 1
            node.body = [ast.Raise(exc=ast.Call(func=ast.Name("NotImplementedError", ast.Load()),
                                                args=[ast.Constant(MESSAGE)], keywords=[]), cause=None)]
            node.decorator_list = [d for d in node.decorator_list if isinstance(d, ast.Name) and d.id in
                                   ("staticmethod", "classmethod", "property")]
            return node
        self.generic_visit(node)
        return self._body(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.generic_visit(node)
        return self._body(node)

    def visit_Module(self, node):
        self.generic_visit(node)
        return self._body(node)


def _refs(node) -> set:
    """Every identifier a piece of code names (a bare name or an attribute)."""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.isidentifier():
            out.add(n.value)                       # getattr(fam, "name"), tables keyed by a method's name
    return out


def _module_name(rel: pathlib.PurePath) -> str:
    parts = ["robosafebench", *rel.with_suffix("").parts]
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imports(tree, here: str) -> set:
    """The robosafebench modules a module imports (absolute or relative, anywhere in it)."""
    out = set()
    pkg = here.rsplit(".", 1)[0]
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ""
            if n.level:
                up = here.split(".")[:-n.level] if not here.endswith("__init__") else here.split(".")[:-n.level + 1]
                base = ".".join(up + ([n.module] if n.module else []))
            out.add(base)
            out.update(f"{base}.{a.name}" for a in n.names)
    return {m for m in out if m.startswith("robosafebench")}


def strategy_only(package: pathlib.Path, trees: dict) -> set:
    """The (module, name) pairs to blank in the families and prototypes: STRATEGIES, and to a fixed point every function
    defined there whose name is referenced only from inside functions already blanked. A reference counts where the
    code can reach the definition: for a module-level function, its own module or a module that imports it (a subclass,
    a helper import); for a method, any module, since a base class's code calls it through `self` (base.judge calls a
    family's `goal`). A name referenced at module or class level there, or by any function not blanked, is kept."""
    mods = {rel: _module_name(rel) for rel in trees}
    imports = {rel: _imports(tree, mods[rel]) for rel, tree in trees.items()}
    defs, calls, top = {}, {}, {}        # defs: (rel, name) -> [nodes]; calls: id(node) -> refs; top: rel -> refs
    funcs = {}                           # rel -> [(name, node, in_scope)]
    methods = set()                      # (rel, name) defined in a class
    for rel, tree in trees.items():
        scope = rel.parts[0] in PROSE_DIRS
        top[rel], funcs[rel] = set(), []

        def walk(node, in_class=False):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    calls[id(child)] = _refs(child) - {child.name}
                    funcs[rel].append((child.name, child, scope))
                    if scope:
                        defs.setdefault((rel, child.name), []).append(child)
                        if in_class:
                            methods.add((rel, child.name))
                    for d in child.decorator_list + [child.args]:
                        top[rel].update(_refs(d))
                elif isinstance(child, ast.ClassDef):
                    for b in child.bases + child.keywords + child.decorator_list:
                        top[rel].update(_refs(b))
                    walk(child, True)
                else:
                    top[rel].update(_refs(child))
        walk(tree)

    def readers(rel):
        """The modules whose code can reach a definition in `rel`: itself and every module importing it."""
        m = mods[rel]
        return [r for r in trees if r == rel or m in imports[r]]
    reach = {rel: readers(rel) for rel in trees if rel.parts[0] in PROSE_DIRS}
    everywhere = list(trees)             # a method is reached through `self` from any class above it (a base's judge)
    blank = {k for k in defs if k[1] in STRATEGIES}
    while True:
        more = set()
        for (rel, name) in defs:
            if (rel, name) in blank or name in STRATEGIES:
                continue
            ok, used = True, False
            for r in (everywhere if (rel, name) in methods else reach[rel]):
                if name in top[r]:
                    ok = False
                    break
                for fname, node, scope in funcs[r]:
                    if name in calls[id(node)]:
                        used = True
                        if not (scope and (r, fname) in blank):
                            ok = False
                            break
                if not ok:
                    break
            if ok and used:
                more.add((rel, name))
        if not more:
            return blank
        blank |= more


def scrub(package: pathlib.Path, leftovers: bool = True) -> dict:
    trees = {}
    for path in sorted(package.rglob("*.py")):
        trees[path.relative_to(package)] = ast.parse(path.read_text(), filename=str(path))
    blank = strategy_only(package, trees)
    files = removed = 0
    for rel, tree in trees.items():
        prose = rel.parts[0] in PROSE_DIRS
        names = {n for r, n in blank if r == rel} if prose else ENTRY_POINTS.get(rel.as_posix(), set())
        if not prose and not names:
            continue
        t = Scrub(prose, names)
        tree = ast.fix_missing_locations(t.visit(tree))
        (package / rel).write_text(ast.unparse(tree) + "\n")
        files += 1
        removed += t.removed
    for cache in sorted(package.rglob("__pycache__"), reverse=True):
        shutil.rmtree(cache)
    if leftovers:                        # the image's build inputs (not when testing on a hand-made package)
        for leftover in BUILD_LEFTOVERS:
            shutil.rmtree(leftover, ignore_errors=True)
        for p in pathlib.Path("/opt/robosafe").glob("**/*.py") if pathlib.Path("/opt/robosafe").is_dir() else ():
            p.unlink()
    return {"files_rewritten": files, "functions_removed": removed,
            "helpers_removed": sum(1 for _, n in blank if n not in STRATEGIES)}


def main() -> int:
    if len(sys.argv) > 1:
        package = pathlib.Path(sys.argv[1])
    else:
        import robosafebench
        package = pathlib.Path(robosafebench.__file__).resolve().parent
    out = scrub(package)
    if out["functions_removed"] < 100:
        raise SystemExit(f"scrub: only {out['functions_removed']} scripted functions found; the image is not the expected one")
    print(f"scrub: {out['files_rewritten']} files rewritten, {out['functions_removed']} functions removed "
          f"({out['helpers_removed']} helper names only the strategies use)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
