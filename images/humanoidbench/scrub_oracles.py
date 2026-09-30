"""Remove upstream's answer keys from the image: pretrained policies, published scores, the reward formula.

WHAT GOES
  data/reach_*/          the hierarchical baseline's trained REACHING policies. A ready-made submission
                         for `reach` and a head start on every manipulation task. "No torch in the image"
                         is not a defence: a .pt is pickled tensors and the net is a few hundred KB.
  logs/*.json            the paper's training curves -- they hand over the achievable return per task.
  dreamerv3/ jaxrl_m/    the paper's baseline training harnesses, and mjx/ its JAX reimplementation.
  ppo/ tdmpc2/ mjx/      Nothing imports them; they exist to solve these tasks.
  every get_reward()     THE SCORING FORMULA, plus the constants and weights that exist only to
  outside KEEP           parameterise it. Reading `Sit.get_reward()` turns "sit on the chair" into
                         "put qpos[2] in [0.68, 0.72]" -- control becomes inversion of an expression, and
                         we measured an agent doing exactly that (docs/LEAKAGE.md).

  Deleting the methods is enough because upstream's own `Task.get_reward()` returns `(0, {})`: the base
  takes over, every environment still steps, and nothing else changes. `Session` sees the override is
  gone and reports no return (shared/rcb_hb.py), so the agent is told plainly rather than fed a zero.
  The constants and weights need the two rules in drop_dead_globals / prune_reward_params, because a
  name match cannot tell a scoring parameter from a description of the task.
  The helpers the formula called are not named *reward* either, so they are settled by what still calls
  them (drop_dead_helpers / drop_unread_returns), and a comment that mentions the reward goes with it
  (drop_reward_comments).

WHAT STAYS
  `get_terminated` (an agent discovers it in one rollout -- dynamics, not scoring), `get_obs`,
  `success_bar`, and any constant a class body still assigns: `_WALK_SPEED`/`_RUN_SPEED` via `_move_speed`, which
  only get_reward read -- the move term's bound and margin, an open gap (docs/LEAKAGE.md).

THE FORMULA IS NOT LOST
  scripts/humanoidbench/rewards.json holds it -- built by running THIS script against a copy and diffing,
  so the two sides cannot drift. gen_tasks.py ships one family's entry in that task's tests/, which the
  verifier's own container is built from, and grade.py patches it back before scoring. The verifier
  therefore runs upstream's exact code and our numbers stay comparable with the paper.

TWO PHASES, because `verify` imports the package it checks:
  `delete`  runs in the SAME Docker layer as the clone (see the Dockerfile: a later layer cannot unwrite
            an earlier one), before pip install.
  `verify`  runs after the install. Fails loudly if anything is left.

See docs/LEAKAGE.md for the general checklist this implements.
"""
import ast
import io
import pathlib
import re
import shutil
import sys
import tokenize

ROOT = pathlib.Path("/opt/humanoid-bench")
PKG = ROOT / "humanoid_bench"
REWARD_METHOD = re.compile(r"reward", re.I)

# Two reward-shaped methods have to survive, and both are plumbing rather than scoring:
#   tasks.py     Task.get_reward -- the base `return 0, {}`. It IS the mechanism: deleting the subclass
#                overrides works precisely because this one takes over.
#   wrappers.py  BaseWrapper.get_reward -- `return self.task.get_reward()`, a forward with no formula in
#                it; removing it would break the wrapper for nothing.
# Everything else is scrubbed wherever it lives. That includes assets/kitchen/, which carries the Franka
# Kitchen originals: `KitchenBase._get_reward_n_score` holds the subtask-completion test the `kitchen`
# task is graded on. Nothing imports it -- it is dead code -- but dead code is still readable, and the
# first version of this script only scanned envs/ and left it behind.
KEEP = {PKG / "tasks.py", PKG / "wrappers.py"}

# The tooling every task ships, COPYed in for the scrub (see the Dockerfile). It reads the package like any
# other code: rcb_hb.py calls `update_move_direction()` for the bookkeeping upstream does only inside
# get_reward, so that helper must survive even though nothing in the package calls it any more.
TOOLING = [pathlib.Path("/tmp/rcb_hb.py")]


def reward_modules() -> list[pathlib.Path]:
    return [f for f in sorted(PKG.rglob("*.py")) if f not in KEEP]


