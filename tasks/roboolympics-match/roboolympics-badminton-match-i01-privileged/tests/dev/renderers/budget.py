"""Frame-time budget of a player-image renderer (renderer rule 3): an observation (all of a seat's cameras) must be
drawn within the task's `frame_budget_ms`. tools/check measures it for the task's `renderer` parameter."""
from __future__ import annotations

import time

from .base import as_cameras


def frame_ms(renderer_cls, scene, state, cameras, n: int = 5, warmup: int = 1, **opts) -> float:
    """Median wall milliseconds per observation (every camera once), after `warmup` untimed observations."""
    cams = as_cameras(cameras)
    r = renderer_cls(scene, **opts)
    try:
        for _ in range(warmup):
            r.render(state, cams)
        times = []
        for _ in range(max(1, n)):
            t = time.perf_counter()
            r.render(state, cams)
            times.append((time.perf_counter() - t) * 1000.0)
    finally:
        r.close()
    times.sort()
    return times[len(times) // 2]


def check_budget(renderer_cls, scene, state, cameras, budget_ms: float, n: int = 5, **opts):
    """(ok, ms): ok when the renderer is real time and its median observation time is within budget_ms."""
    ms = frame_ms(renderer_cls, scene, state, cameras, n=n, **opts)
    return bool(getattr(renderer_cls, "realtime", False) and ms <= float(budget_ms)), ms
