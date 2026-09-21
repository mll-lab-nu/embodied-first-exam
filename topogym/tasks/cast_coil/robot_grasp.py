"""Compatibility exports; shared solver constraint handling lives in robot/."""
from topogym.robot.grasp_constraints import active_grasps, release_grasps

__all__ = ["active_grasps", "release_grasps"]
