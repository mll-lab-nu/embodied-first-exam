"""Latch a swinging link into whichever socket its pin reaches.

`connector_latch.py` is the same idea for a different mechanism: it captures a
free handle and then WRITES its pose every step. That works when the latched body
only has to stay put, and it is wrong here. docx 4.4 judges by lifting: if the
beam is latched into component B's catch, pulling B up has to be resisted through
the latch and the beam's hinge. A pose written every step transmits nothing -- B
would rise and the beam would sit there -- so the latch has to be a constraint the
solver knows about.

Genesis has one: `scene.rigid_solver.add_weld_constraint(link_a, link_b)` fixes
the two links' current relative transform. That makes the latch a real edge in the
scene's constraint graph, which is also what the verifier's union-find reads back
(`get_weld_constraints`) rather than trusting a flag this class sets.

The capture test is on the PIN, not on the beam's body or its joint angle: the pin
is the part that enters a socket, and stating it that way keeps the latch honest
about mechanisms whose joint angle and pin position are not interchangeable. Only
one socket can be latched -- a second capture is refused rather than silently
replacing the first, because "which socket did it go into" is the answer the whole
task turns on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np


@dataclass
class SocketWeld:
    """Weld a moving link to the first socket body its pin gets close enough to.

    ``sockets`` maps a socket name to the link index a latch there welds to.
    ``seat_xy_fn(name)`` reports where that socket's seat is NOW and ``pin_xy_fn()``
    where the pin is, both in the same frame.

    Both are read live rather than passed as fixed positions. A socket bolted to a
    body that can move -- which is exactly the interesting one, since welding to
    something immovable merges nothing -- would otherwise be tested for capture at
    the place it was built, and the latch would fire on a socket that had since
    been pushed aside.
    """

    scene: Any
    moving_link_idx: int
    sockets: dict[str, int]
    seat_xy_fn: Callable[[str], Any]
    pin_xy_fn: Callable[[], Any]
    capture_tolerance_xy: float
    auto_capture: bool = True
    latched: str | None = None
    capture_checks: int = 0
    last_gap: dict[str, float] = field(default_factory=dict)
    step_hook_mode: str = field(default="uninstalled", init=False)
    _original_step: Any = field(default=None, init=False, repr=False)
    _wrapped_step: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.sockets:
            raise ValueError("SocketWeld needs at least one socket to latch into.")
        if float(self.capture_tolerance_xy) <= 0.0:
            raise ValueError("capture_tolerance_xy must be positive.")
        self.sockets = {str(name): int(link_idx) for name, link_idx in self.sockets.items()}
        self.last_gap = {name: float("inf") for name in self.sockets}
        self.install()

    # ------------------------------------------------------------------ hook

    def install(self) -> None:
        if self._wrapped_step is not None:
            return

        original_step = self.scene.step

        def wrapped_step(*args: Any, **kwargs: Any) -> Any:
            result = original_step(*args, **kwargs)
            if self.latched is None and self.auto_capture:
                self.try_engage()
            return result

        self._original_step = original_step
        self._wrapped_step = wrapped_step
        self.scene.step = wrapped_step
        self.step_hook_mode = "step_wrapper"

    def uninstall(self) -> None:
        if self._wrapped_step is None:
            return
        if self.scene.step is self._wrapped_step:
            self.scene.step = self._original_step
        self._original_step = None
        self._wrapped_step = None
        self.step_hook_mode = "uninstalled"

    def __enter__(self) -> "SocketWeld":
        return self

    def __exit__(self, *exc) -> None:
        self.uninstall()

    # ---------------------------------------------------------------- capture

    def gaps(self) -> dict[str, float]:
        """Distance from the pin to each seat right now."""

        pin = np.asarray(self.pin_xy_fn(), dtype=float).reshape(2)
        return {
            name: float(
                np.linalg.norm(pin - np.asarray(self.seat_xy_fn(name), dtype=float).reshape(2))
            )
            for name in self.sockets
        }

    def try_engage(self) -> str | None:
        """Latch if the pin is inside a seat's capture window. Idempotent once latched."""

        if self.latched is not None:
            return self.latched

        self.capture_checks += 1
        self.last_gap = self.gaps()
        tolerance = float(self.capture_tolerance_xy)
        # Nearest first, so a pair of overlapping windows would still resolve to
        # the socket the pin is actually in rather than to whichever was declared
        # first. `LinkbarMergeLayout.validate` keeps them from overlapping at all;
        # this makes the tie-break explicit anyway.
        for name, gap in sorted(self.last_gap.items(), key=lambda item: item[1]):
            if gap > tolerance:
                break
            self.scene.rigid_solver.add_weld_constraint(
                int(self.moving_link_idx), int(self.sockets[name])
            )
            self.latched = name
            return name
        return None

    def release(self) -> str | None:
        """Delete the weld. Inspection and reset only -- a latch does not un-latch itself."""

        if self.latched is None:
            return None
        released = self.latched
        self.scene.rigid_solver.delete_weld_constraint(
            int(self.moving_link_idx), int(self.sockets[released])
        )
        self.latched = None
        return released
