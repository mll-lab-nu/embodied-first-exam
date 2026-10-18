"""World frame <-> team frame (interfaces v1 §2).

World frame: origin at the field centre, x along the 9 m length, y along the 6 m width, z up; metres, seconds, radians.
Blue (team A) attacks +x in the first half; the teams change ends at half time (the SSL game controller's
`blue_team_on_positive_half` flips; rulebook 2026-09-19 §4.3.5 "the goal it will attack in the first half").

Team frame: the team attacks +x; yaw counter-clockwise from +x. For a team attacking -x the team frame is the world
frame turned half a turn about z (x -> -x, y -> -y, yaw -> yaw + pi), so both teams see the field the same way.
"""

from __future__ import annotations

import math

TEAMS = ("blue", "yellow")


def other(team: str) -> str:
    return "yellow" if team == "blue" else "blue"


def attack_sign(team: str, half: int = 1, blue_first_positive: bool = True) -> int:
    """+1 if `team` attacks +x (world) in half `half` (1, 2; the shoot-out keeps the second half's ends), else -1."""
    s = 1 if blue_first_positive else -1
    if team != "blue":
        s = -s
    if half >= 2:
        s = -s
    return s


def wrap(a: float) -> float:
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def to_team(sign: int, x: float, y: float, yaw: float | None = None):
    """world pose -> team pose (sign = attack_sign of the team)."""
    if sign > 0:
        return (x, y) if yaw is None else (x, y, wrap(yaw))
    return (-x, -y) if yaw is None else (-x, -y, wrap(yaw + math.pi))


def to_world(sign: int, x: float, y: float, yaw: float | None = None):
    """team pose -> world pose (the map is its own inverse)."""
    return to_team(sign, x, y, yaw)


def vec_to_team(sign: int, vx: float, vy: float):
    """a world vector (velocity) -> team frame."""
    return (vx, vy) if sign > 0 else (-vx, -vy)


vec_to_world = vec_to_team
