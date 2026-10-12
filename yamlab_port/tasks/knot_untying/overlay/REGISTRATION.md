Registration lines added to the YAMLab copy (apply_overlay.sh does this idempotently):

yamlab/envs/tasks/__init__.py:
    from .knot_untying_manager_cfg import *
    from .knot_untying_manager import *

yamlab/envs/robot_registry.py TASK_ROBOTS:
    "KnotUntying-VeryEasy-v0": "yam",
    "KnotUntying-Easier-v0": "yam",
    "KnotUntying-Easy-v0": "yam",
    "KnotUntying-Medium-v0": "yam",
