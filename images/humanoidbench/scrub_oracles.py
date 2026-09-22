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
                         we measured an agent doing exactly that (local_docs/plan/07-open-questions.md §1).

  Deleting the methods is enough because upstream's own `Task.get_reward()` returns `(0, {})`: the base
  takes over, every environment still steps, and nothing else changes. `Session` sees the override is
  gone and reports no return (shared/rcb_hb.py), so the agent is told plainly rather than fed a zero.
  The constants and weights need the two rules in drop_dead_globals / prune_reward_params, because a
  name match cannot tell a scoring parameter from a description of the task.

WHAT STAYS
  `get_terminated` (an agent discovers it in one rollout -- dynamics, not scoring), `get_obs`,
  `success_bar`, and anything surviving code still reads, such as `_WALK_SPEED` via `_move_speed`.

THE FORMULA IS NOT LOST
  scripts/humanoidbench/rewards.json holds it -- built by running THIS script against a copy and diffing,
  so the two sides cannot drift. gen_tasks.py ships one family's entry in that task's tests/, which Harbor
  copies in only after the agent has finished, and grade.py patches it back before scoring. The verifier
  therefore runs upstream's exact code and our numbers stay comparable with the paper.

TWO PHASES, because `verify` imports the package it checks:
  `delete`  runs in the SAME Docker layer as the clone (see the Dockerfile: a later layer cannot unwrite
            an earlier one), before pip install.
  `verify`  runs after the install. Fails loudly if anything is left.

See docs/LEAKAGE.md for the general checklist this implements.
"""
import ast
import pathlib
import re
import shutil
import sys

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


def reward_modules() -> list[pathlib.Path]:
    return [f for f in sorted(PKG.rglob("*.py")) if f not in KEEP]


def scrub_rewards(path: pathlib.Path) -> tuple[list[str], set[str]]:
    """Delete every reward-shaped method from one module.

    Returns (qualnames removed, names those methods read) -- the second half is what drop_dead_globals
    needs to tell a constant that existed for the formula from one that is merely unused.

    Line-based rather than ast.unparse-based on purpose: unparsing rewrites the whole file (dropping
    comments and normalising formatting), which would make the diff against upstream unreadable and hide
    what else we changed. Cutting the exact line spans keeps every other byte identical.
    """
    src = path.read_text()
    lines = src.split("\n")
    cuts, removed, read = [], [], set()
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.ClassDef):
            continue
        for m in node.body:
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and REWARD_METHOD.search(m.name):
                start = min([d.lineno for d in m.decorator_list] + [m.lineno])
                cuts.append((start - 1, m.end_lineno))
                removed.append(f"{path.stem}.{node.name}.{m.name}")
                read |= _loaded_names(m)
    if not cuts:
        return [], set()
    drop = {i for a, b in cuts for i in range(a, b)}
    path.write_text("\n".join(l for i, l in enumerate(lines) if i not in drop))
    return removed, read


def _loaded_names(tree: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


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
    module-level line is gone. `_WALK_SPEED` fails the second test (`_move_speed = _WALK_SPEED` reads it)
    and stays: it is the task's target speed, not a tolerance.

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

    removed_methods, removed_params, removed_globals = [], [], []
    formula_read: dict[pathlib.Path, set[str]] = {}
    for f in reward_modules():
        names, read = scrub_rewards(f)
        removed_methods += names
        formula_read[f] = read
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
