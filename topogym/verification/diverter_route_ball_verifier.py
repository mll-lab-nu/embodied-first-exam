"""Which exit can the ball still reach?

The C4 (`connectivity`) invariant contract in
`docs/develop/framework/task_taxonomy_zh.md` Section 4.4 wants a reading on a
declared space. Here the space is the BALL's configuration space -- the robot only
turns the flap's lever and never touches the ball -- so `to_info()` declares
`"space": "c_free"`. The reading is S-T reachability, and there is exactly one
S-T pair: from the ball's release point, is there still a route to the target?

One pair because one branch is capped. Two open exits made "connectivity" a label
the judge applied rather than something the scene showed -- both exits counted as
arriving, so nothing in the picture said where the ball was supposed to end up.
With a dead end there is one destination, and whether a route to it exists is
decided by the flap.

Method, and its two departures from `gate_cage_ball_verifier`, which this is
otherwise a copy of:

1. **Obstacles carry a yaw.** 4.1's arena is axis-aligned; here the four branch
   walls and the flap all sit at the branch angle, so a rectangle is
   (centre, half extent, yaw) and a grid point is tested in the rectangle's own
   frame. Each obstacle is grown by the ball's radius separately and the results
   unioned, which is exact: dilation distributes over union. Doing it the other
   way round -- eroding the union of the CLEAR channels -- would be wrong, because
   erosion does not distribute, and two channels eroded by a 26 mm radius can stop
   overlapping at the fork and report an open route as closed.
2. **The fill is clipped at the exit plane.** The free space inside the channels
   is closed except at the two exit mouths, so a fill that ran through one mouth
   would come back round the outside of the structure and reach the other one --
   every phase would read as both-open. Blocking everything past
   `layout.exit_plane_x` makes the mouths sinks instead of doors. Both exits share
   that x by construction (the branches are mirror images), so the clip knows
   nothing about which branch is which.

The lever arm and the knob are NOT obstacles. They ride above the wall tops, and
the widest part of the ball that reaches out to a wall face is its equator, 8 mm
below the arm's underside -- so they are over the channel in plan view while being
clear of the ball in fact. Including them would block a branch that is open.

Measured offline 2026-08-19, by running this judge over the flap's whole travel:
both gaps stay closed from 0 to 15.0 degrees (the ball wedges -- docx 4.3's
intermediate failure state) and exactly one opens from 15.5 degrees on. So the
mechanism's real rotation tolerance is about half its travel, far looser than
`success.seat_tolerance_deg`; see `geometry_ok` for why success does not gate on
the seat.

Grown rectangles keep square corners rather than the true rounded Minkowski ones,
so the estimate is conservative (it can only over-block). The passages here are
90 mm against a 52 mm ball, so nothing turns on the corners.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np

from topogym.tasks.connectivity.diverter_route_ball import (
    SIDES,
    DiverterRouteBallScene,
    side_sign,
)

INVARIANT_NAME = "st_reachable"


def _entity_pos(entity) -> np.ndarray:
    value = entity.get_pos()
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value).reshape(-1, 3)[0].astype(float)


@dataclass(frozen=True)
class OrientedRect:
    """A rectangle in task-frame xy, with a yaw. Half extents are along its own axes."""

    center: tuple[float, float]
    half: tuple[float, float]
    yaw: float = 0.0

    def blocked_mask(self, grid_x: np.ndarray, grid_y: np.ndarray, inflate: float) -> np.ndarray:
        dx = grid_x - float(self.center[0])
        dy = grid_y - float(self.center[1])
        cos_yaw, sin_yaw = np.cos(self.yaw), np.sin(self.yaw)
        local_x = cos_yaw * dx + sin_yaw * dy
        local_y = -sin_yaw * dx + cos_yaw * dy
        return (np.abs(local_x) <= self.half[0] + inflate) & (
            np.abs(local_y) <= self.half[1] + inflate
        )


@dataclass(frozen=True)
class DiverterRouteBallState:
    """One reading of the flap's phase and of where the ball got to."""

    ball_xy: tuple[float, float]
    flap_angle: float
    sealed_side: str | None
    dead_end_side: str
    live_side: str
    target_reachable: bool
    reached_target: bool = False
    in_dead_end: bool = False
    ball_stuck: bool = False
    settle_drift: float = 0.0

    @property
    def seated(self) -> bool:
        """Whether the flap reached one of its two seats.

        Diagnostic only. It is deliberately NOT part of success: docx 4.3 puts the
        marble test in charge, and the measured landing error of the arm (about
        4 degrees) sits right on top of any tolerance tight enough to be worth
        having. What "seated" is good for is telling one failure from another --
        a ball wedged with the flap short of a seat is an under-rotation, a ball
        wedged with it seated is something else.
        """

        return self.sealed_side is not None

    @property
    def invariant_value(self) -> int:
        """Is the target reachable from the ball's release point: 1 or 0.

        A single S-T pair now, not a bit per exit. Closing one branch is what
        makes it a single pair: there is one destination, and the flap decides
        whether a route to it exists.
        """

        return int(bool(self.target_reachable))

    @property
    def judge_disagrees(self) -> bool:
        """The one combination that cannot be true: the ball got somewhere the
        flood fill says it cannot go.

        Only this direction is a contradiction. "A path exists but the ball did
        not take it" is ordinary -- the ball has to be aimed into the branch, and
        a flap that is open but badly angled throws it into a wall. The reverse
        means the judge is wrong, and that has happened: a 6 mm grid over-blocked
        by half a cell diagonal and called an open route closed, which only came
        out because a human watched the ball go through it.
        """

        return bool(self.reached_target and not self.target_reachable)

    @property
    def is_terminal(self) -> bool:
        """Success: the ball reached the target, and is not stuck on the way."""

        return bool(self.reached_target and not self.ball_stuck)

    @property
    def failure_label(self) -> str | None:
        """Which way it went wrong, kept apart from a bare False."""

        if self.is_terminal:
            return None
        if self.in_dead_end:
            return "dead_end"
        if self.ball_stuck:
            # Wedged short of a seat is an under-rotation and is named after its
            # cause; wedged with the flap seated is something else, because a
            # seated flap leaves the full channel width open.
            return "ball_stuck_at_fork" if self.seated else "flap_not_seated"
        return "ball_never_left"

    def to_info(self) -> dict[str, Any]:
        return {
            "invariant": INVARIANT_NAME,
            "invariant_value": self.invariant_value,
            "invariant_signed": False,
            "space": "c_free",
            "subject": "ball",
            "gateway": "diverter_flap",
            "ball_xy": [float(v) for v in self.ball_xy],
            "flap_angle_deg": float(np.rad2deg(self.flap_angle)),
            "sealed_side": self.sealed_side,
            "seated": bool(self.seated),
            "dead_end_side": self.dead_end_side,
            "live_side": self.live_side,
            "target_reachable": bool(self.target_reachable),
            "reached_target": bool(self.reached_target),
            "in_dead_end": bool(self.in_dead_end),
            "ball_stuck": bool(self.ball_stuck),
            "settle_drift": float(self.settle_drift),
            "judge_disagrees": bool(self.judge_disagrees),
            "failure_label": self.failure_label,
            "terminal": bool(self.is_terminal),
        }


