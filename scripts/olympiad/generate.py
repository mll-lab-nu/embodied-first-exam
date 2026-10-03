#!/usr/bin/env python3
"""Generate the Embodied Agent Olympiad tasks (docs/benchmarks/olympiad.md).

    python3 scripts/olympiad/generate.py          # write tasks/<task> for every task below
    python3 scripts/olympiad/generate.py check    # exit 1 if a committed task differs from what would be written

Each sport has a directory scripts/olympiad/<sport>/ with a spec.py whose TASKS dict names its tasks (see
tabletennis/spec.py); this script finds them all. Every task is one parameterized standard-mode task with the real-time protocol (docs/EAI_STANDARD_REALTIME_1_0.md);
its configuration (level, slowdown, seed, ...) is chosen at run time. A task directory is rewritten from:
  * <sport>/<kind>/             the task's own sources (task.toml, environment/, tests/, solution/);
  * shared/<sport>/sim/         the simulator code every task of the sport uses (copied byte for byte);
  * api_errors.py               the model-API error rule (transient vs unrecovered), into every task's sim;
  * scripts/eai_standard/client-requirements.txt   the standard client pins (agent images build from it);
  * program_prompt.py + <sport>/<x>_prompt.py   instruction.md, from the general program-play structure;
  * realtime_standard.py               README.md in the protocol's standard layout;
  * broadcast/broadcast_log.py         the spectator broadcast log, for tasks with `broadcast=True` (read by an optional
                                       spectator renderer; never by the replay or the grader).
"""
import filecmp
import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "scripts"))
from realtime_standard import readme  # noqa: E402
from task_conventions import normalize  # noqa: E402
from common import PINS  # noqa: E402

API_ERRORS = HERE / "api_errors.py"



def load_tasks() -> dict:
    """Every sport's TASKS (scripts/olympiad/<sport>/spec.py), in sport order."""
    tasks = {}
    for spec_py in sorted(HERE.glob("*/spec.py")):
        sys.path.insert(0, str(spec_py.parent))           # the sport's own prompt module
        mod = importlib.util.spec_from_file_location(f"olympiad_{spec_py.parent.name}_spec", spec_py)
        m = importlib.util.module_from_spec(mod)
        mod.loader.exec_module(m)
        for name in m.TASKS:
            assert name not in tasks, f"task {name} defined twice"
        tasks.update(m.TASKS)
    return tasks


TASKS = load_tasks()


def render(name: str, out: Path) -> None:
    spec = TASKS[name]
    src = HERE / spec["source"]
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out, ignore=shutil.ignore_patterns("__pycache__", "scene_extra"))
    shutil.copytree(HERE / spec["shared"], out / "environment/sim", dirs_exist_ok=True)
    shutil.copy2(API_ERRORS, out / "environment/sim/api_errors.py")     # the model-API validity rule, one copy for all
    if spec.get("broadcast"):            # the spectator broadcast log (broadcast/broadcast_log.py; never read back)
        shutil.copy2(HERE / "broadcast" / "broadcast_log.py", out / "environment/sim" / "broadcast_log.py")
    if spec.get("extra_scene"):
        for f in sorted((src / spec["extra_scene"]).iterdir()):
            shutil.copy2(f, out / "environment/sim/scene" / f.name)
    for d in spec["pins_to"]:
        shutil.copy2(PINS, out / d / "client-requirements.txt")
    (out / "instruction.md").write_text(spec["prompt"]())
    (out / "README.md").write_text(readme(name, **spec["readme"]))
    normalize(out)          # PROTOCOL v1.0 conventions (README header table, fields), as every generator finishes


def same_tree(a: Path, b: Path) -> list[str]:
    """Paths that differ between two directory trees (ignoring __pycache__)."""
    diffs = []
    cmp = filecmp.dircmp(a, b, ignore=["__pycache__"])
    diffs += [str(a / x) for x in cmp.left_only + cmp.right_only + cmp.funny_files]
    diffs += [str(a / x) for x in cmp.common_files if not filecmp.cmp(a / x, b / x, shallow=False)]
    for sub in cmp.common_dirs:
        diffs += same_tree(a / sub, b / sub)
    return diffs


def main(argv: list[str]) -> int:
    if argv[:1] == ["check"]:
        bad = 0
        with tempfile.TemporaryDirectory() as tmp:
            for name in TASKS:
                render(name, Path(tmp) / name)
                d = same_tree(ROOT / "tasks" / name, Path(tmp) / name) if (ROOT / "tasks" / name).is_dir() else ["missing"]
                if d:
                    bad = 1
                    print(f"DIFF {name}: {d[:5]}")
        print("olympiad: tasks match their generator" if not bad else "olympiad: run scripts/olympiad/generate.py")
        return bad
    for name in TASKS:
        render(name, ROOT / "tasks" / name)
        print("wrote tasks/" + name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
