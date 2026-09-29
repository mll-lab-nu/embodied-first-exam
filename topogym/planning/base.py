"""Passive scripted policies: data in, one native control action out."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from topogym.utils.snapshots import freeze


class ScriptedPolicy(Protocol):
    def act(self, obs: Mapping) -> Mapping | None:
        """Return one native action; None ends a finite script without stepping.

        initialize(context) and on_segment_end(obs, result) are optional hooks.
        """
        ...


class ActionSequencePolicy:
    """Adapt an already computed sequence; each item consumes one control step."""

    def __init__(self, actions: Sequence[Mapping]):
        if not isinstance(actions, (list, tuple)):
            raise TypeError("actions must be a list or tuple")
        if any(not isinstance(action, Mapping) for action in actions):
            raise TypeError("Each action must be a mapping")
        self._actions = freeze(actions)
        self._index = 0

    def initialize(self, context):
        self._index = 0

    def act(self, obs):
        if self._index == len(self._actions):
            return None
        action = self._actions[self._index]
        self._index += 1
        return action
