"""Task base class.

A :class:`Task` owns a scene (any object with the small interface documented in
:class:`SceneLike`) and implements the task-specific parts: how the scene is reset,
the privileged observation and the success predicate. ``step`` applies an action,
advances the simulation by one control tick, evaluates the success latch and returns
``(obs, info)`` with ``info["success"]`` and ``info["phase"]`` every tick.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable

import numpy as np

from .types import Action, ObsDict


@runtime_checkable
class SceneLike(Protocol):
    """What a task needs from a backend scene (see ``backends/isaaclab_scene.py``)."""

    def step(self, action: Action) -> None: ...
    def robot_obs(self) -> Dict[str, np.ndarray]: ...
    def render_cameras(self) -> Dict[str, np.ndarray]: ...
    def get_state(self) -> Dict[str, Any]: ...
    def set_state(self, state: Dict[str, Any]) -> None: ...


class Task:
    """Base class of every task.

    Subclasses set :attr:`name` and :attr:`success_hold`, and implement
    :meth:`success_predicate`, :meth:`_reset_scene` and (usually)
    :meth:`privileged_obs`. The success latch: ``is_success()`` becomes True once
    ``success_predicate()`` has held for ``success_hold`` consecutive ticks and stays
    True for the rest of the episode (``latch=True``) or follows the hold window
    (``latch=False``).

    Args:
        cfg: the task's configuration dictionary (``tasks/<name>/cfg.yaml``).
        scene: a built backend scene.
        obs_mode: ``"full"`` renders cameras and tactile every tick, ``"state"`` skips
            the image observations (``scripts/replay.py`` re-renders them later).
    """

    name: str = "task"
    success_hold: int = 1
    latch: bool = True
    max_steps: int = 0
    """0 = no step limit."""

    def __init__(self, cfg: Optional[dict] = None, scene: Optional[SceneLike] = None, obs_mode: str = "full"):
        self.cfg: Dict[str, Any] = dict(cfg or {})
        self.scene = scene
        self.obs_mode = obs_mode
        self.t = 0
        self.seed: Optional[int] = None
        self.phase_id = -1
        self._hold_count = 0
        self._latched = False
        self._rng = np.random.default_rng(0)
        self.sensors: Dict[str, Any] = {}
        """Optional extra observation providers (e.g. tactile sensors): name -> callable returning a dict."""

    # ------------------------------------------------------------------ lifecycle
    def reset(self, seed: Optional[int] = None) -> ObsDict:
        """Reset the scene to the task's nominal state and return the first observation."""
        self.seed = int(seed) if seed is not None else 0
        self._rng = np.random.default_rng(self.seed)
        self.t = 0
        self.phase_id = -1
        self._hold_count = 0
        self._latched = False
        self._reset_scene(self.seed)
        self._update_success()
        return self.get_observation()

    def step(self, action: Action, phase_id: int = -1):
        """Apply ``action`` for one control tick. Returns ``(obs, info)``."""
        if not isinstance(action, Action):
            action = Action.from_vector(np.asarray(action))
        self.phase_id = int(phase_id)
        self._apply_action(action)
        self.t += 1
        self._update_success()
        obs = self.get_observation()
        info = self.info()
        return obs, info

    def close(self) -> None:
        """Release backend resources (default: nothing)."""

    # ------------------------------------------------------------------ hooks
    def _reset_scene(self, seed: int) -> None:
        """Place robot and objects in the nominal start state."""
        raise NotImplementedError

    def _apply_action(self, action: Action) -> None:
        if self.scene is None:
            raise RuntimeError("Task has no scene")
        self.scene.step(action)

    def success_predicate(self) -> bool:
        """Instantaneous success test, evaluated every tick."""
        raise NotImplementedError

    def privileged_obs(self) -> Dict[str, np.ndarray]:
        """Object poses and task metrics."""
        return {}

    def metrics(self) -> Dict[str, float]:
        """Scalar diagnostics copied into ``info`` (optional)."""
        return {}

    # ------------------------------------------------------------------ observation
    def get_observation(self) -> ObsDict:
        policy: Dict[str, np.ndarray] = {}
        privileged: Dict[str, np.ndarray] = {}
        if self.scene is not None:
            policy.update(self.scene.robot_obs())
            if self.obs_mode == "full":
                policy.update(self.scene.render_cameras())
        for name, provider in self.sensors.items():
            out = provider() if callable(provider) else provider.read()
            for k, v in out.items():
                (policy if k.endswith("_rgb") else privileged)[k] = v
        privileged.update(self.privileged_obs())
        return {"policy": policy, "privileged": privileged}

    def info(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "success": self.is_success(),
            "success_now": bool(self._success_now),
            "phase": self.phase_id,
            "t": self.t,
        }
        d.update(self.metrics())
        return d

    # ------------------------------------------------------------------ success latch
    def _update_success(self) -> None:
        try:
            now = bool(self.success_predicate())
        except NotImplementedError:
            now = False
        self._success_now = now
        if now:
            self._hold_count += 1
        else:
            self._hold_count = 0
        if self._hold_count >= max(1, self.success_hold):
            self._latched = True
        elif not self.latch:
            self._latched = False

    def is_success(self) -> bool:
        """Success predicate held for ``success_hold`` ticks (latched)."""
        return bool(self._latched)

    @property
    def timed_out(self) -> bool:
        return self.max_steps > 0 and self.t >= self.max_steps

    # ------------------------------------------------------------------ state
    def get_state(self) -> Dict[str, Any]:
        """Robot q/qd, rigid object poses, sidecar blob and the latch counters."""
        st = self.scene.get_state() if self.scene is not None else {}
        st = dict(st)
        st["_task"] = {"t": self.t, "hold": self._hold_count, "latched": self._latched, "seed": self.seed}
        return st

    def set_state(self, state: Dict[str, Any]) -> None:
        st = dict(state)
        meta = st.pop("_task", None)
        if self.scene is not None:
            self.scene.set_state(st)
        if meta:
            self.t = int(meta.get("t", 0))
            self._hold_count = int(meta.get("hold", 0))
            self._latched = bool(meta.get("latched", False))
            self.seed = meta.get("seed", self.seed)


__all__ = ["Task", "SceneLike"]
