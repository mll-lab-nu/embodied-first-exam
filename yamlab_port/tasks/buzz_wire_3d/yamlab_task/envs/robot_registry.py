"""Which robot each task runs on.

Maps every gym task ID to the robot it uses (all tasks here run on the YAM bimanual robot;
adding a robot means adding its tasks to this table). :func:`create_task_environment` looks
the robot up to report it per run, and :func:`robot_for_task` is available wherever code needs
to branch on the robot.
"""

# Gym task ID -> robot name. Base and ``-Mimic-`` variants share the same robot.
TASK_ROBOTS = {
    "PutPotOnCooktop-v0": "yam",
    "PutPotOnCooktop-Mimic-v0": "yam",
    "HangMugOnTree-v0": "yam",
    "HangMugOnTree-Mimic-v0": "yam",
    "BuzzWire3D-VeryEasy-v0": "yam",
    "BuzzWire3D-Easier-v0": "yam",
}


def robot_for_task(task_id: str) -> str:
    """Return the robot a task runs on.

    Args:
        task_id (str): Gym task ID (e.g. ``"PutPotOnCooktop-v0"``).

    Returns:
        str: Robot name (e.g. ``"yam"``); ``"yam"`` for an unregistered task, since every
            task in the repo is currently YAM.
    """
    return TASK_ROBOTS.get(task_id, "yam")