def scrub_rewards(path: pathlib.Path) -> tuple[list[str], set[str], dict[str, bool]]:
    """Delete every reward-shaped method from one module.

    Returns (qualnames removed, names those methods read, what they called on self) -- the second half is
    what drop_dead_globals needs to tell a constant that existed for the formula from one that is merely
    unused, the third what the helper rules need.

    Line-based rather than ast.unparse-based on purpose: unparsing rewrites the whole file (dropping
    comments and normalising formatting), which would make the diff against upstream unreadable and hide
    what else we changed. Cutting the exact line spans keeps every other byte identical.
    """
    return _cut_methods(path, lambda name: bool(REWARD_METHOD.search(name)))


def _cut_methods(path: pathlib.Path, pick) -> tuple[list[str], set[str], dict[str, bool]]:
    src = path.read_text()
    lines = src.split("\n")
    cuts, removed, read, calls = [], [], set(), {}
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.ClassDef):
            continue
        for m in node.body:
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and pick(m.name):
                start = min([d.lineno for d in m.decorator_list] + [m.lineno])
                cuts.append((start - 1, m.end_lineno))
                removed.append(f"{path.stem}.{node.name}.{m.name}")
                read |= _loaded_names(m)
                _merge(calls, _self_calls(m))
    if not cuts:
        return [], set(), {}
    drop = {i for a, b in cuts for i in range(a, b)}
    path.write_text("\n".join(l for i, l in enumerate(lines) if i not in drop))
    return removed, read, calls


def _loaded_names(tree: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def _merge(into: dict[str, bool], more: dict[str, bool]) -> None:
    for k, v in more.items():
        into[k] = into.get(k, False) or v


def _self_calls(tree: ast.AST) -> dict[str, bool]:
    """{name: is the return value used?} for every `self.name(...)` under `tree`. A call that is a statement
    of its own throws its value away; any other call may use it."""
    alone = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr)}
    out: dict[str, bool] = {}
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"):
            _merge(out, {n.func.attr: id(n) not in alone})
    return out


def surviving_uses() -> dict[str, bool]:
    """{name: may its return value be used?} for every attribute that the rest of the package (KEEP included)
    or the tooling still touches. `x.name(...)` as a statement of its own throws the value away, any other
    use of `x.name` may keep it, and a string equal to the name (hasattr, getattr) reaches it without a value."""
    missing = [str(t) for t in TOOLING if not t.is_file()]
    if missing:
        raise SystemExit(f"tooling not found: {missing} -- without it a helper it calls would look dead")
    out: dict[str, bool] = {}
    for f in [*sorted(PKG.rglob("*.py")), *TOOLING]:
        tree = ast.parse(f.read_text())
        alone = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr)}
        called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                _merge(out, {n.func.attr: id(n) not in alone})
            elif isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load) and id(n) not in called:
                _merge(out, {n.attr: True})
            elif isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.isidentifier():
                _merge(out, {n.value: False})
    return out


def drop_dead_helpers(path: pathlib.Path, dead: set[str]) -> tuple[list[str], set[str], dict[str, bool]]:
    """Delete the methods named in `dead`: helpers the formula called that nothing surviving calls. Dead because of
    the removal, and still readable -- truck's `upon_table()` is the placement test the table bonus is paid on,
    down to the coordinates. Returns what scrub_rewards returns, so what only these read can go next."""
    return _cut_methods(path, lambda name: name in dead)


def _value_return(s: ast.AST) -> bool:
    return isinstance(s, ast.Return) and s.value is not None


def _own(stmts: list[ast.stmt]):
    """Every node under these statements, except inside a nested function or lambda."""
    todo = list(stmts)
    while todo:
        n = todo.pop()
        yield n
        todo += [c for c in ast.iter_child_nodes(n)
                 if not isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))]


