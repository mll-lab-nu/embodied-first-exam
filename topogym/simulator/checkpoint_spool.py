"""Private, same-process disk backing for complete tick history.

This is NOT an import/export format. Files live in an owner-only temporary
directory and can only be read with the live engine reference table. Agent
trajectories use numeric NPZ instead; never pass external files to this store.
"""
import gzip
import pickle
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType


def _native(cls, values):
    result = object.__new__(cls)
    vars(result).update(values)
    return result


class Spool:
    def __init__(self, directory=None):
        self.temporary = TemporaryDirectory(prefix="topogym-history-", dir=directory)
        self.root = Path(self.temporary.name)
        self.references = {}
        self.latest = None

    def save(self, state):
        world = state.world
        refs = [item.target for item in getattr(world,"buffers",())]
        refs += [item[0] for item in getattr(world,"engine_flags",())]
        refs += [item[0] for item in getattr(world,"entity_inputs",())]
        native = getattr(world,"native_state",None)
        if native is not None and hasattr(native,"_scene"):
            refs.append(native._scene)
        for item in refs:
            self.references[id(item)] = item
        references = self.references
        class Writer(pickle.Pickler):
            def persistent_id(self, obj):
                if id(obj) in references:
                    return ("engine", id(obj))
                return None

            def reducer_override(self, obj):
                if isinstance(obj, MappingProxyType):
                    return dict, (dict(obj),)
                if not isinstance(obj,type) and type(obj).__module__.startswith("genesis.engine.states"):
                    return _native, (type(obj),vars(obj))
                return NotImplemented
        path = self.root/f"{state.info.state_id}.gz"
        with gzip.open(path,"wb",compresslevel=1) as stream:
            Writer(stream,protocol=5).dump(state)
        self.latest = state

    def load(self, state_id):
        if self.latest is not None and self.latest.info.state_id == state_id:
            return self.latest
        references = self.references
        class Reader(pickle.Unpickler):
            def persistent_load(self, token):
                kind,key = token
                if kind != "engine" or key not in references:
                    raise ValueError("Unknown live engine reference")
                return references[key]
        with gzip.open(self.root/f"{state_id}.gz","rb") as stream:
            return Reader(stream).load()

    def remove(self, state_id):
        (self.root/f"{state_id}.gz").unlink()
        if self.latest is not None and self.latest.info.state_id == state_id:
            self.latest = None

    def close(self):
        self.latest = None
        self.references.clear()
        self.temporary.cleanup()
