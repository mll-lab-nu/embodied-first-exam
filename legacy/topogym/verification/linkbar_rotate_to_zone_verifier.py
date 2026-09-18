"""Is the pin resting on the zone of its own colour? (docx 4.4, reworked)

The invariant is `pin_zone`: which of the two painted zones the beam's end pin is
on, read from the joint angle against the layout's zone windows. It is an angle
test and nothing else -- the zones are paint, the pin never touches them, and there
is no latch. That is deliberate: the previous version of this task judged success
by welding the pin into a socket and pushing a cart, a reading the physics could
make but a viewer could not see. Here the verdict and the picture are one thing.

Two conditions on top of the angle, recorded separately so a miss says why:

- **At rest.** The joint's angular speed is under `success.max_angular_speed` when
  the reading is taken. The beam parks on joint friction after the release, and a
  pin that is still sliding across a zone is not "resting on" it. The caller
  settles `success.settle_steps` before asking.
- **The arm did its job.** `rotate_ok` is the primitive's own gates (target
  error, follow error, lag, release drift, finger travel). A run the arm botched
  is not evidence about the scene either way, and is labelled as such rather than
  as a wrong zone.

`failure_label` names the first condition that failed, in the order a viewer would
notice them: the arm fumbled, the pin is on the wrong colour, the pin is on no
zone, the beam is still moving.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

INVARIANT_NAME = "pin_zone"


@dataclass(frozen=True)
class LinkbarRotateState:
    """One reading: where the pin is, which zone it should be on, and whether it has stopped."""

    pin_angle: float
    pin_zone: str | None
    target_zone: str
    angular_speed: float
    max_angular_speed: float
    # The primitive's own gates. A run the arm botched is not evidence about the
    # scene either way.
    rotate_ok: bool = True

    @property
    def invariant_value(self) -> str | None:
        return self.pin_zone

    @property
    def in_target(self) -> bool:
        return bool(self.pin_zone is not None and self.pin_zone == self.target_zone)

    @property
    def at_rest(self) -> bool:
        return bool(abs(float(self.angular_speed)) <= float(self.max_angular_speed))

    @property
    def geometry_ok(self) -> bool:
        return self.in_target

    @property
    def is_terminal(self) -> bool:
        return bool(self.in_target and self.at_rest and self.rotate_ok)

    @property
    def failure_label(self) -> str | None:
        if self.is_terminal:
            return None
        if not self.rotate_ok:
            return "rotate_check_failed"
        if self.pin_zone is None:
            return "outside_zone"
        if not self.in_target:
            return "wrong_zone"
        return "not_at_rest"

    def to_info(self) -> dict[str, Any]:
        return {
            "invariant": INVARIANT_NAME,
            "invariant_value": self.invariant_value,
            "invariant_signed": False,
            # Where the reading lives, for the C4 contract: the beam's one joint
            # coordinate, partitioned into the two painted windows. Not a ball's
            # free space (4.1, 4.3) and no longer a constraint graph.
            "space": "joint_angle",
            "subject": "linkbar",
            "gateway": "colour_zone",
            "pin_angle": float(self.pin_angle),
            "pin_zone": self.pin_zone,
            "target_zone": self.target_zone,
            "in_target": bool(self.in_target),
            "angular_speed": float(self.angular_speed),
            "at_rest": bool(self.at_rest),
            "rotate_ok": bool(self.rotate_ok),
            "failure_label": self.failure_label,
            "terminal": bool(self.is_terminal),
        }


@dataclass(frozen=True)
class LinkbarRotateEvaluator:
    """Success = the pin rests inside the zone painted its colour, and the beam has stopped."""

    def classify(self, rotate_scene, *, rotate_ok: bool = True) -> LinkbarRotateState:
        layout = rotate_scene.layout
        angle = float(rotate_scene.arm_angle())
        return LinkbarRotateState(
            pin_angle=angle,
            pin_zone=layout.zone_at(angle),
            target_zone=layout.target_zone(),
            angular_speed=float(rotate_scene.arm_velocity()),
            max_angular_speed=float(layout.cfg.success.max_angular_speed),
            rotate_ok=bool(rotate_ok),
        )

    def is_success(self, rotate_scene, **kwargs) -> bool:
        return self.classify(rotate_scene, **kwargs).is_terminal
