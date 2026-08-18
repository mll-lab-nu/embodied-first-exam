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
       pushes along it toward the commanded speed. A glancing contact with the
       diverter flap turns the ball, and the drive then carries it on in the new
       direction. The branch is therefore chosen by the flap's geometry; a drive
       that knew about the branches would be deciding the outcome it is supposed
       to be measuring.

    1b. **It pushes with a bounded force, and never writes velocity.** This is
       what stops it walking the ball through a closed gate. `BallShuttle` writes
       the velocity directly, which is fine against a wide flat gate, but a state
       write beats any contact: the solver resolves the overlap and the next step
       puts the full speed back, ratcheting the ball through. Observed
       2026-08-19 on an under-rotated flap -- 12 mm of plate, and the ball forced
       its way past into the branch. A motor force goes through the solver
       instead, so the flap wins; `max_thrust` is the whole guarantee, and it is
       two orders below what the flap's joint friction resists.

       Nothing writes the spin either. A force through the centre makes the ball
       slide, and floor friction spins it up into rolling on its own -- the
       required friction is a tenth of what is available, so it rolls almost at
       once.
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

    Outside ``region`` -- the driven tray's footprint -- the drive hands over to
    `BallShuttle`'s constant deceleration, so the ball rolls clear and settles
    instead of running to the edge of the table.

    A region rather than the single x threshold this used to take. Measured
    2026-08-19: the threshold sat at the exit centres' x, and the branches run at
    an angle to x, so a ball riding a branch's inner wall was cut loose 11 mm
    BEFORE the mouth -- still inside the channel and still touching the wall. It
    then lost the remaining 0.103 m/s within 5.6 mm, against a coast model that
    predicts 59 mm, because the wall was doing the braking rather than the coast.
    Driving until the tray ends lets the ball leave under power and hand over in
    free space, where the coast is the only thing acting on it.

    The region is a rectangle, and it says nothing about branches -- a ball that
    went the wrong way leaves under power too.
    """

    def __init__(
        self,
        scene: Any,
        ball: Any,
        *,
        speed: float,
        radius: float,
        mass: float,
        region: tuple[float, float, float, float],
        thrust_gain: float = 1.0,
        max_thrust: float = 0.15,
        heading: tuple[float, float] = (1.0, 0.0),
        dt: float = 0.01,
        stall_steps: int = 5,
        offtrack_decel: float = 0.090,
        brake_rect: tuple[float, float, float, float, float] | None = None,
        brake_decel: float = 0.0,
        running: bool = False,
    ) -> None:
        self.scene = scene
        self.ball = ball
        self.speed = float(speed)
        self.radius = float(radius)
        self.mass = float(mass)
        self.thrust_gain = float(thrust_gain)
        self.max_thrust = float(max_thrust)
        x_lo, x_hi, y_lo, y_hi = (float(v) for v in region)
        if x_hi <= x_lo or y_hi <= y_lo:
            raise ValueError(f"HeadingDrive region must be non-empty, got {region}.")
        self.region = (x_lo, x_hi, y_lo, y_hi)
        self.dt = float(dt)
        self.stall_steps = max(1, int(stall_steps))
        self.offtrack_decel = max(0.0, float(offtrack_decel))
        # (cx, cy, half_along, half_across, yaw) in world xy, or None. Inside it
        # the coast brakes hard instead: the landing pad outside the commanded
        # exit, so the ball comes to rest ON the target rather than rolling on.
        self.brake_rect = None if brake_rect is None else tuple(float(v) for v in brake_rect)
        self.brake_decel = max(0.0, float(brake_decel))
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
        self._window: list[np.ndarray] = []
        self._original_step = None

    def start(self) -> None:
        """Release the ball. Idempotent, and resets the stall history."""

        self.running = True
        self.jammed = False
        self._stalled = 0
        self._last_xy = None
        self._window = []

    def ball_xy(self) -> np.ndarray:
        return _as_numpy(self.ball.get_pos()).reshape(-1, 3)[0][:2].astype(float)

    def drive(self) -> None:
        xy = self.ball_xy()
        if self._last_xy is None:
            self._last_xy = xy

        x_lo, x_hi, y_lo, y_hi = self.region
        if not (x_lo <= float(xy[0]) <= x_hi and y_lo <= float(xy[1]) <= y_hi):
            # Off the end of the tray: stop steering and let the
            # rolling-resistance stand-in bring it to rest where it can be seen.
            self.running = False
            self.coasting = True
            self.coast()
            return

        # NET displacement over a window, not per-step. Measured 2026-08-19: a ball
        # pressed against the diverter flap creeps and slides along it at well over
        # the per-step threshold while going nowhere, so a per-step test (which is
        # what `BallShuttle` uses, and which is right for a ball bouncing off a
        # gate) never fired and the run was labelled `ball_never_left` instead of
        # jammed. Over a window, sliding-in-place reads as the standstill it is.
        self._window.append(xy)
        if len(self._window) > self.stall_steps:
            self._window.pop(0)
        if len(self._window) >= self.stall_steps:
            progress = float(np.linalg.norm(xy - self._window[0]))
            if progress < 0.2 * self.speed * self.dt * self.stall_steps:
                self.running = False
                self.jammed = True
                # Hand over to the rolling-resistance stand-in rather than simply
                # stopping. Measured 2026-08-18 (`runs/div_roll_half.log`): the
                # contact leaves the ball ~18 mm/s going backwards, and with no
                # rolling resistance in the solver that velocity is kept forever --
                # the ball wedged at the flap tip, then crept 71 mm back up the lane
                # over the remaining rollout. A jam has to READ as a jam: the ball
                # has to come to rest where it stuck.
                self.coasting = True
                self._last_xy = xy
                self.coast()
                return
        self._last_xy = xy

        measured = _as_numpy(self.ball.get_dofs_velocity()).reshape(-1)[:2].astype(float)
        speed = float(np.linalg.norm(measured))
        # Below a quarter of the command the direction is noise (the ball is in
        # the middle of resolving a contact), so the previous heading is kept
        # rather than amplifying whatever the solver happened to leave behind.
        if speed > 0.25 * self.speed:
            self.heading = measured / speed
        self._push(self.thrust_gain * (self.heading * self.speed - measured))
        self.steps_driven += 1

    def _push(self, force) -> None:
        """Apply a horizontal motor force, magnitude-clamped to `max_thrust`."""

        force = np.asarray(force, dtype=float).reshape(2)
        magnitude = float(np.linalg.norm(force))
        if magnitude > self.max_thrust:
            force = force * (self.max_thrust / magnitude)
        self.ball.control_dofs_force(force, dofs_idx_local=[0, 1])

    def on_pad(self) -> bool:
        """Is the ball on the braking pad?"""

        if self.brake_rect is None:
            return False
        cx, cy, half_along, half_across, yaw = self.brake_rect
        dx, dy = self.ball_xy() - np.array([cx, cy], dtype=float)
        cos_yaw, sin_yaw = np.cos(yaw), np.sin(yaw)
        along = cos_yaw * dx + sin_yaw * dy
        across = -sin_yaw * dx + cos_yaw * dy
        return bool(abs(along) <= half_along and abs(across) <= half_across)

    def coast(self) -> None:
        """Shed speed at a constant rate; same stand-in as `BallShuttle.coast`.

        On the landing pad the rate is `brake_decel` instead, which is the pad
        being a high-friction mat. A mat rather than writing the velocity to zero:
        zeroing would put a physically impossible event into the observation
        stream, and these episodes are meant to become imitation data. The pad sits
        downstream of the exit mouth, where the verdict was already decided, so
        braking there changes where the ball ENDS, not what the episode scored.
        """

        decel = self.brake_decel if self.on_pad() else self.offtrack_decel
        measured = _as_numpy(self.ball.get_dofs_velocity()).reshape(-1)[:2].astype(float)
        speed = float(np.linalg.norm(measured))
        if decel <= 0.0 or speed <= 1e-4:
            self._push(np.zeros(2))
            return
        # Retarding force, not a velocity write: same reason as `drive`. Capped by
        # the speed it would take to a standstill inside one step, so the brake
        # cannot reverse the ball.
        stop = self.mass * speed / self.dt
        self._push(-min(self.mass * decel, stop) * measured / speed)

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