@dataclass(frozen=True)
class DiverterRouteBallEvaluator:
    """Success = the ball left by the commanded exit, with the judge agreeing."""

    def obstacle_rects(self, scene: DiverterRouteBallScene) -> list[OrientedRect]:
        """Footprints of everything that blocks the ball, in task-frame xy.

        The fixtures come from the layout rather than from the Genesis entities:
        they are static and the config is their single source, so reading them
        back would only add a way for the two to disagree. The flap is the one
        moving obstacle and IS read from the scene, through its joint angle.
        """

        layout = scene.layout
        half_width = layout.half_width
        thickness = layout.wall_thickness
        offset = half_width + 0.5 * thickness
        rects: list[OrientedRect] = []

        # Entry lane: two straight side walls plus the inlet end.
        x0, x1 = layout.entry_start_x, layout.junction_x
        for side in SIDES:
            rects.append(
                OrientedRect(
                    center=(0.5 * (x0 + x1), side_sign(side) * offset),
                    half=(0.5 * (x1 - x0), 0.5 * thickness),
                )
            )
        rects.append(
            OrientedRect(
                center=(x0 - 0.5 * thickness, 0.0),
                half=(0.5 * thickness, half_width + thickness),
            )
        )

        # Branch walls: outer away from the splitter, inner toward it. The dead
        # branch runs on past the live one's exit plane and is capped.
        for side in SIDES:
            yaw = float(np.deg2rad(layout.branch_yaw_deg(side)))
            end_station = layout.branch_end_station(side)
            for station, sign in (
                (layout.outer_wall_station, -1.0),
                (layout.inner_wall_station, 1.0),
            ):
                center = layout.branch_point(
                    side, 0.5 * (station + end_station), sign * offset
                )
                rects.append(
                    OrientedRect(
                        center=(float(center[0]), float(center[1])),
                        half=(0.5 * (end_station - station), 0.5 * thickness),
                        yaw=yaw,
                    )
                )
        dead = layout.dead_end_side
        cap_center = layout.branch_point(
            dead, layout.branch_end_station(dead) + 0.5 * thickness
        )
        rects.append(
            OrientedRect(
                center=(float(cap_center[0]), float(cap_center[1])),
                half=(0.5 * thickness, half_width + thickness),
                yaw=float(np.deg2rad(layout.branch_yaw_deg(dead))),
            )
        )

        # The flap, from its live joint angle. It hangs from the pivot at the nose
        # and points along the link's local -x, so its centre is half a length back
        # along that direction. No height test, unlike 4.1's gate: this flap only
        # ever turns, so it is always down in the channel.
        angle = scene.flap_angle()
        length = layout.flap_length
        nose = layout.nose_xy()
        center = nose - 0.5 * length * np.array([np.cos(angle), np.sin(angle)], dtype=float)
        rects.append(
            OrientedRect(
                center=(float(center[0]), float(center[1])),
                half=(0.5 * length, 0.5 * float(layout.cfg.diverter.flap.thickness)),
                yaw=float(angle),
            )
        )
        return rects

    def _exit_patch(self, layout, side: str) -> OrientedRect:
        """Target region for one exit, sitting just INSIDE the exit plane.

        Upstream of the plane because the fill is clipped there; a patch centred on
        the mouth itself would have half its cells cut away. The scene draws its
        target bullseye on this same rectangle, so the picture and the verdict
        cannot drift apart.
        """

        patch = float(layout.cfg.success.exit_patch)
        center = layout.exit_patch_center(side)
        return OrientedRect(
            center=(float(center[0]), float(center[1])),
            half=(0.5 * patch, 0.5 * patch),
        )

    def target_reachable(self, scene: DiverterRouteBallScene) -> bool:
        """Flood-fill the ball's free space from the release point to the target."""

        layout = scene.layout
        radius = layout.ball_radius
        pitch = float(layout.cfg.success.grid_pitch)
        rects = self.obstacle_rects(scene)

        x_lo, x_hi, y_half = layout.footprint_bounds()
        # Nothing past the exit plane takes part: see the module docstring.
        x_hi = min(x_hi, layout.exit_plane_x + pitch)
        xs = np.arange(x_lo, x_hi + pitch, pitch)
        ys = np.arange(-y_half, y_half + pitch, pitch)
        grid_x, grid_y = np.meshgrid(xs, ys, indexing="ij")

        blocked = np.zeros(grid_x.shape, dtype=bool)
        for rect in rects:
            blocked |= rect.blocked_mask(grid_x, grid_y, radius)

        live = layout.live_side
        target_mask = self._exit_patch(layout, live).blocked_mask(grid_x, grid_y, 0.0)

        release = layout.ball_release_center() - np.asarray(layout.task_origin, dtype=float)
        start = (
            int(np.clip(round((float(release[0]) - x_lo) / pitch), 0, len(xs) - 1)),
            int(np.clip(round((float(release[1]) + y_half) / pitch), 0, len(ys) - 1)),
        )
        # The seed cell can read as blocked when the release point is close to the
        # inlet wall, which it is. Seeding there anyway is correct -- the question
        # is where the ball can go, not whether its centre starts clear.
        seen = np.zeros_like(blocked)
        seen[start] = True
        queue = deque([start])
        while queue:
            i, j = queue.popleft()
            if target_mask[i, j]:
                return True
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ni, nj = i + di, j + dj
                if not (0 <= ni < len(xs) and 0 <= nj < len(ys)):
                    continue
                if not seen[ni, nj] and not blocked[ni, nj]:
                    seen[ni, nj] = True
                    queue.append((ni, nj))
        return False

    def classify(
        self,
        scene: DiverterRouteBallScene,
        *,
        reached_target: bool = False,
        in_dead_end: bool = False,
        ball_stuck: bool = False,
        settle_drift: float = 0.0,
    ) -> DiverterRouteBallState:
        layout = scene.layout
        angle = scene.flap_angle()
        ball_xy = (
            _entity_pos(scene.ball_entity())[:2]
            - np.asarray(layout.task_origin, dtype=float)[:2]
        )
        return DiverterRouteBallState(
            ball_xy=(float(ball_xy[0]), float(ball_xy[1])),
            flap_angle=float(angle),
            sealed_side=layout.sealed_side_at(angle),
            dead_end_side=layout.dead_end_side,
            live_side=layout.live_side,
            target_reachable=self.target_reachable(scene),
            reached_target=bool(reached_target),
            in_dead_end=bool(in_dead_end),
            ball_stuck=bool(ball_stuck),
            settle_drift=float(settle_drift),
        )

    def is_success(self, scene: DiverterRouteBallScene, **kwargs) -> bool:
        return self.classify(scene, **kwargs).is_terminal
