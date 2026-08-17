"""Keep a ball running up and down a lane at a fixed speed.

The linear feeder in `gate_cage_ball`. Parts on a real vibratory rail travel at a
speed the rail sets, not one gravity sets, and modelling it that way removes a
whole family of tuning from the scene: no feed ramp, no return ramp, no slope
shallow enough to be at the mercy of solver stiction, and no energy bookkeeping
over a reversal. Speed becomes one number, and the timing that number produces is
exact rather than integrated.

**The drive does not overrule collision.** Only the along-lane velocity component
is written; z stays with gravity and contact, so the ball rests on the floor, and
nothing writes position. When something blocks the lane the solver stops the ball,
this class notices it stopped making progress, and reverses. That is the whole
mechanism, and it is why a closed gate reads as a cage: the ball bounces off the
plate and keeps shuttling INSIDE, while an open doorway simply lets it run out.

Blockage is detected from progress, not from contact queries or from velocity.
The ball's commanded velocity is re-imposed every step, so reading velocity back
would mostly return the command; what actually distinguishes "running" from
"pressed against the gate" is whether the ball moved.

Off the lane the drive stops and a rolling resistance takes over. The solver has
none of its own -- `tests/ball_roll_spike.py` measured a ball holding 0.3997 m/s
to four figures over 2.4 s -- so an escaped ball would otherwise run at full speed
until it fell off the table, which reads as a glitch rather than as an outcome.
The stand-in is a CONSTANT deceleration, which is the right form: rolling
resistance is Coulomb-like, so the distance to a stop grows with the square of the
speed and a faster variant genuinely rolls further. Viscous damping (Genesis'
`set_dofs_damping`) would be the wrong form, and the engine additionally warns
that damping on a free joint is non-physical.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


class BallShuttle:
    """Drive one ball along +/- y at constant speed, reversing when blocked.

    Wraps ``scene.step`` the same way `AttachmentManager` does, so the drive is
    applied once per step with no cooperation needed from the caller's loop.
    """

    def __init__(
        self,
        scene: Any,
        ball: Any,
        *,
        speed: float,
        radius: float,
        lane_min_y: float,
        lane_max_y: float,
        direction: int = 1,
        dt: float = 0.01,
        stall_steps: int = 3,
        offtrack_decel: float = 0.090,
    ) -> None:
        self.scene = scene
        self.ball = ball
        self.speed = float(speed)
        self.radius = float(radius)
        self.lane_min_y = float(lane_min_y)
        self.lane_max_y = float(lane_max_y)
        self.direction = 1 if int(direction) >= 0 else -1
        self.dt = float(dt)
        # One stalled step is noise (a step where the solver happened to resolve a
        # contact); several in a row is a wall.
        self.stall_steps = max(1, int(stall_steps))
        self.offtrack_decel = max(0.0, float(offtrack_decel))
        self.driving = True
        self.coasting = False
        self.reversals = 0
        self._stalled = 0
        self._last_y: float | None = None
        self._original_step = None

    def ball_y(self) -> float:
        return float(_as_numpy(self.ball.get_pos()).reshape(-1, 3)[0][1])

    def drive(self) -> None:
        y = self.ball_y()
        if self._last_y is None:
            self._last_y = y

        if not (self.lane_min_y <= y <= self.lane_max_y):
            # Out of the lane: stop steering and let rolling resistance bring it
            # to rest on the table. An episode that ends with the ball leaving
            # should show it leaving and settling, not running off the edge.
            self.driving = False
            self.coasting = True
            self._last_y = y
            self.coast()
            return

        progress = self.direction * (y - self._last_y)
        # Anything under a fifth of the commanded advance is not motion.
        if progress < 0.2 * self.speed * self.dt:
            self._stalled += 1
            if self._stalled >= self.stall_steps:
                self.direction = -self.direction
                self.reversals += 1
                self._stalled = 0
        else:
            self._stalled = 0
        self._last_y = y

        velocity = _as_numpy(self.ball.get_dofs_velocity()).reshape(-1)[:6].astype(float)
        velocity[0] = 0.0  # stay in the lane
        velocity[1] = self.direction * self.speed
        # Spin to match, so it reads as rolling rather than sliding. Rolling along
        # +y needs spin about -x: the contact point is one radius below the centre,
        # and its velocity v + omega_x * r has to vanish.
        velocity[3] = -velocity[1] / max(self.radius, 1e-9)
        velocity[4] = 0.0
        velocity[5] = 0.0
        self.ball.set_dofs_velocity(velocity)

    def coast(self) -> None:
        """Shed speed at a constant rate, in whatever direction the ball is going.

        Applied to the horizontal components only; z stays with gravity and
        contact. The spin is re-matched each step so a decelerating ball still
        reads as rolling rather than sliding to a halt.
        """

        if self.offtrack_decel <= 0.0:
            return
        velocity = _as_numpy(self.ball.get_dofs_velocity()).reshape(-1)[:6].astype(float)
        speed = float(np.hypot(velocity[0], velocity[1]))
        if speed <= 1e-6:
            return
        scale = max(0.0, speed - self.offtrack_decel * self.dt) / speed
        velocity[0] *= scale
        velocity[1] *= scale
        velocity[3] = -velocity[1] / max(self.radius, 1e-9)
        velocity[4] = velocity[0] / max(self.radius, 1e-9)
        velocity[5] = 0.0
        self.ball.set_dofs_velocity(velocity)

    def __enter__(self) -> BallShuttle:
        if self._original_step is not None:
            return self
        self._original_step = self.scene.step

        def wrapped_step(*args, **kwargs):
            if self.driving:
                self.drive()
            elif self.coasting:
                self.coast()
            return self._original_step(*args, **kwargs)

        self.scene.step = wrapped_step
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._original_step is not None:
            self.scene.step = self._original_step
            self._original_step = None
