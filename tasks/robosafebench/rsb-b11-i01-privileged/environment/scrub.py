"""Remove RoboSafeBench's scripted solutions from the privileged agent image (PROTOCOL H.2, docs/protocol/leakage.md).

The eai-robosafe image holds every family's scripted strategies: the reference handling of each member, the literal
execution, the named wrong and alternative trajectories (`Family.reference`, `comply`, `negatives`, `alternatives`, their
`_control` / `_pose` versions and `control_scripts`), which the standard tasks' references are compiled from. A
privileged agent reads the image, so before its container starts this script rewrites the installed package:

  - every function or method of those names in the families and prototypes keeps its signature and raises instead,
    and so does every function there that only they use (their private helpers: an AST call graph over the families'
    and prototypes' modules, to a fixed point; a name used anywhere else in the package, or outside a function, is kept);
  - the scripted step of a chore (track G: `step(..., do)`, a `"do"` entry of a step dict) becomes None, and the
    function or closure it named raises (a closure defined where it is passed) or, when only such steps used it, is
    blanked like a strategy's helper;
  - a module- or class-level constant of the families and prototypes that only the removed code read (a stop text, a
    question that names a hidden hazard, a waypoint of the safe route) becomes None;
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
              "label_control_scripts", "_reference_rung", "benign_negatives"}
STEP_FUNCS = {"step"}                            # track_g.step(id, kind, text, done, do, ...): its `do` is a scripted step
STEP_DO_INDEX = 4
# the package's own entry points from a strategy name to rows: {module path: names}
ENTRY_POINTS = {"verify/__init__.py": {"scripted", "solver_named", "run"},
                "verify/compile.py": {"compile_strategy", "_compile_strategy", "oracle"}}
PROSE_DIRS = ("families", "prototypes")          # modules whose comments and docstrings describe the solutions
BUILD_LEFTOVERS = ("/opt/rsb_final_wheels", "/opt/robosafe/tools")
MESSAGE = "RoboSafeBench's scripted solutions are not in the privileged image"


def do_values(node) -> list:
    """The expressions a piece of code hands over as a chore's scripted step: argument 4 or `do=` of a `step(...)` call,
    and the value of a `"do"` key of a dict literal."""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func.id if isinstance(n.func, ast.Name) else n.func.attr if isinstance(n.func, ast.Attribute) else None
            if f in STEP_FUNCS:
                if len(n.args) > STEP_DO_INDEX:
                    out.append(n.args[STEP_DO_INDEX])
                out += [k.value for k in n.keywords if k.arg == "do"]
        elif isinstance(n, ast.Dict):
            out += [v for k, v in zip(n.keys, n.values) if isinstance(k, ast.Constant) and k.value == "do"]
    return out


def _blank(node) -> None:
    node.body = [ast.Raise(exc=ast.Call(func=ast.Name("NotImplementedError", ast.Load()),
                                        args=[ast.Constant(MESSAGE)], keywords=[]), cause=None)]
    node.decorator_list = [d for d in node.decorator_list if isinstance(d, ast.Name) and d.id in
                           ("staticmethod", "classmethod", "property")]


class Scrub(ast.NodeTransformer):
    def __init__(self, prose: bool, names: set):
        self.prose, self.names, self.removed = prose, names, 0
        self.found: set = set()          # the names blanked here
        self.steps = 0                   # scripted chore steps (do values) removed
        self.closures: set = set()       # the names of closures handed over as a do value, in the function being visited
        self.do_ids: set = set()         # id() of the do values of the module (prose modules only)

    def visit(self, node):
        if isinstance(node, ast.Module) and self.prose:
            self.do_ids = {id(v) for v in do_values(node)}
        return super().visit(node)

    def generic_visit(self, node):
        if self.prose:                   # a do value -> None (fields holding one: call args, keywords, dict values)
            for field, old in ast.iter_fields(node):
                if isinstance(old, list):
                    for i, v in enumerate(old):
                        if isinstance(v, ast.AST) and id(v) in self.do_ids:
                            old[i] = ast.Constant(None)
                            self.steps += 1
                elif isinstance(old, ast.AST) and id(old) in self.do_ids:
                    setattr(node, field, ast.Constant(None))
                    self.steps += 1
        return super().generic_visit(node)

    def _body(self, node):
        if self.prose and node.body and isinstance(node.body[0], ast.Expr) and \
                isinstance(getattr(node.body[0], "value", None), ast.Constant) and isinstance(node.body[0].value.value, str):
            node.body = node.body[1:] or [ast.Pass()]
        return node

    def visit_FunctionDef(self, node):
        if node.name in self.names or node.name in self.closures:
            self.removed += 1
            self.found.add(node.name)
            _blank(node)
            return node
        outer = self.closures
        if self.prose:                   # closures defined here and handed over as a scripted step
            self.closures = {v.id for v in do_values(node) if isinstance(v, ast.Name) and id(v) in self.do_ids}
        self.generic_visit(node)
        self.closures = outer
        return self._body(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.generic_visit(node)
        return self._body(node)

    def visit_Module(self, node):
        self.generic_visit(node)
        return self._body(node)


def _walk(node, skip: set):
    """ast.walk without the subtrees whose id() is in skip."""
    todo = [node]
    while todo:
        n = todo.pop()
        if id(n) in skip:
            continue
        yield n
        todo.extend(ast.iter_child_nodes(n))


def _refs(node, skip: set = frozenset()) -> set:
    """Every identifier a piece of code names (a bare name or an attribute), outside the subtrees in skip."""
    out = set()
    for n in _walk(node, skip):
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


def _imports(tree, here: str, is_pkg: bool = False) -> set:
    """The robosafebench modules a module imports (absolute or relative, anywhere in it). is_pkg: the module is a
    package's __init__.py (`here` is the package), where `from . import x` is relative to the package itself."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ""
            if n.level:
                parts = here.split(".")
                up = parts[:len(parts) - n.level + int(is_pkg)]
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
    imports = {rel: _imports(tree, mods[rel], rel.name == "__init__.py") for rel, tree in trees.items()}
    defs, calls, top = {}, {}, {}        # defs: (rel, name) -> [nodes]; calls: id(node) -> refs; top: rel -> refs
    funcs = {}                           # rel -> [(name, node, in_scope)]
    methods = set()                      # (rel, name) defined in a class
    steps = {}                           # rel -> refs of its scripted chore steps (do values: removed, like a strategy)
    for rel, tree in trees.items():
        scope = rel.parts[0] in PROSE_DIRS
        top[rel], funcs[rel] = set(), []
        dv = do_values(tree) if scope else []
        skip = {id(v) for v in dv}
        steps[rel] = set().union(*(_refs(v) for v in dv)) if dv else set()

        def walk(node, in_class=False):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    calls[id(child)] = _refs(child, skip) - {child.name}
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
                    top[rel].update(_refs(child, skip))
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
                used = used or (r in steps and name in steps[r])
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


