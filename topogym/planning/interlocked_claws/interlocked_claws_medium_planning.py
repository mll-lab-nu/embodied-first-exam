"""Opposed acute-window policy, beginning at the Task's friction pregrasp."""
from topogym.planning.rigid_reference.feedback import FrictionReferencePolicy, relative_pose, body_pose


def frame_hook_pose(world, frame, hook):
    """T_frame_hook from authorized measured world poses (unit wxyz)."""
    return relative_pose(body_pose(world["bodies"][frame]), body_pose(world["bodies"][hook]))


class InterlockedClawsMediumPolicy(FrictionReferencePolicy):
    task_id = "interlocked_claws"
    robot_id = "aloha"
    model_revision = "opposed_pregrasp_wide2_v1"
