"""chopping_wood (board 0178): the simulator's state can be dumped right after a log is split.

An object a transition rule creates in a control step (here: the two halves of a log the axe splits, OmniGibson's
SlicingRule) is initialized by OmniGibson only at the NEXT simulator step, and until then USDObject.dump_state asserts
("Object must be initialized before dumping state!"). The tooling's state hash (rcb_behavior.Session.state_sha: the
live end-of-episode hash, the checkpoints, the replay's hash at the trajectory's last row) dumps the whole scene, so an
episode or trajectory that ended on the step of a cut crashed instead of being graded.

This patch leaves exactly those objects (the simulator's queue of objects to initialize) out of the dump. They have no
simulated state yet and the next step initializes them; nothing in the simulation changes, a dump with an empty queue
is the same as before (so the frozen instance's hash and every other state hash are unchanged), and a live run and its
replay leave the same objects out at the same step. It is installed when omnigibson.utils.registry_utils is imported
(Python imports this file at startup because its directory is on PYTHONPATH); the shared tooling rcb_behavior.py is
unchanged.
"""
import importlib.abc
import importlib.machinery
import sys

_TARGET = "omnigibson.utils.registry_utils"


def _patch(mod) -> None:
    reg_cls = getattr(mod, "SerializableRegistry", None)
    if reg_cls is None or getattr(reg_cls, "_rcb_pending_init_patch", False):
        return
    orig = reg_cls._dump_state

    def _dump_state(self):
        try:
            import omnigibson as og
            pending = getattr(og.sim, "_objects_to_initialize", None) if og.sim is not None else None
        except Exception:  # noqa: BLE001
            pending = None
        if not pending:
            return orig(self)
        skip = {id(o) for o in pending}
        state = dict()
        for obj in self.objects:
            if id(obj) not in skip and self._dump_filter(obj):
                state[obj.name] = obj.dump_state(serialized=False)
        return state

    reg_cls._dump_state = _dump_state
    reg_cls._rcb_pending_init_patch = True


class _Loader(importlib.abc.Loader):
    def __init__(self, inner):
        self._inner = inner

    def create_module(self, spec):
        return self._inner.create_module(spec)

    def exec_module(self, module):
        self._inner.exec_module(module)
        _patch(module)


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname != _TARGET:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is not None and spec.loader is not None:
            spec.loader = _Loader(spec.loader)
        return spec


if _TARGET in sys.modules:
    _patch(sys.modules[_TARGET])
else:
    sys.meta_path.insert(0, _Finder())