ATTR_FUNCS = {"getattr", "hasattr", "setattr", "delattr"}


def _reads(trees: dict) -> tuple:
    """What the package's code reads, scoped: (bare names loaded, per module; attributes loaded anywhere; identifier
    strings given to getattr / hasattr or listed in an __all__, anywhere). A bare name reaches a module's constant only
    from that module and the modules importing it directly (a constant of a class only from its class body); an
    attribute or getattr from anywhere."""
    names, attrs, strs = {}, set(), set()
    for rel, tree in trees.items():
        names[rel] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                names[rel].add(n.id)
            elif isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load):
                attrs.add(n.attr)
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ATTR_FUNCS and \
                    len(n.args) > 1 and isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str):
                strs.add(n.args[1].value)
            elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets):
                strs.update(c.value for c in ast.walk(n.value) if isinstance(c, ast.Constant) and isinstance(c.value, str))
    return names, attrs, strs


def _is_read(rd: tuple, reach: list, name: str, in_class: bool) -> bool:
    names, attrs, strs = rd
    if name in attrs or name in strs:
        return True
    if in_class:
        return False                     # a class constant is read through an attribute (self.X, Cls.X) or getattr
    return any(name in names[r] for r in reach)   # `from M import X` then X: a bare name in an importer of M


def _constants(tree):
    """The module- and class-level assignments of a module whose targets are all plain names:
    (statement, names, the class body it is in or None)."""
    todo = [(st, None) for st in tree.body]
    while todo:
        st, cls = todo.pop()
        if isinstance(st, ast.ClassDef):
            todo.extend((x, st) for x in st.body)
        elif isinstance(st, (ast.Assign, ast.AnnAssign)) and st.value is not None:
            targets = st.targets if isinstance(st, ast.Assign) else [st.target]
            if all(isinstance(t, ast.Name) for t in targets):
                yield st, {t.id for t in targets}, cls


def _reach(trees: dict) -> dict:
    """rel -> the modules whose bare names can reach its top level: itself and the modules importing it."""
    mods = {rel: _module_name(rel) for rel in trees}
    imports = {rel: _imports(tree, mods[rel], rel.name == "__init__.py") for rel, tree in trees.items()}
    return {rel: [r for r in trees if r == rel or mods[rel] in imports[r]] for rel in trees}


