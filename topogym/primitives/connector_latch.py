from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .physical_contact import entity_pos


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


@dataclass
class ConnectorLatch:
    """Capture a physically inserted rigid handle at a fixed connector pose.

    The latch remains inactive during transport. A scene step hook detects
    entry into the connector capture region and then enforces the latched pose.
    This models the connector's snap-lock mechanism, not a robot-to-object
    grasp attachment.
    """

    scene: Any
    handle: Any
    target_pos: np.ndarray
    capture_tolerance_xy: float
    capture_tolerance_z: float
    capture_max_tilt_deg: float
    auto_capture: bool = True
    target_quat: np.ndarray = field(
        default_factory=lambda: np.array([1.0, 0.0, 0.0, 0.0], dtype=float)
    )
    active: bool = False
    capture_checks: int = 0
    last_xy_error: float = float("inf")
    last_z_error: float = float("inf")
    last_tilt_deg: float = float("inf")
    step_hook_mode: str = field(default="uninstalled", init=False)
    _original_step: Any = field(default=None, init=False, repr=False)
    _wrapped_step: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.target_pos = np.asarray(self.target_pos, dtype=float)
        self.target_quat = np.asarray(self.target_quat, dtype=float)
        if self.target_pos.shape != (3,):
            raise ValueError(f"target_pos must have shape (3,), got {self.target_pos}.")
        if self.target_quat.shape != (4,):
            raise ValueError(f"target_quat must have shape (4,), got {self.target_quat}.")
        quat_norm = float(np.linalg.norm(self.target_quat))
        if quat_norm <= 1e-8:
            raise ValueError("target_quat must have nonzero norm.")
        self.target_quat = self.target_quat / quat_norm
        if float(self.capture_tolerance_xy) <= 0.0:
            raise ValueError("capture_tolerance_xy must be positive.")
        if float(self.capture_tolerance_z) <= 0.0:
            raise ValueError("capture_tolerance_z must be positive.")
        if not 0.0 < float(self.capture_max_tilt_deg) <= 90.0:
            raise ValueError("capture_max_tilt_deg must be in (0, 90].")
        self.install()

    def install(self) -> None:
        """Install a latch hook supported by both old and new Genesis scenes."""
        if self._wrapped_step is not None:
            return

        original_step = self.scene.step

        def wrapped_step(*args: Any, **kwargs: Any) -> Any:
            self.sync()
            result = original_step(*args, **kwargs)
            if self.active:
                self.sync()
            elif self.auto_capture:
                self.try_engage()
            return result

        self._original_step = original_step
        self._wrapped_step = wrapped_step
        self.scene.step = wrapped_step
        self.step_hook_mode = "step_wrapper"

    def uninstall(self) -> None:
        """Restore the scene step method when this latch still owns it."""
        if self._wrapped_step is None:
            return
        if self.scene.step is self._wrapped_step:
            self.scene.step = self._original_step
        self._original_step = None
        self._wrapped_step = None
        self.step_hook_mode = "uninstalled"

    def try_engage(self) -> bool:
        if self.active:
            return True

        self.capture_checks += 1
        current = entity_pos(self.handle)
        quat = _as_numpy(self.handle.get_quat()).reshape(-1, 4)[0].astype(float)
        quat_norm = float(np.linalg.norm(quat))
        if quat_norm <= 1e-8:
            return False
        quat /= quat_norm
        w, x, y, z = quat
        local_z_world = np.array(
            [
                2.0 * (x * z + w * y),
                2.0 * (y * z - w * x),
                1.0 - 2.0 * (x * x + y * y),
            ],
            dtype=float,
        )
        self.last_xy_error = float(np.linalg.norm(current[:2] - self.target_pos[:2]))
        self.last_z_error = abs(float(current[2] - self.target_pos[2]))
        self.last_tilt_deg = float(
            np.rad2deg(np.arccos(np.clip(abs(local_z_world[2]), 0.0, 1.0)))
        )
        self.active = bool(
            self.last_xy_error <= float(self.capture_tolerance_xy)
            and self.last_z_error <= float(self.capture_tolerance_z)
            and self.last_tilt_deg <= float(self.capture_max_tilt_deg)
        )
        if self.active:
            self.sync()
        return self.active

    def sync(self) -> None:
        if not self.active:
            return
        self.handle.set_pos(tuple(self.target_pos), zero_velocity=True)
        self.handle.set_quat(
            tuple(self.target_quat),
            zero_velocity=True,
            relative=False,
        )
