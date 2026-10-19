"""Read-only travel of each real arm, independent of the skill's acting arm.

The native control row commands all arms at once. Selecting one `tcp` cannot
measure the other hand, and switching the selected arm is not hand travel.
"""
from __future__ import annotations

import math


class ArmTravel:
    def __init__(self):
        self.paths: dict[str, float] = {}
        self._last: dict[str, tuple] = {}
        self._tick: int | None = None

    def update(self, snapshot: dict) -> None:
        if snapshot['tick'] == self._tick:
            return
        self._tick = snapshot['tick']
        for arm, pose in snapshot.get('tcps', {}).items():
            here = tuple(float(x) for x in pose[0])
            if arm in self._last:
                self.paths[arm] += math.dist(here, self._last[arm])
            else:
                self.paths[arm] = 0.0
            self._last[arm] = here

    def snapshot(self) -> dict[str, float]:
        return dict(self.paths)


def window_travel(current: dict, start: dict) -> tuple[float, dict]:
    """Maximum per-hand travel in one causal window; no sum of two hands."""
    paths = {name: max(float(value) - float(start[name]), 0.0)
             for name, value in current.items() if name in start}
    return max(paths.values(), default=0.0), paths
