"""Waisted-window policy; the complete grasp/exit route is an explicit oracle."""
from topogym.planning.rigid_reference.feedback import FrictionReferencePolicy


class HedgehogInCageMediumPolicy(FrictionReferencePolicy):
    task_id = "hedgehog_in_cage"
    robot_id = "panda_robotiq"
    model_revision = "waisted4_dark_wood_v1"

    def __init__(self, **kwargs):
        if kwargs.get("part", "solve") == "hold":
            raise ValueError("Hedgehog starts at home; a pregrasp hold would omit actual pickup")
        super().__init__(**kwargs)
