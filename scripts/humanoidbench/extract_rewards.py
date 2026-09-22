#!/usr/bin/env python3
"""Lift every task's reward implementation out of upstream and into rewards.json.

WHY
    The scoring formula is the answer key. HumanoidBench's rewards are dense and hand-tuned -- exact
    bounds, weights and multiplicative gates -- so an agent that reads `Sit.get_reward()` does not have
    to control a robot, it has to invert an expression. We measured that happening: an agent quoted
    `bounds=(0.68, 0.72)` back to us and cleared the bar in 26 steps.
    So the formula leaves the image (images/humanoidbench/scrub_oracles.py deletes it) and lives here
    instead. gen_tasks.py copies the entry for one family into that task's tests/, which Harbor only
    mounts after the agent is done, and grade.py puts it back before scoring.

WHAT IS TAKEN
    Every `*reward*` method reachable on the family's Task class -- get_reward, plus cabinet's four
    get_reward_subtask_* helpers -- recorded against the class that DEFINES it, since several families
    share one (`stair` and `slide` both score through ClimbingUpwards).

    Plus everything the scrub removes ALONGSIDE those methods, because the verifier needs it back:

      module_globals  constants the scrub finds to be write-only once the reward methods are gone --
                      `_STAND_HEIGHT = 1.65` under the comment "Height of head above which stand reward
                      is 1". Constants that surviving code still reads (`_WALK_SPEED`, via
                      `_move_speed = _WALK_SPEED`; kitchen's goal table, via get_obs) are NOT taken:
                      they stay in the image because they describe the task rather than grade it.
      params          scoring weights assigned to a reward-shaped attribute. One case upstream:
                      `Push.__init__` sets `self.reward_dict = {"hand_dist": 0.1, "target_dist": 1,
                      "success": 1000, "terminate": True}`. `get_terminated` reads `["terminate"]`, so
                      that key stays; the three weights come here.

    Rather than re-deriving which of those the scrub will take -- two implementations of one rule drift --
    this runs the real images/humanoidbench/scrub_oracles.py against a COPY of the package and diffs.
    Whatever the image loses is exactly what rewards.json gains.

    Not get_terminated, get_obs or success_bar either: an agent discovers termination in one rollout,
    and the bar is the target rather than the formula. See local_docs/plan/07-open-questions.md §1.

RUN
    Needs an image whose rewards are NOT yet scrubbed, which no current tag is -- build one by commenting
    the scrub step out of images/humanoidbench/Dockerfile, or check out an image from before 0.1.3.
    Mount the REPO ROOT, because this imports images/humanoidbench/scrub_oracles.py:

    docker run --rm -v "$PWD:/repo" -w /repo <unscrubbed-image> \
        python scripts/humanoidbench/extract_rewards.py --out scripts/humanoidbench/rewards.json

    A one-off: rewards.json is committed, and upstream is pinned to commit cb11890, so this only needs
    running again if that pin moves.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import inspect
import json
import pathlib
import re
import shutil
import sys
import tempfile
import textwrap

REWARD_METHOD = re.compile(r"reward", re.I)
UPSTREAM = pathlib.Path("/opt/humanoid-bench")


def _scrubbed_copy() -> pathlib.Path:
    """Run the image's own scrub against a copy of upstream and return where it landed."""
    spec = importlib.util.spec_from_file_location(
        "scrub_oracles", pathlib.Path("images/humanoidbench/scrub_oracles.py").resolve())
    scrub = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scrub)

    tmp = pathlib.Path(tempfile.mkdtemp()) / "humanoid-bench"
    shutil.copytree(UPSTREAM, tmp, symlinks=True)
    scrub.ROOT, scrub.PKG = tmp, tmp / "humanoid_bench"
    scrub.KEEP = {scrub.PKG / p.name for p in scrub.KEEP}
    scrub.delete()
    return tmp


def _module_constants(path: pathlib.Path) -> dict[str, tuple[int, int]]:
    tree = ast.parse(path.read_text())
    return {n.targets[0].id: (n.lineno, n.end_lineno) for n in tree.body
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)}


