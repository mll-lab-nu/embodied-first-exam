"""Put this task's scoring formula back, where the scoring happens: the privileged verifier (tests/) and the
standard-mode sim sidecar (environment/sim/).

This file and the rewards.json beside it are the only copies of the formula a task carries, and the agent can
read neither place: the privileged verifier runs in its own container once the agent's is gone, and the agent
cannot open the sidecar. The image itself has the formula deleted; see images/humanoidbench/scrub_oracles.py.

Patching it back, rather than keeping a private reimplementation, is what keeps our scores comparable with
the paper and with FastTD3: the verifier runs upstream's exact expression, byte for byte as it was lifted
by scripts/humanoidbench/extract_rewards.py.

Call restore() BEFORE opening a Session -- Session decides whether it can score by looking at the class.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path


def _reinstate(cls, attr: str, values: dict) -> None:
    """Merge scoring weights back into an attribute the constructor builds.

    `Push.__init__` sets `self.reward_dict = {...}`; the image keeps only the keys that non-scoring code
    reads (`terminate`, which `get_terminated` uses) and the weights live here. They are per-instance, so
    they go back through the constructor -- restore() runs before any Session exists, by contract. (A frozen
    instance never carries them: rcb_hb leaves reward-shaped attributes out of its snapshot.)
    """
    original = cls.__init__

    def __init__(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if hasattr(self, attr):  # push returns early when env is None, before assigning
            getattr(self, attr).update(values)

    cls.__init__ = __init__


def restore(spec: dict | str | Path = None) -> list[str]:
    """Put back everything the image had removed for this task. Returns what was restored.

    `spec` is one task's entry -- a path to the tests/rewards.json beside this file (the default), or the
    entry itself, which is how gen_tasks.py feeds it one family out of the full table. Three kinds:

      module_globals  constants the scrub found to be write-only once the formula was gone, e.g.
                      `_STAND_HEIGHT = 1.65`. They go back FIRST, because the methods close over them.
      methods         the reward functions themselves, and the helpers the scrub deleted or cut down
                      with them (truck's `upon_table`, maze's `update_move_direction`) as upstream wrote them.
      params          scoring weights the constructor assigns (push only) -- see _reinstate.

    Everything is compiled against the *defining module's own namespace*, so it closes over exactly what
    it closed over upstream: numpy, dm_control's `rewards`, and those constants. That is why this cannot
    be a plain import -- the function has to end up with the original __globals__.
    """
    if not isinstance(spec, dict):
        spec = json.loads(Path(spec or Path(__file__).with_name("rewards.json")).read_text())
    done = []
    for name, source in spec.get("module_globals", {}).items():
        module = importlib.import_module(name)
        exec(compile(source, f"<rewards:{name} constants>", "exec"), vars(module))
        done.append(f"{name} constants")
    for m in spec["methods"]:
        module = importlib.import_module(m["module"])
        namespace = vars(module)
        exec(compile(m["source"], f"<rewards:{m['cls']}.{m['name']}>", "exec"), namespace)
        setattr(getattr(module, m["cls"]), m["name"], namespace[m["name"]])
        done.append(f"{m['module']}.{m['cls']}.{m['name']}")
    for name, entries in spec.get("params", {}).items():
        module = importlib.import_module(name)
        for p in entries:
            _reinstate(getattr(module, p["cls"]), p["attr"], p["values"])
            done.append(f"{name}.{p['cls']}.{p['attr']}")
    if not done:
        raise RuntimeError("restored nothing -- the verifier cannot score")
    return done


# How far a multi-stage task got: upstream's own bookkeeping, which the scoring code advances (in the agent's container,
# rcb_hb's _unscored_bookkeeping advances maze_stage; the rest stays frozen there). Read after a replay, for the
# diagnostics; it never enters the verdict.
PROGRESS = ("current_subtask", "task_index", "maze_stage", "stage", "tasks_to_complete", "packages_on_table")


def progress(task) -> dict:
    """{attribute: value} for the PROGRESS attributes `task` (a Session's `low.task`) has: a number or a name as
    it is, a list as its length (packages on the table), a dict as its sorted keys (kitchen's chores left)."""
    out = {}
    for k in PROGRESS:
        v = getattr(task, k, None)
        if isinstance(v, dict):
            out[k] = sorted(map(str, v))
        elif isinstance(v, (list, tuple)):
            out[k] = len(v)
        elif isinstance(v, str):
            out[k] = v
        elif v is not None:
            out[k] = int(v)
    return out


if __name__ == "__main__":
    for name in restore():
        print(f"restored {name}")
