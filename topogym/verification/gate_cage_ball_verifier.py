"""Is the ball's free space still connected to the outside?

The C4 (`connectivity`) invariant contract in
`docs/develop/framework/task_taxonomy_zh.md` Section 4.4 wants an integer reading
on a declared space. Here the space is the BALL's configuration space, not any
body the gripper touches -- the robot never contacts the ball at all -- so
`to_info()` declares `"space": "c_free"`.

Method: rasterize the arena's floor plan, grow every obstacle by the ball's
radius so the ball can be treated as a point, then flood-fill from where the ball
actually is. Reaching the edge of the rasterized region means a path to the
outside exists and the ball is not caged. This is deterministic and costs
milliseconds, which is why it is the primary judge; the shake test is kept as a
separate physical probe rather than as the definition of success.

The gate counts as an obstacle only when it is low enough to be in the ball's way.
A plate hovering above the walls seals nothing, and a judge that ignored the
plate's height would call an episode successful the moment the arm arrived.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np

from topogym.tasks.connectivity.gate_cage_ball import GateCageBallScene

INVARIANT_NAME = "ball_escape_paths"


def _entity_pos(entity) -> np.ndarray:
    value = entity.get_pos()
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value).reshape(-1, 3)[0].astype(float)


@dataclass(frozen=True)
class GateCageBallState:
    """One reading of where the ball is and whether it can still get out."""

    ball_xy: tuple[float, float]
    ball_z: float
    inside: bool
    caged: bool
    pinched: bool
    gate_blocking: bool
    gate_bottom_z: float
    door_y: float
    release_stable: bool

    @property
    def escape_paths(self) -> int:
        """0 when the ball is boxed in, 1 when a route to the outside remains.

        An integer rather than a bool because Section 4.4 asks for one, and
        because the multi-exit variants (a second gate, a diverter) read on the
        same scale without redefining the invariant.
        """

        return 0 if self.caged else 1

    @property
    def invariant_value(self) -> int:
        return self.escape_paths

    @property
    def geometry_ok(self) -> bool:
        return bool(self.caged and self.inside and not self.pinched)

    @property
    def is_terminal(self) -> bool:
        return bool(self.geometry_ok and self.release_stable)

    @property
    def failure_label(self) -> str | None:
        """Which way it went wrong, kept apart from a bare False.

        Sealing early, sealing late and catching the ball in the doorway are three
        different timing errors, and collapsing them into one label would throw
        away exactly the signal an error analysis over the trigger instant needs.
        """

        if self.is_terminal:
            return None
        if self.pinched:
            return "ball_pinched_in_doorway"
        if not self.inside:
            return "ball_outside" if self.gate_blocking else "ball_escaped"
        if not self.caged:
            return "gate_not_sealed"
        return "unstable_after_release"

    def to_info(self) -> dict[str, Any]:
        return {
            "invariant": INVARIANT_NAME,
            "invariant_value": int(self.invariant_value),
            "invariant_signed": False,
            "space": "c_free",
            "subject": "ball",
            "gateway": "gate_slot",
            "ball_xy": [float(v) for v in self.ball_xy],
            "ball_z": float(self.ball_z),
            "door_y": float(self.door_y),
            "inside": bool(self.inside),
            "caged": bool(self.caged),
            "pinched": bool(self.pinched),
            "gate_blocking": bool(self.gate_blocking),
            "gate_bottom_z": float(self.gate_bottom_z),
            "geometry_ok": bool(self.geometry_ok),
            "release_stable": bool(self.release_stable),
            "failure_label": self.failure_label,
            "terminal": bool(self.is_terminal),
        }


@dataclass(frozen=True)
class GateCageBallEvaluator:
    """Success = the ball ends inside, with no route out, and stays there."""

    def _obstacle_rects(self, scene: GateCageBallScene) -> tuple[np.ndarray, bool, float]:
        """Footprints of everything that blocks the ball, in task-frame xy.

        Rectangles come from the layout rather than from the Genesis entities: the
        fixtures are static and the config is their single source, so reading them
        back would only add a way for the two to disagree. The gate is the one
        moving obstacle and IS read from the scene.
        """

        layout = scene.layout
        cfg = layout.cfg
        inner_lo, inner_hi = layout.wall_inner_x()
        wall_t = float(cfg.channel.wall_thickness)
        slot_near, slot_far = layout.slot_y_extent()
        rects = [
            # (x_min, x_max, y_min, y_max). Side walls come in two segments per
            # side, split around the slot strip where the guide posts stand.
            (inner_lo - wall_t, inner_lo, layout.entry_start_y, slot_near),
            (inner_hi, inner_hi + wall_t, layout.entry_start_y, slot_near),
            (inner_lo - wall_t, inner_lo, slot_far, layout.flat_end_y),
            (inner_hi, inner_hi + wall_t, slot_far, layout.flat_end_y),
            (
                inner_lo - wall_t,
                inner_hi + wall_t,
                layout.flat_end_y,
                layout.flat_end_y + float(cfg.far_wall.thickness),
            ),
        ]
        post_w = float(cfg.gate_slot.post_width)
        post_t = float(cfg.gate_slot.post_thickness)
        half_gap = 0.5 * float(cfg.gate_slot.guide_gap)
        for inner, sign in ((inner_lo, -1.0), (inner_hi, 1.0)):
            x_center = inner + sign * 0.5 * post_w
            for y_center in (
                layout.door_y - half_gap - 0.5 * post_t,
                layout.door_y + half_gap + 0.5 * post_t,
            ):
                rects.append(
                    (
                        x_center - 0.5 * post_w,
                        x_center + 0.5 * post_w,
                        y_center - 0.5 * post_t,
                        y_center + 0.5 * post_t,
                    )
                )
        gate_pos = _entity_pos(scene.gate_entity()) - np.asarray(layout.task_origin, dtype=float)
        gate_height = float(cfg.gate.seated_top_z) - float(cfg.gate.seated_bottom_z)
        gate_bottom_z = float(gate_pos[2]) - 0.5 * gate_height
        # In the ball's way only if it reaches below the ball's crown. Held above
        # that, the plate is a thing in the air and the doorway is still open.
        ball_top_z = layout.floor_top_z + 2.0 * layout.ball_radius
        gate_blocking = gate_bottom_z < ball_top_z
        if gate_blocking:
            gate_w = float(cfg.gate.width)
            gate_t = float(cfg.gate.thickness)
            rects.append(
                (
                    float(gate_pos[0]) - 0.5 * gate_w,
                    float(gate_pos[0]) + 0.5 * gate_w,
                    float(gate_pos[1]) - 0.5 * gate_t,
                    float(gate_pos[1]) + 0.5 * gate_t,
                )
            )
        return np.asarray(rects, dtype=float), gate_blocking, gate_bottom_z

    def classify(
        self, scene: GateCageBallScene, *, release_stable: bool = True
    ) -> GateCageBallState:
        layout = scene.layout
        cfg = layout.cfg
        radius = layout.ball_radius
        pitch = float(cfg.success.grid_pitch)

        ball = _entity_pos(scene.ball_entity()) - np.asarray(layout.task_origin, dtype=float)
        rects, gate_blocking, gate_bottom_z = self._obstacle_rects(scene)

        # Rasterize a region that extends past every fixture, so "the fill reached
        # the edge" unambiguously means "the ball has a route out of the arena"
        # rather than "the grid was too small".
        pad = 4.0 * radius
        x_lo = float(min(rects[:, 0].min(), ball[0])) - pad
        x_hi = float(max(rects[:, 1].max(), ball[0])) + pad
        y_lo = float(min(rects[:, 2].min(), ball[1])) - pad
        y_hi = float(max(rects[:, 3].max(), ball[1])) + pad
        xs = np.arange(x_lo, x_hi + pitch, pitch)
        ys = np.arange(y_lo, y_hi + pitch, pitch)
        grid_x, grid_y = np.meshgrid(xs, ys, indexing="ij")

        # Grow each obstacle by the ball's radius, which turns the ball into a
        # point and makes the fill a plain connectivity question.
        blocked = np.zeros(grid_x.shape, dtype=bool)
        for x0, x1, y0, y1 in rects:
            blocked |= (
                (grid_x >= x0 - radius)
                & (grid_x <= x1 + radius)
                & (grid_y >= y0 - radius)
                & (grid_y <= y1 + radius)
            )

        start = (
            int(np.clip(round((ball[0] - x_lo) / pitch), 0, len(xs) - 1)),
            int(np.clip(round((ball[1] - y_lo) / pitch), 0, len(ys) - 1)),
        )
        # The ball's own cell reads as blocked when it is touching something, which
        # is the normal resting state. Seeding the fill there anyway is correct --
        # the question is where the ball can go, not whether its centre is clear.
        seen = np.zeros_like(blocked)
        seen[start] = True
        queue = deque([start])
        escaped = False
        while queue:
            i, j = queue.popleft()
            if i == 0 or j == 0 or i == len(xs) - 1 or j == len(ys) - 1:
                escaped = True
                break
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ni, nj = i + di, j + dj
                if not seen[ni, nj] and not blocked[ni, nj]:
                    seen[ni, nj] = True
                    queue.append((ni, nj))

        inside = bool(float(ball[1]) > layout.door_y)
        # Caught in the doorway: the plate came down ON the ball, so it is held
        # short of its seat and the ball's body is what is under it. Two readings,
        # both required. Until 2026-09-03 this only asked whether the ball's
        # centre lay within the slot strip, which a caged ball shuttling in a
        # short closed section satisfies every time it touches the seated
        # plate -- four of ten variant cells were labelled pinched that way while
        # the plate sat fully down and the ball rolled free behind it.
        gate_y = float(_entity_pos(scene.gate_entity())[1] - float(layout.task_origin[1]))
        held_up = gate_bottom_z > float(cfg.gate.seated_bottom_z) + 0.005
        under_plate = abs(float(ball[1]) - gate_y) < radius + 0.5 * float(cfg.gate.thickness)
        pinched = bool(gate_blocking and held_up and under_plate)


        return GateCageBallState(
            ball_xy=(float(ball[0]), float(ball[1])),
            ball_z=float(ball[2]),
            inside=inside,
            caged=not escaped,
            pinched=pinched,
            gate_blocking=gate_blocking,
            gate_bottom_z=gate_bottom_z,
            door_y=layout.door_y,
            release_stable=bool(release_stable),
        )

    def is_success(self, scene: GateCageBallScene, *, release_stable: bool = True) -> bool:
        return self.classify(scene, release_stable=release_stable).is_terminal
