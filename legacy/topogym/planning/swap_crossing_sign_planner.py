"""Oracle for `swap_crossing_sign` (docx 3.2): re-plan, take the first move, repeat.

Physical picture: 2 or 3 ropes from a power strip cross 1 or 2 times; the arm
only grasps plugs, and the rope placed last lies on top. Flipping every
crossing therefore takes 2-5 grasp-lift-lay moves in an order the geometry
forces (`swap_crossing_sign_sequence.py` explains why and searches for them).

Each call plans from the *measured* ropes (centerlines, crossing code, plug
poses) to the target code and turns only the first move into hand targets; the
demo executes it, lets the ropes settle, measures again and calls back. A move
the physics resolves a little differently -- the pinned crossing of the stage B
probe slid 4 cm -- is absorbed by the next plan instead of derailing a fixed
script.

Executing one planned move (grasp the plug of rope R; `hang` of it comes off
the table; lay it at the landing):

- Every hand target at the plan's hand height sits on a circle round the peel
  point of radius ``sqrt((carry_taut * hang)^2 - height^2)``: the lift takes the
  plug up onto it (pulled back toward the peel point, not straight up -- straight
  up asks for more rope than was lifted, and on 2026-09-12 dragged the rope before
  the peel point 0.5-6 cm), the carry swings round it in steps of at most
  `swing_step_deg`, and from the end of the swing the plug goes down at the
  landing, 95-97 % of the lifted length out, so the tail lies nearly straight.
  Held further out than the circle, the hand drags the rope (stage C, 2026-09-11:
  1.23-1.26x the tail, 4-8 cm).
- A pinned rope (still under another rope upstream) needs nothing extra: its peel
  point is already past the pin by `hold`, and no target leaves that circle.

Modes, same machinery, different target code:

    oracle         every crossing flipped                   -> success
    restack_same   first no crossings, then the spawn again -> judged `unchanged`
    flip_nearest   only the crossing nearest the plugs      -> success on one
                                                               crossing, `partial_flip` on two
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .rope_crossings import CrossingCode
from .subgoal import PlannedSubgoal
from .swap_crossing_sign_sequence import (
    Move,
    Plan,
    RopeLay,
    SequenceParams,
    best_progress_move,
    crossings_of,
    goal_reached,
    plan_sequence,
    rope_lays,
    target_for,
)
from .untangle_continuous_planner import UntangleContinuousMoveCommand
from .waypoint import EpisodePlan, WaypointPlan, WaypointTarget


def _plug_xy(rope_scene, polyline: np.ndarray, strand: int) -> np.ndarray:
    connector = getattr(rope_scene, "free_end_connectors", {}).get(strand)
    if connector is None:
        return np.asarray(polyline[-1, :2], dtype=float)
    raw = connector.get_pos()
    if hasattr(raw, "detach"):
        raw = raw.detach().cpu().numpy()
    return np.asarray(raw, dtype=float).reshape(-1)[:2]


def _task_state(rope_scene, polylines: dict[int, np.ndarray]) -> tuple[dict[int, RopeLay], np.ndarray]:
    """Measured world centerlines -> planner state in the task frame, plug last."""

    origin = np.asarray(rope_scene.layout.task_origin, dtype=float)
    shifted = {}
    for strand, poly in polylines.items():
        pts = np.asarray(poly, dtype=float) - origin
        # z too: the planner stacks each laid tail at z = 1, 2, ... above the
        # table, which is only "on top" if the measured ropes sit near z = 0.
        # The welded plug's pose is exact; the last centreline bin inherits settle drift.
        pts[-1, :2] = _plug_xy(rope_scene, poly, strand) - origin[:2]
        shifted[strand] = pts
    return rope_lays(shifted), origin


def execute_targets(rope_scene, lay: RopeLay, move: Move, *, origin: np.ndarray, rope_radius: float, params: SequenceParams):
    """(carry, swing, cross, settle, hand_height) in world coordinates for one planned move.

    carry, the swing waypoints and cross are on the circle round the peel point at
    the hand height (module docstring); settle is the landing on the table.
    """

    table = float(rope_scene.layout.world_z(0.0))
    peel = np.asarray(move.peel_xy, dtype=float)
    height = float(move.hand_height)
    radius = math.sqrt(max((params.carry_taut * move.hang) ** 2 - height ** 2, 0.0))
    plug = np.asarray(lay.plug, dtype=float) - peel
    land = np.asarray(move.land_xy, dtype=float) - peel
    start = math.atan2(plug[1], plug[0])
    turn = (math.atan2(land[1], land[0]) - start + math.pi) % (2.0 * math.pi) - math.pi
    # A plug already nearer the peel point than the circle is lifted where it is
    # and eased out to the circle over the swing.
    first = min(float(np.linalg.norm(plug)), radius)
    count = max(1, math.ceil(abs(turn) / math.radians(params.swing_step_deg)))
    points = [
        peel + (first + (radius - first) * i / count) * np.array([math.cos(start + turn * i / count), math.sin(start + turn * i / count)])
        for i in range(count + 1)
    ]

    def world(xy, z):
        return (float(xy[0] + origin[0]), float(xy[1] + origin[1]), float(table + z))

    return (
        world(points[0], height),
        [world(p, height) for p in points[1:-1]],
        world(points[-1], height),
        world(peel + land, rope_radius),
        height,
    )


@dataclass(frozen=True)
class SwapCrossingSignRule:
    mode: str = "oracle"

    def target(self, spawn_code: CrossingCode, *, cleared: bool) -> CrossingCode:
        if self.mode == "restack_same":
            return spawn_code if cleared else ()
        return target_for(self.mode, spawn_code)

    def reached(self, code: CrossingCode, spawn_code: CrossingCode, *, cleared: bool) -> bool:
        """Is this end state the one the mode asks for?

        Compared per rope pair, the way the judge grades it (decision 2026-09-12):
        a pair has to cross as often as the target does with the same rope on top,
        and the order of a pair's crossings along the ropes is free. `target` is
        one code that satisfies this, not the only one.
        """

        return goal_reached(code, self.target(spawn_code, cleared=cleared))

    def plan(
        self,
        rope_scene,
        polylines,
        *,
        spawn_code: CrossingCode,
        cleared: bool,
        params: SequenceParams,
        moved_bystanders: frozenset = frozenset(),
    ) -> Plan | None:
        state, _origin = _task_state(rope_scene, polylines)
        return plan_sequence(state, self.target(spawn_code, cleared=cleared), params, moved_bystanders)

    def decide(
        self,
        rope_scene,
        polylines: dict[int, np.ndarray],
        *,
        spawn_code: CrossingCode,
        cleared: bool,
        params: SequenceParams,
        moved_bystanders: frozenset = frozenset(),
    ) -> tuple[UntangleContinuousMoveCommand, EpisodePlan, Plan] | None:
        """The next move, or None when no sequence reaches the target from here.

        ``moved_bystanders``: ropes this episode already moved and left in no
        crossing (`plan_sequence`).
        """

        state, origin = _task_state(rope_scene, polylines)
        target = self.target(spawn_code, cleared=cleared)
        plan = plan_sequence(state, target, params, moved_bystanders)
        if plan is not None and plan.moves:
            move, moves_left, fallback = plan.moves[0], len(plan.moves), False
        else:
            # No complete sequence from here. Rather than stop with a move
            # available, take the one that puts the most crossings right; it must
            # strictly reduce the mismatch, so this cannot oscillate. Both
            # 3-rope 2-crossing dead ends of 2026-09-12 had such a move.
            move = best_progress_move(state, target, params)
            if move is None:
                return None
            plan, moves_left, fallback = Plan((move,), target, 0), 1, True
        lay = state[move.strand]
        rope_radius = float(rope_scene.layout.cfg.rope.radius)
        carry, swing, cross, settle, height = execute_targets(
            rope_scene, lay, move, origin=origin, rope_radius=rope_radius, params=params
        )
        grasp_world = (float(lay.plug[0] + origin[0]), float(lay.plug[1] + origin[1]))
        partners = sorted({c.a if c.b == move.strand else c.b for c in crossings_of(state, params) if move.strand in (c.a, c.b)})
        command = UntangleContinuousMoveCommand(
            strand_index=int(move.strand),
            under_strand=int(partners[0]) if partners else -1,
            crossing_z_gap=0.0,
            grasp_arclength=1.0,
            grasp_xy=grasp_world,
            place_xy=(float(move.land_xy[0] + origin[0]), float(move.land_xy[1] + origin[1])),
            lift_z=float(rope_scene.layout.world_z(0.0) + height),
            tail_arc=0.0,
            crossing_arc=float(move.hang),
            carry=carry,
            cross=cross,
            settle=settle,
            crossing_count_before=len(crossings_of(state, params)),
        )
        metadata = {
            "strand_index": int(move.strand),
            "hang": float(move.hang),
            "hand_height": float(height),
            "pinned": move.pinned_at is not None,
            "hang_window": list(move.hang_window),
            "reach": float(move.reach),
            "place_clearance": float(move.land_clearance),
            "place_clearance_target": float(params.place_clearance),
            "corridor_clearance": float(move.corridor_clearance),
            "moves_left": moves_left,
            # True = no full sequence existed; this is the best single move.
            "fallback": fallback,
            # hand waypoints between carry and cross, round the peel point
            "swing": [list(p) for p in swing],
        }
        subgoal = PlannedSubgoal(
            subgoal_id=f"relay_s{move.strand}",
            kind="relay_rope_tail",
            entity=rope_scene.layout.strand_name(move.strand),
            target={"strand_index": int(move.strand), "peel_xy": list(move.peel_xy), "land_xy": list(move.land_xy)},
        )
        waypoints = WaypointPlan(
            plan_id="swap_crossing_sign_relay",
            waypoints=(
                WaypointTarget(label="grasp", position=(grasp_world[0], grasp_world[1], float(polylines[move.strand][-1, 2])), metadata={"strand": int(move.strand)}),
                WaypointTarget(label="carry", position=carry, metadata={"hand_height": float(height)}),
                *(WaypointTarget(label="swing", position=p, metadata={}) for p in swing),
                WaypointTarget(label="cross", position=cross, metadata={}),
                WaypointTarget(label="place", position=settle, metadata={}),
            ),
            metadata={"planner": "swap_crossing_sign_sequence"},
        )
        episode_plan = EpisodePlan(
            task_id="swap_crossing_sign",
            subgoals=(subgoal,),
            waypoint_plan=waypoints,
            plan_id="swap_crossing_sign_relay",
            metadata=metadata,
        )
        return command, episode_plan, plan


_MODES = ("oracle", "restack_same", "flip_nearest")


def make_swap_crossing_sign_rule(mode: str) -> SwapCrossingSignRule:
    """`run.oracle_mode` -> rule."""

    if str(mode) not in _MODES:
        raise ValueError(f"unknown oracle_mode {mode!r}; expected one of {sorted(_MODES)}")
    return SwapCrossingSignRule(mode=str(mode))


__all__ = ["SwapCrossingSignRule", "execute_targets", "make_swap_crossing_sign_rule"]
