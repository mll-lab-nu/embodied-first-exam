"""Ball feeders for the `connectivity` tasks: hold a ball's speed, not its path.

Two drives, one per task, sharing a rule: **the drive never overrules collision.**
Only horizontal velocity is written, so gravity and contact keep the ball on the
floor, and nothing writes position. What the two differ on is what happens when
something blocks the way, and that difference is the task:

| class | task | on blockage |
|---|---|---|
| `BallShuttle` | `gate_cage_ball` (docx 4.1) | reverse -- a caged ball keeps shuttling |
| `HeadingDrive` | `diverter_route_ball` (docx 4.3) | stop -- a jam at the fork IS the failure state |

`HeadingDrive` additionally does not steer at all: it maintains the speed and
takes the direction from whatever the solver produced. That is what keeps the
diverter honest -- the flap picks the branch, the feeder does not.

---

Keep a ball running up and down a lane at a fixed speed.

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


class HeadingDrive:
    """Hold a ball's horizontal speed and let collisions choose its direction.

    The feeder in `diverter_route_ball`. Three properties, each of which the task
    depends on:

    1. **It does not steer.** Each step it reads the ball's heading back and
       rescales it to the commanded speed. A glancing contact with the diverter
       flap turns the ball, and the drive then carries it on in the new
       direction. The branch is therefore chosen by the flap's geometry; a drive
       that knew about the branches would be deciding the outcome it is supposed
       to be measuring.
    2. **A blocked ball stops** rather than reversing (which is what
       `BallShuttle` does, because a caged ball has to keep shuttling to read as
       caged). A flap left half-open wedges the ball at the fork, and that
       stopped ball is the intermediate failure state docx 4.3 asks for.
    3. **It starts on command.** The arm turns the lever first and retreats, and
       only then is the ball released -- so the drive is idle until `start()`.
       Nothing has to hold the ball in the meantime: the lane is flat, so a ball
       at rest stays at rest, which is the property that made the horizontal
       layout worth the geometric deviation from the docx's vertical chute.

    Blockage is read from **position progress**, not from velocity: the commanded
    velocity is re-imposed every step, so reading velocity back would mostly
    return the command. This is the same reasoning as `BallShuttle`'s.

    Past ``drive_max_x`` the ball has left through an exit and the drive hands
    over to `BallShuttle`'s constant deceleration, so it rolls clear and settles
    instead of running to the edge of the table. Both exits sit at the same x by
    construction (the branches are mirror images), so one threshold serves both
    and the handover still knows nothing about which branch was taken.
    """

    def __init__(
        self,
        scene: Any,
        ball: Any,
        *,
        speed: float,
        radius: float,
        drive_max_x: float,
        heading: tuple[float, float] = (1.0, 0.0),
        dt: float = 0.01,
        stall_steps: int = 5,
        offtrack_decel: float = 0.090,
        running: bool = False,
    ) -> None:
        self.scene = scene
        self.ball = ball
        self.speed = float(speed)
        self.radius = float(radius)
        self.drive_max_x = float(drive_max_x)
        self.dt = float(dt)
        self.stall_steps = max(1, int(stall_steps))
        self.offtrack_decel = max(0.0, float(offtrack_decel))
        heading = np.asarray(heading, dtype=float).reshape(2)
        norm = float(np.linalg.norm(heading))
        if norm <= 0.0:
            raise ValueError("HeadingDrive needs a non-zero initial heading.")
        self.heading = heading / norm
        self.running = bool(running)
        self.jammed = False
        self.coasting = False
        self.steps_driven = 0
        self._stalled = 0
        self._last_xy: np.ndarray | None = None
        self._original_step = None

    def start(self) -> None:
        """Release the ball. Idempotent, and resets the stall history."""

        self.running = True
        self.jammed = False
        self._stalled = 0
        self._last_xy = None

    def ball_xy(self) -> np.ndarray:
        return _as_numpy(self.ball.get_pos()).reshape(-1, 3)[0][:2].astype(float)

    def drive(self) -> None:
        xy = self.ball_xy()
        if self._last_xy is None:
            self._last_xy = xy

        if float(xy[0]) > self.drive_max_x:
            # Out through an exit: stop steering and let the rolling-resistance
            # stand-in bring it to rest where it can be seen.
            self.running = False
            self.coasting = True
            self.coast()
            return

        progress = float(np.linalg.norm(xy - self._last_xy))
        # Anything under a fifth of the commanded advance is not motion.
        if progress < 0.2 * self.speed * self.dt:
            self._stalled += 1
            if self._stalled >= self.stall_steps:
                self.running = False
                self.jammed = True
                self._last_xy = xy
                return
        else:
            self._stalled = 0
        self._last_xy = xy

        velocity = _as_numpy(self.ball.get_dofs_velocity()).reshape(-1)[:6].astype(float)
        measured = velocity[:2]
        speed = float(np.linalg.norm(measured))
        # Below a quarter of the command the direction is noise (the ball is in
        # the middle of resolving a contact), so the previous heading is kept
        # rather than amplifying whatever the solver happened to leave behind.
        if speed > 0.25 * self.speed:
            self.heading = measured / speed
        velocity[0] = self.heading[0] * self.speed
        velocity[1] = self.heading[1] * self.speed
        # Rolling, not sliding: the contact point one radius below the centre has
        # to be stationary, so omega = (z_hat x v) / r.
        velocity[3] = -velocity[1] / max(self.radius, 1e-9)
        velocity[4] = velocity[0] / max(self.radius, 1e-9)
        velocity[5] = 0.0
        self.ball.set_dofs_velocity(velocity)
        self.steps_driven += 1

    def coast(self) -> None:
        """Shed speed at a constant rate; same stand-in as `BallShuttle.coast`."""

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

    def __enter__(self) -> HeadingDrive:
        if self._original_step is not None:
            return self
        self._original_step = self.scene.step

        def wrapped_step(*args, **kwargs):
            if self.running:
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
