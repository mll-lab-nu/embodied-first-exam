from __future__ import annotations

from typing import Any

from topogym.robot import FrankaPositionIKController


def initialize_franka_controller(
    *,
    scene: Any,
    manifest: Any,
    robot_cfg: Any,
    robot_name: str = "robot",
    reset_home: bool = True,
    settle_steps: int | None = None,
) -> FrankaPositionIKController:
    """Create and initialize the shared Franka position-IK controller.

    This is the standard setup path for task scenes with a Franka: fetch the
    robot from the manifest, configure joint PD gains and force limits, then
    optionally reset the robot to its configured home pose.
    """

    controller = FrankaPositionIKController(
        scene=scene,
        robot=manifest.get(robot_name),
        cfg=robot_cfg,
    )
    controller.configure()
    if reset_home:
        controller.reset_home(settle_steps=settle_steps)
    return controller