def drop_constants(before: set, trees: dict) -> set:
    """Constants of the families and prototypes that the package read before the scrub and reads no more (only removed
    code read them: a stop text, a question naming a hidden hazard, a waypoint): their value -> None, to a fixed point."""
    dropped, reach = set(), _reach(trees)
    while True:
        after, more = _reads(trees), 0
        for rel, tree in trees.items():
            if rel.parts[0] not in PROSE_DIRS:
                continue
            for st, names, cls in _constants(tree):
                if isinstance(st.value, ast.Constant) and st.value.value is None:
                    continue
                own = set() if cls is None else {n.id for x in cls.body if x is not st for n in ast.walk(x)
                                                  if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
                was = any(_is_read(before, reach[rel], n, cls is not None) for n in names)
                now = any(_is_read(after, reach[rel], n, cls is not None) or n in own for n in names)
                if was and not now:
                    st.value = ast.Constant(None)
                    dropped |= {(rel, n) for n in names}
                    more += 1
        if not more:
            return dropped


def step_factories(trees: dict, blank: set) -> set:
    """Methods a chore's scripted step is built by (`do` = `self.m(...)`, e.g. a `_fill(inst)` that returns the closure),
    defined in the class of that call, that no other code of the families and prototypes, or of a module importing
    them, reaches (bare-name clashes elsewhere in the package, `self._fill` of the simulator, do not keep them)."""
    scope = [rel for rel, t in trees.items() if rel.parts[0] in PROSE_DIRS
             or any(m.startswith(("robosafebench.families", "robosafebench.prototypes"))
                    for m in _imports(t, _module_name(rel), rel.name == "__init__.py"))]
    cand = set()
    for rel, tree in trees.items():
        if rel.parts[0] not in PROSE_DIRS:
            continue
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            own = {f.name for f in cls.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
            for v in do_values(cls):
                if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and \
                        isinstance(v.func.value, ast.Name) and v.func.value.id == "self" and v.func.attr in own:
                    cand.add((rel, v.func.attr))
    cand -= blank
    if not cand:
        return set()
    refs = set()
    for rel in scope:
        tree = trees[rel]
        skip = {id(v) for v in do_values(tree)}
        todo = [(n, False) for n in tree.body]
        while todo:
            n, _ = todo.pop()
            if isinstance(n, ast.ClassDef):
                todo.extend((x, True) for x in n.body)
                refs |= set().union(*(_refs(b, skip) for b in n.bases + n.decorator_list)) if n.bases or n.decorator_list else set()
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if (rel, n.name) not in blank and (rel, n.name) not in cand:
                    refs |= _refs(n, skip) - {n.name}
            else:
                refs |= _refs(n, skip)
    return {(rel, m) for rel, m in cand if m not in refs}


def scrub(package: pathlib.Path, leftovers: bool = True) -> dict:
    trees = {}
    for path in sorted(package.rglob("*.py")):
        trees[path.relative_to(package)] = ast.parse(path.read_text(), filename=str(path))
    before = _reads(trees)
    blank = strategy_only(package, trees)
    blank |= step_factories(trees, blank)
    removed = steps = 0
    touched = set()
    for rel, tree in list(trees.items()):
        prose = rel.parts[0] in PROSE_DIRS
        names = {n for r, n in blank if r == rel} if prose else ENTRY_POINTS.get(rel.as_posix(), set())
        if not prose and not names:
            continue
        t = Scrub(prose, names)
        trees[rel] = ast.fix_missing_locations(t.visit(tree))
        touched.add(rel)
        removed += t.removed
        steps += t.steps
        missing = ENTRY_POINTS.get(rel.as_posix(), set()) - t.found
        if missing and leftovers:                    # the package changed: never ship an image with an entry point left in
            raise SystemExit(f"scrub: {rel}: entry points not found: {sorted(missing)}")
    absent = [m for m in ENTRY_POINTS if pathlib.PurePosixPath(m) not in trees]
    if absent and leftovers:
        raise SystemExit(f"scrub: modules with entry points not in the package: {absent}")
    dropped = drop_constants(before, trees)
    touched |= {rel for rel, _ in dropped}
    for rel in sorted(touched):
        (package / rel).write_text(ast.unparse(trees[rel]) + "\n")
    files = len(touched)
    for cache in sorted(package.rglob("__pycache__"), reverse=True):
        shutil.rmtree(cache)
    if leftovers:                        # the image's build inputs (not when testing on a hand-made package)
        for leftover in BUILD_LEFTOVERS:
            shutil.rmtree(leftover, ignore_errors=True)
        for p in pathlib.Path("/opt/robosafe").glob("**/*.py") if pathlib.Path("/opt/robosafe").is_dir() else ():
            p.unlink()
        left = [x for x in BUILD_LEFTOVERS if pathlib.Path(x).exists()] + \
            [str(p) for p in pathlib.Path("/opt/robosafe").glob("**/*.py")]
        if left:
            raise SystemExit(f"scrub: build inputs left in the image: {left[:5]}")
    return {"files_rewritten": files, "functions_removed": removed,
            "helpers_removed": sum(1 for _, n in blank if n not in STRATEGIES),
            "steps_removed": steps, "constants_removed": len(dropped)}


def main() -> int:
    if len(sys.argv) > 1:
        package = pathlib.Path(sys.argv[1])
    else:
        import robosafebench
        package = pathlib.Path(robosafebench.__file__).resolve().parent
    out = scrub(package, leftovers=len(sys.argv) == 1)   # a package given: a copy, never this machine's build inputs
    if out["functions_removed"] < 100:
        raise SystemExit(f"scrub: only {out['functions_removed']} scripted functions found; the image is not the expected one")
    print(f"scrub: {out['files_rewritten']} files rewritten, {out['functions_removed']} functions removed "
          f"({out['helpers_removed']} helper names only the strategies use), {out['steps_removed']} scripted chore steps, "
          f"{out['constants_removed']} constants only they read")
    return 0


if __name__ == "__main__":
    sys.exit(main())
