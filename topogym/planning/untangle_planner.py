from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .subgoal import PlannedSubgoal
from .waypoint import EpisodePlan, WaypointPlan, WaypointTarget


@dataclass(frozen=True)
class UntangleEndpointMoveCommand:
    """One topology-level endpoint relocation for the Untangle task."""

    action: int
    rope_index: int
    rope_name: str
    endpoint_index: int
    endpoint_name: str
    source_hole: tuple[int, int]
    target_hole: tuple[int, int]
    source_xy: tuple[float, float]
    target_xy: tuple[float, float]
    conflict_count_before: int
    conflict_count_after: int


def _hole_distance(layout, a: tuple[int, int], b: tuple[int, int]) -> float:
    pos_a = layout.hole_center(int(a[0]), int(a[1]))
    pos_b = layout.hole_center(int(b[0]), int(b[1]))
    return float(np.linalg.norm(pos_a[:2] - pos_b[:2]))


def _hole_xy(layout, hole: tuple[int, int]) -> tuple[float, float]:
    pos = layout.hole_center(int(hole[0]), int(hole[1]))
    return (float(pos[0]), float(pos[1]))


def plan_next_untangle_move(topology_env, layout) -> tuple[UntangleEndpointMoveCommand, EpisodePlan] | None:
    """Choose the next endpoint move that best reduces the high-level topology.

    This mirrors the original prototype oracle: prefer moving the rope that is
    on top of an active crossing, then choose the valid target hole that lowers
    the conflict count with the shortest endpoint travel.
    """

    state = topology_env.topology_state()
    if state.is_terminal:
        return None

    preferred = [crossing[2] for crossing in state.crossings]
    rope_order: list[int] = []
    for rope_index in preferred + list(range(topology_env.rope_count)):
        if rope_index not in rope_order:
            rope_order.append(rope_index)

    best_action = None
    best_score = (float("inf"), float("inf"))
    best_preview = None
    for rope_index in rope_order:
        path = state.rope_paths[rope_index]
        for endpoint_index in (0, 1):
            current_hole = path[0 if endpoint_index == 0 else -1]
            for row in range(layout.rows):
                for col in range(layout.cols):
                    target_hole = (row, col)
                    if target_hole == current_hole:
                        continue
                    preview, invalid, wrong_rope = topology_env.preview_move(
                        rope_index,
                        endpoint_index,
                        target_hole,
                    )
                    if invalid or wrong_rope:
                        continue
                    score = (
                        float(preview.conflict_count),
                        _hole_distance(layout, current_hole, target_hole),
                    )
                    if score < best_score:
                        best_score = score
                        best_preview = preview
                        best_action = topology_env.move_to_action(
                            rope_index,
                            endpoint_index,
                            target_hole,
                        )

    if best_action is None or best_preview is None:
        return None

    rope_index, endpoint_index, target_hole = topology_env.action_to_move(best_action)
    rope_name = str(topology_env.rope_names[rope_index])
    endpoint_name = "start" if int(endpoint_index) == 0 else "end"
    source_hole = state.rope_paths[rope_index][0 if int(endpoint_index) == 0 else -1]
    command = UntangleEndpointMoveCommand(
        action=int(best_action),
        rope_index=int(rope_index),
        rope_name=rope_name,
        endpoint_index=int(endpoint_index),
        endpoint_name=endpoint_name,
        source_hole=(int(source_hole[0]), int(source_hole[1])),
        target_hole=(int(target_hole[0]), int(target_hole[1])),
        source_xy=_hole_xy(layout, source_hole),
        target_xy=_hole_xy(layout, target_hole),
        conflict_count_before=int(state.conflict_count),
        conflict_count_after=int(best_preview.conflict_count),
    )
    subgoal = PlannedSubgoal(
        subgoal_id=(
            f"{command.rope_name}_{command.endpoint_name}_"
            f"{command.source_hole[0]}_{command.source_hole[1]}_to_"
            f"{command.target_hole[0]}_{command.target_hole[1]}"
        ),
        kind="move_rope_endpoint",
        entity=f"{command.rope_name}:{command.endpoint_name}",
        target={
            "rope_index": command.rope_index,
            "endpoint_index": command.endpoint_index,
            "source_hole": command.source_hole,
            "target_hole": command.target_hole,
            "conflict_count_before": command.conflict_count_before,
            "conflict_count_after": command.conflict_count_after,
        },
    )
    waypoint_plan = WaypointPlan(
        plan_id="untangle_endpoint_relocation",
        waypoints=(
            WaypointTarget(
                label="source_endpoint",
                position=(command.source_xy[0], command.source_xy[1], 0.0),
                metadata={
                    "rope": command.rope_name,
                    "endpoint": command.endpoint_name,
                    "hole": command.source_hole,
                },
            ),
            WaypointTarget(
                label="target_hole",
                position=(command.target_xy[0], command.target_xy[1], 0.0),
                metadata={
                    "rope": command.rope_name,
                    "endpoint": command.endpoint_name,
                    "hole": command.target_hole,
                },
            ),
        ),
        metadata={
            "planner": "untangle_topology_greedy_endpoint_move",
            "action": command.action,
        },
    )
    episode_plan = EpisodePlan(
        task_id="untangle",
        subgoals=(subgoal,),
        waypoint_plan=waypoint_plan,
        plan_id="untangle_topology_greedy_endpoint_move",
        metadata={
            "action": command.action,
            "rope_name": command.rope_name,
            "endpoint_name": command.endpoint_name,
            "conflict_count_before": command.conflict_count_before,
            "conflict_count_after": command.conflict_count_after,
        },
    )
    return command, episode_plan
