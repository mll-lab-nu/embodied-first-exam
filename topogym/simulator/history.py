"""One valid episode trajectory: a record per physical tick, complete checkpoints per storage mode.

"memory" / "disk" keep a complete checkpoint of every tick. "segment" keeps a complete checkpoint of the episode's
first tick and of each tick a segment starts at (Env._checkpoint_current); every other tick keeps a light record
whose ``world`` is None (tick identity, robot targets, task state and RNG are still recorded)."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class StateRef:
    episode_id: str
    state_id: int

    def __post_init__(self):
        if not isinstance(self.episode_id, str) or not self.episode_id:
            raise ValueError("StateRef requires an episode identity")
        if type(self.state_id) is not int or self.state_id < 0:
            raise ValueError("StateRef requires a nonnegative integer state_id")


@dataclass(frozen=True)
class StateInfo:
    episode_id: str
    branch_id: int
    state_id: int
    parent_state_id: int | None
    control_step: int
    physics_step: int
    sim_time_s: float
    terminated: bool
    truncated: bool

    @property
    def ref(self):
        return StateRef(self.episode_id, self.state_id)


@dataclass(frozen=True)
class EpisodeState:
    info: StateInfo
    world: Any
    robot: Any
    task: Any
    rng_state: dict


class EpisodeHistory:
    """No implicit eviction; only reset and explicit rewind invalidate states."""

    def __init__(self, episode_id: str, *, storage="memory", directory=None):
        self.episode_id = episode_id
        self._states: dict[int, EpisodeState] = {}
        if storage not in {"segment", "memory", "disk"}:
            raise ValueError("History storage must be segment, memory or disk")
        self.storage = storage
        self._spool = None
        if storage == "disk":
            from .checkpoint_spool import Spool
            self._spool = Spool(directory)
        self._next_id = 0
        self._next_branch = 1

    def next_state_id(self) -> int:
        return self._next_id

    def append(self, state: EpisodeState) -> None:
        info = state.info
        if info.episode_id != self.episode_id or info.state_id != self._next_id:
            raise ValueError("History identity or state sequence mismatch")
        if info.parent_state_id is not None and info.parent_state_id not in self._states:
            raise ValueError("Unknown parent state")
        if self._spool is not None:
            self._spool.save(state)
        self._states[info.state_id] = state if self._spool is None else info
        self._next_id += 1

    def get(self, state_id: int) -> EpisodeState:
        if isinstance(state_id, bool) or not isinstance(state_id, int):
            raise ValueError("state_id must be an integer from this episode")
        try:
            value = self._states[state_id]
            return value if self._spool is None else self._spool.load(state_id)
        except KeyError as exc:
            raise ValueError(f"Unknown state_id {state_id} in current episode") from exc

    def upgrade(self, state_id: int, world) -> None:
        """Complete a light record ("segment" storage) with the world checkpoint of that same tick."""
        if self._spool is not None:
            raise ValueError("Only in-memory history records can be completed")
        state = self.get(state_id)
        if state.world is not None:
            return
        self._states[state_id] = replace(state, world=world)

    def new_branch(self) -> int:
        result = self._next_branch
        self._next_branch += 1
        return result

    def resolve(self, ref: StateRef) -> EpisodeState:
        if not isinstance(ref, StateRef) or ref.episode_id != self.episode_id:
            raise ValueError("State reference belongs to a different episode")
        return self.get(ref.state_id)

    def truncate_after(self, ref: StateRef) -> tuple[EpisodeState, ...]:
        return tuple(self.iter_truncate_after(ref))

    def iter_truncate_after(self, ref: StateRef):
        """Release discarded snapshots one at a time, including disk backing."""
        self.resolve(ref)
        keys = tuple(self._states)
        discarded = keys[keys.index(ref.state_id) + 1:]
        # Never reset _next_id: stale references must never become valid again.
        for key in discarded:
            state = self.get(key)
            del self._states[key]
            if self._spool is not None:
                self._spool.remove(key)
            yield state

    def states(self) -> tuple[StateInfo, ...]:
        return tuple(state.info if self._spool is None else state for state in self._states.values())

    def close(self):
        if self._spool is not None:
            self._spool.close()
        self._states.clear()


"""Immutable records emitted by the local simulator after a control action."""
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class Transition:
    episode_id: str
    branch_id: int
    previous_state_id: int
    state_id: int
    control_step: int
    physics_step: int
    sim_time_s: float
    physics_steps: int
    action_duration_s: float
    observation: Mapping[str, Any]
    action: Mapping[str, Any]
    next_observation: Mapping[str, Any]
    reward: float
    terminated: bool
    truncated: bool
    info: Mapping[str, Any]
