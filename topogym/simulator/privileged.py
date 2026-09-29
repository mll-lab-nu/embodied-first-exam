"""Explicit read/rewind access to the current seed and current episode only."""
from collections.abc import Mapping
from dataclasses import asdict
import weakref

from topogym.utils.snapshots import freeze
from .history import StateRef


class PrivilegedAccess:
    __slots__ = ("_owner", "_episode_id")

    def __init__(self, env):
        self._owner = weakref.ref(env)
        self._episode_id = env._episode_id

    def _env(self):
        env = self._owner()
        if env is None or not env.config.enable_privileged:
            raise PermissionError("Privileged access was not enabled by the environment owner")
        if env._closed:
            raise RuntimeError("Env is closed")
        if not self._episode_id or self._episode_id != env._episode_id:
            raise RuntimeError("This access handle expired after an episode reset")
        return env

    def rewind_to(self, state_ref):
        env = self._env()
        if isinstance(state_ref, Mapping):
            if set(state_ref) != {"episode_id", "state_id"}:
                raise ValueError("Expected only episode_id and state_id")
            state_ref = StateRef(**state_ref)
        if not isinstance(state_ref, StateRef):
            raise ValueError("rewind_to requires a StateRef, not a bare integer or seed")
        return env._restore(state_ref)

    def get(self, name):
        env = self._env()
        if name not in {"history", "state_info", "world", "robot", "task", "diagnostics"}:
            raise ValueError(f"Unsupported privileged field: {name}")
        if name == "history":
            return freeze([asdict(item) for item in env.state_history])
        if name == "diagnostics" and env._faulted:
            return freeze(dict(faulted=True, fault=env._fault_detail,
                               saved_states=len(env.state_history)))
        env._require_ready()
        if name == "state_info":
            return freeze(asdict(env._history.get(env._state_id).info))
        if name == "world":
            return freeze(env._world.read_state())
        if name == "robot":
            return freeze(env._robot.observe())
        if name == "task":
            return freeze(env._task.get_state())
        return freeze(dict(
            physics_step=env._world.physics_step,
            saved_states=len(env.state_history),
            contact_coverage="rigid contacts only; not complete IPC contact output",
            task_metrics=env._task.result.metrics,
            physics=env._world.read_state().get("ipc", {}),
        ))
