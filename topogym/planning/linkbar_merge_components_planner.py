"""Which catch should the beam go into? (docx 4.4)

Everything else in this task is one fixed motion: take the knob, sweep an arc, let
go. The only decision is which of the two catches to aim at, and the two are the
same part at the same radius costing the same sweep. What separates them is which
assembly each one is bolted to -- so that is what has to be READ, and it is the
whole reason the task is not solvable by looking at the catches.

The decision is arithmetic on the layout, so this module needs no Genesis and is
unit-testable offline.

Two rules behind one interface, the shape `diverter_route_ball_planner` uses, so
the contrast baseline is a measurement rather than an assertion:

    LinkbarOracleRule   read which catch belongs to the other assembly, go there
    NearestSocketRule   go to whichever catch is the shorter turn

`NearestSocketRule` wins exactly the instances where the nearer catch happens to be
B's -- half of them, once the two catch angles are drawn independently on either
side of the start. Keeping it next to the oracle rather than inside a demo is what
turns "the shortcut is pinned at chance" from a claim into a number.

**The oracle does not know the answer by name.** It asks the layout who owns each
catch and picks the one that is not the beam's own assembly, which is exactly the
fact `component_count` turns on. Hard-coding `"b1"` here would make the oracle
right for a reason the verifier does not use, and would quietly survive a layout
where the ownership was swapped.

**The turn never takes the long way round.** The joint is continuous, so both catches
are reachable in either direction, but the far way sweeps the pin through the other
catch and a jaw at pin height is a hard stop. The signed difference is used as-is
rather than wrapped into (-180, 180], which for a layout `LinkbarMergeLayout.validate`
accepts is always the direct path.
"""

from __future__ import annotations

from dataclasses import dataclass

# The assembly the beam is hinged to. A catch bolted to this one is a cycle edge:
# latching there is a real constraint that merges nothing.
BEAM_ASSEMBLY = "component_a"


@dataclass(frozen=True)
class LinkbarRotateCommand:
    """What to do with the beam this episode."""

    target_socket: str
    start_angle: float
    target_angle: float
    sweep: float
    rotate: bool
    reason: str

    @property
    def sweep_sign(self) -> int:
        """+1 for a counter-clockwise turn, -1 for clockwise, 0 for no turn."""

        if self.sweep > 0.0:
            return 1
        if self.sweep < 0.0:
            return -1
        return 0


def _command(layout, current_angle: float, socket: str, reason: str) -> LinkbarRotateCommand:
    current_angle = float(current_angle)
    target = float(layout.target_angle(socket))
    sweep = target - current_angle
    return LinkbarRotateCommand(
        target_socket=str(socket),
        start_angle=current_angle,
        target_angle=target,
        sweep=sweep,
        rotate=abs(sweep) > float(layout.capture_tolerance_xy) / float(layout.arm_radius),
        reason=reason,
    )


@dataclass(frozen=True)
class LinkbarOracleRule:
    """Latch into the catch that belongs to the other assembly, merging the two."""

    def decide(self, layout, current_angle: float) -> LinkbarRotateCommand:
        socket = layout.merging_socket()
        if layout.socket_owner(socket) == BEAM_ASSEMBLY:
            raise ValueError(
                f"Catch {socket!r} is owned by {BEAM_ASSEMBLY!r}, the assembly the beam "
                "is already part of, so latching there would merge nothing. The layout "
                "has no merging catch."
            )
        return _command(layout, current_angle, socket, "merge_other_assembly")


@dataclass(frozen=True)
class NearestSocketRule:
    """Go to whichever catch is the shorter turn, whoever it belongs to.

    The shortcut docx 4.4 names. It is a property of the baseline, not of the scene:
    it never looks at ownership, so randomising the two catch angles independently
    leaves it right half the time.
    """

    def decide(self, layout, current_angle: float) -> LinkbarRotateCommand:
        socket = layout.nearest_socket(float(current_angle))
        return _command(layout, current_angle, socket, "nearest_catch")


def make_linkbar_rule(mode: str):
    """`run.oracle_mode` -> rule."""

    mode = str(mode)
    if mode == "oracle":
        return LinkbarOracleRule()
    if mode == "nearest_socket":
        return NearestSocketRule()
    raise ValueError(
        f"Unknown oracle_mode={mode!r}; expected 'oracle' or 'nearest_socket'."
    )