def drop_unread_returns(path: pathlib.Path, names: set[str]) -> list[str]:
    """Keep what a helper does, drop what it returns, for the helpers named in `names`: the formula called them
    for their value, and surviving code calls them only for their effect. Maze's `update_move_direction()`
    advances the checkpoint and recolours it -- dynamics the tooling replays every step -- and returned the
    bonus for reaching it. A `return <value>` that ends the method goes, as does an `if` at the end that did
    nothing but return one, and then any local that only fed them; any other one loses its value.
    Returns the qualnames cut."""
    src = path.read_text()
    lines = src.split("\n")
    drop, edits, cut = set(), {}, []                        # edits: line index -> its replacement
    for cls in (n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ClassDef)):
        for m in cls.body:
            if not isinstance(m, ast.FunctionDef) or m.name not in names:
                continue
            body, gone = list(m.body), []
            while body and (_value_return(body[-1]) or isinstance(body[-1], ast.If) and not body[-1].orelse
                            and all(_value_return(s) for s in body[-1].body)):
                gone.append(body.pop())
            loads = {n.id for n in _own(body) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
            gone += [s for s in body if isinstance(s, ast.Assign) and len(s.targets) == 1
                     and isinstance(s.targets[0], ast.Name) and s.targets[0].id not in loads
                     and isinstance(s.value, (ast.Name, ast.Attribute, ast.Constant))]
            rest = [s for s in body if s not in gone]
            returns = [n for n in _own(rest) if _value_return(n)]
            if not (gone or returns):
                continue
            for r in returns:                               # keep the line, lose the value
                edits[r.lineno - 1] = lines[r.lineno - 1][: r.col_offset] + "return"
                drop |= set(range(r.lineno, r.end_lineno))
            if not rest:                                    # a body cannot be empty
                first = min(gone, key=lambda s: s.lineno)
                edits[first.lineno - 1] = lines[first.lineno - 1][: first.col_offset] + "pass"
            drop |= {i for s in gone for i in range(s.lineno - 1, s.end_lineno)} - edits.keys()
            cut.append(f"{path.stem}.{cls.name}.{m.name}")
    if cut:
        lines = [edits.get(i, l) for i, l in enumerate(lines)]
        path.write_text("\n".join(l for i, l in enumerate(lines) if i not in drop))
    return cut


def drop_reward_comments(path: pathlib.Path) -> int:
    """Delete comments that mention the reward: they outlive what they described. `# Horizontal speeds above
    which move reward is 1.` still sits on `_WALK_SPEED` -- the task's target speed, which stays -- and says
    where the speed term saturates. Returns how many went."""
    src = path.read_text()
    lines = src.split("\n")
    hits = [t for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type == tokenize.COMMENT and REWARD_METHOD.search(t.string)]
    drop = set()
    for t in hits:
        row, col = t.start[0] - 1, t.start[1]
        if lines[row][:col].strip():
            lines[row] = lines[row][:col].rstrip()          # an inline comment: the code before it stays
        else:
            drop.add(row)
    if hits:
        path.write_text("\n".join(l for i, l in enumerate(lines) if i not in drop))
    return len(hits)


def package_names() -> set[str]:
    """Every name the whole package still reads or imports by name, KEEP included."""
    live: set[str] = set()
    for f in sorted(PKG.rglob("*.py")):
        tree = ast.parse(f.read_text())
        live |= _loaded_names(tree)
        live |= {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    return live


def drop_dead_globals(path: pathlib.Path, formula_read: set[str], live: set[str]) -> list[str]:
    """Delete module-level constants that existed only for the formula. Returns the names removed.

    Run AFTER scrub_rewards, and delete a constant only when BOTH hold:

      * a deleted reward method read it  -- so this is a scoring parameter, not merely unused code. We are
        not here to tidy upstream's dead code, and a constant we cannot explain is one we should not touch.
      * nothing left in the PACKAGE reads it -- package-wide, not module-wide, because another module may
        `from .basic_locomotion_envs import _STAND_HEIGHT`.

    `_STAND_HEIGHT = 1.65`, under the comment "Height of head above which stand reward is 1", passes both:
    its only reader was get_reward, and it says where the stand term saturates. Unreachable is not
    unreadable -- the same argument as assets/kitchen. `global _STAND_HEIGHT; _STAND_HEIGHT = 1.28` in a
    robot-specific branch is a Store, so it neither keeps the constant alive nor breaks once the
    module-level line is gone. `_WALK_SPEED` fails the second test as applied here (a class body's
    `_move_speed = _WALK_SPEED` reads it, although only get_reward read `_move_speed`) and stays: the target speed
    the instruction gives in words, but also the move term's bound and margin (an open gap: docs/LEAKAGE.md).

    extract_rewards.py runs this very function against a copy so rewards.json carries whatever it removes,
    and rcb_rewards.restore() puts them back into the module namespace before the methods compile.
    """
    src = path.read_text()
    tree = ast.parse(src)
    lines = src.split("\n")
    drop, removed = set(), []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id in live or target.id not in formula_read:
            continue
        start = node.lineno - 1
        while start and lines[start - 1].lstrip().startswith("#"):  # take the comment with it
            start -= 1
        drop |= set(range(start, node.end_lineno))
        removed.append(f"{path.stem}.{target.id}")
    if drop:
        path.write_text("\n".join(l for i, l in enumerate(lines) if i not in drop))
    return removed


def prune_reward_params(path: pathlib.Path) -> list[str]:
    """Strip scoring weights out of reward-shaped dict attributes, keeping the keys the rest of the code
    still reads. Returns "qualname[key]" for each weight removed.

    One case exists upstream and it is a real leak: `Push.__init__` sets
    `self.reward_dict = {"hand_dist": 0.1, "target_dist": 1, "success": 1000, "terminate": True}` --
    every weight of the push reward, plus the size of the success bonus, readable as source AND at runtime
    through `s.low.task.reward_dict`. It survives scrub_rewards because it is an attribute assignment, not
    a method named *reward*.

    It cannot simply be deleted: `get_terminated` reads `reward_dict["terminate"]`, which is dynamics. So
    the rule is the same one as drop_dead_globals -- a key survives iff surviving code subscripts it.
    """
    src = path.read_text()
    tree = ast.parse(src)
    lines = src.split("\n")
    edits, removed = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        name = getattr(target, "attr", None) or getattr(target, "id", None)
        if not name or not REWARD_METHOD.search(name) or not isinstance(node.value, ast.Dict):
            continue
        read = {c.slice.value for c in ast.walk(tree)
                if isinstance(c, ast.Subscript) and isinstance(c.slice, ast.Constant)
                and isinstance(c.slice.value, str)
                and (getattr(c.value, "attr", None) or getattr(c.value, "id", None)) == name}
        keep = {k.value: v for k, v in zip(node.value.keys, node.value.values)
                if isinstance(k, ast.Constant) and k.value in read}
        removed += [f"{path.stem}.{name}[{k.value!r}]" for k in node.value.keys
                    if isinstance(k, ast.Constant) and k.value not in read]
        indent = " " * (len(lines[node.lineno - 1]) - len(lines[node.lineno - 1].lstrip()))
        body = ", ".join(f"{k!r}: {ast.unparse(v)}" for k, v in keep.items())
        edits.append((node.lineno - 1, node.end_lineno, f"{indent}{ast.unparse(target)} = {{{body}}}"))
    for start, end, text in reversed(edits):
        lines[start:end] = [text]
    if edits:
        path.write_text("\n".join(lines))
    return removed


def delete() -> int:
    """Phase 1: remove everything. Runs in the SAME layer as the clone -- see the Dockerfile."""
    removed_dirs = []
    for rel in ("data", "logs", "humanoid_bench/mjx", "dreamerv3", "jaxrl_m", "ppo", "tdmpc2"):
        # mjx is the JAX/MJX reimplementation, including its own reward functions. no-torch.patch already
        # severed every import of it, so it is dead weight that happens to carry a copy of the answer key.
        # dreamerv3/ jaxrl_m/ ppo/ tdmpc2/ are the paper's baseline TRAINING harnesses. Nothing imports
        # them, they carry dm_control's own get_reward implementations (which makes every audit of this
        # image noisier), and they are ~1.2 MB of code whose entire purpose is to solve these tasks.
        p = ROOT / rel
        if p.exists():
            shutil.rmtree(p)
            removed_dirs.append(rel)

    # Before scrubbing, not after: a .pyc compiled from the pre-scrub source keeps the formula in its
    # bytecode, and `python -c "import dis, marshal; ..."` reads it straight back out. (An agent tried
    # exactly that against this image.) Dropping the caches first means every .pyc that exists afterwards
    # was compiled from scrubbed source.
    for cache in ROOT.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)

    removed_methods, removed_params, removed_globals, removed_helpers, cut_helpers = [], [], [], [], []
    formula_read: dict[pathlib.Path, set[str]] = {}
    formula_calls: dict[str, bool] = {}
    for f in reward_modules():
        names, read, calls = scrub_rewards(f)
        removed_methods += names
        formula_read[f] = read
        _merge(formula_calls, calls)
    # The helpers those methods called on self, settled by what still calls them: nothing (drop_dead_helpers,
    # repeated, since a helper can be all that called another), or only for their effect (drop_unread_returns).
    pending = dict(formula_calls)
    while pending:
        uses, more = surviving_uses(), {}
        for f in reward_modules():
            names, read, calls = drop_dead_helpers(f, {n for n in pending if n not in uses})
            removed_helpers += names
            formula_read[f] = formula_read.get(f, set()) | read
            _merge(more, calls)
        _merge(formula_calls, more)
        pending = more
    uses = surviving_uses()
    for f in reward_modules():
        cut_helpers += drop_unread_returns(f, {n for n, used in formula_calls.items()
                                               if used and n in uses and not uses[n]})
    comments = sum(drop_reward_comments(f) for f in reward_modules())
    # Order matters: both of these ask "does anything still read this?", which is only true once the
    # reward methods -- the things that read them -- are gone. `live` is package-wide, KEEP included,
    # because a constant may be imported by another module.
    live = package_names()
    for f in reward_modules():
        removed_params += prune_reward_params(f)
        removed_globals += drop_dead_globals(f, formula_read.get(f, set()), live)

    print(f"scrubbed dirs: {removed_dirs or 'nothing'}")
    print(f"scrubbed rewards: {len(removed_methods)} methods in "
          f"{len({m.split('.')[0] for m in removed_methods})} modules")
    for m in removed_methods:
        print(f"  - {m}")
    print(f"scrubbed helpers: removed {removed_helpers or 'nothing'}, returned values cut from "
          f"{cut_helpers or 'nothing'}")
    print(f"scrubbed comments that mention the reward: {comments}")
    print(f"scrubbed reward params: {removed_params or 'nothing'}")
    print(f"scrubbed dead constants: {len(removed_globals)} -> {removed_globals}")
    return 0


def verify() -> int:
    """Phase 2: assert nothing survived AND the package still works. Runs after pip install, because it
    imports the package it is checking."""
    leftovers = []

    # Anything weight-shaped outside the scene assets is a leftover we did not anticipate.
    WEIGHTS = {".pt", ".pth", ".ckpt", ".npy", ".npz", ".pkl", ".msgpack", ".safetensors", ".h5"}
    leftovers += [f"weights: {p.relative_to(ROOT)}" for p in ROOT.rglob("*")
                  if p.is_file() and p.suffix in WEIGHTS and "assets" not in p.parts]

    # Nothing outside KEEP may still define a reward, anywhere in the package.
    for f in reward_modules():
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.ClassDef):
                leftovers += [f"reward: {f.relative_to(PKG)}::{node.name}.{m.name}" for m in node.body
                              if isinstance(m, ast.FunctionDef) and REWARD_METHOD.search(m.name)]

    # No comment may still talk about the reward.
    for f in reward_modules():
        leftovers += [f"reward comment: {f.relative_to(PKG)}:{t.start[0]}"
                      for t in tokenize.generate_tokens(io.StringIO(f.read_text()).readline)
                      if t.type == tokenize.COMMENT and REWARD_METHOD.search(t.string)]

    # Pruning again must be a no-op: it recomputes "which keys does surviving code read?" from the file in
    # front of it, so anything it still finds is a scoring weight we left behind.
    # Constants get no equivalent check here -- deciding one is a formula constant needs the formula, which
    # is gone by now. Their safety net is the end-to-end run: a constant that was removed but not recorded
    # in rewards.json makes the restored get_reward raise NameError, which grade.py reports as
    # grader_error rather than as a score.
    for f in reward_modules():
        leftovers += [f"reward param survived: {x}" for x in prune_reward_params(f)]

    # ...and no compiled copy survives either. KEEP's two plumbing methods are named in their own
    # bytecode, which is expected; anything else means a stale cache outlived the scrub.
    for pyc in ROOT.rglob("*.pyc"):
        source = pyc.parents[1] / (pyc.name.split(".")[0] + ".py")  # __pycache__/x.cpython-311.pyc -> x.py
        if source not in KEEP and b"get_reward" in pyc.read_bytes():
            leftovers.append(f"stale bytecode: {pyc.relative_to(ROOT)}")

    import gymnasium as gym  # noqa: E402  (only importable once the package is consistent)
    import humanoid_bench  # noqa: F401,E402
    from humanoid_bench.tasks import Task

    e = gym.make("h1-walk-v0", render_mode=None)
    e.reset(seed=0)
    _, r, _, _, _ = e.step(e.action_space.sample() * 0)
    task = type(e.unwrapped.task)
    if task.get_reward is not Task.get_reward:
        leftovers.append(f"{task.__name__}.get_reward still overrides the base")
    if r != 0:
        leftovers.append(f"stepping returned a non-zero reward ({r})")
    if not float(e.unwrapped.task.success_bar):
        leftovers.append("success_bar did not survive the scrub")
    e.close()

    print(f"leftovers: {leftovers}")
    return 1 if leftovers else 0


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else "delete"
    sys.exit({"delete": delete, "verify": verify}[phase]())