def _reward_dicts(path: pathlib.Path) -> dict[tuple[str, str], dict]:
    """{(class, attr): literal} for every reward-shaped dict attribute assigned in this module."""
    tree, out = ast.parse(path.read_text()), {}
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        for node in ast.walk(cls):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            name = getattr(node.targets[0], "attr", None)
            if name and REWARD_METHOD.search(name) and isinstance(node.value, ast.Dict):
                try:
                    out[(cls.name, name)] = ast.literal_eval(node.value)
                except ValueError:
                    pass
    return out


def scrub_diff() -> tuple[dict, dict]:
    """What the scrub removes, keyed by module: (constants as source lines, reward params as values)."""
    scrubbed = _scrubbed_copy()
    consts, params = {}, {}
    for before in sorted((UPSTREAM / "humanoid_bench").rglob("*.py")):
        after = scrubbed / before.relative_to(UPSTREAM)
        if not after.is_file():
            continue
        mod = "humanoid_bench." + str(before.relative_to(UPSTREAM / "humanoid_bench")
                                      ).removesuffix(".py").replace("/", ".")
        lines = before.read_text().split("\n")
        gone = _module_constants(before).keys() - _module_constants(after).keys()
        if gone:
            spans = _module_constants(before)
            consts[mod] = "\n".join("\n".join(lines[spans[n][0] - 1:spans[n][1]]) for n in sorted(gone))
        kept = _reward_dicts(after)
        for (cls, attr), full in _reward_dicts(before).items():
            dropped = {k: v for k, v in full.items() if k not in kept.get((cls, attr), {})}
            if dropped:
                params.setdefault(mod, []).append({"cls": cls, "attr": attr, "values": dropped})
    shutil.rmtree(scrubbed.parent, ignore_errors=True)
    return consts, params


def reward_methods(cls) -> dict[str, object]:
    """Every reward-shaped method on this class or its bases, keyed by the name it is bound to.

    Walking the MRO matters: `stair` and `slide` both score through ClimbingUpwards.get_reward, and
    `walk`/`run`/`stand` all share Walk's -- the defining class is what has to be patched back.
    """
    out = {}
    for name in dir(cls):
        if not REWARD_METHOD.search(name):
            continue
        attr = inspect.getattr_static(cls, name, None)
        if inspect.isfunction(attr):
            out[name] = attr
    return out


def defining_class(cls, name: str):
    for base in cls.__mro__:
        if name in vars(base):
            return base
    raise LookupError(f"{cls.__name__}.{name} not found on any base")


def extract(family: str, consts: dict, params: dict) -> dict:
    from humanoid_bench.env import TASKS

    cls = TASKS[family]
    methods = reward_methods(cls)
    if not methods:
        raise LookupError(f"{family}: no reward method found on {cls.__name__}")

    entries = []
    for name, fn in sorted(methods.items()):
        owner = defining_class(cls, name)
        entries.append({
            "module": owner.__module__,
            "cls": owner.__qualname__,
            "name": name,
            # getsource keeps the class-body indentation; exec() needs the def at column 0.
            "source": textwrap.dedent(inspect.getsource(fn)).rstrip("\n"),
        })
    # Whatever the scrub also takes from the modules these methods live in has to come back with them.
    modules = sorted({e["module"] for e in entries})
    rec = {"task_class": f"{cls.__module__}.{cls.__qualname__}", "methods": entries}
    if globals_ := {m: consts[m] for m in modules if m in consts}:
        rec["module_globals"] = globals_
    if params_ := {m: params[m] for m in modules if m in params}:
        rec["params"] = params_
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="rewards.json")
    a = ap.parse_args()

    from humanoid_bench.env import TASKS

    consts, params = scrub_diff()
    out = {}
    for family in sorted(TASKS):
        try:
            out[family] = extract(family, consts, params)
        except Exception as e:
            print(f"{family}: {type(e).__name__}: {e}", file=sys.stderr)
            return 1

    with open(a.out, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)

    for family, rec in sorted(out.items()):
        names = ", ".join(m["name"] for m in rec["methods"])
        owner = rec["methods"][0]["module"].split(".")[-1] + "." + rec["methods"][0]["cls"]
        extra = []
        if rec.get("module_globals"):
            extra.append("+consts")
        if rec.get("params"):
            extra.append("+params")
        print(f"{family:20}{owner:26}{names}  {' '.join(extra)}")
    print(f"\n{len(out)} families -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
