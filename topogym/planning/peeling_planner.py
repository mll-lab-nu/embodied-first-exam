from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .subgoal import PlannedSubgoal
from .waypoint import EpisodePlan, WaypointPlan, WaypointTarget


@dataclass(frozen=True)
class PeelingLiftCommand:
    """One physically-grounded peel/transport/place plan for a single PBD film."""

    grasp_start_xyz: tuple[float, float, float]
    corner_release_groups: int
    peel_group_count: int
    transport_target_xyz: tuple[float, float, float]
    place_target_xyz: tuple[float, float, float]


def plan_peeling_single_lift(layout) -> tuple[PeelingLiftCommand, EpisodePlan]:
    """Resolve the configured Peeling film geometry into a peel/transport/place plan.

    This mirrors the flat-cloth mesh and particle grouping the scene builder uses,
    so the plan is available before the PBD scene is built. The physical demo
    still reads the live grasp point at runtime (particles settle slightly under
    gravity/friction), so this plan is the *intended* sequence, not a replacement
    for the runtime follow-error checks.
    """

    physical = layout.cfg.physical
    mesh = layout.cloth_mesh()
    grasp_indices, adhesion_groups = layout.particle_groups(mesh.vertices)
    grasp_start = mesh.vertices[list(grasp_indices)].mean(axis=0)

    initial_groups = int(layout.cfg.adhesion.initial_release_groups)
    total_groups = len(adhesion_groups)
    remaining_groups = max(0, total_groups - initial_groups)
    sx, _sy = layout.peel_signs
    pull_direction = np.array(
        [
            -sx * float(physical.pull_distance),
            float(physical.pull_y_offset),
            float(physical.pull_height),
        ],
        dtype=float,
    )

    waypoints: list[WaypointTarget] = []
    for index in range(remaining_groups):
        alpha = (index + 1) / max(1, remaining_groups)
        target = grasp_start + alpha * pull_direction
        target[2] += float(physical.lift_delta)
        waypoints.append(
            WaypointTarget.from_sequence(
                f"peel_group_{initial_groups + index + 1:02d}",
                target,
                steps=int(physical.peel_segment_steps),
                metadata={"entity": "peeling_film", "phase": "peel"},
            )
        )

    transport_target = layout.placement_grasp_point(float(physical.transport_z))
    place_target = layout.placement_grasp_point(float(physical.place_corner_z))
    waypoints.append(
        WaypointTarget.from_sequence(
            "transport_to_target",
            transport_target,
            steps=int(physical.transport_steps),
            metadata={"entity": "peeling_film", "phase": "transport"},
        )
    )
    waypoints.append(
        WaypointTarget.from_sequence(
            "place_on_target",
            place_target,
            steps=int(physical.place_steps),
            metadata={"entity": "peeling_film", "phase": "place"},
        )
    )

    command = PeelingLiftCommand(
        grasp_start_xyz=tuple(float(value) for value in grasp_start),
        corner_release_groups=int(physical.corner_release_groups),
        peel_group_count=int(remaining_groups),
        transport_target_xyz=tuple(float(value) for value in transport_target),
        place_target_xyz=tuple(float(value) for value in place_target),
    )
    subgoal = PlannedSubgoal(
        subgoal_id="peeling_film_peel_transport_place",
        kind="peel_and_place",
        entity="peeling_film",
        target={
            "corner_release_groups": command.corner_release_groups,
            "peel_group_count": command.peel_group_count,
            "transport_target_xyz": command.transport_target_xyz,
            "place_target_xyz": command.place_target_xyz,
        },
    )
    waypoint_plan = WaypointPlan(
        plan_id="peeling_single_peel_transport_place",
        waypoints=tuple(waypoints),
        metadata={"planner": "peeling_single_lift"},
    )
    episode_plan = EpisodePlan(
        task_id="peeling",
        subgoals=(subgoal,),
        waypoint_plan=waypoint_plan,
        plan_id="peeling_single_peel_transport_place",
        metadata={
            "peel_group_count": command.peel_group_count,
            "corner_release_groups": command.corner_release_groups,
        },
    )
    return command, episode_plan
