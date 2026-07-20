from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from topogym.primitives.rim_rotate import rim_point_world, signed_rotation

from .subgoal import PlannedSubgoal
from .waypoint import EpisodePlan, WaypointPlan, WaypointTarget


@dataclass(frozen=True)
class StackedPlateRotateCommand:
    """Rotate one disk about the Y rod to the shared sector-alignment target.

    Carries the resolved rim geometry the oracle primitive needs, so execution
    consumes a command instead of recomputing layout math inline.
    """

    disk_name: str
    start_angle: float
    target_angle: float
    center_xyz: tuple[float, float, float]
    radius: float
    grasp_azimuth: float
    roll_sign: int
    grasp_radius_scale: float = 1.0


def _rim_waypoints(command: StackedPlateRotateCommand, *, arc_samples: int) -> list[WaypointTarget]:
    """Approach -> grasp -> arc samples -> retreat rim targets for one disk."""
    center = np.asarray(command.center_xyz, dtype=float)
    radius = float(command.radius)
    grip_radius = radius * float(command.grasp_radius_scale)
    sweep = signed_rotation(command.start_angle, command.target_angle, command.roll_sign)
    grasp_rim = rim_point_world(center, grip_radius, command.grasp_azimuth)

    approach = grasp_rim.copy()
    approach[2] += radius  # lifted clearance above the grasp rim point
    entity = f"disk_{command.disk_name}"

    waypoints = [
        WaypointTarget.from_sequence(
            f"{command.disk_name}_approach",
            approach,
            lifted=True,
            metadata={"entity": entity, "phase": "approach"},
        ),
        WaypointTarget.from_sequence(
            f"{command.disk_name}_grasp",
            grasp_rim,
            metadata={"entity": entity, "phase": "grasp"},
        ),
    ]
    samples = max(1, int(arc_samples))
    for i in range(1, samples + 1):
        azimuth = command.grasp_azimuth + (i / samples) * sweep
        point = rim_point_world(center, grip_radius, azimuth)
        waypoints.append(
            WaypointTarget.from_sequence(
                f"{command.disk_name}_arc_{i:02d}",
                point,
                yaw=command.target_angle,
                metadata={"entity": entity, "phase": "rotate"},
            )
        )
    retreat = waypoints[-1].position
    waypoints.append(
        WaypointTarget.from_sequence(
            f"{command.disk_name}_retreat",
            (retreat[0], retreat[1], retreat[2] + radius),
            lifted=True,
            metadata={"entity": entity, "phase": "retreat"},
        )
    )
    return waypoints


def plan_stacked_plate_rotation(
    layout,
    *,
    arc_samples: int = 6,
) -> tuple[list[StackedPlateRotateCommand], EpisodePlan]:
    """Plan rotating every disk to ``oracle.target_angle_deg`` (align the sectors)."""

    target = float(layout.target_angle())
    grasp_azimuth = float(layout.grasp_azimuth())
    roll_sign = int(layout.roll_sign())
    grasp_radius_scale = float(layout.grasp_radius_scale())

    commands: list[StackedPlateRotateCommand] = []
    waypoints: list[WaypointTarget] = []
    for name in layout.disk_names():
        command = StackedPlateRotateCommand(
            disk_name=str(name),
            start_angle=float(layout.disk_initial_angle(name)),
            target_angle=target,
            center_xyz=tuple(float(v) for v in layout.disk_center(name)),
            radius=float(layout.disk_radius(name)),
            grasp_azimuth=grasp_azimuth,
            roll_sign=roll_sign,
            grasp_radius_scale=grasp_radius_scale,
        )
        commands.append(command)
        waypoints.extend(_rim_waypoints(command, arc_samples=arc_samples))

    subgoal = PlannedSubgoal(
        subgoal_id="align_sectors",
        kind="rotate_disks",
        entity="disks",
        target={
            "target_angle": target,
            "disks": [command.disk_name for command in commands],
        },
    )
    waypoint_plan = WaypointPlan(
        plan_id="stacked_plate_align_sequence",
        waypoints=tuple(waypoints),
        metadata={"planner": "stacked_plate_sector_alignment"},
    )
    episode_plan = EpisodePlan(
        task_id="stacked_plate",
        subgoals=(subgoal,),
        waypoint_plan=waypoint_plan,
        plan_id="stacked_plate_align_sequence",
        metadata={"target_angle": target, "disk_count": len(commands)},
    )
    return commands, episode_plan
