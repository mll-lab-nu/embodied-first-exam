"""Policy clients; both expose .spec, .reset(seed), .infer(obs) and .close()."""
from __future__ import annotations


class PolicyError(RuntimeError):
    """The policy failed, returned a malformed chunk, timed out or disconnected; not a task failure."""


class LocalClient:
    """Calls a BaseVLA in this process; only for tests and HoldVLA (model libraries stay out of TopoGym)."""

    def __init__(self, model):
        self.model = model
        self.spec = model.spec

    def reset(self, seed):
        self._call(self.model.reset, seed)

    def infer(self, obs):
        return self._call(self.model.infer, obs)

    def close(self):
        pass

    @staticmethod
    def _call(method, argument):
        # Same contract as the model server: a model exception becomes a PolicyError.
        try:
            return method(argument)
        except Exception as error:
            raise PolicyError(f"{type(error).__name__}: {error}") from error
